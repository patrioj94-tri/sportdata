"""Generación del informe semanal en PDF."""
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from formatting import format_hours_minutes, format_time_hms, calculate_pace_speed, get_training_type

SPORT_EMOJIS = {'Natación': '🏊‍♀️', 'Ciclismo': '🚴‍♀️', 'Carrera': '🏃‍♀️', 'Fuerza': '🏋️‍♀️'}


def build_weekly_report_pdf(df_week_sorted, sleep_info, sports, last_monday, week_end):
    """Construye el PDF del informe semanal y devuelve un BytesIO listo para descargar."""
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=A4, topMargin=0.5 * inch, bottomMargin=0.5 * inch)
    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#fc4c02'),
        spaceAfter=12,
        alignment=1
    )
    story.append(Paragraph("WEEKLY TRAINING REPORT", title_style))
    story.append(Spacer(1, 0.2 * inch))

    period_text = f"{last_monday.strftime('%A, %B %d')} → {week_end.strftime('%A, %B %d, %Y')}"
    story.append(Paragraph(period_text, styles['Normal']))
    story.append(Spacer(1, 0.3 * inch))

    if sleep_info and sleep_info.get('Total_Hours', 0) > 0:
        story.append(Paragraph("Sleep Summary", styles['Heading2']))
        sleep_data = [
            ['Metric', 'Value'],
            ['Avg Sleep per Night', format_hours_minutes(sleep_info.get('Total_Hours', 0))],
            ['Sleep Score', f"{sleep_info.get('Score', 'N/A')}/100"]
        ]
        sleep_table = Table(sleep_data, colWidths=[3 * inch, 2 * inch])
        sleep_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#fc4c02')),
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

    story.append(Paragraph("Weekly Totals by Discipline", styles['Heading2']))
    summary_data = [['Sport', 'Distance (km)', 'Sessions', 'Time']]
    for sport in sports:
        df_sport = df_week_sorted[df_week_sorted['Sport'] == sport]
        if len(df_sport) > 0:
            total_km = df_sport['Distance_km'].sum()
            total_min = df_sport['Duration_min'].sum()
            total_hrs = int(total_min // 60)
            total_mins = int(total_min % 60)
            summary_data.append([sport, f"{total_km:.1f}", str(len(df_sport)), f"{total_hrs}h {total_mins}m"])

    summary_table = Table(summary_data, colWidths=[1.5 * inch, 1.5 * inch, 1.5 * inch, 1.5 * inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f77b4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.3 * inch))

    story.append(Paragraph("Workout Details", styles['Heading2']))
    for _, activity in df_week_sorted.iterrows():
        sport = activity.get('Sport', 'Otro')
        sport_emoji = SPORT_EMOJIS.get(sport, '⚡')
        distance_km = activity.get('Distance_km', 0)
        duration_min = activity.get('Duration_min', 0)
        moving_duration_min = activity.get('MovingDuration_min', 0)
        time_hms = format_time_hms(duration_min)
        pace_speed = calculate_pace_speed(sport, distance_km, duration_min, moving_duration_min)
        training_type = get_training_type(activity)

        workout_text = f"<b>{sport_emoji} {activity.get('activityName', 'Unnamed')}</b><br/>"
        workout_text += f"Date: {activity['Date'].strftime('%a, %b %d')} | Distance: {distance_km:.2f} km | Time: {time_hms}<br/>"
        workout_text += f"Pace/Speed (Moving): {pace_speed} | Type: {training_type}"

        story.append(Paragraph(workout_text, styles['Normal']))
        story.append(Spacer(1, 0.1 * inch))

    doc.build(story)
    pdf_buffer.seek(0)
    return pdf_buffer
