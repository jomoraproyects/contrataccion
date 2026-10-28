"""Presentación de reportes, sin consultas ni cambios a la base de datos."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

AZUL = colors.HexColor("#1559A6")
TINTA = colors.HexColor("#182D43")
GRIS = colors.HexColor("#516477")
BORDE = colors.HexColor("#DCE5EE")


def _estilos():
    estilos = getSampleStyleSheet()
    estilos["Title"].fontName = "Helvetica-Bold"
    estilos["Title"].fontSize = 22
    estilos["Title"].leading = 27
    estilos["Title"].alignment = 0
    estilos["Title"].textColor = TINTA
    estilos["Heading2"].fontName = "Helvetica-Bold"
    estilos["Heading2"].fontSize = 12
    estilos["Heading2"].leading = 17
    estilos["Heading2"].spaceBefore = 14
    estilos["Heading2"].spaceAfter = 9
    estilos["Heading2"].textColor = AZUL
    estilos["BodyText"].fontSize = 9.5
    estilos["BodyText"].leading = 14
    estilos["BodyText"].textColor = TINTA
    estilos.add(ParagraphStyle("Celda", fontName="Helvetica", fontSize=9, leading=12, textColor=TINTA, splitLongWords=True))
    estilos.add(ParagraphStyle("Cabecera", parent=estilos["Celda"], fontName="Helvetica-Bold", fontSize=8.5, textColor=colors.white))
    estilos.add(ParagraphStyle("Nota", parent=estilos["BodyText"], fontSize=8.5, leading=12, textColor=GRIS))
    return estilos


def _parrafo(texto, estilo):
    return Paragraph(escape(str(texto if texto is not None else "-")).replace("\n", "<br/>"), estilo)


def _tabla(cabeceras, filas, proporciones, ancho, estilos):
    datos = [[_parrafo(c, estilos["Cabecera"]) for c in cabeceras]]
    datos.extend([[c if isinstance(c, Paragraph) else _parrafo(c, estilos["Celda"]) for c in fila] for fila in filas])
    if len(datos) == 1:
        datos.append([_parrafo("Sin registros para los filtros seleccionados", estilos["Celda"])] + [""] * (len(cabeceras) - 1))
    tabla = Table(datos, colWidths=[ancho * p / sum(proporciones) for p in proporciones], repeatRows=1, hAlign="LEFT", splitByRow=1, splitInRow=1)
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F7FB")]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.35, BORDE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return tabla


def _tabla_candidatos(cabeceras, procesos, filas, proporciones, documento, estilos):
    """Mantiene el motivo justo debajo de su candidato, sin anexos separados."""
    from .models import ProcesoSeleccion
    from .reportes import _datos_rechazo

    datos, grupos = [], []
    for indice, (proceso, fila) in enumerate(zip(procesos, filas)):
        inicio = len(datos) + 1  # La fila cero corresponde a las cabeceras.
        datos.append(fila)
        if proceso.estado == ProcesoSeleccion.Estado.RECHAZADO:
            etapa, motivo = _datos_rechazo(proceso)
            texto = (
                f"<b>Motivo de rechazo - {escape(str(etapa))}:</b><br/>"
                + escape(str(motivo)).replace("\r\n", "\n").replace("\n", "<br/>")
            )
            requisitos = getattr(proceso, "requisitos_rechazo", ())
            if requisitos:
                texto += "<br/><b>Validaciones no cumplidas:</b> " + escape(", ".join(requisitos))
            datos.append([Paragraph(texto, estilos["BodyText"])] + [""] * (len(cabeceras) - 1))
        grupos.append((inicio, len(datos), indice))
    tabla = _tabla(cabeceras, datos, proporciones, documento.width, estilos)
    comandos = []
    for inicio, fin, indice in grupos:
        fondo = colors.white if indice % 2 == 0 else colors.HexColor("#F4F7FB")
        comandos.append(("BACKGROUND", (0, inicio), (-1, fin), fondo))
        if fin > inicio:
            comandos.extend([
                ("SPAN", (0, fin), (-1, fin)),
                ("BACKGROUND", (0, fin), (-1, fin), colors.HexColor("#FFF5F2")),
                ("LEFTPADDING", (0, fin), (-1, fin), 12),
                ("LINEBELOW", (0, fin), (-1, fin), 0.8, BORDE),
            ])
    tabla.setStyle(TableStyle(comandos))
    tabla.wrap(documento.width, documento.height)
    tabla.splitInRow = int(any(
        alto + tabla._rowHeights[0] > documento.height for alto in tabla._rowHeights[1:]
    ))
    # No separar candidato y motivo si el bloque cabe en una página.
    # Para observaciones excepcionalmente largas se permite el salto de línea
    # entre páginas, en lugar de fallar la generación del reporte.
    tabla.setStyle(TableStyle([
        ("NOSPLIT", (0, inicio), (-1, fin)) for inicio, fin, _ in grupos
        if fin > inicio and sum(tabla._rowHeights[inicio:fin + 1]) + tabla._rowHeights[0] <= documento.height
    ]))
    return tabla


def _documento(titulo, filtros, total):
    salida = BytesIO()
    documento = SimpleDocTemplate(salida, pagesize=landscape(A4), leftMargin=14*mm, rightMargin=14*mm, topMargin=25*mm, bottomMargin=18*mm, title=titulo, author="Serviciudad")
    estilos = _estilos()
    contenido = [
        _parrafo(titulo, estilos["Title"]),
        _parrafo(f"Filtros aplicados: {filtros}", estilos["Nota"]),
        Spacer(1, 3*mm),
        _parrafo(f"{total} proceso(s) incluidos - todos los resultados filtrados, no solo la página visible.", estilos["Nota"]),
        Spacer(1, 5*mm),
    ]
    generado = timezone.localtime().strftime("%d/%m/%Y %H:%M")
    logo = Path(settings.BASE_DIR) / "static" / "img" / "serviciudad.jpg"

    def pagina(canvas, doc):
        canvas.saveState()
        alto = doc.pagesize[1]
        x = doc.leftMargin
        if logo.is_file():
            canvas.drawImage(str(logo), x, alto - 19*mm, width=11*mm, height=11*mm, preserveAspectRatio=True, mask="auto")
            x += 15*mm
        canvas.setFillColor(AZUL)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(x, alto - 12*mm, "SERVICIUDAD")
        canvas.setFillColor(GRIS)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(x, alto - 16*mm, "Selección de Personal")
        canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, alto - 14*mm, f"Generado: {generado}")
        canvas.setStrokeColor(BORDE)
        canvas.line(doc.leftMargin, 13*mm, doc.pagesize[0] - doc.rightMargin, 13*mm)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(doc.leftMargin, 8*mm, "Uso interno - Información de selección de personal")
        canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 8*mm, f"Página {doc.page}")
        canvas.restoreState()

    return salida, documento, estilos, contenido, pagina


def candidatos_pdf(procesos, filtros):
    procesos = list(procesos)
    salida, doc, estilos, contenido, pagina = _documento("Candidatos por vacante", filtros, len(procesos))
    filas = [[p.nombre_completo, p.cedula, p.celular, p.vacante, p.fecha_llegada.strftime("%d/%m/%Y"), p.get_etapa_actual_display(), p.get_estado_display()] for p in procesos]
    contenido.append(_tabla_candidatos(["Candidato", "Cédula", "Celular", "Vacante", "Llegada HDV", "Etapa actual", "Estado"], procesos, filas, [22, 12, 12, 21, 11, 14, 12], doc, estilos))
    doc.build(contenido, onFirstPage=pagina, onLaterPages=pagina)
    return salida.getvalue()


def trazabilidad_pdf(procesos, resumen, filtros):
    procesos = list(procesos)
    salida, doc, estilos, contenido, pagina = _documento("Trazabilidad de selección", filtros, len(procesos))
    contenido.append(_tabla(["Procesos", "Finalizados", "Con retrasos", "Etapas abiertas"], [[resumen["total"], resumen["finalizados"], resumen["con_retrasos"], resumen["abiertos"]]], [1, 1, 1, 1], doc.width, estilos))
    contenido.append(_parrafo("Procesos filtrados", estilos["Heading2"]))
    filas = [[f"{p.nombre_completo}\nCédula: {p.cedula}", p.vacante, p.fecha_llegada.strftime("%d/%m/%Y"), p.get_etapa_actual_display(), p.get_estado_display(), f"{p.traza_total_horas} h", p.traza_fuera_tiempo] for p in procesos]
    contenido.append(_tabla_candidatos(["Candidato", "Vacante", "Llegada HDV", "Etapa actual", "Estado", "Tiempo hábil", "Etapas con retraso"], procesos, filas, [24, 23, 11, 16, 13, 9, 10], doc, estilos))
    doc.build(contenido, onFirstPage=pagina, onLaterPages=pagina)
    return salida.getvalue()
