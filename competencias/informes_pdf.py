"""PDF informe de curso: portada + página de resultados (estilo informe 25-26)."""

from __future__ import annotations

import math
from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

# Paleta del modelo
BG = (0.04, 0.18, 0.38)  # azul oscuro
BG_GLOW = (0.08, 0.28, 0.55)
LIME = (0.70, 0.83, 0.24)
LIME_DARK = (0.55, 0.68, 0.15)
WHITE = (1, 1, 1)
BANNER = (0.35, 0.55, 0.78)
YELLOW = (0.95, 0.85, 0.30)
ORANGE = (0.95, 0.55, 0.20)
PIE_PROMO = (0.45, 0.78, 0.35)
PIE_PIL = (0.95, 0.82, 0.25)
PIE_REP = (0.95, 0.55, 0.22)
PIE_EXC = (0.35, 0.65, 0.95)  # promoción/titulación excepcional
TABLE_ROW = (0.92, 0.95, 0.98)
ACCENT_BAR = LIME

PAGE = landscape(A4)  # ~842 x 595


def _pdf_txt(s: object) -> str:
    """Helvetica (WinAnsi) no trae 'º'; evita caracteres que se pierden."""
    return (
        str(s or "")
        .replace("º", "o")
        .replace("ª", "a")
        .replace("—", "-")
        .replace("–", "-")
    )


def _logo_path() -> Path | None:
    p = Path("static/logo.png")
    if p.is_file():
        return p
    alt = Path(__file__).resolve().parents[1] / "static" / "logo.png"
    return alt if alt.is_file() else None


def _set_fill(c: canvas.Canvas, rgb: tuple[float, float, float]) -> None:
    c.setFillColorRGB(*rgb)


def _set_stroke(c: canvas.Canvas, rgb: tuple[float, float, float]) -> None:
    c.setStrokeColorRGB(*rgb)


def _paint_bg(c: canvas.Canvas, w: float, h: float) -> None:
    from reportlab.lib.colors import Color

    _set_fill(c, BG)
    c.rect(0, 0, w, h, fill=1, stroke=0)
    cx, cy = w / 2, h * 0.55
    for i, alpha in enumerate((0.14, 0.09, 0.05)):
        r = 180 + i * 70
        c.setFillColor(Color(BG_GLOW[0], BG_GLOW[1], BG_GLOW[2], alpha=alpha))
        c.circle(cx, cy, r, fill=1, stroke=0)
    # Tras colores con alpha, ReportLab deja la opacidad baja y el resto
    # (tablas, texto) queda casi invisible en muchos visores.
    c.setFillAlpha(1)
    c.setStrokeAlpha(1)
    _set_fill(c, WHITE)
    _set_fill(c, ACCENT_BAR)
    c.rect(w - 18, h - 95, 18, 95, fill=1, stroke=0)


def _draw_cover(c: canvas.Canvas, data: dict[str, Any]) -> None:
    w, h = PAGE
    _paint_bg(c, w, h)

    # Banda logo
    band_h = 78
    band_y = h - 130
    from reportlab.lib.colors import Color

    c.setFillColor(Color(BANNER[0], BANNER[1], BANNER[2], alpha=0.55))
    c.roundRect(w * 0.22, band_y, w * 0.56, band_h, 8, fill=1, stroke=0)

    logo = _logo_path()
    if logo:
        try:
            img = ImageReader(str(logo))
            iw, ih = img.getSize()
            max_h = 58
            scale = max_h / float(ih)
            dw, dh = iw * scale, ih * scale
            c.drawImage(
                img,
                (w - dw) / 2,
                band_y + (band_h - dh) / 2,
                width=dw,
                height=dh,
                mask="auto",
            )
        except Exception:
            _set_fill(c, WHITE)
            c.setFont("Helvetica-Bold", 14)
            c.drawCentredString(w / 2, band_y + 32, "IES Antonio García Bellido")

    _set_fill(c, WHITE)
    c.setFont("Helvetica", 36)
    c.drawCentredString(w / 2, h * 0.48, "INFORME RESULTADOS")

    _set_fill(c, LIME)
    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(w / 2, h * 0.40, "EVALUACION FINAL")
    c.drawCentredString(w / 2, h * 0.33, _pdf_txt(data.get("curso_escolar") or ""))


def _rounded_table_header(
    c: canvas.Canvas,
    x: float,
    y: float,
    col_ws: list[float],
    headers: list[str],
    row_h: float,
) -> None:
    total_w = sum(col_ws)
    _set_fill(c, LIME)
    c.roundRect(x, y - row_h, total_w, row_h, 6, fill=1, stroke=0)
    # Solo redondear arriba: tapar abajo
    c.rect(x, y - row_h, total_w, row_h / 2, fill=1, stroke=0)
    _set_fill(c, (0.05, 0.15, 0.25))
    c.setFont("Helvetica-Bold", 9)
    cx = x
    for i, (hw, lab) in enumerate(zip(col_ws, headers)):
        text = _pdf_txt(lab)
        if i == 0:
            c.drawString(cx + 6, y - row_h + 8, text)
        else:
            c.drawCentredString(cx + hw / 2, y - row_h + 8, text)
        cx += hw


def _table_row(
    c: canvas.Canvas,
    x: float,
    y: float,
    col_ws: list[float],
    cells: list[str],
    row_h: float,
    *,
    highlight: bool = False,
    bold: bool = False,
) -> None:
    total_w = sum(col_ws)
    if highlight:
        _set_fill(c, LIME)
    else:
        from reportlab.lib.colors import Color

        c.setFillColor(Color(1, 1, 1, alpha=0.92))
    c.rect(x, y - row_h, total_w, row_h, fill=1, stroke=0)
    _set_stroke(c, (0.75, 0.82, 0.88))
    c.setLineWidth(0.4)
    c.rect(x, y - row_h, total_w, row_h, fill=0, stroke=1)
    if highlight:
        _set_fill(c, (0.05, 0.15, 0.25))
    else:
        _set_fill(c, (0.08, 0.18, 0.32))
    c.setFont("Helvetica-Bold" if bold or highlight else "Helvetica", 9)
    cx = x
    for i, (hw, lab) in enumerate(zip(col_ws, cells)):
        text = _pdf_txt(lab)
        if i == 0:
            c.drawString(cx + 6, y - row_h + 7, text)
        else:
            c.drawCentredString(cx + hw / 2, y - row_h + 7, text)
        cx += hw


def _draw_bar_chart(
    c: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    labels: list[str],
    values: list[float],
    title: str,
    *,
    ymax: float | None = None,
) -> None:
    _set_fill(c, WHITE)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(x + w / 2, y + h - 4, title)

    chart_top = y + h - 22
    chart_bot = y + 28
    chart_left = x + 28
    chart_right = x + w - 10
    chart_h = chart_top - chart_bot
    chart_w = chart_right - chart_left

    vmax = max(values) if values else 1.0
    y_top = float(ymax) if ymax else max(8.0, math.ceil(vmax))

    _set_stroke(c, (0.7, 0.8, 0.9))
    c.setLineWidth(0.5)
    c.setFont("Helvetica", 7)
    _set_fill(c, WHITE)
    for i in range(int(y_top) + 1):
        yy = chart_bot + (i / y_top) * chart_h
        c.line(chart_left, yy, chart_right, yy)
        c.drawRightString(chart_left - 4, yy - 2, str(i))

    n = max(len(values), 1)
    bar_w = chart_w / (n * 1.45)
    gap = bar_w * 0.45
    for i, (lab, val) in enumerate(zip(labels, values)):
        bh = (val / y_top) * chart_h if y_top else 0
        bx = chart_left + gap + i * (bar_w + gap)
        _set_fill(c, LIME)
        c.rect(bx, chart_bot, bar_w, bh, fill=1, stroke=0)
        _set_fill(c, YELLOW)
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(bx + bar_w / 2, chart_bot - 14, lab)


def _draw_pie(
    c: canvas.Canvas,
    cx: float,
    cy: float,
    r: float,
    slices: list[tuple[str, int, tuple[float, float, float]]],
) -> None:
    total = sum(v for _, v, _ in slices) or 1
    # Ángulo desde el eje +X, sentido antihorario; empezamos arriba (-90 en reportlab = 90 visual)
    angle = 90.0
    for _lab, val, color in slices:
        if val <= 0:
            continue
        sweep = 360.0 * val / total
        _set_fill(c, color)
        # Aproximar el sector con triángulos
        steps = max(8, int(abs(sweep) / 3))
        for i in range(steps):
            a0 = math.radians(angle - sweep * i / steps)
            a1 = math.radians(angle - sweep * (i + 1) / steps)
            p = c.beginPath()
            p.moveTo(cx, cy)
            p.lineTo(cx + math.cos(a0) * r, cy + math.sin(a0) * r)
            p.lineTo(cx + math.cos(a1) * r, cy + math.sin(a1) * r)
            p.close()
            c.drawPath(p, fill=1, stroke=0)
        mid = math.radians(angle - sweep / 2)
        tx = cx + math.cos(mid) * (r * 0.55)
        ty = cy + math.sin(mid) * (r * 0.55)
        _set_fill(c, (0.1, 0.1, 0.1))
        c.setFont("Helvetica-Bold", 10)
        pct = int(round(100.0 * val / total))
        c.drawCentredString(tx, ty - 3, f"{pct}%")
        angle -= sweep

    lx = cx + r + 18
    ly = cy + 28
    c.setFont("Helvetica", 9)
    for lab, _val, color in slices:
        _set_fill(c, color)
        c.rect(lx, ly, 10, 10, fill=1, stroke=0)
        _set_fill(c, WHITE)
        c.drawString(lx + 14, ly + 1, lab)
        ly -= 16


def _draw_curso_page(c: canvas.Canvas, data: dict[str, Any]) -> None:
    w, h = PAGE
    _paint_bg(c, w, h)

    _set_fill(c, LIME)
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(w / 2, h - 36, _pdf_txt(data["titulo"]))

    grupos = data["grupos"]
    total = data["total"]
    fmt = data["fmt_media"]

    headers = [""] + [g["label"] for g in grupos] + ["TOTAL"]
    n_cols = len(headers)
    left_w = w * 0.52
    x0 = 28
    y0 = h - 58
    first_col = 88
    other = (left_w - first_col) / max(n_cols - 1, 1)
    col_ws = [first_col] + [other] * (n_cols - 1)
    row_h = 18

    _rounded_table_header(c, x0, y0, col_ws, headers, row_h)
    y = y0 - row_h

    def cells_for(row_label: str, getter) -> list[str]:
        vals = [getter(g) for g in grupos]
        vals.append(getter(None))
        return [row_label] + [str(v) for v in vals]

    rows = [
        (
            "Alumnos",
            lambda g: total["alumnos"]
            if g is None
            else g["alumnos"],
            False,
        ),
        (
            "0 a 2 suspensos",
            lambda g: (
                f"{total['bucket']['0_2']} ({total['bucket_pct']['0_2']}%)"
                if g is None
                else g["bucket"]["0_2"]
            ),
            False,
        ),
        (
            "3 o 4 suspensos",
            lambda g: (
                f"{total['bucket']['3_4']} ({total['bucket_pct']['3_4']}%)"
                if g is None
                else g["bucket"]["3_4"]
            ),
            False,
        ),
        (
            "5 o más suspensos",
            lambda g: (
                f"{total['bucket']['5_mas']} ({total['bucket_pct']['5_mas']}%)"
                if g is None
                else g["bucket"]["5_mas"]
            ),
            False,
        ),
        (
            "Media suspensos",
            lambda g: (
                fmt(total["media_suspensos"])
                if g is None
                else fmt(g["media_suspensos"])
            ),
            True,
        ),
    ]
    for label, getter, hi in rows:
        cells = [label]
        for g in grupos:
            cells.append(str(getter(g)))
        cells.append(str(getter(None)))
        _table_row(c, x0, y, col_ws, cells, row_h, highlight=hi, bold=hi)
        y -= row_h

    # Tabla promoción
    y -= 22
    promo_title = "TITULACIÓN" if data.get("es_titulacion") else "PROMOCIÓN"
    promo_title = _pdf_txt(promo_title)
    promo_w = left_w * 0.72
    _set_fill(c, LIME)
    c.roundRect(x0, y - row_h, promo_w, row_h, 5, fill=1, stroke=0)
    c.rect(x0, y - row_h, promo_w, row_h / 2, fill=1, stroke=0)
    _set_fill(c, (0.05, 0.15, 0.25))
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(x0 + promo_w / 2, y - row_h + 6, promo_title)
    y -= row_h

    cat = total["categorias"]
    pct = total["categorias_pct"]
    if data.get("muestra_pil"):
        promo_rows = [
            (
                "Promoción (no PIL)"
                if not data.get("es_titulacion")
                else "Titula (no PIL)",
                f"{cat['promo']} alumnos ({pct['promo']}%)",
            ),
            ("PIL", f"{cat['pil']} alumnos ({pct['pil']}%)"),
            (
                "Repetir" if not data.get("es_titulacion") else "No titula",
                f"{cat['repetir']} alumnos ({pct['repetir']}%)",
            ),
        ]
    else:
        label_ok = "Promoción" if not data.get("es_titulacion") else "Titula"
        label_ko = "Repetir" if not data.get("es_titulacion") else "No titula"
        promo_rows = [
            (label_ok, f"{cat['promo']} alumnos ({pct['promo']}%)"),
            (label_ko, f"{cat['repetir']} alumnos ({pct['repetir']}%)"),
        ]

    col_promo = [promo_w * 0.45, promo_w * 0.55]
    for lab, val in promo_rows:
        _table_row(c, x0, y, col_promo, [lab, val], row_h)
        y -= row_h

    # Gráficos derecha
    rx = w * 0.55
    rw = w * 0.42
    bar_labels = [_pdf_txt(g["label"]).replace(" ", "") for g in grupos] + [
        _pdf_txt(data["titulo"])
    ]
    bar_vals = [g["media_suspensos"] for g in grupos] + [total["media_suspensos"]]
    ymax_override = float(data.get("chart_ymax") or 0) or None
    _draw_bar_chart(
        c,
        rx,
        h * 0.48,
        rw,
        h * 0.42,
        bar_labels,
        bar_vals,
        "Media suspensos",
        ymax=ymax_override,
    )

    pie_slices: list[tuple[str, int, tuple[float, float, float]]] = []
    if data.get("muestra_pil"):
        pie_slices = [
            ("Promoción", cat["promo"], PIE_PROMO),
            ("PIL", cat["pil"], PIE_PIL),
            ("Repetir", cat["repetir"], PIE_REP),
        ]
    else:
        pie_slices = [
            (
                "Promoción" if not data.get("es_titulacion") else "Titula",
                cat["promo"],
                PIE_PROMO,
            ),
            (
                "Repetir" if not data.get("es_titulacion") else "No titula",
                cat["repetir"],
                PIE_REP,
            ),
        ]
    _draw_pie(c, rx + 90, h * 0.28, 70, pie_slices)


def _bar_gradient(
    c: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    steps: int = 24,
) -> None:
    """Degradado vertical verde (base) → amarillo (cima)."""
    if h <= 0 or w <= 0:
        return
    steps = max(4, steps)
    for i in range(steps):
        t0 = i / steps
        t1 = (i + 1) / steps
        # interpolar verde lima → amarillo
        r = LIME[0] + (YELLOW[0] - LIME[0]) * t1
        g = LIME[1] + (YELLOW[1] - LIME[1]) * t1
        b = LIME[2] + (YELLOW[2] - LIME[2]) * t1
        _set_fill(c, (r, g, b))
        y0 = y + h * t0
        c.rect(x, y0, w, h * (t1 - t0) + 0.3, fill=1, stroke=0)


def _draw_aprobados_page(c: canvas.Canvas, data: dict[str, Any]) -> None:
    w, h = PAGE
    _paint_bg(c, w, h)

    _set_fill(c, LIME)
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(w / 2, h - 36, _pdf_txt(data["titulo"]))

    _set_fill(c, YELLOW)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(w / 2, h - 58, "Porcentaje de aprobados")

    mats = list(data.get("materias_aprobados") or [])
    if not mats:
        _set_fill(c, WHITE)
        c.setFont("Helvetica", 12)
        c.drawCentredString(w / 2, h / 2, "Sin notas de materias para este curso.")
        return

    # Área del gráfico
    left, right = 48.0, w - 48.0
    bot, top = 70.0, h - 80.0
    chart_w = right - left
    chart_h = top - bot

    # Rejilla 0–100 %
    _set_stroke(c, (0.85, 0.9, 0.95))
    c.setLineWidth(0.6)
    c.setFont("Helvetica-Bold", 8)
    _set_fill(c, YELLOW)
    for pct in range(0, 101, 10):
        yy = bot + (pct / 100.0) * chart_h
        c.line(left, yy, right, yy)
        c.drawRightString(left - 6, yy - 2, f"{pct}%")
        c.drawString(right + 6, yy - 2, f"{pct}%")

    n = len(mats)
    slot = chart_w / n
    bar_w = min(36.0, slot * 0.62)
    for i, m in enumerate(mats):
        pct = max(0, min(100, int(m.get("pct") or 0)))
        bh = (pct / 100.0) * chart_h
        bx = left + i * slot + (slot - bar_w) / 2
        _bar_gradient(c, bx, bot, bar_w, bh)
        # Etiqueta % encima (negro sobre amarillo del tope)
        _set_fill(c, (0.05, 0.08, 0.12))
        c.setFont("Helvetica-Bold", 8)
        label_y = bot + bh + 4
        if label_y > top - 2:
            label_y = top - 2
        c.drawCentredString(bx + bar_w / 2, label_y, f"{pct}%")
        # Abreviatura eje X
        _set_fill(c, YELLOW)
        c.setFont("Helvetica-Bold", 7 if n > 14 else 8)
        c.drawCentredString(bx + bar_w / 2, bot - 16, _pdf_txt(m.get("abrev") or ""))


def build_informe_curso_pdf(data: dict[str, Any]) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=PAGE)
    _draw_cover(c, data)
    c.showPage()
    _draw_curso_page(c, data)
    c.showPage()
    _draw_aprobados_page(c, data)
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Informe de grupo (landscape, pantalla)
# ---------------------------------------------------------------------------

_INK = (0.05, 0.15, 0.25)
_ROW_A = (0.96, 0.98, 1.0)
_ROW_B = (0.88, 0.93, 0.97)
_MUTED = (0.75, 0.85, 0.95)


def _grupo_cover(c: canvas.Canvas, data: dict[str, Any]) -> None:
    w, h = PAGE
    _paint_bg(c, w, h)
    from reportlab.lib.colors import Color

    band_h = 78
    band_y = h - 130
    c.setFillColor(Color(BANNER[0], BANNER[1], BANNER[2], alpha=0.55))
    c.roundRect(w * 0.22, band_y, w * 0.56, band_h, 8, fill=1, stroke=0)

    logo = _logo_path()
    if logo:
        try:
            img = ImageReader(str(logo))
            iw, ih = img.getSize()
            max_h = 58
            scale = max_h / float(ih)
            dw, dh = iw * scale, ih * scale
            c.drawImage(
                img,
                (w - dw) / 2,
                band_y + (band_h - dh) / 2,
                width=dw,
                height=dh,
                mask="auto",
            )
        except Exception:
            _set_fill(c, WHITE)
            c.setFont("Helvetica-Bold", 14)
            c.drawCentredString(w / 2, band_y + 32, "IES Antonio Garcia Bellido")

    _set_fill(c, WHITE)
    c.setFont("Helvetica", 32)
    c.drawCentredString(w / 2, h * 0.50, "INFORME RESULTADOS")
    _set_fill(c, LIME)
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(w / 2, h * 0.41, "EVALUACION FINAL")
    c.drawCentredString(
        w / 2, h * 0.33, _pdf_txt(f"{data.get('ambito_label') or 'Grupo'} {data.get('grupo') or ''}")
    )
    _set_fill(c, YELLOW)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(
        w / 2, h * 0.24, _pdf_txt(f"Curso escolar {data.get('curso_escolar') or ''}")
    )


def _grupo_section_title(
    c: canvas.Canvas,
    title: str,
    *,
    subtitle: str = "",
) -> float:
    """Título centrado estilo informe curso; devuelve Y bajo el subtítulo."""
    w, h = PAGE
    _set_fill(c, LIME)
    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(w / 2, h - 40, _pdf_txt(title))
    y = h - 64
    if subtitle:
        _set_fill(c, YELLOW)
        c.setFont("Helvetica-Bold", 13)
        c.drawCentredString(w / 2, y, _pdf_txt(subtitle))
        y -= 20
    return y


def _grupo_footer(
    c: canvas.Canvas,
    page_num: int,
    total: int,
    grupo: str,
    *,
    ambito_label: str = "Grupo",
) -> None:
    w, _h = PAGE
    _set_fill(c, _MUTED)
    c.setFont("Helvetica", 9)
    c.drawString(
        28,
        16,
        _pdf_txt(f"IES Antonio Garcia Bellido  ·  {ambito_label} {grupo}"),
    )
    c.drawRightString(w - 28, 16, f"{page_num} / {total}")


def _grupo_header_row(
    c: canvas.Canvas,
    x: float,
    y: float,
    col_ws: list[float],
    headers: list[str],
    row_h: float,
    *,
    font_size: float = 9,
) -> None:
    total_w = sum(col_ws)
    _set_fill(c, LIME)
    c.roundRect(x, y - row_h, total_w, row_h, 5, fill=1, stroke=0)
    c.rect(x, y - row_h, total_w, row_h / 2, fill=1, stroke=0)
    _set_fill(c, _INK)
    c.setFont("Helvetica-Bold", font_size)
    cx = x
    for i, (hw, lab) in enumerate(zip(col_ws, headers)):
        text = _pdf_txt(lab)
        baseline = y - row_h + (row_h - font_size) / 2 + 1
        if i == 0:
            c.drawString(cx + 8, baseline, text)
        else:
            c.drawCentredString(cx + hw / 2, baseline, text)
        cx += hw


def _grupo_data_row(
    c: canvas.Canvas,
    x: float,
    y: float,
    col_ws: list[float],
    cells: list[str],
    row_h: float,
    *,
    alt: bool = False,
    bold: bool = False,
    font_size: float = 9,
    emphasize_col: int | None = None,
    left_cols: frozenset[int] | None = None,
) -> None:
    total_w = sum(col_ws)
    left_align = left_cols if left_cols is not None else frozenset({0})
    _set_fill(c, _ROW_B if alt else _ROW_A)
    c.rect(x, y - row_h, total_w, row_h, fill=1, stroke=0)
    _set_stroke(c, (0.72, 0.80, 0.88))
    c.setLineWidth(0.35)
    c.line(x, y - row_h, x + total_w, y - row_h)
    cx = x
    baseline = y - row_h + (row_h - font_size) / 2 + 1
    for i, (hw, lab) in enumerate(zip(col_ws, cells)):
        text = _pdf_txt(lab)
        is_emph = emphasize_col is not None and i == emphasize_col
        c.setFont(
            "Helvetica-Bold" if bold or is_emph else "Helvetica",
            font_size + (0.5 if is_emph else 0),
        )
        _set_fill(c, _INK)
        if i in left_align:
            max_chars = max(12, int(hw / (font_size * 0.52)))
            if len(text) > max_chars:
                text = text[: max_chars - 1] + "..."
            c.drawString(cx + 8, baseline, text)
        else:
            c.drawCentredString(cx + hw / 2, baseline, text)
        cx += hw


def _fit_col_ws(col_ws: list[float], total: float) -> list[float]:
    s = sum(col_ws) or 1.0
    if abs(s - total) < 0.5:
        return col_ws
    return [w * total / s for w in col_ws]


def _table_row_metrics(
    n_data_rows: int,
    y_start: float,
    *,
    y_min: float = 40.0,
    min_h: float = 22.0,
    max_h: float = 34.0,
) -> tuple[float, float]:
    """Fila más alta posible para llenar la página; (row_h, font_size)."""
    avail = max(80.0, y_start - y_min)
    slots = max(n_data_rows, 1) + 1  # + cabecera
    row_h = min(max_h, max(min_h, avail / slots))
    font_size = min(14.0, max(11.0, row_h - 10.0))
    return row_h, font_size


def _draw_grupo_table_block(
    c: canvas.Canvas,
    *,
    x: float,
    y: float,
    col_ws: list[float],
    headers: list[str],
    rows: list[list[str]],
    row_h: float = 22.0,
    font_size: float = 11,
    emphasize_col: int | None = None,
    max_rows: int | None = None,
    left_cols: frozenset[int] | None = None,
) -> float:
    """Dibuja cabecera + filas; devuelve Y final. No crea páginas."""
    _grupo_header_row(c, x, y, col_ws, headers, row_h, font_size=font_size)
    y -= row_h
    shown = rows if max_rows is None else rows[:max_rows]
    if not shown:
        _set_fill(c, WHITE)
        c.setFont("Helvetica-Oblique", 12)
        c.drawString(x + 8, y - 18, "Sin datos.")
        return y - 28
    for i, cells in enumerate(shown):
        _grupo_data_row(
            c,
            x,
            y,
            col_ws,
            cells,
            row_h,
            alt=i % 2 == 1,
            font_size=font_size,
            emphasize_col=emphasize_col,
            left_cols=left_cols,
        )
        y -= row_h
    total_w = sum(col_ws)
    _set_stroke(c, LIME_DARK)
    c.setLineWidth(1.2)
    c.line(x, y, x + total_w, y)
    return y


def _chunk_rows(rows: list[list[str]], per_page: int) -> list[list[list[str]]]:
    if not rows:
        return [[]]
    return [rows[i : i + per_page] for i in range(0, len(rows), per_page)]


ALUMNOS_POR_PAGINA = 25


def _draw_ranking_chart_page(c: canvas.Canvas, data: dict[str, Any]) -> None:
    """Página con gráfico de barras del ranking (nota media por materia)."""
    w, h = PAGE
    _paint_bg(c, w, h)
    rank_data = data.get("ranking") or {}
    filas = list(rank_data.get("filas") or [])
    chart_ymax = float(rank_data.get("chart_ymax") or 0) or 10.0

    y_title = _grupo_section_title(
        c,
        "RANKING DE MATERIAS",
        subtitle="Nota media por materia",
    )

    if not filas:
        _set_fill(c, WHITE)
        c.setFont("Helvetica", 12)
        c.drawCentredString(w / 2, h / 2, "Sin calificaciones de acta en esta seleccion.")
        return

    left, right = 48.0, w - 48.0
    bot, top = 70.0, y_title - 18.0
    chart_w = right - left
    chart_h = top - bot
    y_top = max(1.0, chart_ymax)

    _set_stroke(c, (0.85, 0.9, 0.95))
    c.setLineWidth(0.6)
    c.setFont("Helvetica-Bold", 8)
    _set_fill(c, YELLOW)
    y_max_int = int(math.ceil(y_top))
    for i in range(y_max_int + 1):
        yy = bot + (i / y_top) * chart_h
        c.line(left, yy, right, yy)
        c.drawRightString(left - 6, yy - 2, str(i))

    n = len(filas)
    slot = chart_w / n
    bar_w = min(36.0, slot * 0.62)
    fs_label = 7 if n > 14 else 8
    for i, row in enumerate(filas):
        media = float(row.get("media") or 0)
        bh = (media / y_top) * chart_h if y_top else 0
        bx = left + i * slot + (slot - bar_w) / 2
        _bar_gradient(c, bx, bot, bar_w, bh)
        _set_fill(c, (0.05, 0.08, 0.12))
        c.setFont("Helvetica-Bold", fs_label)
        label_y = bot + bh + 4
        if label_y > top - 2:
            label_y = top - 2
        c.drawCentredString(
            bx + bar_w / 2,
            label_y,
            _pdf_txt(row.get("media_display") or "-"),
        )
        _set_fill(c, YELLOW)
        c.setFont("Helvetica-Bold", fs_label)
        c.drawCentredString(
            bx + bar_w / 2,
            bot - 16,
            _pdf_txt(row.get("abrev") or ""),
        )

    _set_fill(c, _MUTED)
    c.setFont("Helvetica", 9)
    c.drawCentredString(w / 2, 48, _pdf_txt(f"Escala 0-{int(y_top)}"))


def build_informe_grupo_pdf(data: dict[str, Any]) -> bytes:
    """PDF landscape profesional: portada + secciones del informe de grupo."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=PAGE)
    w, h = PAGE
    grupo = str(data.get("grupo") or "")
    ambito_label = str(data.get("ambito_label") or "Grupo")
    curso_escolar = str(data.get("curso_escolar") or "")
    margin_x = 32.0
    table_w = w - 2 * margin_x
    footer_reserve = 34.0

    # Precalcular páginas para el pie
    mats = (data.get("materias") or {}).get("filas") or []
    rank = (data.get("ranking") or {}).get("filas") or []
    comps = (data.get("competencias") or {}).get("filas") or []
    dec = data.get("decision") or {}
    alus = (data.get("alumnos") or {}).get("filas") or []

    mat_rows = [
        [
            r.get("materia") or "",
            str(r.get("sobresalientes", 0)),
            str(r.get("notables", 0)),
            str(r.get("bienes", 0)),
            str(r.get("suficientes", 0)),
            str(r.get("suspensos", 0)),
        ]
        for r in mats
    ]
    rank_rows = [
        [
            r.get("materia") or "",
            r.get("media_display") or "-",
            f"{r.get('aprobados', 0)} ({r.get('aprobados_pct', 0)}%)",
            f"{r.get('suspensos', 0)} ({r.get('suspensos_pct', 0)}%)",
        ]
        for r in rank
    ]
    comp_rows = [
        [
            f"{r.get('abreviatura') or ''}  {r.get('nombre') or ''}",
            r.get("media_display") or "-",
            (
                f"{r.get('aprobados', 0)} ({r.get('aprobados_pct', 0)}%)"
                if r.get("n")
                else "-"
            ),
            (
                f"{r.get('suspensos', 0)} ({r.get('suspensos_pct', 0)}%)"
                if r.get("n")
                else "-"
            ),
        ]
        for r in comps
    ]
    dec_rows = [
        [
            r.get("label") or "",
            str(r.get("n", 0)),
            f"{r.get('pct', 0)}%",
        ]
        for r in (dec.get("filas") or [])
    ]
    tiene_grupo_col = any((x.get("grupo") or "").strip() for x in alus)
    alu_rows = []
    for i, r in enumerate(alus):
        row = [str(i + 1)]
        if tiene_grupo_col:
            row.append(r.get("grupo") or "")
        row.extend(
            [
                r.get("alumno") or "",
                r.get("media_comp_display") or "-",
                r.get("media_mat_display") or "-",
                r.get("competencias_resumen") or "",
                r.get("materias_resumen") or "",
                r.get("decision") or "-",
            ]
        )
        alu_rows.append(row)

    alu_chunks = _chunk_rows(alu_rows, ALUMNOS_POR_PAGINA)

    # Páginas: portada + materias + ranking tabla + ranking gráfico + (comp+dec) + alumnos…
    total_pages = 1 + 1 + 1 + 1 + 1 + max(len(alu_chunks), 1)
    page_num = 0

    def finish_page() -> None:
        nonlocal page_num
        page_num += 1
        _grupo_footer(c, page_num, total_pages, grupo, ambito_label=ambito_label)

    # --- Portada ---
    _grupo_cover(c, data)
    finish_page()
    c.showPage()

    # --- Materias ---
    _paint_bg(c, w, h)
    y = _grupo_section_title(
        c,
        "MATERIAS",
        subtitle=(
            f"Distribucion de calificaciones de acta  ·  "
            f"{(data.get('materias') or {}).get('n_alumnos', 0)} alumnos"
        ),
    )
    col_m = _fit_col_ws([340, 70, 70, 70, 70, 90], table_w)
    rh, fs = _table_row_metrics(len(mat_rows), y, y_min=footer_reserve + 8)
    _draw_grupo_table_block(
        c,
        x=margin_x,
        y=y,
        col_ws=col_m,
        headers=["Materia", "SB", "NT", "BI", "SU", "Suspensos"],
        rows=mat_rows,
        row_h=rh,
        font_size=fs,
    )
    finish_page()
    c.showPage()

    # --- Ranking ---
    _paint_bg(c, w, h)
    y = _grupo_section_title(
        c,
        "RANKING DE MATERIAS",
        subtitle="Ordenadas por nota media de acta",
    )
    col_r = _fit_col_ws([360, 100, 140, 140], table_w)
    rh, fs = _table_row_metrics(len(rank_rows), y, y_min=footer_reserve + 8)
    _draw_grupo_table_block(
        c,
        x=margin_x,
        y=y,
        col_ws=col_r,
        headers=["Materia", "Nota media", "Aprobados", "Suspensos"],
        rows=rank_rows,
        row_h=rh,
        font_size=fs,
        emphasize_col=1,
    )
    finish_page()
    c.showPage()

    # --- Ranking (gráfico) ---
    _draw_ranking_chart_page(c, data)
    finish_page()
    c.showPage()

    # --- Competencias + Decisión (misma página) ---
    _paint_bg(c, w, h)
    y = _grupo_section_title(
        c,
        "COMPETENCIAS Y DECISION",
        subtitle="Competencias clave LOMLOE  ·  Decisiones finales de evaluacion",
    )
    _set_fill(c, YELLOW)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(margin_x, y, "Competencias clave")
    y -= 8
    col_c = _fit_col_ws([380, 90, 120, 120], table_w)
    # Reservar espacio inferior para bloque decisión (~160 pt)
    rh_c, fs_c = _table_row_metrics(
        len(comp_rows), y, y_min=footer_reserve + 170, min_h=20, max_h=28
    )
    y = _draw_grupo_table_block(
        c,
        x=margin_x,
        y=y,
        col_ws=col_c,
        headers=["Competencia", "Media", "Aprobados", "Suspensos"],
        rows=comp_rows,
        row_h=rh_c,
        font_size=fs_c,
        emphasize_col=1,
    )

    y -= 26
    bloque = dec.get("titulo_bloque") or "Promocion"
    _set_fill(c, YELLOW)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(
        margin_x,
        y,
        _pdf_txt(
            f"Decision · {bloque}  ({dec.get('n_con_decision', 0)} con decision)"
        ),
    )
    y -= 8

    left_w = table_w * 0.52
    col_d = _fit_col_ws([220, 90, 90], left_w)
    rh_d, fs_d = _table_row_metrics(
        len(dec_rows), y, y_min=footer_reserve + 8, min_h=24, max_h=32
    )
    y_table = _draw_grupo_table_block(
        c,
        x=margin_x,
        y=y,
        col_ws=col_d,
        headers=["Decision", "Alumnos", "%"],
        rows=dec_rows,
        row_h=rh_d,
        font_size=fs_d,
    )

    pie_slices: list[tuple[str, int, tuple[float, float, float]]] = []
    # Color fijo por tipo de decisión (no por índice: al omitir ceros se mezclaban).
    color_by_key = {
        "promo": PIE_PROMO,
        "excepcional": PIE_EXC,
        "pil": PIE_PIL,
        "repetir": PIE_REP,
    }
    for r in dec.get("filas") or []:
        n = int(r.get("n") or 0)
        if n <= 0:
            continue
        key = str(r.get("key") or "").strip().lower()
        color = color_by_key.get(key) or PIE_PROMO
        pie_slices.append((_pdf_txt(r.get("label") or ""), n, color))
    if pie_slices:
        _draw_pie(c, margin_x + left_w + 120, y_table + 50, 64, pie_slices)

    finish_page()
    c.showPage()

    # --- Alumnos: exactamente 25 por página ---
    if tiene_grupo_col:
        col_a = _fit_col_ws([28, 48, 220, 68, 68, 58, 58, 140], table_w)
        headers_a = [
            "#",
            "Grupo",
            "Alumno",
            "Media CC",
            "Media mat.",
            "Comp.",
            "Materias",
            "Decision",
        ]
        left_a = frozenset({0, 1, 2})
        emph_a = 3
    else:
        col_a = _fit_col_ws([32, 250, 72, 72, 64, 64, 156], table_w)
        headers_a = [
            "#",
            "Alumno",
            "Media CC",
            "Media mat.",
            "Comp.",
            "Materias",
            "Decision",
        ]
        left_a = frozenset({0, 1})
        emph_a = 2
    n_alu = len(alus)
    for ci, chunk in enumerate(alu_chunks or [[]]):
        _paint_bg(c, w, h)
        sub = (
            f"Ordenados por media de competencias  ·  {n_alu} alumnos"
            if len(alu_chunks) <= 1
            else (
                f"Ordenados por media de competencias  ·  "
                f"{n_alu} alumnos  ·  hoja {ci + 1}/{len(alu_chunks)}"
            )
        )
        y = _grupo_section_title(c, "ALUMNOS", subtitle=sub)
        # Altura uniforme para cabecera + 25 filas en el hueco disponible
        avail = y - (footer_reserve + 6)
        alu_row_h = avail / (ALUMNOS_POR_PAGINA + 1)
        alu_font = min(12.0, max(9.5, alu_row_h - 7.0))
        _draw_grupo_table_block(
            c,
            x=margin_x,
            y=y,
            col_ws=col_a,
            headers=headers_a,
            rows=chunk,
            row_h=alu_row_h,
            font_size=alu_font,
            emphasize_col=emph_a,
            left_cols=left_a,
        )
        finish_page()
        if ci < len(alu_chunks) - 1:
            c.showPage()

    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Informe etapa · suspensos / grupo
# ---------------------------------------------------------------------------


def _draw_etapa_suspensos_grupo_page(
    c: canvas.Canvas,
    block: dict[str, Any],
    *,
    title: str,
    subtitle: str,
    etapa_label: str,
    page_num: int,
    total_pages: int,
    curso_escolar: str = "",
) -> None:
    """Tabla (alumnos + media) y gráfico de barras de media de suspensos."""
    w, h = PAGE
    _paint_bg(c, w, h)

    _set_fill(c, LIME)
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(w / 2, h - 34, _pdf_txt(title))
    _set_fill(c, YELLOW)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(w / 2, h - 52, _pdf_txt(subtitle))
    if curso_escolar:
        _set_fill(c, WHITE)
        c.setFont("Helvetica", 9)
        c.drawCentredString(
            w / 2, h - 66, _pdf_txt(f"Curso escolar {curso_escolar}")
        )

    grupos = list(block.get("grupos_curso") or [])
    stats = list(block.get("stats") or [])
    total = block.get("total") or {}
    headers = [""] + [_pdf_txt(g) for g in grupos] + ["TOTAL"]
    n_cols = len(headers)
    margin_x = 24.0
    table_w = w - 2 * margin_x
    first_col = 110.0
    other = (table_w - first_col) / max(n_cols - 1, 1)
    col_ws = [first_col] + [other] * (n_cols - 1)
    fs = 9.0 if n_cols <= 10 else (7.0 if n_cols <= 16 else 6.0)
    row_h = 20.0 if n_cols <= 12 else 18.0
    y0 = h - 82

    def _row_cells(label: str, values: list[str], total_val: str) -> list[str]:
        return [label] + values + [total_val]

    alumnos_vals = [str(int(s.get("alumnos") or 0)) for s in stats]
    media_vals = [str(s.get("media_display") or "-") for s in stats]
    rows = [
        _row_cells("Alumnos", alumnos_vals, str(int(total.get("alumnos") or 0))),
        _row_cells(
            "Media suspensos",
            media_vals,
            str(total.get("media_display") or "-"),
        ),
    ]

    _grupo_header_row(c, margin_x, y0, col_ws, headers, row_h, font_size=fs)
    y = y0 - row_h
    for ri, cells in enumerate(rows):
        _grupo_data_row(
            c,
            margin_x,
            y,
            col_ws,
            cells,
            row_h,
            alt=ri % 2 == 1,
            bold=(ri == 1),
            font_size=fs,
            emphasize_col=None if ri == 0 else None,
            left_cols=frozenset({0}),
        )
        y -= row_h

    chart_h = max(120.0, y - 58)
    labels = [_pdf_txt(g) for g in grupos] + ["TOTAL"]
    values = [float(s.get("media") or 0) for s in stats] + [
        float(total.get("media") or 0)
    ]
    displays = [str(s.get("media_display") or "") for s in stats] + [
        str(total.get("media_display") or "")
    ]
    ymax = float(block.get("chart_ymax") or 0) or None
    _draw_bar_chart(
        c,
        margin_x,
        40,
        table_w,
        chart_h,
        labels,
        values,
        "Media de suspensos",
        ymax=ymax,
    )
    chart_bot = 40 + 28
    chart_left = margin_x + 28
    chart_right = margin_x + table_w - 10
    chart_inner_h = (40 + chart_h - 22) - chart_bot
    chart_inner_w = chart_right - chart_left
    y_top = float(ymax) if ymax else max(8.0, math.ceil(max(values) if values else 8.0))
    n = max(len(values), 1)
    bar_w = chart_inner_w / (n * 1.45)
    gap = bar_w * 0.45
    c.setFont("Helvetica-Bold", 7)
    _set_fill(c, YELLOW)
    for i, (val, disp) in enumerate(zip(values, displays)):
        bh = (val / y_top) * chart_inner_h if y_top else 0
        bx = chart_left + gap + i * (bar_w + gap)
        if disp:
            c.drawCentredString(bx + bar_w / 2, chart_bot + bh + 3, _pdf_txt(disp))

    _grupo_footer(
        c,
        page_num,
        total_pages,
        etapa_label,
        ambito_label="Etapa",
    )


def build_informe_etapa_suspensos_grupo_pdf(data: dict[str, Any]) -> bytes:
    """PDF de la vista etapa · Suspensos/grupo (por grupos y por cursos)."""
    etapa_label = _pdf_txt(data.get("grupo") or "Etapa")
    curso_escolar = str(data.get("curso_escolar") or "").strip()
    if not curso_escolar:
        try:
            from competencias.informes_data import _school_year_short

            curso_escolar = _school_year_short()
        except Exception:
            curso_escolar = ""
    pages: list[tuple[str, str, dict[str, Any]]] = [
        (
            f"SUSPENSOS / GRUPO  ·  {etapa_label}",
            "Media de materias suspensas por grupo",
            data,
        )
    ]
    por_curso = data.get("por_curso")
    if isinstance(por_curso, dict) and int(por_curso.get("n_alumnos") or 0) > 0:
        pages.append(
            (
                f"SUSPENSOS / GRUPO  ·  {etapa_label}",
                "Media de materias suspensas por curso",
                por_curso,
            )
        )

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=PAGE)
    total_pages = len(pages)
    for i, (title, subtitle, block) in enumerate(pages, start=1):
        if i > 1:
            c.showPage()
        _draw_etapa_suspensos_grupo_page(
            c,
            block,
            title=title,
            subtitle=subtitle,
            etapa_label=etapa_label,
            page_num=i,
            total_pages=total_pages,
            curso_escolar=curso_escolar,
        )
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Informe de centro (claustro): concatena grupos + cursos + etapas
# ---------------------------------------------------------------------------


def _pdf_section_divider(title: str, subtitle: str = "") -> bytes:
    """Portada de sección (Grupos / Cursos / Etapas) para el PDF de centro."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=PAGE)
    w, h = PAGE
    _paint_bg(c, w, h)
    _set_fill(c, WHITE)
    c.setFont("Helvetica", 18)
    c.drawCentredString(w / 2, h * 0.58, "INFORME DE CENTRO  ·  CLAUSTRO")
    _set_fill(c, LIME)
    c.setFont("Helvetica-Bold", 36)
    c.drawCentredString(w / 2, h * 0.46, _pdf_txt(title))
    if subtitle:
        _set_fill(c, YELLOW)
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(w / 2, h * 0.36, _pdf_txt(subtitle))
    c.save()
    return buf.getvalue()


def _merge_pdf_bytes(parts: list[bytes]) -> bytes:
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for raw in parts:
        if not raw:
            continue
        reader = PdfReader(BytesIO(raw))
        for page in reader.pages:
            writer.add_page(page)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def build_informe_centro_pdf(*, include_grupos: bool = True) -> bytes:
    """PDF claustro: (grupos opcional) + cursos + etapas, desde caché."""
    from db.competencias_informes_cache import get_informe_cache, list_informe_cache_sels
    from utils.text import normalize_for_sort

    parts: list[bytes] = []
    n_content = 0

    if include_grupos:
        grupos = sorted(
            list_informe_cache_sels(ambito="grupo", vista="completo"),
            key=normalize_for_sort,
        )
        grupo_pdfs: list[bytes] = []
        for sel in grupos:
            data, _ = get_informe_cache(ambito="grupo", sel=sel, vista="completo")
            if data is None:
                continue
            grupo_pdfs.append(build_informe_grupo_pdf(data))
        if grupo_pdfs:
            parts.append(
                _pdf_section_divider(
                    "I. GRUPOS",
                    f"{len(grupo_pdfs)} informe{'s' if len(grupo_pdfs) != 1 else ''} de grupo",
                )
            )
            parts.extend(grupo_pdfs)
            n_content += len(grupo_pdfs)

    def _curso_key(sel: str) -> tuple[int, int]:
        raw = (sel or "").strip().lower()
        etapa, _, num_s = raw.partition(":")
        try:
            num = int(num_s)
        except ValueError:
            num = 99
        return (0 if etapa == "eso" else 1, num)

    curso_sels = sorted(
        list_informe_cache_sels(ambito="curso", vista="completo"),
        key=_curso_key,
    )
    curso_pdfs: list[bytes] = []
    for sel in curso_sels:
        data, _ = get_informe_cache(ambito="curso", sel=sel, vista="completo")
        if data is None:
            continue
        curso_pdfs.append(build_informe_grupo_pdf(data))
    if curso_pdfs:
        parts.append(
            _pdf_section_divider(
                "II. CURSOS" if include_grupos else "I. CURSOS",
                f"{len(curso_pdfs)} informe{'s' if len(curso_pdfs) != 1 else ''} de curso",
            )
        )
        parts.extend(curso_pdfs)
        n_content += len(curso_pdfs)

    etapa_pdfs: list[bytes] = []
    for sel in ("eso", "bachillerato"):
        data, _ = get_informe_cache(
            ambito="etapa", sel=sel, vista="suspensos_grupo"
        )
        if data is None:
            continue
        etapa_pdfs.append(build_informe_etapa_suspensos_grupo_pdf(data))
    if etapa_pdfs:
        parts.append(
            _pdf_section_divider(
                "III. ETAPAS" if include_grupos else "II. ETAPAS",
                "Suspensos / grupo por etapa",
            )
        )
        parts.extend(etapa_pdfs)
        n_content += len(etapa_pdfs)

    if n_content == 0 or not parts:
        raise ValueError(
            "No hay datos precalculados para el informe de centro. "
            "Pulsa Calculadora en Informes."
        )
    return _merge_pdf_bytes(parts)
