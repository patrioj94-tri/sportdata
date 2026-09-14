"""Generación del informe semanal en PDF."""
from io import BytesIO

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import timedelta

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image

from formatting import format_hours_minutes, weekly_totals_by_sport

BRAND_ORANGE = colors.HexColor('#fc4c02')


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


def _activity_card(entry, styles):
    accent_color = colors.HexColor(entry['card_color'])
    title_line = f"<b>{entry['sport_emoji']} {entry['activity_name']}</b> — {entry['date'].strftime('%a, %b %d')}"

    if entry['show_time']:
        stats_line = f"{entry['headline_value']} {entry['headline_unit']} | {entry['time_hms']} | {entry['pace_speed']} | {entry['training_type']}"
    else:
        stats_line = f"{entry['headline_value']} | {entry['training_type']}"

    detail_line = f"FC: {entry['avg_hr'] if entry['avg_hr'] else '—'} bpm | Cal: {entry['calories'] if entry['calories'] else '—'} kcal | RPE: {entry['rpe'] if entry['rpe'] else '—'}/10 | {entry['feeling']}"

    cell_content = [Paragraph(f"{title_line}<br/>{stats_line}<br/>{detail_line}", styles['Normal'])]
    if entry['comment']:
        cell_content.append(Paragraph(f'<i>"{entry["comment"]}"</i>', styles['Normal']))

    table = Table([[cell_content]], colWidths=[6.5 * inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8f9fa')),
        ('LINEBEFORE', (0, 0), (0, -1), 5, accent_color),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
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
    story.append(Image(_daily_distance_chart(df_week, selected_monday), width=6.2 * inch, height=2.1 * inch))
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

    # Comentario de la semana (editado por el usuario)
    if health_comment:
        story.append(Paragraph("Comentario de la Semana", styles['Heading2']))
        story.append(Paragraph(health_comment, styles['Normal']))
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
    comp_data = [['Sport', 'Esta semana', 'Semana anterior', 'Diferencia']]
    for sport in sports:
        cur = totals_by_sport.get(sport, {'km': 0.0, 'minutes': 0.0})
        prev = prev_totals_by_sport.get(sport, {'km': 0.0, 'minutes': 0.0})
        if sport == 'Fuerza':
            comp_data.append([sport, format_hours_minutes(cur['minutes'] / 60), format_hours_minutes(prev['minutes'] / 60), f"{(cur['minutes'] - prev['minutes']) / 60:+.1f} h"])
        elif sport == 'Natación':
            comp_data.append([sport, f"{cur['km'] * 1000:.0f} m", f"{prev['km'] * 1000:.0f} m", f"{(cur['km'] - prev['km']) * 1000:+.0f} m"])
        else:
            comp_data.append([sport, f"{cur['km']:.1f} km", f"{prev['km']:.1f} km", f"{cur['km'] - prev['km']:+.1f} km"])

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
    for entry in workout_entries:
        story.append(_activity_card(entry, styles))
        story.append(Spacer(1, 0.12 * inch))

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    pdf_buffer.seek(0)
    return pdf_buffer
