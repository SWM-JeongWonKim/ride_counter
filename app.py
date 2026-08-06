# ---------------------------------------------------------
# 탭 구성 및 새로고침 UI 적용 부분 (app.py 하단)
# ---------------------------------------------------------

# 상단 대시보드 제목 및 새로고침 버튼 영역
col_title, col_btn = st.columns([4, 1])
with col_title:
    st.title("🚖 운영 대시보드")
with col_btn:
    st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
    if st.button("🔄 화면 새로고침", use_container_width=True):
        st.cache_data.clear() # 파싱 데이터 캐시 비우기
        st.rerun()

# ---------------------------------------------------------
# 탭 타이틀 정의 및 권한별 분기
# ---------------------------------------------------------
t_titles = ["📊 통합 Summary", "🧑‍✈️ Safe Guard 별", "🚗 차량 별"]

if st.session_state.user_role in ['admin', 'DM']:
    t_titles.append("🗺️ ADS Monitor")
    t_titles.append("⚙️ 시스템 관리")
    
tbs = st.tabs(t_titles)

with tbs[0]:
    tab_summary.draw_summary_tab(clean_df, f_drive)
with tbs[1]:
    tab_safeguard.draw_safeguard_tab(clean_df, f_drive, sched_df)
with tbs[2]:
    tab_vehicle.draw_car_tab(clean_df, f_drive)
    
if st.session_state.user_role in ['admin', 'DM']:
    with tbs[3]:
        # 🗺️ ADS Monitor 탭 화면 구성 (필요한 모듈이나 함수 호출)
        st.markdown("### 🗺️ ADS Monitor")
        st.info("💡 ADS 모니터링 관련 현황 화면입니다.")
        # 예: monitor_module.draw_ads_monitor_tab(clean_df)
        
    with tbs[4]:
        # ⚙️ 시스템 관리 탭
        am.draw_admin_tab(clean_df, f_drive, u_df, sched_df, m_cars, m_drivers, kst_now, DEFAULT_SHEET_URL)