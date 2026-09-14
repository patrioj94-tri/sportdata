import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import timedelta

from garmin_data import (
    get_garmin_client,
    load_all_garmin_data,
    compute_training_load,
    get_training_readiness_today,
    get_training_status_today,
)
from formatting import (
    get_last_monday,
    format_hours_minutes,
    format_time_hms,
    calculate_pace_speed,
    get_training_type,
    get_perceived_effort_and_feeling,
    get_activity_comments,
    categorize_sport,
    extract_training_status_label,
    LEVEL_MAP,
)
from pdf_report import build_weekly_report_pdf

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
        readiness = get_training_readiness_today(client)
        training_status_raw = get_training_status_today(client)
        status_label, status_explanation = extract_training_status_label(training_status_raw)

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
        m4.metric("Sleep Score", f"{sleep_info.get('Score', 'N/A')}/100", format_hours_minutes(sleep_info.get('Total_Hours', 0)))
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

        # TAB 2: RECOMENDACIONES (con datos reales de Garmin: Training Readiness + Training Status)
        with tab_guidance:
            st.subheader("💡 Daily Recovery & Garmin Recommendations")

            readiness_score = readiness.get('score')
            readiness_level = readiness.get('level')
            feedback_long = readiness.get('feedbackLong')
            feedback_short = readiness.get('feedbackShort')

            c1, c2 = st.columns([1, 2])
            with c1:
                if readiness_score:
                    st.metric(
                        "🎯 Training Readiness",
                        f"{readiness_score}/100",
                        LEVEL_MAP.get(str(readiness_level).upper(), str(readiness_level).title() if readiness_level else '')
                    )
                st.metric("Sleep Score", f"{sleep_info.get('Score', 'N/A')}", f"{sleep_info.get('Qualifier', '')}")
                if not df_health.empty:
                    latest = df_health.iloc[0]
                    st.metric("Resting HR", f"{latest.get('Resting_HR', 'N/A')} bpm")
                    st.metric("Body Battery Peak", f"{latest.get('Body_Battery_Max', 'N/A')} / 100")

            with c2:
                if status_label:
                    st.markdown(f"### {status_label}")
                    st.info(status_explanation)
                else:
                    st.markdown(f"### Guidance Context ({sleep_info.get('Date', 'Recent Session')})")

                if readiness_score:
                    st.markdown("**📋 Recomendación de Garmin para hoy**")
                    st.info(feedback_long or feedback_short or 'No hay recomendación disponible para hoy.')

                    factors = [
                        ('😴 Sueño', readiness.get('sleepScoreFactorPercent')),
                        ('🫀 HRV', readiness.get('hrvFactorPercent')),
                        ('🔋 Recuperación', readiness.get('recoveryTimeFactorPercent')),
                        ('🏋️ Carga', readiness.get('acwrFactorPercent')),
                        ('😰 Estrés', readiness.get('stressHistoryFactorPercent')),
                    ]
                    factors = [(label, val) for label, val in factors if val is not None]
                    if factors:
                        st.caption("Factores que están afectando tu forma hoy (según Garmin):")
                        fcols = st.columns(len(factors))
                        for col, (label, val) in zip(fcols, factors):
                            col.metric(label, f"{val:+d}%" if isinstance(val, (int, float)) else str(val))

                    recovery_hours = readiness.get('recoveryTime')
                    if recovery_hours:
                        st.caption(f"⏱️ Tiempo de recuperación estimado: {recovery_hours}h")
                elif not status_label:
                    st.info(sleep_info.get('Feedback', 'No recommendations available.'))

        # TAB 3: ANÁLISIS DE SUEÑO
        with tab_sleep:
            st.subheader(f"Sleep Stage Distribution ({sleep_info.get('Date', 'Latest Session')})")
            if sleep_info and sleep_info.get('Total_Hours', 0) > 0:
                sc1, sc2 = st.columns([1, 2])
                with sc1:
                    st.metric("Total Duration", format_hours_minutes(sleep_info.get('Total_Hours', 0)))
                    st.metric("Deep Sleep", format_hours_minutes(sleep_info.get('Deep_Hours', 0)))
                    st.metric("Light Sleep", format_hours_minutes(sleep_info.get('Light_Hours', 0)))
                    st.metric("REM Sleep", format_hours_minutes(sleep_info.get('REM_Hours', 0)))

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
                            st.metric("😴 Avg Sleep per Night", format_hours_minutes(sleep_info.get('Total_Hours', 0)))
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

                        perceived_effort, feeling = get_perceived_effort_and_feeling(activity, client)

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
                            pdf_buffer = build_weekly_report_pdf(df_week_sorted, sleep_info, sports, last_monday, week_end)

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
