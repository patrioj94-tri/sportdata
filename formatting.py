"""Funciones puras de formato y de interpretación de los datos de Garmin."""
import pandas as pd
from datetime import datetime, timedelta

from garmin_data import get_activity_self_evaluation
from translations import t


def get_last_monday():
    """Obtiene la fecha del último lunes (o hoy si es lunes)."""
    today = datetime.now().date()
    days_since_monday = today.weekday()
    if days_since_monday == 0:
        return today
    else:
        return today - timedelta(days=days_since_monday)


def format_hours_minutes(hours_decimal):
    """Convierte horas decimales (7.5) a formato '7h 30\'' """
    if not hours_decimal:
        return "0h 00'"
    total_minutes = int(round(hours_decimal * 60))
    hrs = total_minutes // 60
    mins = total_minutes % 60
    return f"{hrs}h {mins:02d}'"


def format_time_hms(minutes):
    """Convierte minutos a formato HH:MM:SS."""
    if not minutes or minutes == 0:
        return "0:00:00"
    total_seconds = int(minutes * 60)
    hours = total_seconds // 3600
    remaining = total_seconds % 3600
    mins = remaining // 60
    secs = remaining % 60
    if hours > 0:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def calculate_pace_speed(sport, distance_km, duration_min, moving_duration_min=None):
    """Calcula el ritmo/velocidad utilizando preferentemente el tiempo en movimiento."""
    active_duration = moving_duration_min if (moving_duration_min and moving_duration_min > 0) else duration_min

    if not distance_km or distance_km <= 0 or not active_duration or active_duration <= 0:
        return "—"

    if sport == 'Ciclismo':
        speed_kmh = distance_km / (active_duration / 60.0)
        return f"{speed_kmh:.1f} km/h"

    elif sport == 'Carrera':
        pace_min_km = active_duration / distance_km
        p_mins = int(pace_min_km)
        p_secs = int(round((pace_min_km - p_mins) * 60))
        if p_secs == 60:
            p_mins += 1
            p_secs = 0
        return f"{p_mins}:{p_secs:02d} min/km"

    elif sport == 'Natación':
        distance_m = distance_km * 1000.0
        pace_sec_100m = (active_duration * 60.0) / (distance_m / 100.0)
        p_mins = int(pace_sec_100m // 60)
        p_secs = int(round(pace_sec_100m % 60))
        if p_secs == 60:
            p_mins += 1
            p_secs = 0
        return f"{p_mins}:{p_secs:02d} /100m"

    return "—"


def get_training_type(activity):
    """Extrae el tipo de entrenamiento explorando metadatos de Garmin."""
    possible_sources = [
        activity.get('workoutName'),
        activity.get('trainingType'),
        activity.get('eventType'),
        activity.get('subTypeId'),
        activity.get('activityType', {})
    ]

    name = str(activity.get('activityName', '')).lower()
    if 'tempo' in name:
        return 'Tempo'
    elif 'series' in name or 'interval' in name or 'fartlek' in name:
        return 'Intervals'
    elif 'rodaje' in name or 'long' in name or 'tirada' in name:
        return 'Long Run / Endurance'
    elif 'recuperacion' in name or 'suave' in name or 'easy' in name:
        return 'Recovery'

    for src in possible_sources:
        if isinstance(src, dict):
            type_key = src.get('typeKey') or src.get('subTypeKey') or ''
            if type_key and str(type_key).lower() not in ['uncategorized', 'generic', 'other']:
                return str(type_key).replace('_', ' ').title()
        elif isinstance(src, str) and src.strip():
            if src.lower() not in ['n/a', 'none', 'uncategorized', 'generic', '9', '10']:
                return src.replace('_', ' ').title()

    return 'Regular Training'


def get_perceived_effort_and_feeling(activity, client):
    """Extrae el esfuerzo percibido (RPE) y la sensación en el entreno."""
    eval_dict = activity.get('activityEvaluation', {}) or {}

    effort = (
        activity.get('perceivedExertion') or
        activity.get('perceivedEffort') or
        activity.get('effort') or
        eval_dict.get('perceivedExertion') or
        0
    )
    if isinstance(effort, float) and pd.isna(effort):
        effort = 0

    feeling_raw = (
        activity.get('feeling') or
        activity.get('feelingScore') or
        eval_dict.get('feeling') or
        ""
    )

    activity_id = activity.get('activityId')
    if not effort and not feeling_raw and activity_id:
        rpe, feel = get_activity_self_evaluation(client, activity_id)
        if rpe:
            effort = rpe
        if feel is not None:
            feeling_raw = feel

    feeling_map = {
        'VERY_WEAK': '😫 Muy mal',
        'WEAK': '🙁 Mal',
        'NORMAL': '😐 Normal',
        'STRONG': '🙂 Bien',
        'VERY_STRONG': '🔥 Excelente',
        '1': '😫 Muy mal',
        '2': '🙁 Mal',
        '3': '😐 Normal',
        '4': '🙂 Bien',
        '5': '🔥 Excelente',
        '0': '😫 Muy mal',
        '25': '🙁 Mal',
        '50': '😐 Normal',
        '75': '🙂 Bien',
        '100': '🔥 Excelente'
    }

    if isinstance(feeling_raw, float) and pd.isna(feeling_raw):
        feeling_raw = None

    if feeling_raw in (None, ""):
        feeling = None
    elif isinstance(feeling_raw, (int, float)):
        feeling_key = str(int(round(feeling_raw / 25.0) * 25)) if feeling_raw > 5 else str(int(feeling_raw))
        feeling = feeling_map.get(feeling_key, feeling_raw)
    else:
        feeling_key = str(feeling_raw).upper()
        feeling = feeling_map.get(feeling_key, feeling_raw)

    return int(effort) if effort else 0, feeling


def get_activity_comments(activity):
    """Extrae comentarios o descripción de la actividad."""
    comment = (activity.get('description') or
               activity.get('comment') or
               activity.get('notes') or
               '')

    if pd.isna(comment):
        return None

    comment_str = str(comment).strip()
    if comment_str.lower() in ['nan', 'none', '']:
        return None

    return comment_str


def categorize_sport(activity):
    """Categoriza la actividad en disciplina deportiva."""
    activity_type = activity.get('activityType', {})
    if isinstance(activity_type, dict):
        type_key = activity_type.get('typeKey', '').lower()
    else:
        type_key = str(activity_type).lower()

    if 'swimming' in type_key or 'pool' in type_key:
        return 'Natación'
    elif 'cycling' in type_key or 'bike' in type_key:
        return 'Ciclismo'
    elif 'running' in type_key or 'trail_run' in type_key:
        return 'Carrera'
    elif 'strength' in type_key or 'weight' in type_key:
        return 'Fuerza'
    else:
        return 'Otro'


# --- INTERPRETACIÓN DE TRAINING STATUS / READINESS DE GARMIN ---
# Las claves son las que devuelve Garmin (en inglés); el texto que se muestra sale de
# translations.py, para que cambie con el idioma elegido.
STATUS_KEYS = [
    'PRODUCTIVE', 'PEAKING', 'MAINTAINING', 'OVERREACHING',
    'RECOVERY', 'UNPRODUCTIVE', 'DETRAINING', 'NO_STATUS',
]


def translate_level(level):
    """Nivel de Training Readiness (PRIME, HIGH, LOW...) traducido al idioma activo."""
    if not level:
        return ''
    key = f"level_{str(level).upper()}"
    translated = t(key)
    return translated if translated != key else str(level).title()


def translate_feeling(feeling):
    """Etiqueta de sensación traducida. Internamente la sensación se guarda siempre con la
    etiqueta en español (es la clave), y aquí se convierte al idioma activo."""
    if feeling in FEELING_OPTIONS:
        return t(f"feeling_{FEELING_OPTIONS.index(feeling)}")
    return feeling or t('feeling_0')


def translate_sport(sport):
    """Nombre de disciplina traducido (internamente siempre se usa el nombre en español)."""
    key = f"sport_{sport}"
    translated = t(key)
    return translated if translated != key else sport


def extract_training_status_label(status_data):
    """Busca de forma flexible la etiqueta de Training Status (Productive, Maintaining...)
    dentro de la respuesta de Garmin, ya que su estructura anidada varía según cuenta/dispositivo."""
    def find_label(obj):
        if isinstance(obj, dict):
            for v in obj.values():
                result = find_label(v)
                if result:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = find_label(item)
                if result:
                    return result
        elif isinstance(obj, str):
            upper = obj.upper()
            for key in STATUS_KEYS:
                if key in upper:
                    return t(f"status_{key}"), t(f"status_{key}_desc")
        return None

    if not status_data:
        return None, None
    return find_label(status_data) or (None, None)


# --- INFORME SEMANAL: helpers de agregación y presentación ---
SPORT_EMOJIS = {'Ciclismo': '🚴‍♀️', 'Carrera': '🏃‍♀️', 'Natación': '🏊‍♀️', 'Fuerza': '🏋️‍♀️'}

FEELING_OPTIONS = ['Sin anotar', '😫 Muy mal', '🙁 Mal', '😐 Normal', '🙂 Bien', '🔥 Excelente']

# Valor numérico que Garmin usa internamente para la sensación (escala 0-100 en pasos de 25),
# para poder devolvérsela al guardar.
FEELING_TO_GARMIN = {
    '😫 Muy mal': 0,
    '🙁 Mal': 25,
    '😐 Normal': 50,
    '🙂 Bien': 75,
    '🔥 Excelente': 100,
}


def format_activity_headline(sport, distance_km, duration_min):
    """Cada disciplina destaca la métrica que tiene sentido en su contexto:
    natación en metros, fuerza en tiempo, carrera/ciclismo en km.
    Devuelve (valor_principal, unidad, mostrar_tiempo_aparte)."""
    if sport == 'Fuerza':
        return format_time_hms(duration_min), '', False
    if sport == 'Natación':
        return f"{distance_km * 1000:.0f}", "M", True
    return f"{distance_km:.2f}", "KM", True


def format_discipline_headline(sport, km, minutes):
    """Valor destacado por disciplina en los resúmenes semanales (mismo criterio
    que format_activity_headline, pero para un total agregado)."""
    if sport == 'Fuerza':
        return format_hours_minutes(minutes / 60)
    if sport == 'Natación':
        return f"{km * 1000:.0f} m"
    return f"{km:.1f} km"


def get_intensity_color(rpe):
    """Devuelve un color hex según la intensidad (RPE) de un entreno, para resaltar
    visualmente las tarjetas de actividad: verde = fácil, rojo = muy duro."""
    if not rpe or rpe <= 0:
        return '#fc4c02'
    if rpe <= 3:
        return '#22c55e'
    if rpe <= 6:
        return '#f59e0b'
    if rpe <= 8:
        return '#ef4444'
    return '#991b1b'


def weekly_overall_totals(df_week):
    """Distancia, sesiones y minutos totales de una semana (todas las disciplinas)."""
    if df_week.empty:
        return {'km': 0.0, 'sessions': 0, 'minutes': 0.0}
    return {
        'km': float(df_week['Distance_km'].sum()),
        'sessions': len(df_week),
        'minutes': float(df_week['Duration_min'].sum()),
    }


def delta_class(value, threshold=0.05):
    """Clasifica una variación numérica en 'positive'/'negative'/'neutral' para
    pintarla con el color e icono correspondiente (▲/▼) en el resumen visual."""
    if value > threshold:
        return 'positive'
    if value < -threshold:
        return 'negative'
    return 'neutral'


def format_discipline_delta(sport, cur, prev):
    """Texto de variación semanal para una disciplina, en la unidad que corresponda."""
    suffix = t('vs_prev_week')
    if sport == 'Fuerza':
        delta_min = cur['minutes'] - prev['minutes']
        return f"{delta_min / 60:+.1f} h {suffix}"
    if sport == 'Natación':
        delta_m = (cur['km'] - prev['km']) * 1000
        return f"{delta_m:+.0f} m {suffix}"
    delta_km = cur['km'] - prev['km']
    return f"{delta_km:+.1f} km {suffix}"


def weekly_totals_by_sport(df_week, sports):
    """Distancia, sesiones y minutos totales de una semana, desglosados por disciplina."""
    totals = {}
    for sport in sports:
        if df_week.empty or 'Sport' not in df_week.columns:
            totals[sport] = {'km': 0.0, 'sessions': 0, 'minutes': 0.0}
            continue
        df_sport = df_week[df_week['Sport'] == sport]
        totals[sport] = {
            'km': float(df_sport['Distance_km'].sum()) if len(df_sport) else 0.0,
            'sessions': len(df_sport),
            'minutes': float(df_sport['Duration_min'].sum()) if len(df_sport) else 0.0,
        }
    return totals


SPORT_COLORS = {'Ciclismo': '#fc4c02', 'Carrera': '#3b82f6', 'Natación': '#06b6d4', 'Fuerza': '#a855f7'}


def build_stat_row(sport, distance_km, time_hms, pace_speed, avg_hr, calories):
    """Las 4 estadísticas destacadas de la tarjeta de un entreno, adaptadas a la disciplina."""
    hr_str = f"{avg_hr}" if avg_hr else "—"
    cal_str = f"{calories}" if calories else "—"
    if sport == 'Fuerza':
        return [(time_hms, t('stat_duration')), (cal_str, t('stat_kcal')), (hr_str, t('stat_hr')), ('—', t('stat_pace'))]
    if sport == 'Natación':
        return [(f"{distance_km * 1000:.0f}", t('stat_meters')), (time_hms, t('stat_time')), (pace_speed, t('stat_pace_100m')), (cal_str, t('stat_kcal'))]
    unit_label = t('stat_speed') if sport == 'Ciclismo' else t('stat_pace_km')
    return [(f"{distance_km:.2f}", t('stat_km')), (time_hms, t('stat_time')), (pace_speed, unit_label), (hr_str, t('stat_hr'))]


def format_rpe_pill(rpe, feeling):
    """Texto corto para la píldora de esfuerzo/sensación de la tarjeta."""
    translated = translate_feeling(feeling) if feeling and feeling != 'Sin anotar' else ''
    feeling_text = translated.split(' ', 1)[-1] if translated else ''
    if rpe and feeling_text:
        return f"RPE {rpe} · {feeling_text}"
    if rpe:
        return f"RPE {rpe}"
    return feeling_text or t('feeling_0')


def format_lap_row(sport, lap):
    """Da formato a un intervalo/serie (lap) de Garmin para mostrarlo en una tabla."""
    distance_km = (lap.get('distance') or 0) / 1000.0
    duration_min = (lap.get('duration') or 0) / 60.0
    value, unit, _ = format_activity_headline(sport, distance_km, duration_min)
    avg_hr = lap.get('averageHR')
    return {
        t('lap_number'): lap.get('lapIndex', '—'),
        t('lap_distance'): f"{value} {unit}".strip(),
        t('lap_duration'): format_time_hms(duration_min),
        t('lap_pace'): calculate_pace_speed(sport, distance_km, duration_min),
        t('lap_hr'): f"{int(avg_hr)} bpm" if avg_hr else '—',
    }


def build_week_calendar(df_week, selected_monday):
    """Para cada día Lun-Dom de la semana, qué deportes se practicaron (o ninguno).
    'entries' trae (emoji, activity_id) por actividad, para poder enlazar cada icono
    directamente a su tarjeta en el listado de entrenos."""
    days = []
    for offset in range(7):
        day = selected_monday + timedelta(days=offset)
        if df_week.empty or 'Sport' not in df_week.columns:
            day_acts = df_week.iloc[0:0]
        else:
            day_acts = df_week[df_week['Date'] == day]
        entries = [
            (SPORT_EMOJIS.get(row.get('Sport'), '⚡'), row.get('activityId'))
            for _, row in day_acts.iterrows()
        ]
        days.append({'date': day, 'entries': entries, 'count': len(entries)})
    return days
