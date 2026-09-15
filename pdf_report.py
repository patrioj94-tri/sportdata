"""Generación del informe semanal en PDF."""
from io import BytesIO

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from datetime import timedelta

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image

from formatting import format_hours_minutes, weekly_totals_by_sport, translate_sport, SPORT_COLORS
from translations import t

BRAND_ORANGE = colors.HexColor('#fc4c02')

# Nota sobre iconos: reportlab (con las fuentes estándar Helvetica) no sabe dibujar emoji,
# así que en el PDF el color hace el trabajo que en la web hacen los iconos: cada deporte
# tiene su propia "chip" de color (ver SPORT_COLORS), y la intensidad del entreno se ve en
# la barra de color de cada tarjeta.


def _daily_distance_chart(df_week, selected_monday):
    """Gráfico de barras con la distancia diaria de la semana, como imagen PNG."""
    days = [selected_monday + timedelta(days=i) for i in range(7)]
    daily_km = []
    for day in days:
        if df_week.empty:
            daily_km.append(0)
        else:
            day_df = df_week[df_week['Date'] == day]
            daily_km.append(day_df['Distance_km'].sum() if len(day_df) else 0)

    fig, ax = plt.subplots(figsize=(6.2, 1.8), dpi=150)
    ax.bar([d.strftime('%a') for d in days], daily_km, color='#fc4c02')
    ax.set_ylabel('km', fontsize=8)
    ax.set_title(t('pdf_daily_distance'), fontsize=10, color='#333333')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.tick_params(labelsize=8)
    fig.tight_layout()

    img_buffer = BytesIO()
    fig.savefig(img_buffer, format='png')
    plt.close(fig)
    img_buffer.seek(0)
    return img_buffer


def _week_hero_image(overall, overall_prev, totals_by_sport, sports):
    """Infografía con los 3 grandes números de la semana (con flecha de variación) y un
    donut con el reparto del tiempo por disciplina. Todo dibujado (nada de texto-emoji),
    para que el PDF se vea tan visual como el resumen de la app."""
    fig = plt.figure(figsize=(7.0, 2.5), dpi=150)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.6, 1])

    tiles_ax = fig.add_subplot(gs[0, 0])
    tiles_ax.axis('off')
    tiles_ax.set_xlim(0, 3)
    tiles_ax.set_ylim(0, 1)

    tiles = [
        (t('pdf_distance'), f"{overall['km']:.1f} km", overall['km'] - overall_prev['km'], 'km'),
        (t('pdf_time'), format_hours_minutes(overall['minutes'] / 60), (overall['minutes'] - overall_prev['minutes']) / 60, 'h'),
        (t('pdf_workouts'), str(overall['sessions']), overall['sessions'] - overall_prev['sessions'], ''),
    ]
    for i, (label, value, delta, unit) in enumerate(tiles):
        x0 = i + 0.06
        box = mpatches.FancyBboxPatch((x0, 0.06), 0.88, 0.88, boxstyle="round,pad=0.02,rounding_size=0.06",
                                       linewidth=0, facecolor='#fff8f4')
        tiles_ax.add_patch(box)
        cx = x0 + 0.44
        tiles_ax.text(cx, 0.62, value, ha='center', va='center', fontsize=17, fontweight='bold', color='#181614')
        tiles_ax.text(cx, 0.42, label, ha='center', va='center', fontsize=7.5, color='#767676')
        if delta > 0.05:
            arrow, dcolor = '▲', '#22c55e'
        elif delta < -0.05:
            arrow, dcolor = '▼', '#ef4444'
        else:
            arrow, dcolor = '→', '#767676'
        delta_text = f"{arrow} {delta:+.1f}{unit}" if unit else f"{arrow} {delta:+d}"
        tiles_ax.text(cx, 0.22, delta_text, ha='center', va='center', fontsize=8.5, fontweight='bold', color=dcolor)

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
    img_buffer = BytesIO()
    fig.savefig(img_buffer, format='png', bbox_inches='tight')
    plt.close(fig)
    img_buffer.seek(0)
    return img_buffer


def _header_footer(canvas, doc):
    canvas.saveState()
    page_w, page_h = doc.pagesize
    canvas.setFillColor(BRAND_ORANGE)
    canvas.rect(0, page_h - 0.55 * inch, page_w, 0.55 * inch, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont('Helvetica-Bold', 13)
    canvas.drawString(0.5 * inch, page_h - 0.37 * inch, "PATRI'S DATA LAB")
    canvas.setFont('Helvetica', 9)
    canvas.setFillColor(colors.HexColor('#888888'))
    canvas.drawRightString(page_w - 0.5 * inch, 0.35 * inch, f"{t('pdf_page')} {doc.page}")
    canvas.restoreState()


def _sport_chip(sport):
    """Chip de color por disciplina: hace en el PDF el papel que el icono hace en la web."""
    chip = Table([[translate_sport(sport).upper()]], colWidths=[1.15 * inch], rowHeights=[0.22 * inch])
    chip.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(SPORT_COLORS.get(sport, '#fc4c02'))),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return chip


def _activity_card(entry, styles):
    accent_color = colors.HexColor(entry['card_color'])

    title_line = f"<b>{entry['activity_name']}</b> — {entry['date'].strftime('%a, %b %d')}"
    header_row = Table(
        [[_sport_chip(entry['sport']), Paragraph(title_line, styles['Normal'])]],
        colWidths=[1.25 * inch, 5.0 * inch],
    )
    header_row.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    if entry['show_time']:
        stats_line = f"{entry['headline_value']} {entry['headline_unit']} · {entry['time_hms']} · {entry['pace_speed']} · {entry['training_type']}"
    else:
        stats_line = f"{entry['headline_value']} · {entry['training_type']}"

    detail_line = f"FC: {entry['avg_hr'] if entry['avg_hr'] else '—'} bpm · Cal: {entry['calories'] if entry['calories'] else '—'} kcal · RPE: {entry['rpe'] if entry['rpe'] else '—'}/10 · {entry['feeling']}"

    cell_content = [header_row, Spacer(1, 5), Paragraph(f"{stats_line}<br/>{detail_line}", styles['Normal'])]
    if entry['comment']:
        cell_content.append(Spacer(1, 3))
        cell_content.append(Paragraph(f'<i>"{entry["comment"]}"</i>', styles['Normal']))

    table = Table([[cell_content]], colWidths=[6.5 * inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8f9fa')),
        ('LINEBEFORE', (0, 0), (0, -1), 5, accent_color),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    return table


def _discipline_comparison_table(totals_by_sport, prev_totals_by_sport, sports):
    header = [t('pdf_discipline'), t('pdf_this_week'), t('pdf_prev_week'), t('pdf_difference')]
    rows = [header]
    row_colors = [None]
    for sport in sports:
        cur = totals_by_sport.get(sport, {'km': 0.0, 'minutes': 0.0})
        prev = prev_totals_by_sport.get(sport, {'km': 0.0, 'minutes': 0.0})
        label = translate_sport(sport)
        if sport == 'Fuerza':
            rows.append([label, format_hours_minutes(cur['minutes'] / 60), format_hours_minutes(prev['minutes'] / 60), f"{(cur['minutes'] - prev['minutes']) / 60:+.1f} h"])
        elif sport == 'Natación':
            rows.append([label, f"{cur['km'] * 1000:.0f} m", f"{prev['km'] * 1000:.0f} m", f"{(cur['km'] - prev['km']) * 1000:+.0f} m"])
        else:
            rows.append([label, f"{cur['km']:.1f} km", f"{prev['km']:.1f} km", f"{cur['km'] - prev['km']:+.1f} km"])
        row_colors.append(SPORT_COLORS.get(sport, '#fc4c02'))

    table = Table(rows, colWidths=[1.5 * inch, 1.6 * inch, 1.6 * inch, 1.3 * inch], repeatRows=1)
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#181614')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.white),
    ]
    for i, hexcolor in enumerate(row_colors):
        if hexcolor:
            style.append(('BACKGROUND', (0, i), (0, i), colors.HexColor(hexcolor)))
            style.append(('TEXTCOLOR', (0, i), (0, i), colors.white))
            style.append(('FONTNAME', (0, i), (0, i), 'Helvetica-Bold'))
            style.append(('BACKGROUND', (1, i), (-1, i), colors.HexColor('#f8f9fa')))
    table.setStyle(TableStyle(style))
    return table


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
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'CustomTitle', parent=styles['Heading1'], fontSize=24, textColor=BRAND_ORANGE, spaceAfter=2, alignment=1
    )
    subtitle_style = ParagraphStyle(
        'Subtitle', parent=styles['Normal'], fontSize=11, textColor=colors.HexColor('#767676'), alignment=1, spaceAfter=4
    )
    story.append(Paragraph(t('pdf_title'), title_style))
    period_text = f"{selected_monday.strftime('%A, %B %d')} → {week_end.strftime('%A, %B %d, %Y')}"
    story.append(Paragraph(period_text, subtitle_style))
    story.append(Spacer(1, 0.15 * inch))

    # Infografía: los 3 grandes números de la semana + donut por disciplina
    story.append(Image(_week_hero_image(overall, overall_prev, totals_by_sport, sports), width=7.0 * inch, height=2.5 * inch))
    story.append(Spacer(1, 0.1 * inch))

    # Gráfico de distancia diaria
    story.append(Image(_daily_distance_chart(df_week, selected_monday), width=6.2 * inch, height=1.8 * inch))
    story.append(Spacer(1, 0.2 * inch))

    # Training Readiness / Status
    if readiness.get('score') or status_label:
        story.append(Paragraph(t('pdf_form_state'), styles['Heading2']))
        lines = []
        if readiness.get('score'):
            lines.append(f"{t('pdf_readiness')}: <b>{readiness.get('score')}/100</b>")
        if status_label:
            plain_status = status_label.split(' ', 1)[-1] if ' ' in status_label else status_label
            lines.append(f"{t('pdf_status')}: <b>{plain_status}</b>")
        if status_explanation:
            lines.append(status_explanation)
        feedback = readiness.get('feedbackLong') or readiness.get('feedbackShort')
        if feedback:
            lines.append(feedback)
        story.append(Paragraph("<br/>".join(lines), styles['Normal']))
        story.append(Spacer(1, 0.2 * inch))

    # Comentario de la semana (editado por el usuario)
    if health_comment:
        story.append(Paragraph(t('pdf_week_comment'), styles['Heading2']))
        story.append(Paragraph(health_comment, styles['Normal']))
        story.append(Spacer(1, 0.2 * inch))

    # Resumen de sueño
    if sleep_info and sleep_info.get('Total_Hours', 0) > 0:
        story.append(Paragraph(t('pdf_sleep'), styles['Heading2']))
        sleep_data = [
            [t('pdf_avg_sleep'), format_hours_minutes(sleep_info.get('Total_Hours', 0))],
            [t('sleep_score'), f"{sleep_info.get('Score', 'N/A')}/100"]
        ]
        sleep_table = Table(sleep_data, colWidths=[2.5 * inch, 2 * inch])
        sleep_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#181614')),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.whitesmoke),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (1, 0), (1, -1), colors.HexColor('#fff8f4')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.white),
        ]))
        story.append(sleep_table)
        story.append(Spacer(1, 0.25 * inch))

    story.append(Paragraph(t('pdf_comparison'), styles['Heading2']))
    story.append(_discipline_comparison_table(totals_by_sport, prev_totals_by_sport, sports))
    story.append(Spacer(1, 0.3 * inch))

    story.append(Paragraph(t('pdf_your_workouts'), styles['Heading2']))
    story.append(Spacer(1, 0.1 * inch))
    for entry in workout_entries:
        story.append(_activity_card(entry, styles))
        story.append(Spacer(1, 0.12 * inch))

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    pdf_buffer.seek(0)
    return pdf_buffer
