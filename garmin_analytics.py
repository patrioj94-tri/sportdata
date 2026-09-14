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
    get_activity_splits,
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
    SPORT_EMOJIS,
    SPORT_COLORS,
    FEELING_OPTIONS,
    get_intensity_color,
    weekly_overall_totals,
    weekly_totals_by_sport,
    build_week_calendar,
    format_activity_headline,
    format_discipline_headline,
    format_discipline_delta,
    build_stat_row,
    format_rpe_pill,
    format_lap_row,
)
from pdf_report import build_weekly_report_pdf

# --- CONFIGURACIÓN DE PÁGINA Y ESTILOS ---
st.set_page_config(page_title="Patri's Data Lab", layout="wide", page_icon="🏊‍♀️")

st.markdown("""
<style>
    .strava-card {
        background-color: #ffffff;
        border-radius: 14px;
        padding: 16px 18px;
        margin-bottom: 4px;
        box-shadow: 0 1px 2px rgba(24,22,20,.06), 0 8px 20px -12px rgba(24,22,20,.15);
    }
    .strava-top {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 12px;
    }
    .icon-badge {
        width: 38px;
        height: 38px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.05rem;
        flex-shrink: 0;
        color: #fff;
        background: var(--sport-color, #fc4c02);
    }
    .strava-top .who {
        flex: 1;
        min-width: 0;
    }
    .strava-top .title {
        font-weight: 700;
        font-size: 1rem;
        line-height: 1.25;
    }
    .strava-top .meta {
        font-size: 0.78rem;
        color: #767676;
        margin-top: 2px;
    }
    .rpe-pill {
        font-size: 0.7rem;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 100px;
        color: #fff;
        background: var(--pill-color, #767676);
        flex-shrink: 0;
        white-space: nowrap;
    }
    .stat-row {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        border-top: 1px solid #eee;
        padding-top: 12px;
        gap: 4px;
    }
    .stat-row .stat .v {
        font-weight: 700;
        font-size: 1.2rem;
        line-height: 1;
        color: #181614;
    }
    .stat-row .stat .l {
        font-size: 0.65rem;
        color: #767676;
        text-transform: uppercase;
        letter-spacing: .04em;
        margin-top: 3px;
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
        df_health, sleep_info, hrv_data, respiration_data, df_acts = load_all_garmin_data(client, days, user_key=email)
        df_load = compute_training_load(df_acts, days)
        readiness = get_training_readiness_today(client, user_key=email)
        training_status_raw = get_training_status_today(client, user_key=email)
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

            if 'weekly_report_monday' not in st.session_state:
                st.session_state.weekly_report_monday = get_last_monday()

            current_monday = get_last_monday()
            selected_monday = st.session_state.weekly_report_monday
            week_end = selected_monday + timedelta(days=6)

            nav1, nav2, nav3 = st.columns([1, 3, 1])
            with nav1:
                if st.button("◀ Semana anterior", key="prev_week"):
                    st.session_state.weekly_report_monday = selected_monday - timedelta(days=7)
                    st.rerun()
            with nav2:
                st.markdown(f"<div style='text-align:center'>📅 <b>{selected_monday.strftime('%d %b')} → {week_end.strftime('%d %b, %Y')}</b></div>", unsafe_allow_html=True)
                if selected_monday != current_monday:
                    if st.button("↩️ Volver a esta semana", key="reset_week"):
                        st.session_state.weekly_report_monday = current_monday
                        st.rerun()
            with nav3:
                if selected_monday < current_monday:
                    if st.button("Semana siguiente ▶", key="next_week"):
                        st.session_state.weekly_report_monday = selected_monday + timedelta(days=7)
                        st.rerun()

            # Contexto de forma del día (Training Readiness / Status de Garmin)
            if readiness.get('score') or status_label:
                rc1, rc2 = st.columns(2)
                with rc1:
                    if readiness.get('score'):
                        st.metric("🎯 Training Readiness (hoy)", f"{readiness.get('score')}/100")
                with rc2:
                    if status_label:
                        st.caption(f"{status_label} — {status_explanation}")

            health_comment = st.text_area(
                "💬 Comentario sobre tu estado de salud/forma esta semana (aparecerá en el informe)",
                value=st.session_state.get("health_comment", ""),
                key="health_comment",
                height=70,
            )

            st.divider()

            if not df_acts.empty:
                df_week = df_acts[(df_acts['Date'] >= selected_monday) & (df_acts['Date'] <= week_end)].copy()
                prev_monday = selected_monday - timedelta(days=7)
                prev_week_end = selected_monday - timedelta(days=1)
                df_prev_week = df_acts[(df_acts['Date'] >= prev_monday) & (df_acts['Date'] <= prev_week_end)].copy()

                if len(df_week) > 0:
                    df_week['Sport'] = df_week.apply(categorize_sport, axis=1)
                    if not df_prev_week.empty:
                        df_prev_week['Sport'] = df_prev_week.apply(categorize_sport, axis=1)

                    if sleep_info and sleep_info.get('Total_Hours', 0) > 0:
                        sl1, sl2 = st.columns(2)
                        with sl1:
                            st.metric("😴 Avg Sleep per Night", format_hours_minutes(sleep_info.get('Total_Hours', 0)))
                        with sl2:
                            st.metric("⭐ Sleep Score", f"{sleep_info.get('Score', 'N/A')}/100")
                        st.divider()

                    # Tira de calendario Lun-Dom
                    st.markdown("### 🗓️ Vista de la semana")
                    calendar_days = build_week_calendar(df_week, selected_monday)
                    cal_cols = st.columns(7)
                    for col, day_info in zip(cal_cols, calendar_days):
                        with col:
                            st.markdown(f"**{day_info['date'].strftime('%a')}**")
                            st.caption(day_info['date'].strftime('%d/%m'))
                            st.markdown(" ".join(day_info['emojis']) if day_info['emojis'] else "💤")

                    st.divider()

                    # Resumen total de la semana, comparado con la anterior
                    overall = weekly_overall_totals(df_week)
                    overall_prev = weekly_overall_totals(df_prev_week)

                    st.markdown("### 📦 RESUMEN TOTAL DE LA SEMANA")
                    tot1, tot2, tot3 = st.columns(3)
                    tot1.metric("Distancia total", f"{overall['km']:.1f} km", f"{overall['km'] - overall_prev['km']:+.1f} km vs. sem. ant.")
                    tot2.metric("Tiempo total", format_hours_minutes(overall['minutes'] / 60), f"{(overall['minutes'] - overall_prev['minutes']) / 60:+.1f} h vs. sem. ant.")
                    tot3.metric("Sesiones", f"{overall['sessions']}", f"{overall['sessions'] - overall_prev['sessions']:+d} vs. sem. ant.")

                    st.divider()

                    st.markdown("### 💪 WEEKLY TOTALS BY DISCIPLINE")
                    summary_cols = st.columns(4)

                    sports = ['Ciclismo', 'Carrera', 'Natación', 'Fuerza']
                    totals_by_sport = weekly_totals_by_sport(df_week, sports)
                    prev_totals_by_sport = weekly_totals_by_sport(df_prev_week, sports)

                    for idx, sport in enumerate(sports):
                        emoji = SPORT_EMOJIS.get(sport, '⚡')
                        t = totals_by_sport[sport]
                        prev_t = prev_totals_by_sport[sport]

                        with summary_cols[idx]:
                            if t['sessions'] > 0:
                                headline = format_discipline_headline(sport, t['km'], t['minutes'])
                                delta_text = format_discipline_delta(sport, t, prev_t)
                                st.metric(f"{emoji} {sport}", headline, delta_text)
                                total_hrs = int(t['minutes'] // 60)
                                total_mins = int(t['minutes'] % 60)
                                st.caption(f"{t['sessions']} ses. • {total_hrs}h {total_mins}m")
                            else:
                                st.metric(f"{emoji} {sport}", "—", "No sessions")

                    st.divider()

                    st.markdown("### 🎯 WORKOUT LOG")
                    st.caption("Puedes corregir el RPE, la sensación y añadir un comentario antes de generar el informe.")

                    df_week_sorted = df_week.sort_values('Date', ascending=False)
                    unique_days = sorted(df_week_sorted['Date'].unique(), reverse=True)
                    workout_entries = []

                    for day_idx, day in enumerate(unique_days):
                        day_acts = df_week_sorted[df_week_sorted['Date'] == day]
                        day_label = day.strftime('%A, %d %b')
                        n = len(day_acts)
                        with st.expander(f"📅 {day_label} ({n} entreno{'s' if n != 1 else ''})", expanded=(day_idx == 0)):
                            for act_idx, (_, activity) in enumerate(day_acts.iterrows()):
                                sport = activity.get('Sport', 'Otro')
                                sport_emoji = SPORT_EMOJIS.get(sport, '⚡')
                                sport_color = SPORT_COLORS.get(sport, '#fc4c02')
                                activity_id = activity.get('activityId')

                                distance_km = activity.get('Distance_km', 0)
                                duration_min = activity.get('Duration_min', 0)
                                moving_duration_min = activity.get('MovingDuration_min', 0)

                                time_hms = format_time_hms(duration_min)
                                pace_speed = calculate_pace_speed(sport, distance_km, duration_min, moving_duration_min)
                                training_type = get_training_type(activity)
                                headline_value, headline_unit, show_time = format_activity_headline(sport, distance_km, duration_min)

                                default_rpe, default_feeling = get_perceived_effort_and_feeling(activity, client)
                                default_feeling_option = default_feeling if default_feeling in FEELING_OPTIONS else 'Sin anotar'
                                default_comment = get_activity_comments(activity) or ''
                                default_title = activity.get('activityName', 'Entrenamiento')

                                rpe_key = f"rpe_{activity_id}"
                                feeling_key = f"feeling_{activity_id}"
                                comment_key = f"comment_{activity_id}"
                                title_key = f"title_{activity_id}"
                                detail_key = f"show_detail_{activity_id}"

                                perceived_effort = st.session_state.get(rpe_key, default_rpe)
                                feeling = st.session_state.get(feeling_key, default_feeling_option)
                                comments = st.session_state.get(comment_key, default_comment)
                                title = st.session_state.get(title_key, default_title)
                                card_color = get_intensity_color(perceived_effort)

                                avg_hr_val = activity.get('averageHR')
                                avg_hr = int(avg_hr_val) if pd.notna(avg_hr_val) and avg_hr_val else 0

                                cal_val = activity.get('Active_Calories')
                                calories = int(cal_val) if pd.notna(cal_val) and cal_val else 0

                                # Tarjeta estilo Strava: icono de disciplina, título, píldora de esfuerzo, stats en fila
                                stats = build_stat_row(sport, distance_km, time_hms, pace_speed, avg_hr, calories)
                                stats_html = "".join(f'<div class="stat"><div class="v">{v}</div><div class="l">{l}</div></div>' for v, l in stats)
                                rpe_pill_text = format_rpe_pill(perceived_effort, feeling)

                                st.markdown(f"""
                                <div class="strava-card">
                                    <div class="strava-top" style="--sport-color: {sport_color};">
                                        <div class="icon-badge">{sport_emoji}</div>
                                        <div class="who">
                                            <div class="title">{title}</div>
                                            <div class="meta">{activity['Date'].strftime('%a, %b %d')} · {training_type}</div>
                                        </div>
                                        <div class="rpe-pill" style="--pill-color: {card_color};">{rpe_pill_text}</div>
                                    </div>
                                    <div class="stat-row">{stats_html}</div>
                                </div>
                                """, unsafe_allow_html=True)

                                if detail_key not in st.session_state:
                                    st.session_state[detail_key] = False

                                btn_label = "🔼 Ocultar detalle" if st.session_state[detail_key] else "🔍 Ver entrenamiento / intervalos"
                                if st.button(btn_label, key=f"toggle_{activity_id}"):
                                    st.session_state[detail_key] = not st.session_state[detail_key]
                                    st.rerun()

                                if st.session_state[detail_key]:
                                    with st.container(border=True):
                                        st.markdown("**✏️ Editar entreno**")
                                        title = st.text_input("Título", value=title, key=title_key)
                                        ec1, ec2 = st.columns(2)
                                        with ec1:
                                            perceived_effort = st.slider("📊 Esfuerzo (RPE)", 0, 10, value=int(perceived_effort), key=rpe_key)
                                        with ec2:
                                            feeling = st.selectbox("🎭 Sensación", FEELING_OPTIONS, index=FEELING_OPTIONS.index(feeling), key=feeling_key)
                                        comments = st.text_area("💬 Comentario", value=comments, key=comment_key, height=68)

                                        st.markdown("**📊 Intervalos / Series**")
                                        laps = get_activity_splits(client, activity_id) if activity_id else []
                                        if laps:
                                            lap_rows = [format_lap_row(sport, lap) for lap in laps]
                                            st.dataframe(pd.DataFrame(lap_rows), use_container_width=True, hide_index=True)
                                        else:
                                            st.caption("Esta actividad no tiene series/intervalos guardados en Garmin.")

                                workout_entries.append({
                                    'sport': sport, 'sport_emoji': sport_emoji,
                                    'activity_name': title,
                                    'date': activity['Date'], 'headline_value': headline_value,
                                    'headline_unit': headline_unit, 'show_time': show_time,
                                    'time_hms': time_hms, 'pace_speed': pace_speed, 'training_type': training_type,
                                    'avg_hr': avg_hr, 'calories': calories, 'rpe': perceived_effort,
                                    'feeling': feeling, 'comment': comments, 'card_color': card_color,
                                })

                                if act_idx < n - 1:
                                    st.divider()

                    st.divider()

                    # EXPORTACIÓN PDF
                    st.markdown("### 📥 Export Report")

                    if st.button("📄 Download Weekly Report as PDF", key="download_pdf"):
                        try:
                            pdf_buffer = build_weekly_report_pdf(
                                workout_entries, df_week, sleep_info, sports, selected_monday, week_end,
                                health_comment=health_comment,
                                readiness=readiness, status_label=status_label, status_explanation=status_explanation,
                                prev_totals_by_sport=prev_totals_by_sport, overall=overall, overall_prev=overall_prev,
                            )

                            st.download_button(
                                label="✅ PDF Ready - Click to Download",
                                data=pdf_buffer,
                                file_name=f"Weekly_Report_{selected_monday.strftime('%Y%m%d')}.pdf",
                                mime="application/pdf",
                                key="pdf_download"
                            )
                            st.success("✅ PDF generated successfully!")
                        except ImportError:
                            st.error("📦 Please install reportlab and matplotlib: `pip install reportlab matplotlib`")
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
