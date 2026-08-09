from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, connection
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date

from .forms import (
    AccionProcesoForm,
    CambiarPasswordUsuarioForm,
    DecisionForm,
    EditarProcesoGerenciaForm,
    EditarUsuarioOperativoForm,
    ProcesoForm,
    UsuarioOperativoForm,
)
from .calendario import segundos_habiles_entre, sumar_segundos_habiles
from .models import CambioGerencia, EventoSeguridad, Perfil, ProcesoSeleccion, SeguimientoEtapa
from .security import registrar_evento


def _rol(usuario):
    return getattr(getattr(usuario, "perfil", None), "rol", None)


def _exigir_gerente(usuario):
    if _rol(usuario) != Perfil.Rol.GERENTE:
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
        anulada_en=timezone.now(),
        anulada_por_gerencia=usuario,
    )


def _ajustar_seguimiento_gerencia(proceso, usuario):
    ahora = timezone.now()
    proceso.seguimientos.filter(fin__isnull=True).update(
        fin=ahora,
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
    filtrados = _filtrar(request, queryset)
    pagina = Paginator(filtrados, 20).get_page(request.GET.get("page"))
    parametros = request.GET.copy()
    parametros.pop("page", None)
    return {
        "procesos": pagina,
        "page_obj": pagina,
        "querystring": parametros.urlencode(),
        "titulo": titulo,
        "descripcion": descripcion,
        "estados": ProcesoSeleccion.Estado.choices,
        "etapas": ProcesoSeleccion.Etapa.choices,
        "puede_crear": _rol(request.user) == Perfil.Rol.CONTRATACION,
    }


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
        contexto["asignaciones"] = SeguimientoEtapa.objects.filter(
            proceso__activo=True,
            proceso__etapa_actual=rol,
            proceso__estado__in=[ProcesoSeleccion.Estado.EN_CURSO, ProcesoSeleccion.Estado.LISTO_CONTRATACION],
            etapa=rol,
            fin__isnull=True,
        ).select_related("proceso").order_by("fecha_limite")
        contexto["historial_terminados"] = _procesos_visibles(
            request.user,
            ProcesoSeleccion.objects.filter(
                activo=True,
                estado__in=[ProcesoSeleccion.Estado.RECHAZADO, ProcesoSeleccion.Estado.CONTRATADO],
            ),
        ).order_by("-actualizado_en")[:20]
    return render(request, "procesos/lista.html", contexto)


@login_required
def trazabilidad(request):
    _exigir_gerente(request.user)
    abiertos = list(SeguimientoEtapa.objects.filter(
        fin__isnull=True, proceso__activo=True,
    ).select_related("proceso").order_by("fecha_limite"))
    vencidos = [item for item in abiertos if item.esta_vencido]
    por_vencer = [item for item in abiertos if not item.esta_vencido and item.dias_restantes <= 1]
    en_plazo = [item for item in abiertos if item not in vencidos and item not in por_vencer]
    metricas = []
    for valor, etiqueta in ProcesoSeleccion.Etapa.choices:
        cerrados = list(SeguimientoEtapa.objects.filter(etapa=valor, fin__isnull=False).exclude(
            resultado=SeguimientoEtapa.Resultado.AJUSTADO
        ))
        promedio = round(sum(item.duracion_horas for item in cerrados) / len(cerrados), 1) if cerrados else None
        a_tiempo = sum(not item.esta_vencido for item in cerrados)
        metricas.append({
            "etapa": etiqueta,
            "plazo": SeguimientoEtapa(proceso_id=0, etapa=valor).plazo_dias,
            "promedio_horas": promedio,
            "cumplimiento": round(a_tiempo * 100 / len(cerrados)) if cerrados else None,
            "finalizados": len(cerrados),
        })
    recientes = SeguimientoEtapa.objects.filter(fin__isnull=False).select_related(
        "proceso", "cerrado_por"
    ).order_by("-fin")[:50]
    return render(request, "procesos/trazabilidad.html", {
        "abiertos": abiertos,
        "vencidos": vencidos,
        "por_vencer": por_vencer,
        "en_plazo": en_plazo,
        "metricas": metricas,
        "recientes": recientes,
    })


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
    _exigir_gerente(request.user)
    qs = ProcesoSeleccion.objects.filter(activo=False)
    contexto = _contexto_lista(
        request, qs, "Candidatos desactivados", "Registros conservados fuera de las listas operativas que pueden restaurarse cuando sea necesario."
    )
    return render(request, "procesos/lista.html", contexto)


@login_required
def crear_proceso(request):
    _exigir_roles(request, Perfil.Rol.CONTRATACION)
    form = ProcesoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        proceso = form.save(commit=False)
        proceso.creado_por = request.user
        try:
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
    _exigir_gerente(request.user)
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
    _exigir_gerente(request.user)
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
def lista_usuarios(request):
    _exigir_gerente(request.user)
    usuarios = User.objects.select_related("perfil").order_by("perfil__rol", "first_name", "username")
    bloqueados_temporales = Q(perfil__bloqueado_hasta__gt=timezone.now())
    return render(request, "procesos/usuarios_lista.html", {
        "usuarios": usuarios,
        "usuarios_activos": usuarios.filter(is_active=True).exclude(bloqueados_temporales).count(),
        "usuarios_bloqueados": usuarios.filter(Q(is_active=False) | bloqueados_temporales).distinct().count(),
    })


@login_required
def auditoria_seguridad(request):
    _exigir_gerente(request.user)
    eventos = EventoSeguridad.objects.select_related("usuario")[:200]
    return render(request, "procesos/auditoria_seguridad.html", {"eventos": eventos})


@login_required
def crear_usuario(request):
    _exigir_gerente(request.user)
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
    _exigir_gerente(request.user)
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
    })


@login_required
def editar_usuario(request, pk):
    _exigir_gerente(request.user)
    usuario = get_object_or_404(User.objects.select_related("perfil"), pk=pk)
    if usuario.perfil.rol == Perfil.Rol.GERENTE:
        raise PermissionDenied("Las cuentas de Gerente no se modifican desde esta pantalla.")
    form = EditarUsuarioOperativoForm(request.POST or None, instance=usuario)
    if request.method == "POST" and form.is_valid():
        usuario = form.save()
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
        "descripcion": "Actualice sus datos, cambie el área o bloquee temporalmente el acceso.",
        "texto_boton": "Guardar cambios",
    })
