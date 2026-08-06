import streamlit as st
import time
import firebase_manager as fm
import admin_utils as utils

def draw_user_management(u_df, m_cars, m_drivers):
    c1, c2 = st.columns([5, 1])
    c1.markdown(utils.get_premium_header("👥", "회원 명단 관리", "#4F46E5"), unsafe_allow_html=True)
    
    if not u_df.empty:
        u_df['대시보드 접근'] = u_df.apply(lambda x: utils.parse_bool(x.get('can_view_dashboard', x.get('is_approved', False))), axis=1).astype(bool)
        u_df['시스템 관리'] = u_df.apply(lambda x: utils.parse_bool(x.get('is_admin', x.get('role') == 'admin')), axis=1).astype(bool)
        u_df['운영파트'] = u_df.apply(lambda x: utils.parse_bool(x.get('is_driver', False)), axis=1).astype(bool)
        u_df['지원파트'] = u_df.apply(lambda x: utils.parse_bool(x.get('is_support', False)), axis=1).astype(bool)
        
        if 'shift' not in u_df.columns: u_df['shift'] = '주간 (08:00~17:30)'
        if 'region' not in u_df.columns: u_df['region'] = '상암'
        
        u_df['shift'] = u_df['shift'].fillna('주간 (08:00~17:30)')
        u_df['region'] = u_df['region'].fillna('상암')
        
        u_edit = u_df[['user_id', 'name', 'position', 'region', 'shift', '지원파트', '대시보드 접근', '시스템 관리', '운영파트']].copy()
        disable_cols = ['user_id', 'name', 'position']
        
        super_admin_id = "syoh@swm.ai", "dwkim2@swm.ai"
        if st.session_state.get('user_id') != super_admin_id: 
            disable_cols.append('시스템 관리')
        
        edited_u = st.data_editor(
            u_edit, 
            hide_index=True, 
            use_container_width=True, 
            num_rows="dynamic", 
            disabled=disable_cols, 
            column_config={
                "user_id": st.column_config.TextColumn("아이디(ID)", width="medium"), 
                "name": st.column_config.TextColumn("이름", width="small"), 
                "position": st.column_config.TextColumn("직책", width="small"), 
                "region": st.column_config.SelectboxColumn("지역", options=["상암", "강남", "안양", "전체"], width="small"),
                "shift": st.column_config.SelectboxColumn("주/야간", options=["주간 (08:00~17:30)", "야간 (21:00~06:00)", "주간", "야간"], width="medium"),
                "지원파트": st.column_config.CheckboxColumn("지원", width="small"), 
                "대시보드 접근": st.column_config.CheckboxColumn("대시보드", width="small"), 
                "시스템 관리": st.column_config.CheckboxColumn("어드민", width="small"), 
                "운영파트": st.column_config.CheckboxColumn("운영(기사)", width="small")
            }, 
            key="user_editor"
        )
        
        if c2.button("💾 권한 저장(적용)", key="btn_save_users"):
            orig_uids = set(u_edit['user_id'].dropna())
            curr_uids = set(edited_u['user_id'].dropna())
            
            for uid in (orig_uids - curr_uids): 
                fm.delete_user(str(uid).strip())
                
            new_drivers = []
            for _, r in edited_u.iterrows():
                uid = str(r.get('user_id', '')).strip()
                if not uid or uid == 'nan': continue 
                    
                fm.update_user_permissions(
                    uid, 
                    utils.parse_bool(r.get('대시보드 접근')), 
                    utils.parse_bool(r.get('시스템 관리')), 
                    utils.parse_bool(r.get('운영파트')), 
                    utils.parse_bool(r.get('지원파트'))
                )
                
                region_val = str(r.get('region', '상암'))
                shift_val = str(r.get('shift', '주간 (08:00~17:30)'))
                fm.db_update('users', uid, {'shift': shift_val, 'region': region_val})
                
                if utils.parse_bool(r.get('운영파트')): 
                    new_drivers.append(str(r.get('name', '')).strip())
                    
            fm.update_master_data(m_cars, sorted(list(set([n for n in new_drivers if n and n != 'nan']))))
            st.success("권한 및 주/야간/지역 정보 동기화 완료!")
            time.sleep(1)
            st.rerun()

    st.divider()
    st.markdown(utils.get_premium_header("🔄", "계정 정보 변경(ID/PW) 승인 대기열", "#F59E0B"), unsafe_allow_html=True)
    pending_reqs = fm.get_account_requests()
    
    if not pending_reqs: 
        st.info("💡 현재 결재 대기 중인 변경 요청이 없습니다.")
    else:
        for req in pending_reqs:
            req_id = req.get('req_id')
            old_id = req.get('old_id')
            new_id = req.get('new_id', '')
            new_pw = req.get('new_pw', '')
            name = req.get('name', '이름없음')
            
            with st.container(border=True):
                st.markdown(f"<h4 style='color:#0f172a; margin-bottom:10px;'>👤 <span style='color:#4F46E5;'>{name}</span> 요원 변경 신청</h4>", unsafe_allow_html=True)
                rc1, rc2 = st.columns([4, 1])
                
                pw_bg = "#fee2e2" if new_pw else "#e2e8f0"
                pw_text = "#991b1b" if new_pw else "#64748b"
                pw_msg = "요청함 🔒" if new_pw else "변경 안 함"
                
                new_id_display = new_id if new_id else '(변경 없음)'
                
                html_content = f"<div style='background:#f8fafc; padding:12px; border-radius:10px; font-size:14px; color:#475569; border: 1px solid #f1f5f9;'><div style='margin-bottom: 5px;'><b>기존 아이디:</b> <code style='color:#ef4444; background:transparent;'>{old_id}</code> ➡️ <b>새 아이디:</b> <code style='color:#10b981; background:transparent;'>{new_id_display}</code></div><div><b>비밀번호 변경:</b> <span style='background:{pw_bg}; color:{pw_text}; padding:3px 8px; border-radius:6px; font-weight:600; font-size:12px;'>{pw_msg}</span></div></div>"
                rc1.markdown(html_content, unsafe_allow_html=True)
                
                with rc2:
                    if st.button("✅ 승인", key=f"app_{req_id}", type="primary", use_container_width=True):
                        s, m = fm.approve_account_request(req_id, old_id, new_id, new_pw)
                        if s: st.success(m) 
                        else: st.error(m)
                        time.sleep(1.5)
                        st.rerun()
                        
                    if st.button("❌ 반려", key=f"rej_{req_id}", use_container_width=True):
                        s, m = fm.reject_account_request(req_id)
                        st.warning(m)
                        time.sleep(1)
                        st.rerun()