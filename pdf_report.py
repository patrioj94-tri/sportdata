"""Generación del informe semanal en PDF."""
from io import BytesIO

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from datetime import timedelta

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image

from formatting import (
    format_hours_minutes,
    format_time_hms,
    calculate_pace_speed,
    get_training_type,
    get_perceived_effort_and_feeling,
    get_activity_comments,
    get_intensity_color,
    weekly_totals_by_sport,
    SPORT_EMOJIS,
)

BRAND_ORANGE = colors.HexColor('#fc4c02')


def _daily_distance_chart(df_week_sorted, selected_monday):
    """Gráfico de barras con la distancia diaria de la semana, como imagen PNG."""
    days = [selected_monday + timedelta(days=i) for i in range(7)]
    daily_km = []
    for day in days:
        if df_week_sorted.empty:
            daily_km.append(0)
        else:
            day_df = df_week_sorted[df_week_sorted['Date'] == day]
            daily_km.append(day_df['Distance_km'].sum() if len(day_df) else 0)

    fig, ax = plt.subplots(figsize=(6.2, 2.1), dpi=150)
    ax.bar([d.strftime('%a') for d in days], daily_km, color='#fc4c02')
    ax.set_ylabel('km', fontsize=8)
    ax.set_title('Distancia diaria de la semana', fontsize=10, color='#333333')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.tick_params(labelsize=8)
    fig.tight_layout()

    img_buffer = BytesIO()
    fig.savefig(img_buffer, format='png')
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
    canvas.drawRightString(page_w - 0.5 * inch, 0.35 * inch, f"Página {doc.page}")
    canvas.restoreState()


def _activity_card(activity, styles, client):
    sport = activity.get('Sport', 'Otro')
    sport_emoji = SPORT_EMOJIS.get(sport, '⚡')
    distance_km = activity.get('Distance_km', 0)
    duration_min = activity.get('Duration_min', 0)
    moving_duration_min = activity.get('MovingDuration_min', 0)
    time_hms = format_time_hms(duration_min)
    pace_speed = calculate_pace_speed(sport, distance_km, duration_min, moving_duration_min)
    training_type = get_training_type(activity)

    perceived_effort, feeling = get_perceived_effort_and_feeling(activity, client)
    accent_color = colors.HexColor(get_intensity_color(perceived_effort))

    avg_hr_val = activity.get('averageHR')
    avg_hr = int(avg_hr_val) if pd.notna(avg_hr_val) and avg_hr_val else 0
    cal_val = activity.get('Active_Calories')
    calories = int(cal_val) if pd.notna(cal_val) and cal_val else 0

    title_line = f"<b>{sport_emoji} {activity.get('activityName', 'Unnamed')}</b> — {activity['Date'].strftime('%a, %b %d')}"
    stats_line = f"{distance_km:.2f} km | {time_hms} | {pace_speed} | {training_type}"
    detail_line = f"FC: {avg_hr if avg_hr else '—'} bpm | Cal: {calories if calories else '—'} kcal | RPE: {perceived_effort if perceived_effort else '—'}/10 | {feeling or 'Sin anotar'}"

    cell_content = [Paragraph(f"{title_line}<br/>{stats_line}<br/>{detail_line}", styles['Normal'])]

    comments = get_activity_comments(activity)
    if comments:
        cell_content.append(Paragraph(f'<i>"{comments}"</i>', styles['Normal']))

    table = Table([[cell_content]], colWidths=[6.5 * inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8f9fa')),
        ('LINEBEFORE', (0, 0), (0, -1), 5, accent_color),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    return table


def build_weekly_report_pdf(df_week_sorted, sleep_info, sports, selected_monday, week_end, client,
                             readiness=None, status_label=None, status_explanation=None,
                             prev_totals_by_sport=None, overall=None, overall_prev=None):
    """Construye el PDF del informe semanal y devuelve un BytesIO listo para descargar."""
    readiness = readiness or {}
    prev_totals_by_sport = prev_totals_by_sport or {s: {'km': 0.0, 'sessions': 0, 'minutes': 0.0} for s in sports}
    overall = overall or {'km': 0.0, 'sessions': 0, 'minutes': 0.0}
    overall_prev = overall_prev or {'km': 0.0, 'sessions': 0, 'minutes': 0.0}
    totals_by_sport = weekly_totals_by_sport(df_week_sorted, sports)

    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=A4, topMargin=0.9 * inch, bottomMargin=0.7 * inch)
    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=22,
        textColor=BRAND_ORANGE,
        spaceAfter=6,
        alignment=1
    )
    story.append(Paragraph("WEEKLY TRAINING REPORT", title_style))
    period_text = f"{selected_monday.strftime('%A, %B %d')} → {week_end.strftime('%A, %B %d, %Y')}"
    story.append(Paragraph(period_text, ParagraphStyle('Period', parent=styles['Normal'], alignment=1)))
    story.append(Spacer(1, 0.25 * inch))

    # Gráfico de distancia diaria
    story.append(Image(_daily_distance_chart(df_week_sorted, selected_monday), width=6.2 * inch, height=2.1 * inch))
    story.append(Spacer(1, 0.25 * inch))

    # Training Readiness / Status
    if readiness.get('score') or status_label:
        story.append(Paragraph("Estado de Forma", styles['Heading2']))
        lines = []
        if readiness.get('score'):
            lines.append(f"Training Readiness: <b>{readiness.get('score')}/100</b>")
        if status_label:
            plain_status = status_label.split(' ', 1)[-1] if ' ' in status_label else status_label
            lines.append(f"Training Status: <b>{plain_status}</b>")
        if status_explanation:
            lines.append(status_explanation)
        feedback = readiness.get('feedbackLong') or readiness.get('feedbackShort')
        if feedback:
            lines.append(feedback)
        story.append(Paragraph("<br/>".join(lines), styles['Normal']))
        story.append(Spacer(1, 0.25 * inch))

    # Resumen de sueño
    if sleep_info and sleep_info.get('Total_Hours', 0) > 0:
        story.append(Paragraph("Sleep Summary", styles['Heading2']))
        sleep_data = [
            ['Metric', 'Value'],
            ['Avg Sleep per Night', format_hours_minutes(sleep_info.get('Total_Hours', 0))],
            ['Sleep Score', f"{sleep_info.get('Score', 'N/A')}/100"]
        ]
        sleep_table = Table(sleep_data, colWidths=[3 * inch, 2 * inch])
        sleep_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BRAND_ORANGE),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(sleep_table)
        story.append(Spacer(1, 0.3 * inch))

    # Resumen total + comparativa vs semana anterior
    story.append(Paragraph("Resumen Total vs. Semana Anterior", styles['Heading2']))
    overall_data = [
        ['', 'Esta semana', 'Semana anterior', 'Diferencia'],
        ['Distancia', f"{overall['km']:.1f} km", f"{overall_prev['km']:.1f} km", f"{overall['km'] - overall_prev['km']:+.1f} km"],
        ['Tiempo', format_hours_minutes(overall['minutes'] / 60), format_hours_minutes(overall_prev['minutes'] / 60), f"{(overall['minutes'] - overall_prev['minutes']) / 60:+.1f} h"],
        ['Sesiones', str(overall['sessions']), str(overall_prev['sessions']), f"{overall['sessions'] - overall_prev['sessions']:+d}"],
    ]
    overall_table = Table(overall_data, colWidths=[1.5 * inch, 1.6 * inch, 1.6 * inch, 1.3 * inch], repeatRows=1)
    overall_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f77b4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(overall_table)
    story.append(Spacer(1, 0.3 * inch))

    story.append(Paragraph("Comparativa por Disciplina", styles['Heading2']))
    comp_data = [['Sport', 'Esta semana (km)', 'Semana anterior (km)', 'Diferencia']]
    for sport in sports:
        cur = totals_by_sport.get(sport, {'km': 0.0})
        prev = prev_totals_by_sport.get(sport, {'km': 0.0})
        diff = cur['km'] - prev['km']
        comp_data.append([sport, f"{cur['km']:.1f}", f"{prev['km']:.1f}", f"{diff:+.1f}"])

    comp_table = Table(comp_data, colWidths=[1.5 * inch, 1.6 * inch, 1.6 * inch, 1.3 * inch], repeatRows=1)
    comp_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f77b4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(comp_table)
    story.append(Spacer(1, 0.3 * inch))

    story.append(Paragraph("Workout Details", styles['Heading2']))
    story.append(Spacer(1, 0.1 * inch))
    for _, activity in df_week_sorted.iterrows():
        story.append(_activity_card(activity, styles, client))
        story.append(Spacer(1, 0.12 * inch))

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    pdf_buffer.seek(0)
    return pdf_buffer
