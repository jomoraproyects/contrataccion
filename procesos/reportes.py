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
    resumen = libro.active
    resumen.title = "Resumen"
    resumen.append(["Indicadores de selección"])
    resumen.append(["Periodo", rango])
    resumen.append([])
    resumen.append(["Indicador", "Valor"])
    for etiqueta, valor in (
        ("Procesos", indicadores["total"]),
        ("En curso", indicadores["en_curso"]),
        ("Listos para contratación", indicadores["listos"]),
        ("Contratados", indicadores["contratados"]),
        ("Rechazados", indicadores["rechazados"]),
        ("Contratados sobre finalizados", indicadores["porcentaje_contratados"] / 100),
        ("Rechazados sobre finalizados", indicadores["porcentaje_rechazados"] / 100),
        (
            "Área con más retrasos",
            indicadores["area_mas_retrasos"]["etapa"] if indicadores["area_mas_retrasos"] else "Sin retrasos",
        ),
        ("Procesos próximos a vencer", len(indicadores["proximos_vencer"])),
    ):
        resumen.append([etiqueta, valor])
    resumen["B10"].number_format = "0%"
    resumen["B11"].number_format = "0%"

    hoja_procesos = libro.create_sheet("Procesos")
    hoja_procesos.append([
        "ID", "Candidato", "Cédula", "Vacante", "Fecha de llegada",
        "Etapa actual", "Estado", "Tiempo total hábil (h)",
    ])
    for proceso in procesos:
        hoja_procesos.append([
            proceso.pk,
            _texto_excel(proceso.nombre_completo),
            _texto_excel(proceso.cedula),
            _texto_excel(proceso.vacante),
            proceso.fecha_llegada,
            proceso.get_etapa_actual_display(),
            proceso.get_estado_display(),
            proceso.duracion_total_horas,
        ])
    for celda in hoja_procesos["E"][1:]:
        celda.number_format = "yyyy-mm-dd"

    hoja_meses = libro.create_sheet("Procesos por mes")
    hoja_meses.append(["Mes", "Procesos iniciados"])
    for item in indicadores["por_mes"]:
        hoja_meses.append([item["periodo"], item["cantidad"]])

    hoja_etapas = libro.create_sheet("Tiempos por etapa")
    hoja_etapas.append([
        "Etapa", "Promedio (h)", "Mediana (h)", "Finalizadas", "Abiertas", "Con retraso",
    ])
    for item in indicadores["por_etapa"]:
        hoja_etapas.append([
            item["etapa"], item["promedio_horas"], item["mediana_horas"],
            item["finalizadas"], item["abiertas"], item["retrasos"],
        ])

    hoja_vacantes = libro.create_sheet("Vacantes")
    hoja_vacantes.append(["Vacante o área", "Candidatos"])
    for item in indicadores["vacantes"]:
        hoja_vacantes.append([_texto_excel(item["vacante"]), item["cantidad"]])

    hoja_vencimientos = libro.create_sheet("Próximos a vencer")
    hoja_vencimientos.append(["Candidato", "Vacante", "Etapa", "Fecha límite", "Situación"])
    for item in indicadores["proximos_vencer"]:
        hoja_vencimientos.append([
            _texto_excel(item.proceso.nombre_completo),
            _texto_excel(item.proceso.vacante),
            item.get_etapa_display(),
            timezone.localtime(item.fecha_limite).replace(tzinfo=None),
            item.estado_plazo,
        ])
    for celda in hoja_vencimientos["D"][1:]:
        celda.number_format = "yyyy-mm-dd hh:mm"

    encabezado = PatternFill("solid", fgColor="1559A6")
    for hoja in libro.worksheets:
        hoja.freeze_panes = "A2"
        hoja.sheet_view.showGridLines = False
        for celda in hoja[1]:
            celda.fill = encabezado
            celda.font = Font(color="FFFFFF", bold=True)
            celda.alignment = Alignment(vertical="center")
        for columna in hoja.columns:
            ancho = min(max(len(str(celda.value or "")) for celda in columna) + 3, 42)
            hoja.column_dimensions[columna[0].column_letter].width = max(ancho, 12)
    resumen["A1"].font = Font(size=16, bold=True, color="FFFFFF")
    for celda in resumen[4]:
        celda.fill = encabezado
        celda.font = Font(color="FFFFFF", bold=True)
    resumen.freeze_panes = None

    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue()


def exportar_pdf(procesos, indicadores, rango):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table

    salida = BytesIO()
    documento = SimpleDocTemplate(
        salida,
        pagesize=landscape(A4),
        rightMargin=1.2 * cm,
        leftMargin=1.2 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        title="Indicadores de selección",
    )
    estilos = getSampleStyleSheet()
    contenido = [
        Paragraph("Indicadores de selección", estilos["Title"]),
        Paragraph(f"Periodo: {escape(rango)}", estilos["Normal"]),
        Spacer(1, 0.35 * cm),
    ]
    resumen = [
        ["Procesos", "En curso", "Listos", "Contratados", "Rechazados", "% contratado", "% rechazado"],
        [
            indicadores["total"], indicadores["en_curso"], indicadores["listos"],
            indicadores["contratados"], indicadores["rechazados"],
            f'{indicadores["porcentaje_contratados"]}%', f'{indicadores["porcentaje_rechazados"]}%',
        ],
    ]
    tabla_resumen = Table(resumen, repeatRows=1)
    tabla_resumen.setStyle(_estilo_tabla_pdf(colors))
    area_retrasos = indicadores["area_mas_retrasos"]
    detalle_retrasos = (
        f'{escape(area_retrasos["etapa"])} ({area_retrasos["retrasos"]} retrasos)'
        if area_retrasos else "Sin retrasos registrados"
    )
    contenido.extend([
        tabla_resumen,
        Spacer(1, 0.2 * cm),
        Paragraph(
            f"Área con más retrasos: <b>{detalle_retrasos}</b>. "
            f"Procesos próximos a vencer: <b>{len(indicadores['proximos_vencer'])}</b>.",
            estilos["Normal"],
        ),
        Spacer(1, 0.45 * cm),
    ])

    contenido.append(Paragraph("Tiempos por etapa", estilos["Heading2"]))
    filas_etapa = [["Etapa", "Promedio (h)", "Mediana (h)", "Finalizadas", "Abiertas", "Retrasos"]]
    for item in indicadores["por_etapa"]:
        filas_etapa.append([
            escape(item["etapa"]), item["promedio_horas"] if item["promedio_horas"] is not None else "-",
            item["mediana_horas"] if item["mediana_horas"] is not None else "-",
            item["finalizadas"], item["abiertas"], item["retrasos"],
        ])
    tabla_etapas = Table(filas_etapa, repeatRows=1, colWidths=[7 * cm, 3 * cm, 3 * cm, 3 * cm, 3 * cm, 3 * cm])
    tabla_etapas.setStyle(_estilo_tabla_pdf(colors))
    contenido.extend([tabla_etapas, Spacer(1, 0.45 * cm)])

    contenido.append(Paragraph("Procesos por mes", estilos["Heading2"]))
    filas_meses = [["Mes", "Procesos iniciados"]] + [
        [item["etiqueta"], item["cantidad"]] for item in indicadores["por_mes"]
    ]
    if len(filas_meses) == 1:
        filas_meses.append(["Sin datos", 0])
    tabla_meses = Table(filas_meses, repeatRows=1, colWidths=[5 * cm, 4 * cm])
    tabla_meses.setStyle(_estilo_tabla_pdf(colors))
    contenido.extend([tabla_meses, Spacer(1, 0.35 * cm)])

    titulo_vacantes = Paragraph("Vacantes con más candidatos", estilos["Heading2"])
    filas_vacantes = [["Vacante o área", "Candidatos"]] + [
        [Paragraph(escape(item["vacante"]), estilos["BodyText"]), item["cantidad"]]
        for item in indicadores["vacantes"]
    ]
    if len(filas_vacantes) == 1:
        filas_vacantes.append(["Sin datos", 0])
    tabla_vacantes = Table(filas_vacantes, repeatRows=1, colWidths=[10 * cm, 4 * cm])
    tabla_vacantes.setStyle(_estilo_tabla_pdf(colors))
    contenido.append(KeepTogether([titulo_vacantes, tabla_vacantes, Spacer(1, 0.45 * cm)]))

    if indicadores["proximos_vencer"]:
        filas_vencimientos = [["Candidato", "Vacante", "Etapa", "Fecha límite", "Situación"]]
        for item in indicadores["proximos_vencer"]:
            filas_vencimientos.append([
                Paragraph(escape(item.proceso.nombre_completo), estilos["BodyText"]),
                Paragraph(escape(item.proceso.vacante), estilos["BodyText"]),
                Paragraph(escape(item.get_etapa_display()), estilos["BodyText"]),
                timezone.localtime(item.fecha_limite).strftime("%d/%m/%Y %H:%M"),
                item.estado_plazo,
            ])
        tabla_vencimientos = Table(
            filas_vencimientos,
            repeatRows=1,
            colWidths=[5 * cm, 5 * cm, 5 * cm, 3.5 * cm, 4.5 * cm],
        )
        tabla_vencimientos.setStyle(_estilo_tabla_pdf(colors))
        contenido.append(KeepTogether([
            Paragraph("Procesos próximos a vencer", estilos["Heading2"]),
            tabla_vencimientos,
            Spacer(1, 0.45 * cm),
        ]))

    contenido.append(Paragraph("Procesos filtrados", estilos["Heading2"]))
    filas = [["Candidato", "Cédula", "Vacante", "Llegada", "Etapa", "Estado", "Tiempo (h)"]]
    for proceso in procesos:
        filas.append([
            Paragraph(escape(proceso.nombre_completo), estilos["BodyText"]),
            escape(proceso.cedula),
            Paragraph(escape(proceso.vacante), estilos["BodyText"]),
            proceso.fecha_llegada.strftime("%d/%m/%Y"),
            Paragraph(escape(proceso.get_etapa_actual_display()), estilos["BodyText"]),
            proceso.get_estado_display(),
            proceso.duracion_total_horas,
        ])
    if len(filas) == 1:
        filas.append(["Sin procesos para el periodo", "", "", "", "", "", ""])
    tabla = Table(
        filas,
        repeatRows=1,
        colWidths=[4.8 * cm, 2.7 * cm, 5.2 * cm, 2.7 * cm, 4.5 * cm, 2.8 * cm, 2.2 * cm],
    )
    tabla.setStyle(_estilo_tabla_pdf(colors))
    contenido.append(tabla)
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
