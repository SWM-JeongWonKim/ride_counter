import streamlit as st
import admin_tabs as tabs
import admin_utils as utils

def draw_admin_tab(clean_df, df_drive, u_df, sched_df, m_cars, m_drivers, kst_now):
    st.markdown("<style>.admin-header { font-size: 24px; font-weight: 800; color: #1E293B; margin-bottom: 20px; }</style>", unsafe_allow_html=True)
    st.markdown("<div class='admin-header'>⚙️ 시스템 및 운영 관리</div>", unsafe_allow_html=True)
    
    super_admin_id = "syoh@swm.ai", "dwkim2@swm.ai"
    is_super_admin = (st.session_state.get('user_id') == super_admin_id)
    
    is_authorized_admin = False
    current_uid = st.session_state.get('user_id')
    if not u_df.empty and current_uid in u_df['user_id'].values:
        u_row = u_df[u_df['user_id'] == current_uid].iloc[0]
        is_admin_flag = utils.parse_bool(u_row.get('is_admin', False))
        pos = str(u_row.get('position', ''))
        if is_admin_flag and pos in ['Area Manager', 'Data Manager']:
            is_authorized_admin = True
            
    can_manage_data = is_super_admin or is_authorized_admin
    
    tab_titles = ["📅 배차 스케줄 관리", "👥 회원 명단 관리", "🚗 운영 차량 관리"]
    if can_manage_data:
        tab_titles.append("🗄️ 데이터 수정/관리")
        
    t_objs = st.tabs(tab_titles)
    
    with t_objs[0]:
        tabs.draw_schedule_management(clean_df, sched_df, u_df, m_cars, m_drivers, kst_now)
    with t_objs[1]:
        tabs.draw_user_management(u_df, m_cars, m_drivers)
    with t_objs[2]:
        tabs.draw_fleet_management(m_cars, m_drivers)
        
    if can_manage_data:
        with t_objs[3]:
            tabs.draw_data_management(clean_df, df_drive, m_cars, m_drivers, kst_now)