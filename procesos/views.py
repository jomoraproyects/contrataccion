import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, connection, transaction
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .forms import (
    AccionProcesoForm,
    CambiarPasswordUsuarioForm,
    DecisionForm,
    EditarProcesoGerenciaForm,
    EditarUsuarioOperativoForm,
    EliminarProcesoForm,
    IndicadoresFiltroForm,
    NuevoProcesoForm,
    ProcesoForm,
    TrazabilidadFiltroForm,
    UsuarioOperativoForm,
)
from .calendario import segundos_habiles_entre, sumar_segundos_habiles
from .models import (
    PLAZOS_ETAPA_DIAS,
    Candidato,
    CambioGerencia,
    EventoSeguridad,
    Perfil,
    ProcesoSeleccion,
    SeguimientoEtapa,
)
from .notificaciones import seguimientos_notificables
from .reportes import (
    calcular_indicadores,
    exportar_excel,
    exportar_pdf,
    exportar_trazabilidad_excel,
    exportar_trazabilidad_pdf,
    filtrar_procesos_por_fecha,
)
from .security import registrar_evento
from .validacion import normalizar_cedula


logger = logging.getLogger(__name__)


def _rol(usuario):
    return getattr(getattr(usuario, "perfil", None), "rol", None)


def _exigir_gerente(request):
    if _rol(request.user) != Perfil.Rol.GERENTE:
        registrar_evento(
            request, EventoSeguridad.Tipo.ACCESO_DENEGADO, usuario=request.user,
            identificador=request.user.username, detalle=f"Ruta de Gerencia: {request.path}",
        )
        raise PermissionDenied("Solo el Gerente puede realizar esta acción.")


def _exigir_roles(request, *roles):
    if _rol(request.user) not in roles:
        registrar_evento(
            request, EventoSeguridad.Tipo.ACCESO_DENEGADO, usuario=request.user,
            identificador=request.user.username, detalle=f"Ruta: {request.path}",
        )
        raise PermissionDenied("No tiene permiso para consultar esta información.")


def _procesos_visibles(usuario, queryset=None):
    queryset = queryset if queryset is not None else ProcesoSeleccion.objects.all()
    rol = _rol(usuario)
    if rol == Perfil.Rol.GERENTE:
        return queryset
    if rol == Perfil.Rol.CONTRATACION:
        return queryset.filter(activo=True).filter(
            Q(creado_por=usuario) | Q(etapa_actual=Perfil.Rol.CONTRATACION)
        ).distinct()
    if rol in (Perfil.Rol.RRHH, Perfil.Rol.PSICOLOGIA, Perfil.Rol.SEGURIDAD):
        return queryset.filter(activo=True).filter(
            Q(etapa_actual=rol, estado__in=[ProcesoSeleccion.Estado.EN_CURSO, ProcesoSeleccion.Estado.LISTO_CONTRATACION])
            | Q(decisiones__etapa=rol, estado__in=[ProcesoSeleccion.Estado.RECHAZADO, ProcesoSeleccion.Estado.CONTRATADO])
        ).distinct()
    return queryset.none()


def _registrar_cambio(proceso, usuario, tipo, descripcion, etapa_anterior="", estado_anterior=""):
    return CambioGerencia.objects.create(
        proceso=proceso,
        candidato_nombre=proceso.nombre_completo,
        cedula=proceso.cedula,
        tipo=tipo,
        descripcion=descripcion.strip(),
        etapa_anterior=etapa_anterior,
        etapa_nueva=proceso.etapa_actual,
        estado_anterior=estado_anterior,
        estado_nuevo=proceso.estado,
        realizado_por=usuario,
    )


def _anular_decisiones_incompatibles(proceso, usuario):
    orden = list(ProcesoSeleccion.Etapa.values)
    indice_actual = orden.index(proceso.etapa_actual)
    incompatibles = Q(resultado="RECHAZADO")
    if proceso.estado != ProcesoSeleccion.Estado.CONTRATADO:
        etapas_desde_actual = orden[indice_actual:]
        incompatibles |= Q(etapa__in=etapas_desde_actual)
    proceso.decisiones.filter(vigente=True).filter(incompatibles).update(
        vigente=False,
        etapa_vigente=None,
        anulada_en=timezone.now(),
        anulada_por_gerencia=usuario,
    )


def _ajustar_seguimiento_gerencia(proceso, usuario):
    ahora = timezone.now()
    proceso.seguimientos.filter(fin__isnull=True).update(
        fin=ahora,
        proceso_en_curso=None,
        resultado=SeguimientoEtapa.Resultado.AJUSTADO,
        cerrado_por=usuario,
    )
    if proceso.activo and not proceso.esta_finalizado:
        proceso.abrir_seguimiento(proceso.etapa_actual, ahora)


def _filtrar(request, queryset):
    q = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "")
    etapa = request.GET.get("etapa", "")
    vacante = request.GET.get("vacante", "").strip()
    fecha_desde = request.GET.get("fecha_desde", "")
    fecha_hasta = request.GET.get("fecha_hasta", "")
    if q:
        for termino in q.split():
            queryset = queryset.filter(
                Q(nombre__icontains=termino) | Q(apellidos__icontains=termino) | Q(cedula__icontains=termino)
            )
    if estado:
        queryset = queryset.filter(estado=estado)
    if etapa:
        queryset = queryset.filter(etapa_actual=etapa)
    if vacante:
        queryset = queryset.filter(vacante__icontains=vacante)
    if parse_date(fecha_desde):
        queryset = queryset.filter(fecha_llegada__gte=parse_date(fecha_desde))
    if parse_date(fecha_hasta):
        queryset = queryset.filter(fecha_llegada__lte=parse_date(fecha_hasta))
    return queryset


def _contexto_lista(request, queryset, titulo, descripcion):
    filtrados = _filtrar(request, queryset).order_by("-fecha_llegada", "-creado_en", "-pk")
    pagina = Paginator(filtrados, 5).get_page(request.GET.get("page"))
    parametros = request.GET.copy()
    parametros.pop("page", None)
    return {
        "procesos": pagina,
        "page_obj": pagina,
        "paginas": _opciones_paginacion(pagina),
        "querystring": parametros.urlencode(),
        "titulo": titulo,
        "descripcion": descripcion,
        "estados": ProcesoSeleccion.Estado.choices,
        "etapas": ProcesoSeleccion.Etapa.choices,
        "puede_crear": _rol(request.user) == Perfil.Rol.CONTRATACION,
    }


def _procesos_indicadores(request, formulario):
    base = _procesos_visibles(
        request.user,
        ProcesoSeleccion.objects.filter(activo=True).select_related("creado_por").prefetch_related("seguimientos"),
    )
    return filtrar_procesos_por_fecha(base, formulario).order_by("-fecha_llegada", "-creado_en", "-pk")


def _opciones_paginacion(pagina):
    return [
        {
            "numero": numero,
            "actual": numero == pagina.number,
            "separador": numero == Paginator.ELLIPSIS,
        }
        for numero in pagina.paginator.get_elided_page_range(
            pagina.number,
            on_each_side=2,
            on_ends=1,
        )
    ]


def _rango_indicadores(formulario):
    desde = formulario.cleaned_data.get("fecha_desde")
    hasta = formulario.cleaned_data.get("fecha_hasta")
    partes = []
    if desde and hasta:
        partes.append(f"Fecha: {desde.strftime('%d/%m/%Y')} a {hasta.strftime('%d/%m/%Y')}")
    elif desde:
        partes.append(f"Fecha: desde {desde.strftime('%d/%m/%Y')}")
    elif hasta:
        partes.append(f"Fecha: hasta {hasta.strftime('%d/%m/%Y')}")
    estado = formulario.cleaned_data.get("estado")
    etapa = formulario.cleaned_data.get("etapa")
    vacante = formulario.cleaned_data.get("vacante", "").strip()
    q = formulario.cleaned_data.get("q", "").strip()
    situacion = formulario.cleaned_data.get("situacion")
    if estado:
        partes.append(f"Estado: {dict(ProcesoSeleccion.Estado.choices).get(estado, estado)}")
    if etapa:
        partes.append(f"Área/etapa: {dict(ProcesoSeleccion.Etapa.choices).get(etapa, etapa)}")
    if vacante:
        partes.append(f"Vacante/área: {vacante}")
    if q:
        partes.append(f"Búsqueda: {q}")
    if situacion:
        partes.append(f"Cumplimiento: {dict(TrazabilidadFiltroForm.SITUACIONES).get(situacion, situacion)}")
    return " · ".join(partes) if partes else "Todos los registros disponibles"


def _nombre_exportacion_indicadores(formulario):
    datos = formulario.cleaned_data
    partes = ["candidatos"]
    if datos.get("estado"):
        partes.append(slugify(dict(ProcesoSeleccion.Estado.choices)[datos["estado"]]))
    if datos.get("vacante"):
        partes.append(slugify(datos["vacante"])[:35])
    if datos.get("q"):
        partes.extend(["busqueda", slugify(datos["q"])[:25]])
    if datos.get("fecha_desde"):
        partes.extend(["desde", datos["fecha_desde"].isoformat()])
    if datos.get("fecha_hasta"):
        partes.extend(["hasta", datos["fecha_hasta"].isoformat()])
    return "-".join(parte for parte in partes if parte)[:140]


def _respuesta_exportacion(request, formato, generador_excel, generador_pdf, nombre, volver_a):
    try:
        if formato == "xlsx":
            contenido = generador_excel()
            tipo = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif formato == "pdf":
            contenido = generador_pdf()
            tipo = "application/pdf"
        else:
            return HttpResponseBadRequest("Formato de exportación no válido.")
    except Exception:
        logger.exception("No fue posible generar la exportación %s", nombre)
        messages.error(
            request,
            "No fue posible generar el archivo. Verifique que las dependencias del servidor estén actualizadas.",
        )
        return redirect(volver_a)
    fecha = timezone.localdate().isoformat()
    respuesta = HttpResponse(contenido, content_type=tipo)
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}-{fecha}.{formato}"'
    respuesta["Cache-Control"] = "private, no-store"
    return respuesta


def _destino_post_seguro(request):
    destino = request.POST.get("next", "")
    if destino and url_has_allowed_host_and_scheme(
        destino,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return destino
    return reverse("procesos:lista")


@require_GET
def salud(request):
    """Comprobación mínima para el balanceador, sin exponer datos internos."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"estado": "no_disponible"}, status=503)
    return JsonResponse({"estado": "ok"})


@login_required
@never_cache
@require_GET
def consultar_candidato_cedula(request):
    """Permite a Contratación reutilizar una identidad sin duplicar la cédula."""
    _exigir_roles(request, Perfil.Rol.CONTRATACION)
    try:
        cedula = normalizar_cedula(request.GET.get("cedula", ""))
    except ValidationError:
        return JsonResponse({"encontrado": False})
    candidato = Candidato.objects.filter(cedula=cedula).first()
    if not candidato:
        return JsonResponse({"encontrado": False})
    procesos = candidato.procesos.order_by("-creado_en", "-pk")
    ultimo = procesos.first()
    ultimo_rechazo = procesos.filter(estado=ProcesoSeleccion.Estado.RECHAZADO).first()
    abierto = procesos.filter(
        activo=True,
        estado__in=[ProcesoSeleccion.Estado.EN_CURSO, ProcesoSeleccion.Estado.LISTO_CONTRATACION],
    ).first()
    return JsonResponse({
        "encontrado": True,
        "nombre": candidato.nombre,
        "apellidos": candidato.apellidos,
        "celular": candidato.celular,
        "cantidad_procesos": procesos.count(),
        "proceso_abierto": bool(abierto),
        "ultimo_proceso": {
            "vacante": ultimo.vacante,
            "estado": ultimo.get_estado_display(),
            "fecha": ultimo.fecha_llegada.strftime("%d/%m/%Y"),
        } if ultimo else None,
        "ultimo_rechazo": {
            "vacante": ultimo_rechazo.vacante,
            "etapa": ultimo_rechazo.etapa_rechazo,
            "motivo": ultimo_rechazo.motivo_rechazo,
        } if ultimo_rechazo else None,
    })


@login_required
def lista_procesos(request):
    base = _procesos_visibles(request.user, ProcesoSeleccion.objects.filter(activo=True))
    qs = base.exclude(estado__in=[ProcesoSeleccion.Estado.RECHAZADO, ProcesoSeleccion.Estado.CONTRATADO])
    contexto = _contexto_lista(request, qs, "Procesos en curso", "Candidatos que están avanzando por las etapas.")
    contexto["resumen_global"] = base.aggregate(
        activos=Count("id", filter=Q(estado=ProcesoSeleccion.Estado.EN_CURSO)),
        listos=Count("id", filter=Q(estado=ProcesoSeleccion.Estado.LISTO_CONTRATACION)),
        contratados=Count("id", filter=Q(estado=ProcesoSeleccion.Estado.CONTRATADO)),
        rechazados=Count("id", filter=Q(estado=ProcesoSeleccion.Estado.RECHAZADO)),
    )
    rol = _rol(request.user)
    if rol in ProcesoSeleccion.Etapa.values:
        contexto["mostrar_asignaciones"] = True
        asignaciones = SeguimientoEtapa.objects.filter(
            proceso__activo=True,
            proceso__etapa_actual=rol,
            proceso__estado__in=[ProcesoSeleccion.Estado.EN_CURSO, ProcesoSeleccion.Estado.LISTO_CONTRATACION],
            etapa=rol,
            fin__isnull=True,
        ).select_related("proceso").order_by("fecha_limite", "pk")
        contexto["asignaciones"] = Paginator(asignaciones, 5).get_page(request.GET.get("asignaciones_page"))
        contexto["asignaciones_paginas"] = _opciones_paginacion(contexto["asignaciones"])
        parametros_asignaciones = request.GET.copy()
        parametros_asignaciones.pop("asignaciones_page", None)
        contexto["asignaciones_querystring"] = parametros_asignaciones.urlencode()
        historial_terminados = _procesos_visibles(
            request.user,
            ProcesoSeleccion.objects.filter(
                activo=True,
                estado__in=[ProcesoSeleccion.Estado.RECHAZADO, ProcesoSeleccion.Estado.CONTRATADO],
            ),
        ).order_by("-actualizado_en", "-pk")
        contexto["historial_terminados"] = Paginator(historial_terminados, 5).get_page(request.GET.get("historial_page"))
        contexto["historial_paginas"] = _opciones_paginacion(contexto["historial_terminados"])
        parametros_historial = request.GET.copy()
        parametros_historial.pop("historial_page", None)
        contexto["historial_querystring"] = parametros_historial.urlencode()
    return render(request, "procesos/lista.html", contexto)


@login_required
def trazabilidad(request):
    _exigir_gerente(request)
    formulario = TrazabilidadFiltroForm(request.GET or None)
    procesos_qs = ProcesoSeleccion.objects.select_related("creado_por").prefetch_related(
        Prefetch(
            "seguimientos",
            queryset=SeguimientoEtapa.objects.select_related("cerrado_por").order_by("inicio"),
        ),
    )
    if formulario.is_valid():
        datos = formulario.cleaned_data
        q = datos.get("q", "").strip()
        if q:
            for termino in q.split():
                procesos_qs = procesos_qs.filter(
                    Q(nombre__icontains=termino)
                    | Q(apellidos__icontains=termino)
                    | Q(cedula__icontains=termino)
                )
        if datos.get("fecha_desde"):
            procesos_qs = procesos_qs.filter(fecha_llegada__gte=datos["fecha_desde"])
        if datos.get("fecha_hasta"):
            procesos_qs = procesos_qs.filter(fecha_llegada__lte=datos["fecha_hasta"])
        if datos.get("estado"):
            procesos_qs = procesos_qs.filter(estado=datos["estado"])
        if datos.get("etapa"):
            procesos_qs = procesos_qs.filter(etapa_actual=datos["etapa"])
        if datos.get("vacante"):
            procesos_qs = procesos_qs.filter(vacante__icontains=datos["vacante"].strip())

    procesos = list(procesos_qs)
    for proceso in procesos:
        seguimientos = list(proceso.seguimientos.all())
        proceso.traza_seguimientos = seguimientos
        proceso.traza_abierto = next((item for item in seguimientos if item.fin is None), None)
        proceso.traza_total_horas = round(sum(item.duracion_horas for item in seguimientos), 1)
        proceso.traza_mas_lenta = max(seguimientos, key=lambda item: item.duracion_horas, default=None)
        proceso.traza_fuera_tiempo = sum(item.esta_vencido for item in seguimientos)
        if proceso.traza_abierto:
            proceso.traza_estado_plazo = proceso.traza_abierto.estado_plazo
            proceso.traza_clase_plazo = proceso.traza_abierto.clase_plazo
        else:
            proceso.traza_estado_plazo = "Proceso finalizado"
            proceso.traza_clase_plazo = "secondary"

    situacion = formulario.cleaned_data.get("situacion", "") if formulario.is_valid() else ""
    if situacion == "vencidos":
        procesos = [p for p in procesos if p.traza_abierto and p.traza_abierto.esta_vencido]
    elif situacion == "por_vencer":
        procesos = [
            p for p in procesos
            if p.traza_abierto and not p.traza_abierto.esta_vencido and p.traza_abierto.dias_restantes <= 1
        ]
    elif situacion == "con_retrasos":
        procesos = [p for p in procesos if p.traza_fuera_tiempo]
    elif situacion == "sin_retrasos":
        procesos = [p for p in procesos if not p.traza_fuera_tiempo]

    orden = formulario.cleaned_data.get("orden") if formulario.is_valid() else "recientes"
    if orden == "demora":
        procesos.sort(key=lambda p: (p.traza_total_horas, p.fecha_llegada), reverse=True)
    elif orden == "vencimiento":
        procesos.sort(key=lambda p: (
            p.traza_abierto is None,
            p.traza_abierto.fecha_limite if p.traza_abierto else p.actualizado_en,
        ))
    elif orden == "nombre":
        procesos.sort(key=lambda p: p.nombre_completo.casefold())
    else:
        procesos.sort(key=lambda p: (p.fecha_llegada, p.creado_en, p.pk), reverse=True)

    seguimientos_filtrados = [item for proceso in procesos for item in proceso.traza_seguimientos]
    abiertos = sorted(
        [item for item in seguimientos_filtrados if item.fin is None and item.proceso.activo],
        key=lambda item: item.fecha_limite,
    )
    vencidos = [item for item in abiertos if item.esta_vencido]
    por_vencer = [item for item in abiertos if not item.esta_vencido and item.dias_restantes <= 1]
    en_plazo = [item for item in abiertos if item not in vencidos and item not in por_vencer]
    metricas = []
    for valor, etiqueta in ProcesoSeleccion.Etapa.choices:
        todos_etapa = [item for item in seguimientos_filtrados if item.etapa == valor]
        abiertos_etapa = [item for item in todos_etapa if item.fin is None]
        cerrados = [
            item for item in todos_etapa
            if item.fin is not None and item.resultado != SeguimientoEtapa.Resultado.AJUSTADO
        ]
        medidos = [item for item in todos_etapa if item.resultado != SeguimientoEtapa.Resultado.AJUSTADO]
        promedio = round(sum(item.duracion_horas for item in medidos) / len(medidos), 1) if medidos else None
        a_tiempo = sum(not item.esta_vencido for item in cerrados)
        metricas.append({
            "valor": valor,
            "etapa": etiqueta,
            "plazo": SeguimientoEtapa(proceso_id=0, etapa=valor).plazo_dias,
            "promedio_horas": promedio,
            "cumplimiento": round(a_tiempo * 100 / len(cerrados)) if cerrados else None,
            "finalizados": len(cerrados),
            "medidos": len(medidos),
            "abiertos": len(abiertos_etapa),
            "vencidos": sum(item.esta_vencido for item in abiertos_etapa),
        })
    cuello_botella = max(
        (metrica for metrica in metricas if metrica["promedio_horas"] is not None),
        key=lambda metrica: metrica["promedio_horas"],
        default=None,
    )
    if cuello_botella:
        cuello_botella["es_cuello_botella"] = True
    mayor_promedio = max((metrica["promedio_horas"] or 0 for metrica in metricas), default=0)
    for metrica in metricas:
        metrica["barra_porcentaje"] = (
            round(metrica["promedio_horas"] * 100 / mayor_promedio)
            if metrica["promedio_horas"] is not None and mayor_promedio else 0
        )

    parametros = request.GET.copy()
    parametros.pop("page", None)
    parametros.pop("exportar", None)
    resumen_trazabilidad = {
        "total": len(procesos),
        "con_retrasos": sum(bool(p.traza_fuera_tiempo) for p in procesos),
        "finalizados": sum(p.esta_finalizado for p in procesos),
        "abiertos": len(abiertos),
    }
    formato_exportacion = request.GET.get("exportar", "")
    if formato_exportacion:
        if not formulario.is_valid():
            return HttpResponseBadRequest("Los filtros de trazabilidad no son válidos.")
        filtros = _rango_indicadores(formulario)
        volver_a = reverse("procesos:trazabilidad")
        if parametros:
            volver_a = f"{volver_a}?{parametros.urlencode()}"
        return _respuesta_exportacion(
            request,
            formato_exportacion,
            lambda: exportar_trazabilidad_excel(procesos, metricas, resumen_trazabilidad, filtros),
            lambda: exportar_trazabilidad_pdf(procesos, metricas, resumen_trazabilidad, filtros),
            "trazabilidad-seleccion",
            volver_a,
        )

    pagina = Paginator(procesos, 5).get_page(request.GET.get("page"))
    return render(request, "procesos/trazabilidad.html", {
        "formulario_filtros": formulario,
        "procesos": pagina,
        "page_obj": pagina,
        "paginas": _opciones_paginacion(pagina),
        "querystring": parametros.urlencode(),
        "total_procesos": len(procesos),
        "procesos_con_retrasos": resumen_trazabilidad["con_retrasos"],
        "procesos_finalizados": resumen_trazabilidad["finalizados"],
        "abiertos": abiertos,
        "vencidos": vencidos,
        "por_vencer": por_vencer,
        "en_plazo": en_plazo,
        "metricas": metricas,
        "cuello_botella": cuello_botella,
        "hay_filtros": any(request.GET.get(nombre) for nombre in formulario.fields if nombre != "orden"),
    })


@login_required
def indicadores(request):
    _exigir_roles(request, Perfil.Rol.GERENTE, Perfil.Rol.CONTRATACION)
    formulario = IndicadoresFiltroForm(request.GET)
    procesos = list(_procesos_indicadores(request, formulario)) if formulario.is_valid() else []
    resumen = calcular_indicadores(procesos)
    pagina = Paginator(procesos, 5).get_page(request.GET.get("page"))
    parametros = request.GET.copy()
    parametros.pop("page", None)
    return render(request, "procesos/indicadores.html", {
        "formulario_filtros": formulario,
        "procesos": pagina,
        "page_obj": pagina,
        "paginas": _opciones_paginacion(pagina),
        "indicadores": resumen,
        "rango": _rango_indicadores(formulario) if formulario.is_valid() else "Rango inválido",
        "querystring": parametros.urlencode(),
        "hay_filtros": any(request.GET.get(nombre) for nombre in formulario.fields),
    })


@login_required
@require_GET
def exportar_indicadores(request, formato):
    _exigir_roles(request, Perfil.Rol.GERENTE, Perfil.Rol.CONTRATACION)
    formulario = IndicadoresFiltroForm(request.GET)
    if not formulario.is_valid():
        return HttpResponseBadRequest("El rango de fechas no es válido.")
    procesos = list(_procesos_indicadores(request, formulario))
    resumen = calcular_indicadores(procesos)
    rango = _rango_indicadores(formulario)
    parametros = request.GET.urlencode()
    volver_a = reverse("procesos:indicadores")
    if parametros:
        volver_a = f"{volver_a}?{parametros}"
    return _respuesta_exportacion(
        request,
        formato,
        lambda: exportar_excel(procesos, resumen, rango),
        lambda: exportar_pdf(procesos, resumen, rango),
        _nombre_exportacion_indicadores(formulario),
        volver_a,
    )


@login_required
@require_POST
def marcar_notificacion_leida(request, pk):
    get_object_or_404(seguimientos_notificables(request.user), pk=pk)
    leidas = list(dict.fromkeys(request.session.get("notificaciones_leidas", []) + [pk]))[-200:]
    request.session["notificaciones_leidas"] = leidas
    return redirect(_destino_post_seguro(request))


@login_required
@require_POST
def marcar_notificaciones_leidas(request):
    ids = list(seguimientos_notificables(request.user).values_list("pk", flat=True)[:200])
    anteriores = request.session.get("notificaciones_leidas", [])
    request.session["notificaciones_leidas"] = list(dict.fromkeys(anteriores + ids))[-200:]
    return redirect(_destino_post_seguro(request))


@login_required
def lista_contratacion(request):
    _exigir_roles(request, Perfil.Rol.GERENTE, Perfil.Rol.CONTRATACION)
    qs = _procesos_visibles(request.user, ProcesoSeleccion.objects.filter(activo=True)).filter(
        Q(estado=ProcesoSeleccion.Estado.LISTO_CONTRATACION) | Q(estado=ProcesoSeleccion.Estado.CONTRATADO)
    ).prefetch_related("seguimientos")
    contexto = _contexto_lista(request, qs, "Contratación", "Candidatos listos para contratar o ya contratados.")
    contexto["mostrar_tiempos"] = True
    return render(request, "procesos/lista.html", contexto)


@login_required
def lista_rechazados(request):
    _exigir_roles(request, Perfil.Rol.GERENTE, Perfil.Rol.CONTRATACION)
    qs = _procesos_visibles(request.user, ProcesoSeleccion.objects.filter(
        activo=True, estado=ProcesoSeleccion.Estado.RECHAZADO
    )).prefetch_related("decisiones", "cambios_gerencia")
    contexto = _contexto_lista(request, qs, "Rechazados", "Procesos finalizados por rechazo.")
    contexto["mostrar_rechazo"] = True
    return render(request, "procesos/lista.html", contexto)


@login_required
def lista_archivados(request):
    _exigir_gerente(request)
    qs = ProcesoSeleccion.objects.filter(activo=False)
    contexto = _contexto_lista(
        request, qs, "Candidatos desactivados", "Registros conservados fuera de las listas operativas que pueden restaurarse cuando sea necesario."
    )
    return render(request, "procesos/lista.html", contexto)


@login_required
def crear_proceso(request):
    _exigir_roles(request, Perfil.Rol.CONTRATACION)
    form = NuevoProcesoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        proceso = form.save(commit=False)
        proceso.creado_por = request.user
        try:
            with transaction.atomic():
                proceso.save()
        except IntegrityError:
            form.add_error("cedula", "Esta cédula ya tiene otro proceso abierto.")
            return render(request, "procesos/formulario.html", {"form": form})
        messages.success(request, "El proceso fue creado y enviado a Talento Humano.")
        return redirect("procesos:detalle", pk=proceso.pk)
    return render(request, "procesos/formulario.html", {"form": form})


@login_required
def detalle_proceso(request, pk):
    visibles = _procesos_visibles(request.user, ProcesoSeleccion.objects.select_related("creado_por").prefetch_related(
        "decisiones__decidido_por", "decisiones__anulada_por_gerencia",
        "cambios_gerencia__realizado_por", "seguimientos__cerrado_por"
    ))
    proceso = get_object_or_404(visibles, pk=pk)
    es_gerente = _rol(request.user) == Perfil.Rol.GERENTE
    if not proceso.activo and not es_gerente:
        raise PermissionDenied("Este candidato está desactivado.")
    puede_decidir = proceso.puede_decidir(request.user)
    form = DecisionForm(request.POST or None) if puede_decidir else None
    if request.method == "POST":
        if not puede_decidir:
            raise PermissionDenied("No tiene permiso para tomar esta decisión.")
        if form.is_valid():
            try:
                proceso.registrar_decision(request.user, form.cleaned_data["resultado"], form.cleaned_data["observacion"])
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                if not _procesos_visibles(request.user, ProcesoSeleccion.objects.filter(pk=proceso.pk)).exists():
                    messages.success(
                        request,
                        f"La decisión fue guardada. El proceso fue enviado a {proceso.get_etapa_actual_display()}.",
                    )
                    return redirect("procesos:lista")
                messages.success(request, "La decisión fue guardada correctamente.")
                return redirect("procesos:detalle", pk=proceso.pk)

    decisiones = {d.etapa: d for d in proceso.decisiones.all() if d.vigente}
    orden = list(ProcesoSeleccion.Etapa.values)
    indice_actual = orden.index(proceso.etapa_actual)
    ultimo_ajuste = proceso.cambios_gerencia.filter(tipo=CambioGerencia.Tipo.ACTUALIZACION).first()
    etapas = []
    for indice, (valor, etiqueta) in enumerate(ProcesoSeleccion.Etapa.choices):
        if proceso.estado == ProcesoSeleccion.Estado.CONTRATADO:
            estado_visual = "done"
        elif proceso.estado == ProcesoSeleccion.Estado.RECHAZADO:
            estado_visual = "done" if indice < indice_actual else "rejected" if indice == indice_actual else ""
        else:
            estado_visual = "done" if indice < indice_actual else "current" if indice == indice_actual else ""
        etapas.append({
            "valor": valor,
            "etiqueta": etiqueta,
            "decision": decisiones.get(valor),
            "estado_visual": estado_visual,
            "ajustada": bool(ultimo_ajuste and ultimo_ajuste.etapa_nueva == valor and (
                ultimo_ajuste.etapa_anterior != ultimo_ajuste.etapa_nueva or ultimo_ajuste.estado_anterior != ultimo_ajuste.estado_nuevo
            )),
        })
    return render(request, "procesos/detalle.html", {
        "proceso": proceso,
        "form": form,
        "puede_decidir": puede_decidir,
        "es_gerente": es_gerente,
        "ultimo_cambio_gerencia": proceso.cambios_gerencia.first(),
        "seguimientos": proceso.seguimientos.all(),
        "etapas": etapas,
    })


@login_required
def editar_proceso_gerencia(request, pk):
    _exigir_gerente(request)
    proceso = get_object_or_404(ProcesoSeleccion, pk=pk)
    etapa_anterior, estado_anterior = proceso.etapa_actual, proceso.estado
    form = EditarProcesoGerenciaForm(request.POST or None, instance=proceso)
    if request.method == "POST" and form.is_valid():
        campos = [form.fields[nombre].label for nombre in form.changed_data if nombre != "motivo_cambio"]
        proceso = form.save()
        if etapa_anterior != proceso.etapa_actual or estado_anterior != proceso.estado:
            _anular_decisiones_incompatibles(proceso, request.user)
            _ajustar_seguimiento_gerencia(proceso, request.user)
        descripcion = f"{form.cleaned_data['motivo_cambio']} Campos actualizados: {', '.join(campos) or 'ninguno'}."
        _registrar_cambio(
            proceso, request.user, CambioGerencia.Tipo.ACTUALIZACION, descripcion,
            etapa_anterior=etapa_anterior, estado_anterior=estado_anterior,
        )
        messages.success(request, "El candidato fue actualizado y el cambio quedó registrado en el historial.")
        return redirect("procesos:detalle", pk=proceso.pk)
    return render(request, "procesos/proceso_editar.html", {"form": form, "proceso": proceso})


@login_required
def cambiar_actividad_proceso(request, pk):
    _exigir_gerente(request)
    proceso = get_object_or_404(ProcesoSeleccion, pk=pk)
    accion = "restaurar" if not proceso.activo else "desactivar"
    form = AccionProcesoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        archivado_desde = proceso.archivado_en
        proceso.activo = not proceso.activo
        proceso.archivado_en = None if proceso.activo else timezone.now()
        proceso.archivado_por = None if proceso.activo else request.user
        try:
            proceso.save(update_fields=["activo", "archivado_en", "archivado_por", "actualizado_en"])
        except IntegrityError:
            proceso.refresh_from_db()
            form.add_error(None, "No se puede restaurar: esta cédula ya tiene otro proceso abierto.")
            return render(request, "procesos/proceso_confirmar.html", {
                "form": form, "proceso": proceso, "accion": accion,
                "titulo": f"{accion.title()} candidato",
                "descripcion": "El historial y las decisiones se conservarán.",
                "texto_boton": accion.title(), "peligrosa": proceso.activo,
            })
        if proceso.activo:
            seguimiento_abierto = proceso.seguimientos.filter(fin__isnull=True).first()
            if seguimiento_abierto and archivado_desde:
                pausa = segundos_habiles_entre(archivado_desde, timezone.now())
                seguimiento_abierto.fecha_limite = sumar_segundos_habiles(
                    seguimiento_abierto.fecha_limite, pausa
                )
                seguimiento_abierto.segundos_pausados += pausa
                seguimiento_abierto.save(update_fields=["fecha_limite", "segundos_pausados"])
            elif not proceso.esta_finalizado:
                proceso.abrir_seguimiento(proceso.etapa_actual)
        tipo = CambioGerencia.Tipo.RESTAURADO if proceso.activo else CambioGerencia.Tipo.ARCHIVADO
        _registrar_cambio(proceso, request.user, tipo, form.cleaned_data["motivo"])
        messages.success(request, f"El candidato fue {'restaurado' if proceso.activo else 'desactivado'} correctamente.")
        return redirect("procesos:detalle", pk=proceso.pk)
    return render(request, "procesos/proceso_confirmar.html", {
        "form": form, "proceso": proceso, "accion": accion,
        "titulo": f"{accion.title()} candidato",
        "descripcion": "El historial y las decisiones se conservarán.",
        "texto_boton": accion.title(), "peligrosa": proceso.activo,
    })


@login_required
def eliminar_proceso_gerencia(request, pk):
    _exigir_gerente(request)
    proceso = get_object_or_404(
        ProcesoSeleccion.objects.select_related("candidato"),
        pk=pk,
        activo=False,
    )
    form = EliminarProcesoForm(request.POST if request.method == "POST" else None)
    otros_procesos_activos = proceso.candidato.procesos.filter(activo=True).count()
    if request.method == "POST" and form.is_valid():
        candidato = proceso.candidato
        cedula = candidato.cedula
        with transaction.atomic():
            procesos_candidato = ProcesoSeleccion.objects.select_for_update().filter(candidato=candidato)
            if procesos_candidato.filter(activo=True).exists():
                form.add_error(
                    None,
                    "No se puede eliminar todavía: la persona tiene otro proceso activo. Desactívelo primero.",
                )
            else:
                ids_procesos = list(procesos_candidato.values_list("pk", flat=True))
                CambioGerencia.objects.filter(Q(proceso_id__in=ids_procesos) | Q(cedula=cedula)).delete()
                procesos_candidato.delete()
                candidato.delete()
        if not form.errors:
            messages.success(request, "El candidato y todo su historial fueron eliminados definitivamente.")
            return redirect("procesos:archivados")
        otros_procesos_activos = candidato.procesos.filter(activo=True).count()
    return render(request, "procesos/proceso_confirmar.html", {
        "form": form,
        "proceso": proceso,
        "accion": "eliminar",
        "titulo": "Eliminar candidato definitivamente",
        "descripcion": "Esta acción borra la información personal, todos sus procesos, decisiones y trazabilidad.",
        "texto_boton": "Eliminar definitivamente",
        "peligrosa": True,
        "otros_procesos_activos": otros_procesos_activos,
    })


@login_required
def lista_usuarios(request):
    _exigir_gerente(request)
    usuarios = User.objects.select_related("perfil").exclude(
        perfil__rol=Perfil.Rol.SIN_ASIGNAR
    ).order_by("-date_joined", "-pk")
    bloqueados_temporales = Q(perfil__bloqueado_hasta__gt=timezone.now())
    usuarios_activos = usuarios.filter(is_active=True).exclude(bloqueados_temporales).count()
    usuarios_bloqueados = usuarios.filter(Q(is_active=False) | bloqueados_temporales).distinct().count()
    pagina = Paginator(usuarios, 5).get_page(request.GET.get("page"))
    for usuario in pagina.object_list:
        usuario.plazo_gestion_dias = PLAZOS_ETAPA_DIAS.get(usuario.perfil.rol)
    return render(request, "procesos/usuarios_lista.html", {
        "usuarios": pagina,
        "page_obj": pagina,
        "paginas": _opciones_paginacion(pagina),
        "usuarios_activos": usuarios_activos,
        "usuarios_bloqueados": usuarios_bloqueados,
    })


@login_required
def crear_usuario(request):
    _exigir_gerente(request)
    form = UsuarioOperativoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.save()
        registrar_evento(
            request, EventoSeguridad.Tipo.USUARIO_CREADO, usuario=request.user,
            identificador=usuario.username, detalle=f"Cuenta creada: {usuario.pk}",
        )
        messages.success(request, f"El usuario {usuario.username} fue creado correctamente.")
        return redirect("procesos:usuarios")
    return render(request, "procesos/usuario_formulario.html", {
        "form": form,
        "titulo": "Crear usuario",
        "descripcion": "Cree una cuenta y asigne el área que podrá gestionar.",
        "texto_boton": "Crear usuario",
    })


@login_required
def cambiar_password_usuario(request, pk):
    _exigir_gerente(request)
    usuario = get_object_or_404(User.objects.select_related("perfil"), pk=pk)
    if usuario.perfil.rol == Perfil.Rol.GERENTE:
        raise PermissionDenied("Las cuentas de Gerente no se modifican desde esta pantalla.")
    form = CambiarPasswordUsuarioForm(usuario, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        usuario.perfil.limpiar_bloqueo()
        registrar_evento(
            request, EventoSeguridad.Tipo.PASSWORD_CAMBIADA, usuario=request.user,
            identificador=usuario.username, detalle=f"Contraseña actualizada: {usuario.pk}",
        )
        messages.success(request, f"La contraseña de {usuario.username} fue actualizada.")
        return redirect("procesos:usuarios")
    return render(request, "procesos/usuario_formulario.html", {
        "form": form,
        "usuario_objetivo": usuario,
        "titulo": "Cambiar contraseña",
        "descripcion": f"Establezca una contraseña nueva para {usuario.get_full_name() or usuario.username}.",
        "texto_boton": "Guardar nueva contraseña",
        "confirmar_accion": True,
        "confirmacion_mensaje": "Se reemplazará la contraseña de esta cuenta.",
    })


@login_required
def editar_usuario(request, pk):
    _exigir_gerente(request)
    usuario = get_object_or_404(User.objects.select_related("perfil"), pk=pk)
    if usuario.perfil.rol == Perfil.Rol.GERENTE:
        raise PermissionDenied("Las cuentas de Gerente no se modifican desde esta pantalla.")
    form = EditarUsuarioOperativoForm(request.POST or None, instance=usuario)
    if request.method == "POST" and form.is_valid():
        usuario = form.save()
        if usuario.perfil.rol == Perfil.Rol.CONTRATACION and not usuario.is_active:
            usuario.is_active = True
            usuario.save(update_fields=["is_active"])
        if usuario.is_active:
            usuario.perfil.limpiar_bloqueo()
        estado = "habilitado" if usuario.is_active else "bloqueado"
        registrar_evento(
            request, EventoSeguridad.Tipo.USUARIO_EDITADO, usuario=request.user,
            identificador=usuario.username, detalle=f"Cuenta {usuario.pk}: {estado}; rol {usuario.perfil.rol}",
        )
        messages.success(request, f"El usuario {usuario.username} fue actualizado y quedó {estado}.")
        return redirect("procesos:usuarios")
    return render(request, "procesos/usuario_formulario.html", {
        "form": form,
        "usuario_objetivo": usuario,
        "titulo": "Editar usuario",
        "descripcion": "Actualice sus datos o cambie el área. Gerencia y Contratación no pueden bloquearse manualmente.",
        "texto_boton": "Guardar cambios",
        "confirmar_accion": True,
        "confirmacion_mensaje": "Se modificarán los datos, el rol o el acceso de esta cuenta.",
    })
