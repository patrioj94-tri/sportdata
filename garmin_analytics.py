import hashlib
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, timedelta

from garmin_data import (
    get_garmin_client,
    get_garmin_client_from_token,
    load_all_garmin_data,
    compute_training_load,
    get_training_readiness_for_date,
    get_training_status_for_date,
    get_activity_splits,
    set_activity_title,
    set_activity_comment,
    set_activity_evaluation,
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
    translate_level,
    translate_sport,
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
    delta_class,
    FEELING_TO_GARMIN,
)
from pdf_report import build_weekly_report_pdf
from translations import t, set_language, get_language, LANGUAGES

# --- IDIOMA Y MODO DE VISTA ---
# Se leen antes que nada: el layout (ancho/móvil) solo puede fijarse en set_page_config,
# que tiene que ser la primera llamada de Streamlit. Los selectores de la barra lateral
# escriben en session_state, así que en el rerun siguiente ya se aplica el valor nuevo.
view_mode = st.session_state.get('view_mode', 'desktop')
is_mobile = view_mode == 'mobile'
set_language(st.session_state.get('lang', 'es'))
lang = get_language()

# --- CONFIGURACIÓN DE PÁGINA Y ESTILOS ---
st.set_page_config(
    page_title="Patri's Data Lab",
    layout="centered" if is_mobile else "wide",
    page_icon="🏊‍♀️",
)

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
    /* En pantallas estrechas las 4 estadísticas se reparten en 2x2 en vez de apretarse */
    @media (max-width: 640px) {
        .stat-row { grid-template-columns: repeat(2, 1fr); row-gap: 10px; }
        .strava-top .title { font-size: 0.95rem; }
        .sticker-row { font-size: 1.6rem; }
    }
    .sticker-row {
        font-size: 2.1rem;
        line-height: 1.5;
        letter-spacing: 4px;
    }
    .week-hero {
        display: flex;
        gap: 14px;
        flex-wrap: wrap;
        margin-bottom: 4px;
    }
    .hero-tile {
        flex: 1;
        min-width: 140px;
        background: linear-gradient(155deg, #fff 0%, #fff8f4 100%);
        border-radius: 18px;
        padding: 18px 16px;
        text-align: center;
        box-shadow: 0 1px 2px rgba(24,22,20,.06), 0 8px 20px -12px rgba(24,22,20,.15);
    }
    .hero-tile .hero-icon { font-size: 1.8rem; }
    .hero-tile .hero-value {
        font-size: 1.7rem;
        font-weight: 800;
        margin-top: 4px;
        color: #181614;
    }
    .hero-tile .hero-label {
        font-size: 0.72rem;
        color: #767676;
        text-transform: uppercase;
        letter-spacing: .05em;
        margin-top: 2px;
    }
    .hero-tile .hero-delta {
        font-size: 0.82rem;
        font-weight: 700;
        margin-top: 8px;
    }
    .hero-tile .hero-delta.positive { color: #22c55e; }
    .hero-tile .hero-delta.negative { color: #ef4444; }
    .hero-tile .hero-delta.neutral { color: #767676; }
    .discipline-tile {
        background: #ffffff;
        border-radius: 16px;
        padding: 14px 12px;
        text-align: center;
        box-shadow: 0 1px 2px rgba(24,22,20,.06), 0 8px 20px -12px rgba(24,22,20,.15);
    }
    .discipline-tile .icon-badge { margin: 0 auto 8px; }
    .discipline-tile .d-value { font-size: 1.3rem; font-weight: 800; color: #181614; }
    .discipline-tile .d-label { font-size: 0.7rem; color: #767676; text-transform: uppercase; letter-spacing: .04em; margin-top: 2px; }
    .discipline-tile .d-delta { font-size: 0.75rem; font-weight: 700; margin-top: 6px; }
    .discipline-tile .d-delta.positive { color: #22c55e; }
    .discipline-tile .d-delta.negative { color: #ef4444; }
    .discipline-tile .d-delta.neutral { color: #767676; }
</style>
""", unsafe_allow_html=True)

# Título y Subtítulo Destacado
st.title("Patri's Data Lab 🏊‍♀️🚴‍♀️🏃‍♀️")
st.markdown("<p style='font-size: 1.35rem; font-weight: 800; color: #fc4c02; margin-top: -15px;'>Do it for fun!</p>", unsafe_allow_html=True)

# --- BARRA LATERAL ---
st.sidebar.selectbox(
    t('language'), options=list(LANGUAGES.keys()),
    format_func=lambda code: LANGUAGES[code], key='lang',
)
st.sidebar.radio(
    t('view_mode'), options=['desktop', 'mobile'],
    format_func=lambda v: t(f'view_{v}'), key='view_mode', horizontal=True,
)
st.sidebar.divider()

st.sidebar.header(t('credentials'))

# Garmin protege su pantalla de login con Cloudflare, que bloquea las IPs de servidores: por
# eso desde la app desplegada no funciona entrar con contraseña (HTTP 403). La alternativa es
# un token que cada persona genera una vez en su propio ordenador (ver generar_token.py) y
# pega aquí: vale ~1 año y evita el login bloqueado. En local la contraseña sigue funcionando.
login_method = st.sidebar.radio(
    t('login_method'), options=['token', 'password'],
    format_func=lambda m: t(f'login_{m}'), horizontal=True, key='login_method',
)

email = password = user_token = ""
if login_method == 'token':
    user_token = st.sidebar.text_area(t('paste_token'), height=90, key='user_token',
                                      placeholder='{"oauth1_token": ..., "oauth2_token": ...}')
    st.sidebar.caption(t('token_help'))
else:
    email = st.sidebar.text_input(t('garmin_email'))
    password = st.sidebar.text_input(t('garmin_password'), type="password")

days = st.sidebar.slider(t('analysis_window'), 30, 1095, 365, step=30)

if user_token.strip() or (email and password):
    if user_token.strip():
        # La clave de usuario sale del propio token, para que la caché no se mezcle entre personas
        email = hashlib.sha256(user_token.strip().encode()).hexdigest()[:16]
        client = get_garmin_client_from_token(user_token.strip(), user_key=email)
    else:
        client = get_garmin_client(email, password)

    if client:
        df_health, sleep_info, hrv_data, respiration_data, df_acts = load_all_garmin_data(client, days, user_key=email)
        df_load = compute_training_load(df_acts, days)
        today = datetime.now().date()
        readiness = get_training_readiness_for_date(client, today.isoformat(), user_key=email)
        training_status_raw = get_training_status_for_date(client, today.isoformat(), user_key=email)
        status_label, status_explanation = extract_training_status_label(training_status_raw)

        # MÉTICAS GLOBALES
        st.subheader(t('overview'))
        overview_cols = st.columns(2 if is_mobile else 6)
        m1, m2, m3, m4, m5, m6 = [overview_cols[i % len(overview_cols)] for i in range(6)]

        latest_load = df_load.iloc[-1] if not df_load.empty else {}
        ctl = latest_load.get('Fitness_CTL', 0)
        atl = latest_load.get('Fatigue_ATL', 0)
        tsb = latest_load.get('Form_TSB', 0)

        m1.metric(t('fitness_ctl'), f"{ctl:.1f}")
        m2.metric(t('fatigue_atl'), f"{atl:.1f}")
        m3.metric(t('form_tsb'), f"{tsb:.1f}", delta=t('optimal_race_form') if 5 <= tsb <= 20 else t('high_fatigue_risk') if tsb < -20 else t('taper_rest'))
        m4.metric(t('sleep_score'), f"{sleep_info.get('Score', 'N/A')}/100", format_hours_minutes(sleep_info.get('Total_Hours', 0)))
        m5.metric(t('hrv_status'), f"{hrv_data.get('Status', 'N/A').title()}")
        m6.metric(t('active_days'), f"{df_acts['Date'].nunique() if not df_acts.empty else 0}")

        st.divider()

        # PESTAÑAS DEL DASHBOARD
        tab_load, tab_guidance, tab_sleep, tab_hrv_resp, tab_heat, tab_monthly, tab_health, tab_weekly, tab_logs = st.tabs([
            t('tab_load'), t('tab_guidance'), t('tab_sleep'), t('tab_hrv'), t('tab_heatmap'),
            t('tab_monthly'), t('tab_health'), t('tab_weekly'), t('tab_logs'),
        ])

        # TAB 1: MODELO DE CARGA DE ENTRENAMIENTO
        with tab_load:
            st.subheader(t('load_title'))
            st.caption(t('load_caption'))

            fig_tl = go.Figure()
            fig_tl.add_trace(go.Bar(x=df_load['Date'], y=df_load['Effort'], name=t('daily_effort'), marker_color='rgba(252, 76, 2, 0.25)'))
            fig_tl.add_trace(go.Scatter(x=df_load['Date'], y=df_load['Fitness_CTL'], name=t('fitness_line'), line=dict(color='#1f77b4', width=3)))
            fig_tl.add_trace(go.Scatter(x=df_load['Date'], y=df_load['Fatigue_ATL'], name=t('fatigue_line'), line=dict(color='#d62728', width=2)))
            fig_tl.add_trace(go.Scatter(x=df_load['Date'], y=df_load['Form_TSB'], name=t('form_line'), line=dict(color='#2ca02c', width=2, dash='dot')))

            fig_tl.update_layout(
                title=t('load_chart_title'),
                xaxis_title=t('date'),
                yaxis_title=t('load_points'),
                hovermode="x unified",
                template="plotly_white",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_tl, use_container_width=True)

        # TAB 2: RECOMENDACIONES (con datos reales de Garmin: Training Readiness + Training Status)
        with tab_guidance:
            st.subheader(t('guidance_title'))

            readiness_score = readiness.get('score')
            readiness_level = readiness.get('level')
            feedback_long = readiness.get('feedbackLong')
            feedback_short = readiness.get('feedbackShort')

            c1, c2 = st.columns([1, 2]) if not is_mobile else (st.container(), st.container())
            with c1:
                if readiness_score:
                    st.metric(t('training_readiness'), f"{readiness_score}/100", translate_level(readiness_level))
                st.metric(t('sleep_score'), f"{sleep_info.get('Score', 'N/A')}", f"{sleep_info.get('Qualifier', '')}")
                if not df_health.empty:
                    latest = df_health.iloc[0]
                    st.metric(t('resting_hr'), f"{latest.get('Resting_HR', 'N/A')} bpm")
                    st.metric(t('body_battery_peak'), f"{latest.get('Body_Battery_Max', 'N/A')} / 100")

            with c2:
                if status_label:
                    st.markdown(f"### {status_label}")
                    st.info(status_explanation)
                else:
                    st.markdown(f"### {t('guidance_context')} ({sleep_info.get('Date', '')})")

                if readiness_score:
                    st.markdown(t('garmin_recommendation'))
                    st.info(feedback_long or feedback_short or t('no_recommendation'))

                    factors = [
                        (t('factor_sleep'), readiness.get('sleepScoreFactorPercent')),
                        (t('factor_hrv'), readiness.get('hrvFactorPercent')),
                        (t('factor_recovery'), readiness.get('recoveryTimeFactorPercent')),
                        (t('factor_load'), readiness.get('acwrFactorPercent')),
                        (t('factor_stress'), readiness.get('stressHistoryFactorPercent')),
                    ]
                    factors = [(label, val) for label, val in factors if val is not None]
                    if factors:
                        st.caption(t('factors_caption'))
                        fcols = st.columns(2 if is_mobile else len(factors))
                        for idx_f, (label, val) in enumerate(factors):
                            fcols[idx_f % len(fcols)].metric(label, f"{val:+d}%" if isinstance(val, (int, float)) else str(val))

                    recovery_hours = readiness.get('recoveryTime')
                    if recovery_hours:
                        st.caption(t('recovery_time').format(h=recovery_hours))
                elif not status_label:
                    st.info(sleep_info.get('Feedback', t('no_recommendations_available')))

        # TAB 3: ANÁLISIS DE SUEÑO
        with tab_sleep:
            st.subheader(t('sleep_distribution').format(date=sleep_info.get('Date', t('latest_session'))))
            if sleep_info and sleep_info.get('Total_Hours', 0) > 0:
                sc1, sc2 = st.columns([1, 2]) if not is_mobile else (st.container(), st.container())
                with sc1:
                    st.metric(t('total_duration'), format_hours_minutes(sleep_info.get('Total_Hours', 0)))
                    st.metric(t('deep_sleep'), format_hours_minutes(sleep_info.get('Deep_Hours', 0)))
                    st.metric(t('light_sleep'), format_hours_minutes(sleep_info.get('Light_Hours', 0)))
                    st.metric(t('rem_sleep'), format_hours_minutes(sleep_info.get('REM_Hours', 0)))

                with sc2:
                    sleep_stages = pd.DataFrame({
                        'Stage': [t('stage_deep'), t('stage_light'), t('stage_rem')],
                        'Hours': [sleep_info.get('Deep_Hours', 0), sleep_info.get('Light_Hours', 0), sleep_info.get('REM_Hours', 0)]
                    })
                    fig_sleep = px.pie(sleep_stages, values='Hours', names='Stage', title=t('sleep_breakdown'), color_discrete_sequence=px.colors.sequential.Darkmint)
                    fig_sleep.update_layout(template="plotly_white")
                    st.plotly_chart(fig_sleep, use_container_width=True)
            else:
                st.warning(t('no_sleep_data'))

        # TAB 4: HRV Y RESPIRACIÓN
        with tab_hrv_resp:
            st.subheader(t('hrv_title'))
            col_hrv, col_resp = st.columns(2) if not is_mobile else (st.container(), st.container())
            with col_hrv:
                st.markdown(t('hrv_status_header'))
                st.metric(t('hrv_status'), f"{hrv_data.get('Status', 'N/A').title()}")
                st.metric(t('last_night_avg'), f"{hrv_data.get('Last_Night_Avg', 'N/A')} ms")
                st.metric(t('baseline_avg'), f"{hrv_data.get('Weekly_Avg', 'N/A')} ms")
            with col_resp:
                st.markdown(t('respiration_header'))
                st.metric(t('awake_respiration'), f"{respiration_data.get('Avg_Waking', 'N/A')} br/pm")
                st.metric(t('sleep_respiration'), f"{respiration_data.get('Avg_Sleep', 'N/A')} br/pm")

        # TAB 5: HEATMAP
        with tab_heat:
            st.subheader(t('heatmap_title'))
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
            st.subheader(t('monthly_title'))
            if not df_acts.empty:
                monthly_agg = df_acts.groupby(['Year', 'MonthNum', 'Month'])['Distance_km'].sum().reset_index().sort_values(by=['Year', 'MonthNum'])
                fig_monthly = px.bar(monthly_agg, x='Month', y='Distance_km', color=monthly_agg['Year'].astype(str), barmode='group', template="plotly_white")
                st.plotly_chart(fig_monthly, use_container_width=True)

        # TAB 7: SALUD Y ESTRÉS
        with tab_health:
            st.subheader(t('health_title'))
            if not df_health.empty:
                fig_health = go.Figure()
                fig_health.add_trace(go.Scatter(x=df_health['Date'], y=df_health['Body_Battery_Max'], name=t('body_battery_max'), line=dict(color='limegreen', width=3)))
                fig_health.add_trace(go.Scatter(x=df_health['Date'], y=df_health['Avg_Stress'], name=t('avg_stress'), line=dict(color='crimson', width=2)))
                fig_health.update_layout(template="plotly_white")
                st.plotly_chart(fig_health, use_container_width=True)

        # TAB 8: INFORME SEMANAL DETALLADO
        with tab_weekly:
            st.markdown(t('weekly_title'))

            current_monday = get_last_monday()
            num_weeks = max(1, days // 7)
            week_options = [current_monday - timedelta(weeks=i) for i in range(num_weeks)]

            def _week_label(monday):
                end = monday + timedelta(days=6)
                label = f"{monday.strftime('%d %b')} – {end.strftime('%d %b %Y')}"
                return f"{label}  {t('this_week')}" if monday == current_monday else label

            selected_monday = st.selectbox(
                t('week_selector'),
                options=week_options,
                format_func=_week_label,
                key="weekly_report_monday",
            )
            week_end = selected_monday + timedelta(days=6)
            is_current_week = selected_monday == current_monday

            # Training Readiness / Status de Garmin para la fecha de referencia de esta semana.
            # Garmin sí guarda esto por día, así que para una semana pasada se pide el último
            # día de esa semana; para la semana actual se pide hoy.
            today = datetime.now().date()
            readiness_date = today if is_current_week else week_end
            week_readiness = get_training_readiness_for_date(client, readiness_date.isoformat(), user_key=email)
            week_status_raw = get_training_status_for_date(client, readiness_date.isoformat(), user_key=email)
            week_status_label, week_status_explanation = extract_training_status_label(week_status_raw)

            if week_readiness.get('score') or week_status_label:
                rc1, rc2 = st.columns(2) if not is_mobile else (st.container(), st.container())
                with rc1:
                    if week_readiness.get('score'):
                        rlabel = t('readiness_today') if is_current_week else t('readiness_on').format(date=readiness_date.strftime('%d %b'))
                        st.metric(rlabel, f"{week_readiness.get('score')}/100")
                with rc2:
                    if week_status_label:
                        st.caption(f"{week_status_label} — {week_status_explanation}")

            health_comment = st.text_area(
                t('health_comment_label'),
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

                    # Sueño medio de esa semana (a partir del histórico diario; ya no depende
                    # de "la última noche", así que funciona también para semanas pasadas).
                    week_sleep_summary = {}
                    if not df_health.empty:
                        week_health = df_health[(df_health['Date'].dt.date >= selected_monday) & (df_health['Date'].dt.date <= week_end)]
                        week_sleep = week_health['Sleep_Hours'].dropna() if 'Sleep_Hours' in week_health else pd.Series(dtype=float)
                        week_sleep_score = week_health['Sleep_Score'].dropna() if 'Sleep_Score' in week_health else pd.Series(dtype=float)
                        if len(week_sleep) > 0:
                            week_sleep_summary = {'Total_Hours': week_sleep.mean(), 'Score': f"{week_sleep_score.mean():.0f}" if len(week_sleep_score) > 0 else 'N/A'}
                            sl1, sl2 = st.columns(2) if not is_mobile else (st.container(), st.container())
                            with sl1:
                                st.metric(t('avg_sleep_week'), format_hours_minutes(week_sleep_summary['Total_Hours']))
                            with sl2:
                                if len(week_sleep_score) > 0:
                                    st.metric(t('avg_sleep_score'), f"{week_sleep_summary['Score']}/100")
                            st.divider()

                    # Tira de calendario Lun-Dom: haz clic en un icono para ir directo a esa actividad
                    st.markdown(t('week_view'))
                    calendar_days = build_week_calendar(df_week, selected_monday)
                    cal_cols = st.columns(7)
                    for col, day_info in zip(cal_cols, calendar_days):
                        with col:
                            st.markdown(f"**{day_info['date'].strftime('%a')}**")
                            st.caption(day_info['date'].strftime('%d/%m'))
                            if day_info['entries']:
                                links = " ".join(
                                    f'<a href="#activity-{aid}" style="text-decoration:none;">{emoji}</a>'
                                    for emoji, aid in day_info['entries']
                                )
                                st.markdown(f'<div class="sticker-row">{links}</div>', unsafe_allow_html=True)
                            else:
                                st.markdown('<div class="sticker-row">💤</div>', unsafe_allow_html=True)

                    st.divider()

                    # Resumen total de la semana, comparado con la anterior
                    overall = weekly_overall_totals(df_week)
                    overall_prev = weekly_overall_totals(df_prev_week)
                    vs_prev = t('vs_prev_week')

                    st.markdown(t('week_summary'))
                    tot1, tot2, tot3 = st.columns(3) if not is_mobile else (st.container(), st.container(), st.container())
                    tot1.metric(t('total_distance'), f"{overall['km']:.1f} km", f"{overall['km'] - overall_prev['km']:+.1f} km {vs_prev}")
                    tot2.metric(t('total_time'), format_hours_minutes(overall['minutes'] / 60), f"{(overall['minutes'] - overall_prev['minutes']) / 60:+.1f} h {vs_prev}")
                    tot3.metric(t('sessions'), f"{overall['sessions']}", f"{overall['sessions'] - overall_prev['sessions']:+d} {vs_prev}")

                    st.divider()

                    st.markdown(t('totals_by_discipline'))
                    summary_cols = st.columns(2 if is_mobile else 4)

                    sports = ['Ciclismo', 'Carrera', 'Natación', 'Fuerza']
                    totals_by_sport = weekly_totals_by_sport(df_week, sports)
                    prev_totals_by_sport = weekly_totals_by_sport(df_prev_week, sports)

                    for idx, sport in enumerate(sports):
                        emoji = SPORT_EMOJIS.get(sport, '⚡')
                        sport_totals = totals_by_sport[sport]
                        prev_sport_totals = prev_totals_by_sport[sport]

                        with summary_cols[idx % len(summary_cols)]:
                            if sport_totals['sessions'] > 0:
                                headline = format_discipline_headline(sport, sport_totals['km'], sport_totals['minutes'])
                                delta_text = format_discipline_delta(sport, sport_totals, prev_sport_totals)
                                st.metric(f"{emoji} {translate_sport(sport)}", headline, delta_text)
                                total_hrs = int(sport_totals['minutes'] // 60)
                                total_mins = int(sport_totals['minutes'] % 60)
                                st.caption(f"{sport_totals['sessions']} {t('sessions_short')} • {total_hrs}h {total_mins}m")
                            else:
                                st.metric(f"{emoji} {translate_sport(sport)}", "—", t('no_sessions'))

                    st.divider()

                    st.markdown(t('workout_log'))
                    st.caption(t('workout_log_caption'))

                    df_week_sorted = df_week.sort_values('Date', ascending=False)
                    unique_days = sorted(df_week_sorted['Date'].unique(), reverse=True)
                    workout_entries = []

                    for day_idx, day in enumerate(unique_days):
                        day_acts = df_week_sorted[df_week_sorted['Date'] == day]
                        day_label = day.strftime('%A, %d %b')
                        n = len(day_acts)
                        st.markdown(f"#### 📅 {day_label}")
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

                            perceived_effort = st.session_state.get(rpe_key, default_rpe)
                            feeling = st.session_state.get(feeling_key, default_feeling_option)
                            comments = st.session_state.get(comment_key, default_comment)
                            title = st.session_state.get(title_key, default_title)
                            card_color = get_intensity_color(perceived_effort)

                            avg_hr_val = activity.get('averageHR')
                            avg_hr = int(avg_hr_val) if pd.notna(avg_hr_val) and avg_hr_val else 0

                            cal_val = activity.get('Active_Calories')
                            calories = int(cal_val) if pd.notna(cal_val) and cal_val else 0

                            # Tarjeta estilo Strava: icono de disciplina, título, píldora de esfuerzo, stats en fila.
                            # El id es lo que permite que un clic en el calendario de la semana salte aquí.
                            stats = build_stat_row(sport, distance_km, time_hms, pace_speed, avg_hr, calories)
                            stats_html = "".join(f'<div class="stat"><div class="v">{v}</div><div class="l">{l}</div></div>' for v, l in stats)
                            rpe_pill_text = format_rpe_pill(perceived_effort, feeling)

                            st.markdown(f"""
                            <div class="strava-card" id="activity-{activity_id}">
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

                            # Pestañas propias (en vez de st.tabs) para poder cerrarlas: volver a
                            # pulsar la pestaña abierta la cierra y deja la tarjeta limpia.
                            panel_key = f"panel_{activity_id}"
                            if panel_key not in st.session_state:
                                st.session_state[panel_key] = 'feedback'

                            tb1, tb2, _tb_sp = st.columns([1, 1, 3])
                            with tb1:
                                if st.button(t('tab_feedback'), key=f"tab_fb_{activity_id}", use_container_width=True,
                                             type="primary" if st.session_state[panel_key] == 'feedback' else "secondary"):
                                    st.session_state[panel_key] = None if st.session_state[panel_key] == 'feedback' else 'feedback'
                                    st.rerun()
                            with tb2:
                                if st.button(t('tab_intervals'), key=f"tab_iv_{activity_id}", use_container_width=True,
                                             type="primary" if st.session_state[panel_key] == 'intervals' else "secondary"):
                                    st.session_state[panel_key] = None if st.session_state[panel_key] == 'intervals' else 'intervals'
                                    st.rerun()

                            if st.session_state[panel_key] == 'feedback':
                                ec1, ec2, ec3 = st.columns([2, 1, 1]) if not is_mobile else (st.container(), st.container(), st.container())
                                with ec1:
                                    title = st.text_input(t('field_title'), value=title, key=title_key)
                                with ec2:
                                    perceived_effort = st.slider(t('field_rpe'), 0, 10, value=int(perceived_effort), key=rpe_key)
                                with ec3:
                                    feeling = st.selectbox(t('field_feeling'), FEELING_OPTIONS,
                                                           index=FEELING_OPTIONS.index(feeling), key=feeling_key,
                                                           format_func=lambda f: t(f"feeling_{FEELING_OPTIONS.index(f)}"))
                                comments = st.text_area(t('field_comment'), value=comments, key=comment_key, height=60)

                                # Guardar de vuelta en Garmin para que no se pierda al cerrar la app
                                if st.button(t('save_to_garmin'), key=f"save_{activity_id}"):
                                    ok_title = set_activity_title(client, activity_id, title)
                                    ok_comment = set_activity_comment(client, activity_id, comments)
                                    ok_eval = set_activity_evaluation(
                                        client, activity_id, perceived_effort, FEELING_TO_GARMIN.get(feeling)
                                    )
                                    if ok_title and ok_comment:
                                        msg = t('save_ok')
                                        msg += t('save_ok_eval') if ok_eval else t('save_ko_eval')
                                        st.success(msg)
                                    else:
                                        st.error(t('save_error'))
                            elif st.session_state[panel_key] == 'intervals':
                                laps = get_activity_splits(client, activity_id) if activity_id else []
                                if laps:
                                    lap_rows = [format_lap_row(sport, lap) for lap in laps]
                                    st.dataframe(pd.DataFrame(lap_rows), use_container_width=True, hide_index=True)
                                else:
                                    st.caption(t('no_intervals'))

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

                    st.divider()

                    # EXPORTACIÓN PDF
                    st.markdown(t('export_report'))

                    if st.button(t('download_pdf'), key="download_pdf"):
                        try:
                            pdf_buffer = build_weekly_report_pdf(
                                workout_entries, df_week, week_sleep_summary, sports, selected_monday, week_end,
                                health_comment=health_comment,
                                readiness=week_readiness,
                                status_label=week_status_label,
                                status_explanation=week_status_explanation,
                                prev_totals_by_sport=prev_totals_by_sport, overall=overall, overall_prev=overall_prev,
                            )

                            st.download_button(
                                label=t('pdf_ready'),
                                data=pdf_buffer,
                                file_name=f"Weekly_Report_{selected_monday.strftime('%Y%m%d')}.pdf",
                                mime="application/pdf",
                                key="pdf_download"
                            )
                            st.success(t('pdf_success'))
                        except ImportError:
                            st.error(t('pdf_missing_libs'))
                        except Exception as e:
                            st.error(t('pdf_error').format(error=e))
                else:
                    st.warning(t('no_workouts_week'))
            else:
                st.warning(t('no_activity_data'))

        # TAB 9: REGISTRO DE ACTIVIDADES
        with tab_logs:
            st.subheader(t('activity_registry'))
            if not df_acts.empty:
                cols = ['activityName', 'Sport', 'Date', 'Distance_km', 'Duration_min', 'Elevation_m', 'Effort']
                avail = [c for c in cols if c in df_acts.columns]
                st.dataframe(df_acts[avail].sort_values(by='Date', ascending=False), use_container_width=True, hide_index=True)

else:
    st.info(t('enter_credentials'))
