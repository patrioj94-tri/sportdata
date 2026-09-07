import os
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, timedelta
from garminconnect import Garmin

# --- CONFIGURACIÓN DE PÁGINA Y ESTILOS ---
st.set_page_config(page_title="Patri's Data Lab", layout="wide", page_icon="🏊‍♀️")

st.markdown("""
<style>
    .activity-card {
        background-color: #f8f9fa;
        border-left: 5px solid #fc4c02; /* Naranja Deportivo */
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 12px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.06);
    }
    .badge-type {
        background-color: rgba(252, 76, 2, 0.12);
        color: #fc4c02;
        padding: 4px 12px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-block;
        border: 1px solid rgba(252, 76, 2, 0.25);
    }
</style>
""", unsafe_allow_html=True)

# Título y Subtítulo Destacado
st.title("Patri's Data Lab 🏊‍♀️🚴‍♀️🏃‍♀️")
st.markdown("<p style='font-size: 1.35rem; font-weight: 800; color: #fc4c02; margin-top: -15px;'>Do it for fun!</p>", unsafe_allow_html=True)

TOKEN_DIR = os.path.expanduser("~/.garminconnect")

# --- FUNCIONES DE UTILIDAD ---
def get_last_monday():
    """Obtiene la fecha del último lunes (o hoy si es lunes)."""
    today = datetime.now().date()
    days_since_monday = today.weekday()
    if days_since_monday == 0:
        return today
    else:
        return today - timedelta(days=days_since_monday)

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

def get_perceived_effort_and_feeling(activity):
    """Extrae el esfuerzo percibido (RPE) y la sensación en el entreno."""
    eval_dict = activity.get('activityEvaluation', {}) or {}
    
    effort = (
        activity.get('perceivedExertion') or 
        activity.get('perceivedEffort') or 
        activity.get('effort') or 
        eval_dict.get('perceivedExertion') or 
        0
    )
    
    feeling_raw = (
        activity.get('feeling') or 
        activity.get('feelingScore') or 
        eval_dict.get('feeling') or 
        ""
    )
    
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
        '5': '🔥 Excelente'
    }
    
    feeling_str = str(feeling_raw).upper()
    feeling = feeling_map.get(feeling_str, feeling_raw if feeling_raw else None)
    
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

@st.cache_resource(show_spinner=False)
def get_garmin_client(email, password):
    try:
        client = Garmin(email, password)
        try:
            client.login(TOKEN_DIR)
        except Exception:
            client.login()
            os.makedirs(TOKEN_DIR, exist_ok=True)
            client.garth.dump(TOKEN_DIR)
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
def load_all_garmin_data(_client, days_back=365):
    today = datetime.now().date()
    
    # 1. EXTRACCIÓN DE SALUD Y SUEÑO
    daily_stats = []
    sleep_info = {}
    health_days = min(days_back, 90)
    
    for i in range(health_days):
        day_str = (today - timedelta(days=i)).isoformat()
        try:
            stats = _client.get_stats(day_str) or {}
            user_summary = _client.get_user_summary(day_str) or {}
            combined = {**stats, **user_summary}
            
            if combined:
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
        except Exception:
            continue

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

# --- BARRA LATERAL ---
st.sidebar.header("🔒 Credentials")
email = st.sidebar.text_input("Garmin Email")
password = st.sidebar.text_input("Garmin Password", type="password")
days = st.sidebar.slider("Analysis Window (Days)", 30, 1095, 365, step=30)

if email and password:
    client = get_garmin_client(email, password)
    if client:
        df_health, sleep_info, hrv_data, respiration_data, df_acts = load_all_garmin_data(client, days)
        df_load = compute_training_load(df_acts, days)

        # MÉTICAS GLOBALES
        st.subheader("📊 General Overview & Training State")
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        
        latest_load = df_load.iloc[-1] if not df_load.empty else {}
        ctl = latest_load.get('Fitness_CTL', 0)
        atl = latest_load.get('Fatigue_ATL', 0)
        tsb = latest_load.get('Form_TSB', 0)

        m1.metric("Fitness (CTL)", f"{ctl:.1f}")
        m2.metric("Fatigue (ATL)", f"{atl:.1f}")
        m3.metric("Form / TSB", f"{tsb:.1f}", delta="Optimal Race Form" if 5 <= tsb <= 20 else "High Fatigue Risk" if tsb < -20 else "Taper / Rest")
        m4.metric("Sleep Score", f"{sleep_info.get('Score', 'N/A')}/100", f"{sleep_info.get('Total_Hours', 0)} h")
        m5.metric("HRV Status", f"{hrv_data.get('Status', 'N/A').title()}")
        m6.metric("Active Days", f"{df_acts['Date'].nunique() if not df_acts.empty else 0}")

        st.divider()

        # PESTAÑAS DEL DASHBOARD
        tab_load, tab_guidance, tab_sleep, tab_hrv_resp, tab_heat, tab_monthly, tab_health, tab_weekly, tab_logs = st.tabs([
            "📈 Training Load",
            "💡 Guidance",
            "🌙 Sleep",
            "🫀 HRV & Resp",
            "📅 Heatmap", 
            "📊 Monthly", 
            "🩺 Health & Stress",
            "📊 Weekly Report",
            "📋 Activity Log"
        ])

        # TAB 1: MODELO DE CARGA DE ENTRENAMIENTO
        with tab_load:
            st.subheader("SportTracks Training Load Model (Banister Framework)")
            st.caption("Tracks long-term Fitness (CTL), short-term Fatigue (ATL), and Form (TSB) over time.")
            
            fig_tl = go.Figure()
            fig_tl.add_trace(go.Bar(x=df_load['Date'], y=df_load['Effort'], name='Daily Effort', marker_color='rgba(252, 76, 2, 0.25)'))
            fig_tl.add_trace(go.Scatter(x=df_load['Date'], y=df_load['Fitness_CTL'], name='Fitness (CTL - 42d)', line=dict(color='#1f77b4', width=3)))
            fig_tl.add_trace(go.Scatter(x=df_load['Date'], y=df_load['Fatigue_ATL'], name='Fatigue (ATL - 7d)', line=dict(color='#d62728', width=2)))
            fig_tl.add_trace(go.Scatter(x=df_load['Date'], y=df_load['Form_TSB'], name='Form (TSB)', line=dict(color='#2ca02c', width=2, dash='dot')))

            fig_tl.update_layout(
                title="Fitness, Fatigue, and Form Chart",
                xaxis_title="Date",
                yaxis_title="Load / Impulse Points",
                hovermode="x unified",
                template="plotly_white",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_tl, use_container_width=True)

        # TAB 2: RECOMENDACIONES
        with tab_guidance:
            st.subheader("Daily Recovery & Garmin Recommendations")
            c1, c2 = st.columns([1, 2])
            with c1:
                st.metric("Sleep Score", f"{sleep_info.get('Score', 'N/A')}", f"{sleep_info.get('Qualifier', '')}")
                if not df_health.empty:
                    latest = df_health.iloc[0]
                    st.metric("Resting HR", f"{latest.get('Resting_HR', 'N/A')} bpm")
                    st.metric("Body Battery Peak", f"{latest.get('Body_Battery_Max', 'N/A')} / 100")
            with c2:
                st.markdown(f"### Guidance Context ({sleep_info.get('Date', 'Recent Session')})")
                st.info(sleep_info.get('Feedback', 'No recommendations available.'))

        # TAB 3: ANÁLISIS DE SUEÑO
        with tab_sleep:
            st.subheader(f"Sleep Stage Distribution ({sleep_info.get('Date', 'Latest Session')})")
            if sleep_info and sleep_info.get('Total_Hours', 0) > 0:
                sc1, sc2 = st.columns([1, 2])
                with sc1:
                    st.metric("Total Duration", f"{sleep_info.get('Total_Hours', 0)} h")
                    st.metric("Deep Sleep", f"{sleep_info.get('Deep_Hours', 0)} h")
                    st.metric("Light Sleep", f"{sleep_info.get('Light_Hours', 0)} h")
                    st.metric("REM Sleep", f"{sleep_info.get('REM_Hours', 0)} h")
                
                with sc2:
                    sleep_stages = pd.DataFrame({
                        'Stage': ['Deep', 'Light', 'REM'],
                        'Hours': [sleep_info.get('Deep_Hours', 0), sleep_info.get('Light_Hours', 0), sleep_info.get('REM_Hours', 0)]
                    })
                    fig_sleep = px.pie(sleep_stages, values='Hours', names='Stage', title="Sleep Stage Breakdown", color_discrete_sequence=px.colors.sequential.Darkmint)
                    fig_sleep.update_layout(template="plotly_white")
                    st.plotly_chart(fig_sleep, use_container_width=True)
            else:
                st.warning("No detailed sleep stage data returned for recent days.")

        # TAB 4: HRV Y RESPIRACIÓN
        with tab_hrv_resp:
            st.subheader("Heart Rate Variability & Respiration")
            col_hrv, col_resp = st.columns(2)
            with col_hrv:
                st.markdown("### 🫀 HRV Status")
                st.metric("HRV Status", f"{hrv_data.get('Status', 'N/A').title()}")
                st.metric("Last Night Avg", f"{hrv_data.get('Last_Night_Avg', 'N/A')} ms")
                st.metric("7-Day Baseline Avg", f"{hrv_data.get('Weekly_Avg', 'N/A')} ms")
            with col_resp:
                st.markdown("### 🫁 Respiration Rate")
                st.metric("Awake Respiration", f"{respiration_data.get('Avg_Waking', 'N/A')} br/pm")
                st.metric("Sleep Respiration", f"{respiration_data.get('Avg_Sleep', 'N/A')} br/pm")

        # TAB 5: HEATMAP
        with tab_heat:
            st.subheader("Activity Volume Matrix")
            if not df_acts.empty:
                hm = df_acts.groupby('Date')['Distance_km'].sum().reset_index()
                hm['Date'] = pd.to_datetime(hm['Date'])
                hm['DayOfWeek'] = hm['Date'].dt.day_name()
                hm['WeekNumber'] = hm['Date'].dt.isocalendar().week
                fig_heat = px.scatter(
                    hm, x='WeekNumber', y='DayOfWeek', size='Distance_km', color='Distance_km',
                    color_continuous_scale="Oranges", template="plotly_white",
                    category_orders={"DayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]}
                )
                fig_heat.update_layout(yaxis_autorange="reversed")
                st.plotly_chart(fig_heat, use_container_width=True)

        # TAB 6: PROGRESIÓN MENSUAL
        with tab_monthly:
            st.subheader("Monthly Progress")
            if not df_acts.empty:
                monthly_agg = df_acts.groupby(['Year', 'MonthNum', 'Month'])['Distance_km'].sum().reset_index().sort_values(by=['Year', 'MonthNum'])
                fig_monthly = px.bar(monthly_agg, x='Month', y='Distance_km', color=monthly_agg['Year'].astype(str), barmode='group', template="plotly_white")
                st.plotly_chart(fig_monthly, use_container_width=True)

        # TAB 7: SALUD Y ESTRÉS
        with tab_health:
            st.subheader("Body Battery & Stress Dynamics")
            if not df_health.empty:
                fig_health = go.Figure()
                fig_health.add_trace(go.Scatter(x=df_health['Date'], y=df_health['Body_Battery_Max'], name='Body Battery Max', line=dict(color='limegreen', width=3)))
                fig_health.add_trace(go.Scatter(x=df_health['Date'], y=df_health['Avg_Stress'], name='Avg Stress Score', line=dict(color='crimson', width=2)))
                fig_health.update_layout(template="plotly_white")
                st.plotly_chart(fig_health, use_container_width=True)

        # TAB 8: INFORME SEMANAL DETALLADO
        with tab_weekly:
            st.markdown("# 📊 WEEKLY TRAINING REPORT")
            
            last_monday = get_last_monday()
            week_end = last_monday + timedelta(days=6)
            st.caption(f"📅 {last_monday.strftime('%A, %B %d')} → {week_end.strftime('%A, %B %d, %Y')}")
            
            if not df_acts.empty:
                df_week = df_acts[df_acts['Date'] >= last_monday].copy()
                
                if len(df_week) > 0:
                    df_week['Sport'] = df_week.apply(categorize_sport, axis=1)
                    
                    if sleep_info and sleep_info.get('Total_Hours', 0) > 0:
                        sl1, sl2 = st.columns(2)
                        with sl1:
                            st.metric("😴 Avg Sleep per Night", f"{sleep_info.get('Total_Hours', 0):.1f} h")
                        with sl2:
                            st.metric("⭐ Sleep Score", f"{sleep_info.get('Score', 'N/A')}/100")
                    
                    st.divider()
                    
                    st.markdown("### 💪 WEEKLY TOTALS BY DISCIPLINE")
                    summary_cols = st.columns(4)
                    
                    sports = ['Ciclismo', 'Carrera', 'Natación', 'Fuerza']
                    sport_emojis = {'Ciclismo': '🚴‍♀️', 'Carrera': '🏃‍♀️', 'Natación': '🏊‍♀️', 'Fuerza': '🏋️‍♀️'}
                    
                    for idx, sport in enumerate(sports):
                        df_sport = df_week[df_week['Sport'] == sport]
                        emoji = sport_emojis.get(sport, '⚡')
                        
                        if len(df_sport) > 0:
                            total_km = df_sport['Distance_km'].sum()
                            total_min = df_sport['Duration_min'].sum()
                            total_hrs = int(total_min // 60)
                            total_mins = int(total_min % 60)
                            count = len(df_sport)
                            
                            with summary_cols[idx]:
                                st.metric(f"{emoji} {sport}", f"{total_km:.1f} km", f"{count} ses. • {total_hrs}h {total_mins}m")
                        else:
                            with summary_cols[idx]:
                                st.metric(f"{emoji} {sport}", "—", "No sessions")
                    
                    st.divider()
                    
                    st.markdown("### 🎯 WORKOUT LOG")
                    
                    df_week_sorted = df_week.sort_values('Date', ascending=False)
                    
                    for idx, (_, activity) in enumerate(df_week_sorted.iterrows()):
                        sport = activity.get('Sport', 'Otro')
                        sport_emoji = {'Natación': '🏊‍♀️', 'Ciclismo': '🚴‍♀️', 'Carrera': '🏃‍♀️', 'Fuerza': '🏋️‍♀️'}.get(sport, '⚡')
                        
                        distance_km = activity.get('Distance_km', 0)
                        duration_min = activity.get('Duration_min', 0)
                        moving_duration_min = activity.get('MovingDuration_min', 0)
                        
                        time_hms = format_time_hms(duration_min)
                        pace_speed = calculate_pace_speed(sport, distance_km, duration_min, moving_duration_min)
                        training_type = get_training_type(activity)
                        
                        perceived_effort, feeling = get_perceived_effort_and_feeling(activity)
                        
                        avg_hr_val = activity.get('averageHR')
                        avg_hr = int(avg_hr_val) if pd.notna(avg_hr_val) and avg_hr_val else 0
                        
                        cal_val = activity.get('Active_Calories')
                        calories = int(cal_val) if pd.notna(cal_val) and cal_val else 0
                        
                        comments = get_activity_comments(activity)
                        
                        # Tarjeta Limpia de Actividad
                        st.markdown(f"""
                        <div class="activity-card">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <span style="font-size: 1.15rem; font-weight: 700;">{sport_emoji} {activity.get('activityName', 'Entrenamiento')}</span>
                                <span style="color: #666; font-size: 0.85rem; font-weight: 500;">{activity['Date'].strftime('%a, %b %d')}</span>
                            </div>
                            <div style="font-size: 1.8rem; font-weight: 800; margin: 8px 0;">
                                {distance_km:.2f} <span style="font-size: 0.9rem; color: #fc4c02; font-weight: 700;">KM</span> &nbsp;•&nbsp; {time_hms}
                            </div>
                            <div style="margin-bottom: 4px;">
                                <span class="badge-type">🏷️ {training_type}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Métricas adicionales (5 columnas con Esfuerzo Percibido y Sensación)
                        m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns(5)
                        
                        m_col1.metric("⚡ Ritmo (Mov.)", pace_speed)
                        m_col2.metric("❤️ FC Promedio", f"{avg_hr} bpm" if avg_hr > 0 else "—")
                        m_col3.metric("🔥 Calorías", f"{calories} kcal" if calories > 0 else "—")
                        m_col4.metric("📊 Esfuerzo (RPE)", f"{perceived_effort}/10" if perceived_effort > 0 else "Sin anotar")
                        m_col5.metric("🎭 Sensación", feeling if feeling else "Sin anotar")
                            
                        if comments:
                            st.caption(f"💬 *\"{comments}\"*")
                            
                        st.divider()
                    
                    # EXPORTACIÓN PDF
                    st.markdown("### 📥 Export Report")
                    
                    if st.button("📄 Download Weekly Report as PDF", key="download_pdf"):
                        try:
                            from reportlab.lib.pagesizes import A4
                            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                            from reportlab.lib.units import inch
                            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
                            from reportlab.lib import colors
                            from io import BytesIO
                            
                            pdf_buffer = BytesIO()
                            doc = SimpleDocTemplate(pdf_buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
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
                            story.append(Spacer(1, 0.2*inch))
                            
                            period_text = f"{last_monday.strftime('%A, %B %d')} → {week_end.strftime('%A, %B %d, %Y')}"
                            story.append(Paragraph(period_text, styles['Normal']))
                            story.append(Spacer(1, 0.3*inch))
                            
                            if sleep_info and sleep_info.get('Total_Hours', 0) > 0:
                                story.append(Paragraph("Sleep Summary", styles['Heading2']))
                                sleep_data = [
                                    ['Metric', 'Value'],
                                    ['Avg Sleep per Night', f"{sleep_info.get('Total_Hours', 0):.1f} h"],
                                    ['Sleep Score', f"{sleep_info.get('Score', 'N/A')}/100"]
                                ]
                                sleep_table = Table(sleep_data, colWidths=[3*inch, 2*inch])
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
                                story.append(Spacer(1, 0.3*inch))
                            
                            story.append(Paragraph("Weekly Totals by Discipline", styles['Heading2']))
                            summary_data = [['Sport', 'Distance (km)', 'Sessions', 'Time']]
                            for sport in sports:
                                df_sport = df_week[df_week['Sport'] == sport]
                                if len(df_sport) > 0:
                                    total_km = df_sport['Distance_km'].sum()
                                    total_min = df_sport['Duration_min'].sum()
                                    total_hrs = int(total_min // 60)
                                    total_mins = int(total_min % 60)
                                    summary_data.append([sport, f"{total_km:.1f}", str(len(df_sport)), f"{total_hrs}h {total_mins}m"])
                            
                            summary_table = Table(summary_data, colWidths=[1.5*inch, 1.5*inch, 1.5*inch, 1.5*inch])
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
                            story.append(Spacer(1, 0.3*inch))
                            
                            story.append(Paragraph("Workout Details", styles['Heading2']))
                            for _, activity in df_week_sorted.iterrows():
                                sport = activity.get('Sport', 'Otro')
                                sport_emoji = {'Natación': '🏊‍♀️', 'Ciclismo': '🚴‍♀️', 'Carrera': '🏃‍♀️', 'Fuerza': '🏋️‍♀️'}.get(sport, '⚡')
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
                                story.append(Spacer(1, 0.1*inch))
                            
                            doc.build(story)
                            pdf_buffer.seek(0)
                            
                            st.download_button(
                                label="✅ PDF Ready - Click to Download",
                                data=pdf_buffer,
                                file_name=f"Weekly_Report_{last_monday.strftime('%Y%m%d')}.pdf",
                                mime="application/pdf",
                                key="pdf_download"
                            )
                            st.success("✅ PDF generated successfully!")
                        except ImportError:
                            st.error("📦 Please install reportlab: `pip install reportlab`")
                        except Exception as e:
                            st.error(f"Error generating PDF: {e}")
                else:
                    st.warning("No workouts found for this week.")
            else:
                st.warning("No activity data available.")

        # TAB 9: REGISTRO DE ACTIVIDADES
        with tab_logs:
            st.subheader("Activity Registry")
            if not df_acts.empty:
                cols = ['activityName', 'Sport', 'Date', 'Distance_km', 'Duration_min', 'Elevation_m', 'Effort']
                avail = [c for c in cols if c in df_acts.columns]
                st.dataframe(df_acts[avail].sort_values(by='Date', ascending=False), use_container_width=True, hide_index=True)

else:
    st.info("👈 Enter your Garmin Connect credentials in the sidebar to load Patri's Data Lab.")