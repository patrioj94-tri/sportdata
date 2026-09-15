"""Generación del informe semanal en PDF."""
import os
import re
from io import BytesIO
from xml.sax.saxutils import escape

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.image as mpimg
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from datetime import timedelta

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image

from formatting import format_hours_minutes, weekly_totals_by_sport, translate_sport, translate_feeling, SPORT_COLORS, SPORT_EMOJIS
from translations import t

BRAND_ORANGE = colors.HexColor('#fc4c02')
INK = colors.HexColor('#181614')
INK_SOFT = colors.HexColor('#6f6763')
LINE = colors.HexColor('#e6e0da')
SURFACE = colors.HexColor('#f8f6f3')

# --- EMOJIS COMO IMÁGENES ---
# Las fuentes estándar de PDF no saben dibujar emojis, así que se insertan como pequeñas
# imágenes (Twemoji, CC-BY 4.0; ver assets/emoji/LICENSE.txt). En un Paragraph de reportlab
# se hace con la etiqueta <img>, y en las figuras de matplotlib con OffsetImage.
EMOJI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'emoji')

_EMOJI_RE = re.compile(
    "([\U0001F300-\U0001FAFF☀-➿⭐⭕⏰-⏿❤✅❔]"
    "️?(?:‍[\U0001F300-\U0001FAFF☀-➿♀♂]️?)*)"
)


def _emoji_path(char):
    full = "-".join(f"{ord(c):x}" for c in char)
    stripped = "-".join(f"{ord(c):x}" for c in char if ord(c) != 0xFE0F)
    for code in (full, stripped):
        path = os.path.join(EMOJI_DIR, code + ".png")
        if os.path.exists(path):
            return path
    return None


def emojify(text, size=11):
    """Texto listo para un Paragraph: escapa el XML y convierte cada emoji en una imagen inline."""
    if text is None:
        return ""
    out = []
    for i, part in enumerate(_EMOJI_RE.split(str(text))):
        if i % 2 == 1:
            path = _emoji_path(part)
            out.append(f'<img src="{path}" width="{size}" height="{size}" valign="-2"/>' if path else escape(part))
        else:
            out.append(escape(part))
    return "".join(out)


def _mpl_emoji(ax, char, x, y, zoom=0.6):
    """Coloca un emoji (como imagen) en unas coordenadas de datos de un eje de matplotlib."""
    path = _emoji_path(char)
    if not path:
        return
    img = mpimg.imread(path)
    ax.add_artist(AnnotationBbox(OffsetImage(img, zoom=zoom), (x, y), frameon=False, xycoords='data'))


# --- ESTILOS ---
_styles = getSampleStyleSheet()
STYLE_TITLE = ParagraphStyle('T', parent=_styles['Heading1'], fontSize=24, leading=30, textColor=BRAND_ORANGE, alignment=1, spaceAfter=2)
STYLE_SUB = ParagraphStyle('S', parent=_styles['Normal'], fontSize=11, textColor=INK_SOFT, alignment=1, spaceAfter=4)
STYLE_H2 = ParagraphStyle('H2', parent=_styles['Heading2'], fontSize=14, leading=20, textColor=INK, spaceBefore=6, spaceAfter=6, keepWithNext=1)
STYLE_BODY = ParagraphStyle('B', parent=_styles['Normal'], fontSize=9.5, leading=14, textColor=INK)
STYLE_MUTED = ParagraphStyle('M', parent=STYLE_BODY, textColor=INK_SOFT)
STYLE_CARD_TITLE = ParagraphStyle('CT', parent=STYLE_BODY, fontSize=10.5, leading=15)
STYLE_CHIP = ParagraphStyle('C', parent=STYLE_BODY, fontSize=8, leading=10, textColor=colors.white, alignment=1)
STYLE_CELL = ParagraphStyle('Cell', parent=STYLE_BODY, alignment=1)
STYLE_CELL_HEAD = ParagraphStyle('CellH', parent=STYLE_CELL, textColor=colors.white, fontName='Helvetica-Bold')


def _h2(text):
    return Paragraph(emojify(text, size=14), STYLE_H2)


# --- FIGURAS ---
def _daily_distance_chart(df_week, selected_monday):
    """Barras con la distancia diaria de la semana, como imagen PNG."""
    days = [selected_monday + timedelta(days=i) for i in range(7)]
    daily_km = []
    for day in days:
        if df_week.empty:
            daily_km.append(0)
        else:
            day_df = df_week[df_week['Date'] == day]
            daily_km.append(day_df['Distance_km'].sum() if len(day_df) else 0)

    fig, ax = plt.subplots(figsize=(6.2, 1.8), dpi=150)
    ax.bar([d.strftime('%a') for d in days], daily_km, color='#fc4c02', width=0.6)
    ax.set_ylabel('km', fontsize=8, color='#6f6763')
    ax.set_title(t('pdf_daily_distance'), fontsize=10, color='#333333')
    for side in ('top', 'right', 'left'):
        ax.spines[side].set_visible(False)
    ax.spines['bottom'].set_color('#e6e0da')
    ax.tick_params(labelsize=8, colors='#6f6763', length=0)
    ax.grid(axis='y', color='#eeeae6', linewidth=0.8)
    ax.set_axisbelow(True)
    fig.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format='png')
    plt.close(fig)
    buf.seek(0)
    return buf


def _week_hero_image(overall, overall_prev, totals_by_sport, sports):
    """Los 3 grandes números de la semana (con su emoji y flecha de variación) y un donut
    con el reparto del tiempo por disciplina."""
    fig = plt.figure(figsize=(7.0, 2.5), dpi=150)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.6, 1])

    tiles_ax = fig.add_subplot(gs[0, 0])
    tiles_ax.axis('off')
    tiles_ax.set_xlim(0, 3)
    tiles_ax.set_ylim(0, 1)

    tiles = [
        ('🔥', t('pdf_distance'), f"{overall['km']:.1f} km", overall['km'] - overall_prev['km'], 'km'),
        ('⏱️', t('pdf_time'), format_hours_minutes(overall['minutes'] / 60), (overall['minutes'] - overall_prev['minutes']) / 60, 'h'),
        ('🎉', t('pdf_workouts'), str(overall['sessions']), overall['sessions'] - overall_prev['sessions'], ''),
    ]
    for i, (emoji, label, value, delta, unit) in enumerate(tiles):
        x0 = i + 0.06
        tiles_ax.add_patch(mpatches.FancyBboxPatch(
            (x0, 0.04), 0.88, 0.92, boxstyle="round,pad=0.02,rounding_size=0.07",
            linewidth=0, facecolor='#fff6f0'))
        cx = x0 + 0.44
        _mpl_emoji(tiles_ax, emoji, cx, 0.80, zoom=0.5)
        tiles_ax.text(cx, 0.52, value, ha='center', va='center', fontsize=16, fontweight='bold', color='#181614')
        tiles_ax.text(cx, 0.34, label, ha='center', va='center', fontsize=7.5, color='#767676')
        if delta > 0.05:
            arrow, dcolor = '▲', '#22c55e'
        elif delta < -0.05:
            arrow, dcolor = '▼', '#ef4444'
        else:
            arrow, dcolor = '→', '#767676'
        delta_text = f"{arrow} {delta:+.1f}{unit}" if unit else f"{arrow} {delta:+d}"
        tiles_ax.text(cx, 0.16, delta_text, ha='center', va='center', fontsize=8.5, fontweight='bold', color=dcolor)

    donut_ax = fig.add_subplot(gs[0, 1])
    active = {s: totals_by_sport[s]['minutes'] for s in sports if totals_by_sport[s]['sessions'] > 0}
    if active:
        wedge_colors = [SPORT_COLORS.get(s, '#fc4c02') for s in active]
        wedges, _ = donut_ax.pie(list(active.values()), colors=wedge_colors, startangle=90, wedgeprops=dict(width=0.42))
        donut_ax.legend(wedges, [translate_sport(s) for s in active], loc='center left', bbox_to_anchor=(1.02, 0.5), fontsize=7.5, frameon=False)
        donut_ax.set_title(t('pdf_time_by_discipline'), fontsize=8.5, color='#333333')
    else:
        donut_ax.axis('off')
        donut_ax.text(0.5, 0.5, t('pdf_no_workouts'), ha='center', va='center', fontsize=8, color='#767676')

    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf


# --- BLOQUES DEL PDF ---
def _header_footer(canvas, doc):
    canvas.saveState()
    page_w, page_h = doc.pagesize
    canvas.setFillColor(BRAND_ORANGE)
    canvas.rect(0, page_h - 0.55 * inch, page_w, 0.55 * inch, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont('Helvetica-Bold', 13)
    brand = "PATRI'S DATA LAB"
    canvas.drawString(0.5 * inch, page_h - 0.37 * inch, brand)
    x = 0.5 * inch + canvas.stringWidth(brand, 'Helvetica-Bold', 13) + 0.15 * inch
    for emoji in ('🏊‍♀️', '🚴‍♀️', '🏃‍♀️'):
        path = _emoji_path(emoji)
        if path:
            canvas.drawImage(path, x, page_h - 0.44 * inch, 0.22 * inch, 0.22 * inch, mask='auto')
            x += 0.28 * inch
    canvas.setFont('Helvetica', 9)
    canvas.setFillColor(colors.HexColor('#888888'))
    canvas.drawRightString(page_w - 0.5 * inch, 0.35 * inch, f"{t('pdf_page')} {doc.page}")
    canvas.restoreState()


def _soft_table(rows, col_widths, header_bg=BRAND_ORANGE, first_col_colors=None):
    """Tabla sin rejilla negra: cabecera de color, filas suaves y líneas finas claras."""
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), header_bg),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LINEBELOW', (0, 1), (-1, -1), 0.6, LINE),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
    ]
    for i in range(1, len(rows)):
        if i % 2 == 0:
            style.append(('BACKGROUND', (0, i), (-1, i), SURFACE))
    if first_col_colors:
        for i, hexcolor in enumerate(first_col_colors):
            if hexcolor:
                style.append(('BACKGROUND', (0, i), (0, i), colors.HexColor(hexcolor)))
    table.setStyle(TableStyle(style))
    return table


def _sport_chip(sport):
    """Chip de color con el emoji y el nombre de la disciplina."""
    label = f"{emojify(SPORT_EMOJIS.get(sport, '⚡'), size=10)} <b>{escape(translate_sport(sport).upper())}</b>"
    chip = Table([[Paragraph(label, STYLE_CHIP)]], colWidths=[1.3 * inch], rowHeights=[0.26 * inch])
    chip.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(SPORT_COLORS.get(sport, '#fc4c02'))),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROUNDEDCORNERS', [5, 5, 5, 5]),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    return chip


def _activity_card(entry):
    accent = colors.HexColor(entry['card_color'])

    title_md = f"<b>{emojify(entry['activity_name'])}</b> <font color='#6f6763'>· {escape(entry['date'].strftime('%a %d %b'))}</font>"
    header_row = Table([[_sport_chip(entry['sport']), Paragraph(title_md, STYLE_CARD_TITLE)]], colWidths=[1.4 * inch, 4.85 * inch])
    header_row.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    if entry['show_time']:
        stats = f"{escape(entry['headline_value'])} {escape(entry['headline_unit'])} · ⏱️ {escape(entry['time_hms'])} · {escape(entry['pace_speed'])}"
    else:
        stats = f"⏱️ {escape(entry['headline_value'])}"
    stats += f" · 🏷️ {escape(entry['training_type'])}"

    hr = entry['avg_hr'] if entry['avg_hr'] else '—'
    cal = entry['calories'] if entry['calories'] else '—'
    rpe = entry['rpe'] if entry['rpe'] else '—'
    feeling = translate_feeling(entry['feeling'])
    detail = f"❤️ {hr} bpm · 🔥 {cal} kcal · 📊 RPE {rpe}/10 · 🎭 {feeling}"

    content = [
        header_row,
        Spacer(1, 5),
        Paragraph(emojify(stats, size=10), STYLE_BODY),
        Paragraph(emojify(detail, size=10), STYLE_MUTED),
    ]
    if entry['comment']:
        content.append(Spacer(1, 3))
        content.append(Paragraph(emojify(f"💬 {entry['comment']}", size=10), ParagraphStyle('Q', parent=STYLE_BODY, fontName='Helvetica-Oblique')))

    card = Table([[content]], colWidths=[6.5 * inch])
    card.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), SURFACE),
        ('LINEBEFORE', (0, 0), (0, -1), 5, accent),
        ('ROUNDEDCORNERS', [8, 8, 8, 8]),
        ('LEFTPADDING', (0, 0), (-1, -1), 14),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    return card


def _discipline_comparison_table(totals_by_sport, prev_totals_by_sport, sports):
    header = [Paragraph(escape(h), STYLE_CELL_HEAD) for h in (t('pdf_discipline'), t('pdf_this_week'), t('pdf_prev_week'), t('pdf_difference'))]
    rows = [header]
    first_col_colors = [None]
    for sport in sports:
        cur = totals_by_sport.get(sport, {'km': 0.0, 'minutes': 0.0})
        prev = prev_totals_by_sport.get(sport, {'km': 0.0, 'minutes': 0.0})
        if sport == 'Fuerza':
            vals = (format_hours_minutes(cur['minutes'] / 60), format_hours_minutes(prev['minutes'] / 60), f"{(cur['minutes'] - prev['minutes']) / 60:+.1f} h")
        elif sport == 'Natación':
            vals = (f"{cur['km'] * 1000:.0f} m", f"{prev['km'] * 1000:.0f} m", f"{(cur['km'] - prev['km']) * 1000:+.0f} m")
        else:
            vals = (f"{cur['km']:.1f} km", f"{prev['km']:.1f} km", f"{cur['km'] - prev['km']:+.1f} km")
        name_cell = Paragraph(f"{emojify(SPORT_EMOJIS.get(sport, '⚡'), size=10)} <b>{escape(translate_sport(sport))}</b>", STYLE_CELL_HEAD)
        rows.append([name_cell] + [Paragraph(escape(v), STYLE_CELL) for v in vals])
        first_col_colors.append(SPORT_COLORS.get(sport, '#fc4c02'))

    return _soft_table(rows, [1.6 * inch, 1.6 * inch, 1.6 * inch, 1.2 * inch], header_bg=INK, first_col_colors=first_col_colors)


def build_weekly_report_pdf(workout_entries, df_week, sleep_info, sports, selected_monday, week_end,
                             health_comment=None, readiness=None, status_label=None, status_explanation=None,
                             prev_totals_by_sport=None, overall=None, overall_prev=None):
    """Construye el PDF del informe semanal y devuelve un BytesIO listo para descargar.
    workout_entries ya trae el RPE/sensación/comentario tal como los haya editado el usuario."""
    readiness = readiness or {}
    prev_totals_by_sport = prev_totals_by_sport or {s: {'km': 0.0, 'sessions': 0, 'minutes': 0.0} for s in sports}
    overall = overall or {'km': 0.0, 'sessions': 0, 'minutes': 0.0}
    overall_prev = overall_prev or {'km': 0.0, 'sessions': 0, 'minutes': 0.0}
    totals_by_sport = weekly_totals_by_sport(df_week, sports)

    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=A4, topMargin=0.9 * inch, bottomMargin=0.7 * inch)
    story = []

    story.append(Paragraph(emojify(f"🎉 {t('pdf_title')}", size=22), STYLE_TITLE))
    period_text = f"📅 {selected_monday.strftime('%A, %B %d')} → {week_end.strftime('%A, %B %d, %Y')}"
    story.append(Paragraph(emojify(period_text, size=11), STYLE_SUB))
    story.append(Spacer(1, 0.15 * inch))

    # Infografía: los 3 grandes números de la semana + donut por disciplina
    story.append(Image(_week_hero_image(overall, overall_prev, totals_by_sport, sports), width=7.0 * inch, height=2.5 * inch))
    story.append(Spacer(1, 0.1 * inch))

    # Gráfico de distancia diaria
    story.append(Image(_daily_distance_chart(df_week, selected_monday), width=6.2 * inch, height=1.8 * inch))
    story.append(Spacer(1, 0.2 * inch))

    # Training Readiness / Status
    if readiness.get('score') or status_label:
        story.append(_h2(f"🎯 {t('pdf_form_state')}"))
        lines = []
        if readiness.get('score'):
            lines.append(f"{t('pdf_readiness')}: <b>{readiness.get('score')}/100</b>")
        if status_label:
            lines.append(f"{t('pdf_status')}: <b>{emojify(status_label)}</b>")
        if status_explanation:
            lines.append(escape(status_explanation))
        feedback = readiness.get('feedbackLong') or readiness.get('feedbackShort')
        if feedback:
            lines.append(f"<font color='#6f6763'>{escape(feedback)}</font>")
        story.append(Paragraph("<br/>".join(lines), STYLE_BODY))
        story.append(Spacer(1, 0.2 * inch))

    # Comentario de la semana (editado por el usuario)
    if health_comment:
        story.append(_h2(f"💬 {t('pdf_week_comment')}"))
        story.append(Paragraph(emojify(health_comment), ParagraphStyle('HC', parent=STYLE_BODY, fontName='Helvetica-Oblique')))
        story.append(Spacer(1, 0.2 * inch))

    # Sueño
    if sleep_info and sleep_info.get('Total_Hours', 0) > 0:
        story.append(_h2(f"😴 {t('pdf_sleep')}"))
        sleep_rows = [
            [Paragraph(emojify(f"😴 {t('pdf_avg_sleep')}", size=10), STYLE_CELL_HEAD),
             Paragraph(escape(format_hours_minutes(sleep_info.get('Total_Hours', 0))), STYLE_CELL)],
            [Paragraph(emojify(f"⭐ {t('sleep_score')}", size=10), STYLE_CELL_HEAD),
             Paragraph(f"{escape(str(sleep_info.get('Score', 'N/A')))}/100", STYLE_CELL)],
        ]
        sleep_table = Table(sleep_rows, colWidths=[2.6 * inch, 2.0 * inch])
        sleep_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), INK),
            ('BACKGROUND', (1, 0), (1, -1), SURFACE),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LINEBELOW', (0, 0), (-1, -2), 0.6, colors.white),
            ('ROUNDEDCORNERS', [6, 6, 6, 6]),
        ]))
        story.append(sleep_table)
        story.append(Spacer(1, 0.25 * inch))

    story.append(_h2(f"🏅 {t('pdf_comparison')}"))
    story.append(_discipline_comparison_table(totals_by_sport, prev_totals_by_sport, sports))
    story.append(Spacer(1, 0.3 * inch))

    story.append(_h2(f"🎯 {t('pdf_your_workouts')}"))
    story.append(Spacer(1, 0.05 * inch))
    for entry in workout_entries:
        story.append(_activity_card(entry))
        story.append(Spacer(1, 0.12 * inch))

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    pdf_buffer.seek(0)
    return pdf_buffer
