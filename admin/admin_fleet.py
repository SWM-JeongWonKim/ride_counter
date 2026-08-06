import streamlit as st
import pandas as pd
import time
import firebase_manager as fm
import admin_utils as utils

def draw_fleet_management(m_cars, m_drivers):
    c1, c2 = st.columns([5, 1])
    # [수정] utils 모듈의 get_premium_header 사용
    c1.markdown(utils.get_premium_header("🚗", "운영 차량 목록 관리", "#3B82F6"), unsafe_allow_html=True)
    
    edited_c = st.data_editor(
        pd.DataFrame({'차량번호': m_cars}), 
        hide_index=True, 
        num_rows="dynamic", 
        use_container_width=True, 
        key="car_editor"
    )
    
    if c2.button("💾 변경내용 적용", key="btn_save_cars"):
        updated_cars = sorted(list(set([str(r['차량번호']).strip() for _, r in edited_c.iterrows() if pd.notna(r['차량번호']) and str(r['차량번호']).strip()])))
        fm.update_master_data(updated_cars, m_drivers)
        st.success("차량 목록 업데이트 완료!")
        time.sleep(1)
        st.rerun()
