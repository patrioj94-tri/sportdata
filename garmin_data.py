"""Capa de acceso a Garmin Connect: login, cacheo y extracción de datos crudos."""
import hashlib
import os
import pandas as pd
import streamlit as st
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from garminconnect import Garmin

SESSIONS_ROOT = os.path.expanduser("~/.garminconnect_sessions")


def _token_dir_for(email):
    """Carpeta de sesión aislada por email: esta app la usan varias personas del
    equipo, así que cada cuenta de Garmin debe tener su propio token guardado
    (una carpeta compartida haría que una persona pudiera heredar la sesión de otra)."""
    email_hash = hashlib.sha256(email.strip().lower().encode()).hexdigest()[:16]
    return os.path.join(SESSIONS_ROOT, email_hash)


@st.cache_resource(show_spinner=False)
def get_garmin_client(email, password):
    token_dir = _token_dir_for(email)
    try:
        client = Garmin(email, password)
        try:
            client.login(token_dir)
        except Exception:
            client.login()
            os.makedirs(token_dir, exist_ok=True)
            client.garth.dump(token_dir)
        return client
    except Exception as e:
        st.sidebar.error(f"Authentication failed: {e}")
        return None


# --- MOTOR DE CARGA DE ENTRENAMIENTO (BANISTER MODEL) ---
def compute_training_load(df_acts, days_back=365):
    """Calcula Carga Diaria, Fitness (CTL - 42d), Fatiga (ATL - 7d) y Estado de Forma (TSB)."""
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days_back + 60)

    date_range = pd.date_range(start=start_date, end=end_date, freq='D')
    df_load = pd.DataFrame({'Date': date_range})
    df_load['Date'] = df_load['Date'].dt.date

    if df_acts.empty:
        df_load['Effort'] = 0.0
    else:
        def calc_effort(row):
            duration_min = row.get('Duration_min', 0)
            avg_hr = row.get('averageHR', 0)
            max_hr = row.get('maxHR', 185)

            if avg_hr and avg_hr > 0:
                intensity_ratio = avg_hr / max_hr if max_hr > 0 else 0.7
                effort = duration_min * (intensity_ratio ** 2) * 2
            else:
                effort = row.get('Active_Calories', duration_min * 5) / 10
            return effort

        df_acts['Effort'] = df_acts.apply(calc_effort, axis=1)
        daily_effort = df_acts.groupby('Date')['Effort'].sum().reset_index()
        df_load = pd.merge(df_load, daily_effort, on='Date', how='left').fillna(0)

    df_load['Fitness_CTL'] = df_load['Effort'].ewm(span=42, adjust=False).mean()
    df_load['Fatigue_ATL'] = df_load['Effort'].ewm(span=7, adjust=False).mean()
    df_load['Form_TSB'] = df_load['Fitness_CTL'] - df_load['Fatigue_ATL']

    filter_start = end_date - timedelta(days=days_back)
    return df_load[df_load['Date'] >= filter_start].copy()


@st.cache_data(ttl=1800, show_spinner="Syncing Patri's health, HRV, sleep, and telemetry...")
def load_all_garmin_data(_client, days_back=365, user_key=None):
    # user_key (el email) no se usa dentro de la función: existe solo para que la
    # caché de Streamlit distinga entre usuarios. "_client" no se incluye en la
    # clave de caché (por el guion bajo), así que sin esto dos personas de la app
    # pedirían el mismo días_back y una recibiría los datos cacheados de la otra.
    today = datetime.now().date()

    # 1. EXTRACCIÓN DE SALUD Y SUEÑO (en paralelo para acelerar la carga)
    daily_stats = []
    sleep_info = {}
    health_days = min(days_back, 90)
    day_strs = [(today - timedelta(days=i)).isoformat() for i in range(health_days)]

    def _fetch_day_combined(day_str):
        try:
            stats = _client.get_stats(day_str) or {}
            user_summary = _client.get_user_summary(day_str) or {}
            return day_str, {**stats, **user_summary}
        except Exception:
            return day_str, None

    combined_by_day = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_fetch_day_combined, d) for d in day_strs]
        for future in as_completed(futures):
            day_str, combined = future.result()
            if combined:
                combined_by_day[day_str] = combined

    for day_str in day_strs:
        combined = combined_by_day.get(day_str)
        if not combined:
            continue

        daily_stats.append({
            'Date': day_str,
            'Resting_HR': combined.get('restingHeartRate'),
            'Body_Battery_Max': combined.get('bodyBatteryHighestValue'),
            'Avg_Stress': combined.get('averageStressLevel'),
            'Steps': combined.get('totalSteps'),
            'Active_Calories': combined.get('activeKilocalories')
        })

        if not sleep_info:
            sleep_secs = combined.get('userSleepSeconds') or combined.get('totalSleepSeconds') or combined.get('sleepTimeSeconds') or 0
            if sleep_secs > 0:
                sleep_info = {
                    'Date': day_str,
                    'Score': combined.get('sleepScore') or combined.get('overallSleepScore') or 'N/A',
                    'Qualifier': str(combined.get('sleepQuality', 'Logged')).replace('_', ' ').title(),
                    'Total_Hours': round(sleep_secs / 3600, 1),
                    'Deep_Hours': round((combined.get('deepSleepSeconds', 0) or 0) / 3600, 1),
                    'Light_Hours': round((combined.get('lightSleepSeconds', 0) or 0) / 3600, 1),
                    'REM_Hours': round((combined.get('remSleepSeconds', 0) or 0) / 3600, 1),
                    'Feedback': f"Sleep session recorded on {day_str}."
                }

    # Fallback para datos de sueño
    if not sleep_info:
        for offset in range(7):
            target_date = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
            try:
                raw_sleep = _client.get_sleep_data(target_date) or {}
                dto = raw_sleep.get('dailySleepDTO', {}) or {}
                sleep_secs = dto.get('sleepTimeSeconds', 0) or raw_sleep.get('totalSleepSeconds', 0) or 0

                if sleep_secs > 0:
                    sleep_info = {
                        'Date': target_date,
                        'Score': dto.get('sleepScores', {}).get('overall', {}).get('value', 'N/A'),
                        'Qualifier': 'Logged',
                        'Total_Hours': round(sleep_secs / 3600, 1),
                        'Deep_Hours': round((dto.get('deepSleepSeconds', 0) or 0) / 3600, 1),
                        'Light_Hours': round((dto.get('lightSleepSeconds', 0) or 0) / 3600, 1),
                        'REM_Hours': round((dto.get('remSleepSeconds', 0) or 0) / 3600, 1),
                        'Feedback': f"Sleep session recorded on {target_date}."
                    }
                    break
            except Exception:
                continue

    # 2. EXTRACCIÓN DE HRV Y RESPIRACIÓN
    hrv_data, respiration_data = {}, {}
    try:
        hrv_raw = _client.get_hrv_data(today.strftime("%Y-%m-%d"))
        if hrv_raw and 'hrvSummary' in hrv_raw:
            s = hrv_raw['hrvSummary']
            hrv_data = {'Weekly_Avg': s.get('weeklyAvg', 'N/A'), 'Last_Night_Avg': s.get('lastNightAvg', 'N/A'), 'Status': s.get('status', 'N/A'), 'Feedback': s.get('feedback', '')}
    except Exception:
        hrv_data = {'Status': 'N/A', 'Weekly_Avg': 'N/A', 'Last_Night_Avg': 'N/A'}

    try:
        resp_raw = _client.get_respiration_data(today.strftime("%Y-%m-%d"))
        if resp_raw:
            respiration_data = {'Avg_Waking': resp_raw.get('avgWakingRespirationValue', 'N/A'), 'Avg_Sleep': resp_raw.get('avgSleepRespirationValue', 'N/A')}
    except Exception:
        respiration_data = {'Avg_Waking': 'N/A', 'Avg_Sleep': 'N/A'}

    df_health = pd.DataFrame(daily_stats)
    if not df_health.empty:
        df_health['Date'] = pd.to_datetime(df_health['Date'])

    # 3. EXTRACCIÓN DE ACTIVIDADES CON TIEMPO EN MOVIMIENTO
    start_date = datetime.now() - timedelta(days=days_back + 60)
    raw_acts = _client.get_activities_by_date(start_date.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
    df_acts = pd.DataFrame(raw_acts) if raw_acts else pd.DataFrame()

    if not df_acts.empty:
        df_acts['Date'] = pd.to_datetime(df_acts.get('startTimeLocal', datetime.now())).dt.date
        df_acts['DateTime'] = pd.to_datetime(df_acts.get('startTimeLocal', datetime.now()))
        df_acts['Distance_km'] = df_acts.get('distance', 0) / 1000.0
        df_acts['Duration_min'] = df_acts.get('duration', 0) / 60.0
        df_acts['MovingDuration_min'] = df_acts.get('movingDuration', 0) / 60.0
        df_acts['Elevation_m'] = df_acts.get('elevationGain', 0)
        df_acts['Sport'] = df_acts['activityType'].apply(lambda x: x.get('typeKey', 'Other') if isinstance(x, dict) else 'Other') if 'activityType' in df_acts.columns else 'Other'
        df_acts['Year'] = df_acts['DateTime'].dt.year
        df_acts['Month'] = df_acts['DateTime'].dt.strftime('%b')
        df_acts['MonthNum'] = df_acts['DateTime'].dt.month

    return df_health, sleep_info, hrv_data, respiration_data, df_acts


@st.cache_data(ttl=1800, show_spinner=False)
def get_activity_self_evaluation(_client, activity_id):
    """Obtiene el RPE y la sensación (feel) autoevaluados manualmente en Garmin Connect.
    Estos campos no vienen en el listado general de actividades: solo están en el
    detalle de cada actividad, bajo summaryDTO.directWorkoutRpe / directWorkoutFeel."""
    try:
        detail = _client.get_activity(activity_id) or {}
        summary = detail.get('summaryDTO', {}) or {}
        rpe_raw = summary.get('directWorkoutRpe')
        feel_raw = summary.get('directWorkoutFeel')
        rpe = round(rpe_raw / 10) if rpe_raw else 0
        return rpe, feel_raw
    except Exception:
        return 0, None


@st.cache_data(ttl=1800, show_spinner=False)
def get_activity_splits(_client, activity_id):
    """Devuelve los intervalos/series (laps) guardados en Garmin para una actividad, si los tiene."""
    try:
        data = _client.get_activity_splits(activity_id) or {}
        return data.get('lapDTOs', []) or []
    except Exception:
        return []


@st.cache_data(ttl=1800, show_spinner=False)
def get_training_readiness_today(_client, user_key=None):
    """Puntuación de preparación diaria de Garmin (0-100), con los factores que la componen:
    sueño, HRV, recuperación, carga de entreno y estrés. user_key aísla la caché por usuario
    (ver comentario en load_all_garmin_data)."""
    try:
        data = _client.get_training_readiness(datetime.now().date().isoformat())
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


@st.cache_data(ttl=1800, show_spinner=False)
def get_training_status_today(_client, user_key=None):
    """Estado de entrenamiento de Garmin (Productive, Maintaining, Overreaching, etc.).
    user_key aísla la caché por usuario (ver comentario en load_all_garmin_data)."""
    try:
        return _client.get_training_status(datetime.now().date().isoformat()) or {}
    except Exception:
        return {}
