import os
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, timedelta
from garminconnect import Garmin

st.set_page_config(page_title="Patri's Data", layout="wide", page_icon="🧬")
st.title("🧬 Patri's Data")
st.caption("Private local intelligence: Training Load, Fitness/Fatigue, Recovery & Biometrics.")

TOKEN_DIR = os.path.expanduser("~/.garminconnect")

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

# --- BANISTER TRAINING LOAD ENGINE ---
def compute_training_load(df_acts, days_back=365):
    """Calculates Effort, Fitness (CTL - 42d), Fatigue (ATL - 7d), and Form (TSB)."""
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
    
    # 1. SLEEP & DAILY STATS EXTRACTION
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

    # Fallback for Sleep Data
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

    # 2. HRV & RESPIRATION EXTRACTION
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

    # 3. ACTIVITIES EXTRACTION
    start_date = datetime.now() - timedelta(days=days_back + 60)
    raw_acts = _client.get_activities_by_date(start_date.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
    df_acts = pd.DataFrame(raw_acts) if raw_acts else pd.DataFrame()
    
    if not df_acts.empty:
        df_acts['Date'] = pd.to_datetime(df_acts.get('startTimeLocal', datetime.now())).dt.date
        df_acts['DateTime'] = pd.to_datetime(df_acts.get('startTimeLocal', datetime.now()))
        df_acts['Distance_km'] = df_acts.get('distance', 0) / 1000.0
        df_acts['Duration_min'] = df_acts.get('duration', 0) / 60.0
        df_acts['Elevation_m'] = df_acts.get('elevationGain', 0)
        df_acts['Sport'] = df_acts['activityType'].apply(lambda x: x.get('typeKey', 'Other') if isinstance(x, dict) else 'Other') if 'activityType' in df_acts.columns else 'Other'
        df_acts['Year'] = df_acts['DateTime'].dt.year
        df_acts['Month'] = df_acts['DateTime'].dt.strftime('%b')
        df_acts['MonthNum'] = df_acts['DateTime'].dt.month

    return df_health, sleep_info, hrv_data, respiration_data, df_acts

# --- SIDEBAR CONTROLS ---
st.sidebar.header("🔒 Private Credentials")
email = st.sidebar.text_input("Garmin Email")
password = st.sidebar.text_input("Garmin Password", type="password")
days = st.sidebar.slider("Analysis Window (Days)", 30, 1095, 365, step=30)

if email and password:
    client = get_garmin_client(email, password)
    if client:
        df_health, sleep_info, hrv_data, respiration_data, df_acts = load_all_garmin_data(client, days)
        df_load = compute_training_load(df_acts, days)

        # Global KPIs
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

        # DASHBOARD TABS
        tab_load, tab_guidance, tab_sleep, tab_hrv_resp, tab_heat, tab_monthly, tab_health, tab_logs = st.tabs([
            "📈 SportTracks Training Load",
            "💡 Daily Guidance",
            "🌙 Sleep Analysis",
            "🫀 HRV & Respiration",
            "📅 Heatmap", 
            "📊 Monthly Progression", 
            "🩺 Health & Stress", 
            "📋 Activity Log"
        ])

        # TAB 1: SPORTTRACKS TRAINING LOAD MODEL
        with tab_load:
            st.subheader("SportTracks Training Load Model (Banister Framework)")
            st.caption("Tracks long-term Fitness (CTL), short-term Fatigue (ATL), and Form (TSB) over time.")
            
            fig_tl = go.Figure()
            fig_tl.add_trace(go.Bar(x=df_load['Date'], y=df_load['Effort'], name='Daily Effort', marker_color='rgba(200, 200, 200, 0.4)'))
            fig_tl.add_trace(go.Scatter(x=df_load['Date'], y=df_load['Fitness_CTL'], name='Fitness (CTL - 42d)', line=dict(color='dodgerblue', width=3)))
            fig_tl.add_trace(go.Scatter(x=df_load['Date'], y=df_load['Fatigue_ATL'], name='Fatigue (ATL - 7d)', line=dict(color='crimson', width=2)))
            fig_tl.add_trace(go.Scatter(x=df_load['Date'], y=df_load['Form_TSB'], name='Form (TSB)', line=dict(color='mediumseagreen', width=2, dash='dot')))

            fig_tl.update_layout(
                title="Fitness, Fatigue, and Form Chart",
                xaxis_title="Date",
                yaxis_title="Load / Impulse Points",
                hovermode="x unified",
                template="plotly_white",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_tl, use_container_width=True)

        # TAB 2: GUIDANCE
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

        # TAB 3: SLEEP ANALYSIS (RESTORED)
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
                    st.plotly_chart(fig_sleep, use_container_width=True)
            else:
                st.warning("No detailed sleep stage data returned for recent days.")

        # TAB 4: HRV & RESPIRATION
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
                    color_continuous_scale="Viridis", template="plotly_white",
                    category_orders={"DayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]}
                )
                fig_heat.update_layout(yaxis_autorange="reversed")
                st.plotly_chart(fig_heat, use_container_width=True)

        # TAB 6: MONTHLY PROGRESSION
        with tab_monthly:
            st.subheader("Monthly Progress")
            if not df_acts.empty:
                monthly_agg = df_acts.groupby(['Year', 'MonthNum', 'Month'])['Distance_km'].sum().reset_index().sort_values(by=['Year', 'MonthNum'])
                fig_monthly = px.bar(monthly_agg, x='Month', y='Distance_km', color=monthly_agg['Year'].astype(str), barmode='group', template="plotly_white")
                st.plotly_chart(fig_monthly, use_container_width=True)

        # TAB 7: HEALTH
        with tab_health:
            st.subheader("Body Battery & Stress Dynamics")
            if not df_health.empty:
                fig_health = go.Figure()
                fig_health.add_trace(go.Scatter(x=df_health['Date'], y=df_health['Body_Battery_Max'], name='Body Battery Max', line=dict(color='limegreen', width=3)))
                fig_health.add_trace(go.Scatter(x=df_health['Date'], y=df_health['Avg_Stress'], name='Avg Stress Score', line=dict(color='crimson', width=2)))
                fig_health.update_layout(template="plotly_white")
                st.plotly_chart(fig_health, use_container_width=True)

        # TAB 8: LOGS
        with tab_logs:
            st.subheader("Activity Registry")
            if not df_acts.empty:
                cols = ['activityName', 'Sport', 'Date', 'Distance_km', 'Duration_min', 'Elevation_m', 'Effort']
                avail = [c for c in cols if c in df_acts.columns]
                st.dataframe(df_acts[avail].sort_values(by='Date', ascending=False), use_container_width=True, hide_index=True)

else:
    st.info("👈 Enter your Garmin Connect credentials in the sidebar to load Patri's Data.")