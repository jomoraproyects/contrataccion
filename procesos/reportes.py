from collections import Counter
from io import BytesIO
from statistics import mean, median
from xml.sax.saxutils import escape

from django.utils import timezone

from .models import ProcesoSeleccion, SeguimientoEtapa


def filtrar_procesos_por_fecha(queryset, formulario):
    if not formulario.is_valid():
        return queryset.none()
    desde = formulario.cleaned_data.get("fecha_desde")
    hasta = formulario.cleaned_data.get("fecha_hasta")
    if desde:
        queryset = queryset.filter(fecha_llegada__gte=desde)
    if hasta:
        queryset = queryset.filter(fecha_llegada__lte=hasta)
    estado = formulario.cleaned_data.get("estado")
    etapa = formulario.cleaned_data.get("etapa")
    vacante = formulario.cleaned_data.get("vacante", "").strip()
    if estado:
        queryset = queryset.filter(estado=estado)
    if etapa:
        queryset = queryset.filter(etapa_actual=etapa)
    if vacante:
        queryset = queryset.filter(vacante__icontains=vacante)
    return queryset


def calcular_indicadores(procesos):
    procesos = list(procesos)
    seguimientos = [item for proceso in procesos for item in proceso.seguimientos.all()]
    cerrados = [
        item for item in seguimientos
        if item.fin is not None and item.resultado != SeguimientoEtapa.Resultado.AJUSTADO
    ]
    abiertos = [
        item for item in seguimientos
        if item.fin is None and item.proceso.activo and not item.proceso.esta_finalizado
    ]

    contratados = sum(p.estado == ProcesoSeleccion.Estado.CONTRATADO for p in procesos)
    rechazados = sum(p.estado == ProcesoSeleccion.Estado.RECHAZADO for p in procesos)
    finalizados = contratados + rechazados

    por_mes_contador = Counter((p.fecha_llegada.year, p.fecha_llegada.month) for p in procesos)
    meses = [
        {
            "periodo": f"{anio:04d}-{mes:02d}",
            "etiqueta": f"{mes:02d}/{anio}",
            "cantidad": cantidad,
        }
        for (anio, mes), cantidad in sorted(por_mes_contador.items())
    ]

    metricas_etapa = []
    for valor, etiqueta in ProcesoSeleccion.Etapa.choices:
        cerrados_etapa = [item for item in cerrados if item.etapa == valor]
        todos_etapa = [item for item in seguimientos if item.etapa == valor and item.resultado != SeguimientoEtapa.Resultado.AJUSTADO]
        duraciones = [item.duracion_horas for item in cerrados_etapa]
        metricas_etapa.append({
            "valor": valor,
            "etapa": etiqueta,
            "promedio_horas": round(mean(duraciones), 1) if duraciones else None,
            "mediana_horas": round(median(duraciones), 1) if duraciones else None,
            "finalizadas": len(cerrados_etapa),
            "abiertas": sum(item.fin is None for item in todos_etapa),
            "retrasos": sum(item.esta_vencido for item in todos_etapa),
        })

    con_retrasos = [item for item in metricas_etapa if item["retrasos"]]
    area_mas_retrasos = max(con_retrasos, key=lambda item: item["retrasos"], default=None)
    proximos_vencer = sorted(
        [item for item in abiertos if not item.esta_vencido and item.dias_restantes <= 1],
        key=lambda item: item.fecha_limite,
    )
    vacantes = [
        {"vacante": vacante, "cantidad": cantidad}
        for vacante, cantidad in Counter(p.vacante.strip() for p in procesos).most_common(10)
    ]

    return {
        "total": len(procesos),
        "en_curso": sum(p.estado == ProcesoSeleccion.Estado.EN_CURSO for p in procesos),
        "listos": sum(p.estado == ProcesoSeleccion.Estado.LISTO_CONTRATACION for p in procesos),
        "contratados": contratados,
        "rechazados": rechazados,
        "finalizados": finalizados,
        "porcentaje_contratados": round(contratados * 100 / finalizados) if finalizados else 0,
        "porcentaje_rechazados": round(rechazados * 100 / finalizados) if finalizados else 0,
        "por_mes": meses,
        "por_etapa": metricas_etapa,
        "area_mas_retrasos": area_mas_retrasos,
        "proximos_vencer": proximos_vencer,
        "vacantes": vacantes,
    }


def _texto_excel(valor):
    texto = str(valor or "")
    return f"'{texto}" if texto.startswith(("=", "+", "-", "@")) else texto


def exportar_excel(procesos, indicadores, rango):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Candidatos"
    hoja.append([
        "Candidato", "Cédula", "Celular", "Vacante",
        "Fecha de llegada de la hoja de vida", "Etapa actual", "Estado",
    ])
    for proceso in procesos:
        hoja.append([
            _texto_excel(proceso.nombre_completo),
            _texto_excel(proceso.cedula),
            _texto_excel(proceso.celular),
            _texto_excel(proceso.vacante),
            proceso.fecha_llegada,
            proceso.get_etapa_actual_display(),
            proceso.get_estado_display(),
        ])
    for celda in hoja["E"][1:]:
        celda.number_format = "yyyy-mm-dd"

    encabezado = PatternFill("solid", fgColor="1559A6")
    hoja.freeze_panes = "A2"
    hoja.auto_filter.ref = hoja.dimensions
    hoja.sheet_view.showGridLines = False
    for celda in hoja[1]:
        celda.fill = encabezado
        celda.font = Font(color="FFFFFF", bold=True)
        celda.alignment = Alignment(vertical="center")
    for columna in hoja.columns:
        ancho = min(max(len(str(celda.value or "")) for celda in columna) + 3, 44)
        hoja.column_dimensions[columna[0].column_letter].width = max(ancho, 14)

    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue()


def exportar_pdf(procesos, indicadores, rango):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table

    salida = BytesIO()
    documento = SimpleDocTemplate(
        salida,
        pagesize=landscape(A4),
        rightMargin=1.2 * cm,
        leftMargin=1.2 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        title="Candidatos por vacante",
    )
    estilos = getSampleStyleSheet()
    contenido = [
        Paragraph("Candidatos por vacante", estilos["Title"]),
        Paragraph(f"Filtros aplicados: {escape(rango)}", estilos["Normal"]),
        Spacer(1, 0.35 * cm),
    ]
    filas = [["Candidato", "Cédula", "Celular", "Vacante", "Llegada HDV", "Etapa actual", "Estado"]]
    for proceso in procesos:
        filas.append([
            Paragraph(escape(proceso.nombre_completo), estilos["BodyText"]),
            escape(proceso.cedula),
            escape(proceso.celular),
            Paragraph(escape(proceso.vacante), estilos["BodyText"]),
            proceso.fecha_llegada.strftime("%d/%m/%Y"),
            Paragraph(escape(proceso.get_etapa_actual_display()), estilos["BodyText"]),
            proceso.get_estado_display(),
        ])
    if len(filas) == 1:
        filas.append(["Sin candidatos para los filtros seleccionados", "", "", "", "", "", ""])
    tabla = Table(
        filas,
        repeatRows=1,
        colWidths=[5 * cm, 3 * cm, 3.3 * cm, 5.2 * cm, 3 * cm, 4.2 * cm, 3.2 * cm],
    )
    tabla.setStyle(_estilo_tabla_pdf(colors))
    contenido.append(tabla)
    documento.build(contenido)
    return salida.getvalue()


def _fecha_excel(valor):
    if valor is None:
        return None
    if timezone.is_aware(valor):
        return timezone.localtime(valor).replace(tzinfo=None)
    return valor


def exportar_trazabilidad_excel(procesos, metricas, resumen, filtros):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    libro = Workbook()
    hoja_resumen = libro.active
    hoja_resumen.title = "Resumen"
    hoja_resumen.append(["Trazabilidad de selección"])
    hoja_resumen.append(["Filtros aplicados", filtros])
    hoja_resumen.append([])
    hoja_resumen.append(["Indicador", "Valor"])
    hoja_resumen.append(["Procesos encontrados", resumen["total"]])
    hoja_resumen.append(["Procesos finalizados", resumen["finalizados"]])
    hoja_resumen.append(["Procesos con retrasos", resumen["con_retrasos"]])
    hoja_resumen.append(["Etapas abiertas", resumen["abiertos"]])

    hoja_candidatos = libro.create_sheet("Candidatos")
    hoja_candidatos.append([
        "ID", "Candidato", "Cédula", "Vacante o área", "Fecha de llegada",
        "Etapa actual", "Estado", "Tiempo total hábil (h)", "Etapa de mayor demora",
        "Etapas fuera de tiempo",
    ])
    for proceso in procesos:
        hoja_candidatos.append([
            proceso.pk,
            _texto_excel(proceso.nombre_completo),
            _texto_excel(proceso.cedula),
            _texto_excel(proceso.vacante),
            proceso.fecha_llegada,
            proceso.get_etapa_actual_display(),
            proceso.get_estado_display(),
            proceso.traza_total_horas,
            proceso.traza_mas_lenta.get_etapa_display() if proceso.traza_mas_lenta else "-",
            proceso.traza_fuera_tiempo,
        ])
    for celda in hoja_candidatos["E"][1:]:
        celda.number_format = "yyyy-mm-dd"

    hoja_etapas = libro.create_sheet("Detalle por etapa")
    hoja_etapas.append([
        "Candidato", "Cédula", "Vacante o área", "Etapa", "Plazo (días hábiles)",
        "Inicio", "Finalización", "Fecha límite", "Tiempo hábil (h)", "Resultado", "Cumplimiento",
    ])
    for proceso in procesos:
        for seguimiento in proceso.traza_seguimientos:
            hoja_etapas.append([
                _texto_excel(proceso.nombre_completo),
                _texto_excel(proceso.cedula),
                _texto_excel(proceso.vacante),
                seguimiento.get_etapa_display(),
                seguimiento.plazo_dias,
                _fecha_excel(seguimiento.inicio),
                _fecha_excel(seguimiento.fin),
                _fecha_excel(seguimiento.fecha_limite),
                seguimiento.duracion_horas,
                seguimiento.get_resultado_display() or "Pendiente",
                seguimiento.estado_plazo,
            ])
    for columna in ("F", "G", "H"):
        for celda in hoja_etapas[columna][1:]:
            celda.number_format = "yyyy-mm-dd hh:mm"

    hoja_areas = libro.create_sheet("Resumen por área")
    hoja_areas.append([
        "Área o etapa", "Plazo (días hábiles)", "Promedio (h)",
        "Cumplimiento", "Abiertas", "Vencidas", "Finalizadas",
    ])
    for metrica in metricas:
        hoja_areas.append([
            metrica["etapa"], metrica["plazo"], metrica["promedio_horas"],
            metrica["cumplimiento"] / 100 if metrica["cumplimiento"] is not None else None,
            metrica["abiertos"], metrica["vencidos"], metrica["finalizados"],
        ])
    for celda in hoja_areas["D"][1:]:
        celda.number_format = "0%"

    encabezado = PatternFill("solid", fgColor="1559A6")
    for hoja in libro.worksheets:
        hoja.freeze_panes = "A2"
        hoja.sheet_view.showGridLines = False
        for celda in hoja[1]:
            celda.fill = encabezado
            celda.font = Font(color="FFFFFF", bold=True)
            celda.alignment = Alignment(vertical="center")
        for columna in hoja.columns:
            ancho = min(max(len(str(celda.value or "")) for celda in columna) + 3, 44)
            hoja.column_dimensions[columna[0].column_letter].width = max(ancho, 12)
    hoja_resumen["A1"].font = Font(size=16, bold=True, color="FFFFFF")
    hoja_resumen.freeze_panes = None

    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue()


def exportar_trazabilidad_pdf(procesos, metricas, resumen, filtros):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table

    salida = BytesIO()
    documento = SimpleDocTemplate(
        salida,
        pagesize=landscape(A4),
        rightMargin=1 * cm,
        leftMargin=1 * cm,
        topMargin=1 * cm,
        bottomMargin=1 * cm,
        title="Trazabilidad de selección",
    )
    estilos = getSampleStyleSheet()
    contenido = [
        Paragraph("Trazabilidad de selección", estilos["Title"]),
        Paragraph(f"Filtros aplicados: {escape(filtros)}", estilos["Normal"]),
        Spacer(1, 0.3 * cm),
    ]
    tabla_resumen = Table([
        ["Procesos", "Finalizados", "Con retrasos", "Etapas abiertas"],
        [resumen["total"], resumen["finalizados"], resumen["con_retrasos"], resumen["abiertos"]],
    ], repeatRows=1, colWidths=[5.5 * cm] * 4)
    tabla_resumen.setStyle(_estilo_tabla_pdf(colors))
    contenido.extend([tabla_resumen, Spacer(1, 0.4 * cm)])

    contenido.append(Paragraph("Comportamiento por área", estilos["Heading2"]))
    filas_areas = [["Área", "Plazo", "Promedio", "% a tiempo", "Abiertas", "Vencidas", "Finalizadas"]]
    for metrica in metricas:
        filas_areas.append([
            Paragraph(escape(metrica["etapa"]), estilos["BodyText"]),
            f'{metrica["plazo"]} días',
            f'{metrica["promedio_horas"]} h' if metrica["promedio_horas"] is not None else "-",
            f'{metrica["cumplimiento"]}%' if metrica["cumplimiento"] is not None else "-",
            metrica["abiertos"], metrica["vencidos"], metrica["finalizados"],
        ])
    tabla_areas = Table(
        filas_areas, repeatRows=1,
        colWidths=[6.8 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 2.3 * cm, 2.3 * cm, 2.5 * cm],
    )
    tabla_areas.setStyle(_estilo_tabla_pdf(colors))
    contenido.extend([tabla_areas, Spacer(1, 0.4 * cm)])

    contenido.append(Paragraph("Procesos filtrados", estilos["Heading2"]))
    filas_procesos = [[
        "Candidato", "Cédula", "Vacante o área", "Llegada", "Etapa", "Estado", "Tiempo", "Retrasos",
    ]]
    for proceso in procesos:
        filas_procesos.append([
            Paragraph(escape(proceso.nombre_completo), estilos["BodyText"]),
            escape(proceso.cedula),
            Paragraph(escape(proceso.vacante), estilos["BodyText"]),
            proceso.fecha_llegada.strftime("%d/%m/%Y"),
            Paragraph(escape(proceso.get_etapa_actual_display()), estilos["BodyText"]),
            proceso.get_estado_display(),
            f"{proceso.traza_total_horas} h",
            proceso.traza_fuera_tiempo,
        ])
    if len(filas_procesos) == 1:
        filas_procesos.append(["Sin procesos para estos filtros", "", "", "", "", "", "", ""])
    tabla_procesos = Table(
        filas_procesos, repeatRows=1,
        colWidths=[4.3 * cm, 2.5 * cm, 4.6 * cm, 2.4 * cm, 4 * cm, 2.6 * cm, 2.2 * cm, 2 * cm],
    )
    tabla_procesos.setStyle(_estilo_tabla_pdf(colors))
    contenido.extend([tabla_procesos, Spacer(1, 0.4 * cm)])

    contenido.append(Paragraph("Detalle de etapas", estilos["Heading2"]))
    filas_etapas = [["Candidato", "Etapa", "Plazo", "Inicio", "Finalización", "Tiempo", "Resultado", "Cumplimiento"]]
    for proceso in procesos:
        for seguimiento in proceso.traza_seguimientos:
            filas_etapas.append([
                Paragraph(escape(proceso.nombre_completo), estilos["BodyText"]),
                Paragraph(escape(seguimiento.get_etapa_display()), estilos["BodyText"]),
                f"{seguimiento.plazo_dias} días",
                timezone.localtime(seguimiento.inicio).strftime("%d/%m/%Y %H:%M"),
                timezone.localtime(seguimiento.fin).strftime("%d/%m/%Y %H:%M") if seguimiento.fin else "En curso",
                f"{seguimiento.duracion_horas} h",
                seguimiento.get_resultado_display() or "Pendiente",
                seguimiento.estado_plazo,
            ])
    if len(filas_etapas) == 1:
        filas_etapas.append(["Sin etapas para estos filtros", "", "", "", "", "", "", ""])
    tabla_etapas = Table(
        filas_etapas, repeatRows=1,
        colWidths=[4 * cm, 4 * cm, 2.2 * cm, 3.2 * cm, 3.2 * cm, 2.2 * cm, 2.8 * cm, 3.4 * cm],
    )
    tabla_etapas.setStyle(_estilo_tabla_pdf(colors))
    contenido.append(tabla_etapas)
    documento.build(contenido)
    return salida.getvalue()


def _estilo_tabla_pdf(colors):
    from reportlab.platypus import TableStyle

    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1559A6")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EEF4FA")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#B7C6D8")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ])
