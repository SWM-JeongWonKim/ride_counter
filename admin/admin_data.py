import streamlit as st
import pandas as pd
import datetime
import time
import io
import zipfile
import json
import ast
import firebase_manager as fm
import admin_utils as utils

def json_default(obj):
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    return str(obj)

def get_editable_issues(df):
    irs = []
    try:
        sw_db = fm.load_data('sw_versions')
    except:
        sw_db = {}
        
    for _, r in df.iterrows():
        ms = r.get('report_memos', {})
        if isinstance(ms, str):
            try: ms = ast.literal_eval(ms)
            except: ms = {}
        if not isinstance(ms, dict): continue
        
        ks = [k for k in ms.keys() if not str(k).startswith('ADMIN_')]
        doc_id = r.get('doc_id')
        
        rst = r.get('ride_start_time')
        ride_dt = pd.to_datetime(rst, unit='ms', utc=True).tz_convert('Asia/Seoul') if pd.notna(rst) and str(rst).strip() else pd.NaT
        sw_key = f"{ride_dt.strftime('%Y-%m-%d')}_{str(r.get('carNumber', '')).strip()}" if pd.notna(ride_dt) else ""
        sw = sw_db.get(sw_key, {})
        
        for k in ks:
            memo_txt = str(ms[k])
            maj, min_cat, dtl = "", "", memo_txt
            if memo_txt.startswith("["):
                ei = memo_txt.find("]")
                if ei != -1:
                    cp = memo_txt[1:ei]
                    dtl = memo_txt[ei+1:].strip()
                    if ">" in cp:
                        p = cp.split(">")
                        maj, min_cat = p[0].strip(), p[1].strip()
                    else:
                        maj = cp.strip()
            
            try: dt_obj = pd.to_datetime(int(k), unit='ms').tz_localize('UTC').tz_convert('Asia/Seoul')
            except: dt_obj = r.get('dt_obj', pd.NaT)
            
            d_str = dt_obj.strftime('%Y-%m-%d') if pd.notna(dt_obj) else ""
            t_str = dt_obj.strftime('%H:%M:%S') if pd.notna(dt_obj) else ""
            
            irs.append({
                'doc_id': doc_id,
                'timestamp_key': str(k),
                '운행일자': d_str,
                '발생시간': t_str,
                '발생위치': f"{r.get('latitude', '-')} , {r.get('longitude', '-')}",
                '차량번호': str(r.get('carNumber', '-')).strip(),
                '운행인원': str(r.get('driverName', '-')).strip(),
                '대분류': maj,
                '중분류': min_cat,
                '내용': dtl,
                'SV': str(r.get('SW_Safeview', sw.get('Safeview', '-'))).strip(),
                'CPU': str(r.get('SW_CPU', sw.get('CPU', '-'))).strip(),
                'MCU': str(r.get('SW_MCU', sw.get('MCU', '-'))).strip(),
                'V1': str(r.get('SW_VPU1', sw.get('VPU1', '-'))).strip(),
                'V2': str(r.get('SW_VPU2', sw.get('VPU2', '-'))).strip(),
                'V3': str(r.get('SW_VPU3', sw.get('VPU3', '-'))).strip(),
                'V4': str(r.get('SW_VPU4', sw.get('VPU4', '-'))).strip()
            })
    return pd.DataFrame(irs)

def draw_data_management(clean_df, df_drive, m_cars, m_drivers, kst_now):
    st.markdown(utils.get_premium_header("🚨", "[최고 관리자 전용] 시스템 및 데이터 베이스 제어", "#EF4444"), unsafe_allow_html=True)
    st.info("💡 파이어베이스(클라우드)의 최신 데이터를 대시보드로 즉시 강제 동기화하거나, 전체 데이터를 엑셀/압축 백업할 수 있습니다.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("☁️ 전체 DB 강제 새로고침 (대시보드 캐시 초기화 및 즉시 동기화)", type="primary", use_container_width=True):
            with st.spinner("클라우드에서 데이터를 긁어오는 중..."):
                success, msg = fm.force_sync_from_firebase()
                if success: 
                    st.success(msg)
                    time.sleep(1.5)
                    st.rerun()
                else: 
                    st.error("🚨 동기화 실패")
    with col2:
        if st.button("📦 전체 데이터 백업 생성 (.zip)", use_container_width=True):
            try:
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    zip_file.writestr("users.json", json.dumps(fm.get_all_users(), ensure_ascii=False, indent=2, default=json_default))
                    _, m_data = fm.get_master_data()
                    zip_file.writestr("master_settings.json", json.dumps(m_data, ensure_ascii=False, indent=2, default=json_default))
                    zip_file.writestr("schedules.json", json.dumps(fm.get_schedules(), ensure_ascii=False, indent=2, default=json_default))
                    zip_file.writestr("account_requests.json", json.dumps(fm.get_account_requests(), ensure_ascii=False, indent=2, default=json_default))
                    zip_file.writestr("ride_logs.json", json.dumps(fm.get_ride_logs(), ensure_ascii=False, indent=2, default=json_default))
                    zip_file.writestr("driving_logs.json", json.dumps(fm.get_driving_logs(), ensure_ascii=False, indent=2, default=json_default))
                st.download_button("📥 핵심 DB 백업 다운로드 (.zip)", data=zip_buffer.getvalue(), file_name=f"RideCounter_Core_Backup_{kst_now.strftime('%Y%m%d_%H%M')}.zip", mime="application/zip", use_container_width=True)
            except Exception as e:
                st.error(f"오류: {e}")
                
    st.divider()
    
    # 공통 필터 영역
    f2_c1, f2_c2, f2_c3 = st.columns(3)
    with f2_c1: drv_date = st.date_input("🗓️ 날짜 필터", value=(kst_now.date(), kst_now.date()), key="f_drv_date")
    with f2_c2: drv_car = st.multiselect("🚗 차량 필터", options=m_cars, key="f_drv_car", placeholder="전체")
    with f2_c3: drv_name = st.multiselect("👤 인원 필터", options=m_drivers, key="f_drv_name", placeholder="전체")

    # ===============================================
    # 1. 탑승 기록 (Ride Logs)
    # ===============================================
    st.markdown(utils.get_premium_header("📝", "1. 탑승 기록(Ride Logs) 풀-수정", "#8B5CF6"), unsafe_allow_html=True)
    if not clean_df.empty:
        filtered_rides = clean_df.copy()
        filtered_rides['shift_date_obj'] = pd.to_datetime(filtered_rides['shift_date']).dt.date
        
        if isinstance(drv_date, tuple) and len(drv_date) == 2: 
            filtered_rides = filtered_rides[(filtered_rides['shift_date_obj'] >= drv_date[0]) & (filtered_rides['shift_date_obj'] <= drv_date[1])]
        elif isinstance(drv_date, tuple) and len(drv_date) == 1: 
            filtered_rides = filtered_rides[filtered_rides['shift_date_obj'] == drv_date[0]]
        else: 
            filtered_rides = filtered_rides[filtered_rides['shift_date_obj'] == drv_date]
            
        if drv_car: filtered_rides = filtered_rides[filtered_rides['carNumber'].isin(drv_car)]
        if drv_name: filtered_rides = filtered_rides[filtered_rides['driverName'].isin(drv_name)]

        ride_edit_df = filtered_rides[filtered_rides['status'] != 'ISSUE_ONLY'].copy()
        
        if not ride_edit_df.empty and 'doc_id' in ride_edit_df.columns:
            def fmt_time(ts):
                if pd.isna(ts) or str(ts).strip() in ['', '0', 'nan', 'None']: return "-"
                try: return pd.to_datetime(float(ts), unit='ms', utc=True).tz_convert('Asia/Seoul').strftime('%H:%M:%S')
                except: return "-"

            ride_edit_df['탑승일자'] = ride_edit_df['dt_obj'].dt.strftime('%Y-%m-%d')
            ride_edit_df['탑승시간'] = ride_edit_df['ride_start_time'].apply(fmt_time)
            ride_edit_df['하차시간'] = ride_edit_df['ride_end_time'].apply(fmt_time)

            ride_cols = ['doc_id', '탑승일자', '탑승시간', '하차시간', 'carNumber', 'driverName', 'callCount', 'passengers']
            r_edit_df = ride_edit_df[[c for c in ride_cols if c in ride_edit_df.columns]].sort_values(['탑승일자', '탑승시간'], ascending=[False, False]).copy()

            # [에러 방지] Data Editor에 넘기기 전 숫자/문자열 강제 캐스팅
            for col in ['callCount', 'passengers']:
                if col in r_edit_df.columns: r_edit_df[col] = pd.to_numeric(r_edit_df[col], errors='coerce').fillna(0).astype(int)
            for col in ['탑승일자', '탑승시간', '하차시간', 'carNumber', 'driverName']:
                if col in r_edit_df.columns: r_edit_df[col] = r_edit_df[col].fillna('').astype(str).replace(['nan', 'None', '<NA>'], '')

            edited_r = st.data_editor(
                r_edit_df, 
                hide_index=True, 
                use_container_width=True, 
                num_rows="dynamic", 
                disabled=['doc_id'], 
                column_config={
                    "doc_id": None, 
                    "탑승일자": st.column_config.TextColumn("탑승일자", width="small"),
                    "탑승시간": st.column_config.TextColumn("탑승시간", width="small"),
                    "하차시간": st.column_config.TextColumn("하차시간", width="small"),
                    "carNumber": st.column_config.SelectboxColumn("차량 번호", options=m_cars, width="small"), 
                    "driverName": st.column_config.SelectboxColumn("기사 명", options=m_drivers, width="small"), 
                    "callCount": st.column_config.NumberColumn("호출", width="small"), 
                    "passengers": st.column_config.NumberColumn("탑승객", width="small")
                }, 
                key="ride_editor"
            )
            
            if st.button("💾 탑승 기록 수정 적용", key="btn_save_ride", type="primary"):
                orig_r = set(r_edit_df['doc_id'].dropna())
                curr_r = set(edited_r['doc_id'].dropna())
                for r_id in (orig_r - curr_r): fm.delete_ride_log(r_id) 
                
                for _, row in edited_r.iterrows():
                    if pd.isna(row['doc_id']) or str(row['doc_id']).strip() == "": continue
                    orig_row = r_edit_df[r_edit_df['doc_id'] == row['doc_id']].iloc[0]
                    updates = {}
                    
                    if str(row['carNumber']) != str(orig_row['carNumber']): updates['carNumber'] = str(row['carNumber'])
                    if str(row['driverName']) != str(orig_row['driverName']): updates['driverName'] = str(row['driverName'])
                    if str(row['callCount']) != str(orig_row['callCount']): updates['callCount'] = int(row['callCount'])
                    if str(row['passengers']) != str(orig_row['passengers']): updates['passengers'] = int(row['passengers'])
                    
                    if updates: fm.db_update('ride_logs', row['doc_id'], updates)
                st.success("탑승 기록 반영 완료!")
                time.sleep(1)
                st.rerun()

    # ===============================================
    # 2. 이슈 현황 (Issue Logs)
    # ===============================================
    st.divider()
    st.markdown(utils.get_premium_header("🚨", "2. 이슈 현황(Issue Logs) 내용 수정", "#EF4444"), unsafe_allow_html=True)
    if not clean_df.empty:
        editable_issues = get_editable_issues(filtered_rides)
        if not editable_issues.empty:
            i_edit_df = editable_issues.sort_values(['운행일자', '발생시간'], ascending=[False, False]).copy()
            
            # [에러 방지] 텍스트 형변환
            for col in i_edit_df.columns:
                i_edit_df[col] = i_edit_df[col].fillna('').astype(str).replace(['nan', 'None', '<NA>'], '')
                
            edited_i = st.data_editor(
                i_edit_df,
                hide_index=True,
                use_container_width=True,
                disabled=['doc_id', 'timestamp_key', '운행일자', '발생시간', '발생위치', '차량번호', '운행인원', 'SV', 'CPU', 'MCU', 'V1', 'V2', 'V3', 'V4'],
                column_config={
                    "doc_id": None, "timestamp_key": None,
                    "운행일자": st.column_config.TextColumn("운행일자", width="small"),
                    "발생시간": st.column_config.TextColumn("발생시간", width="small"),
                    "발생위치": st.column_config.TextColumn("발생위치", width="small"),
                    "차량번호": st.column_config.TextColumn("차량번호", width="small"),
                    "운행인원": st.column_config.TextColumn("운행인원", width="small"),
                    "대분류": st.column_config.TextColumn("대분류", width="small"),
                    "중분류": st.column_config.TextColumn("중분류", width="small"),
                    "내용": st.column_config.TextColumn("내용", width="large")
                },
                key="issue_editor"
            )
            
            if st.button("💾 이슈 내용 수정 적용", key="btn_save_issues", type="primary"):
                for _, row in edited_i.iterrows():
                    orig_row = i_edit_df[(i_edit_df['doc_id'] == row['doc_id']) & (i_edit_df['timestamp_key'] == row['timestamp_key'])].iloc[0]
                    if row['대분류'] != orig_row['대분류'] or row['중분류'] != orig_row['중분류'] or row['내용'] != orig_row['내용']:
                        new_cat = f"[{row['대분류']} > {row['중분류']}] " if row['대분류'] and row['중분류'] else (f"[{row['대분류']}] " if row['대분류'] else "")
                        new_memo = new_cat + str(row['내용'])
                        fm.db_update('ride_logs', row['doc_id'], {f"report_memos.{row['timestamp_key']}": new_memo})
                st.success("이슈 내용 반영 완료!")
                time.sleep(1)
                st.rerun()

    # ===============================================
    # 3. 운행일지 (Drive Logs)
    # ===============================================
    st.divider()
    st.markdown(utils.get_premium_header("🚖", "3. 차량 별 운행일지 풀-수정", "#10B981"), unsafe_allow_html=True)
    if not df_drive.empty:
        filtered_drives = df_drive.copy()
        filtered_drives['dt_obj'] = pd.to_datetime(filtered_drives['timestamp'] if 'timestamp' in filtered_drives.columns else filtered_drives['날짜'], errors='coerce')
        filtered_drives['dt_obj'] = filtered_drives['dt_obj'].dt.tz_convert('Asia/Seoul') if filtered_drives['dt_obj'].dt.tz is not None else filtered_drives['dt_obj'].dt.tz_localize('Asia/Seoul')
        filtered_drives['shift_date_obj'] = filtered_drives['dt_obj'].dt.date
        
        if isinstance(drv_date, tuple) and len(drv_date) == 2: 
            filtered_drives = filtered_drives[(filtered_drives['shift_date_obj'] >= drv_date[0]) & (filtered_drives['shift_date_obj'] <= drv_date[1])]
        elif isinstance(drv_date, tuple) and len(drv_date) == 1: 
            filtered_drives = filtered_drives[filtered_drives['shift_date_obj'] == drv_date[0]]
        else: 
            filtered_drives = filtered_drives[filtered_drives['shift_date_obj'] == drv_date]
            
        if drv_car: filtered_drives = filtered_drives[filtered_drives['차량번호'].isin(drv_car)]
        if drv_name: filtered_drives = filtered_drives[filtered_drives['Safe_Guard'].isin(drv_name)]

        if not filtered_drives.empty and 'doc_id' in filtered_drives.columns:
            show_cols = ['doc_id', '날짜', '차량번호', 'Safe_Guard', '출발_km', '종료_km', '총주행거리(km)', '출발_배터리_차량', '종료_배터리_차량', '특이사항']
            d_edit_df = filtered_drives[[c for c in show_cols if c in filtered_drives.columns]].sort_values('날짜', ascending=False).copy()
            
            # [에러 방지] 타입 강제 캐스팅
            for col in ['출발_km', '종료_km', '총주행거리(km)']:
                if col in d_edit_df.columns:
                    d_edit_df[col] = pd.to_numeric(d_edit_df[col], errors='coerce').fillna(0).astype(int)
            for col in ['특이사항', '차량번호', 'Safe_Guard', '날짜', '출발_배터리_차량', '종료_배터리_차량']:
                if col in d_edit_df.columns:
                    d_edit_df[col] = d_edit_df[col].fillna('').astype(str).replace(['nan', 'None', '<NA>'], '')

            edited_d = st.data_editor(
                d_edit_df, 
                hide_index=True, 
                use_container_width=True, 
                num_rows="dynamic", 
                disabled=['doc_id'], 
                column_config={
                    "doc_id": None, 
                    "날짜": st.column_config.TextColumn("날짜", width="small"), 
                    "차량번호": st.column_config.SelectboxColumn("차량", options=m_cars, width="small"), 
                    "Safe_Guard": st.column_config.SelectboxColumn("작성자(운행자)", options=m_drivers, width="medium"), 
                    "출발_km": st.column_config.NumberColumn("출발km", width="small"), 
                    "종료_km": st.column_config.NumberColumn("종료km", width="small"), 
                    "총주행거리(km)": st.column_config.NumberColumn("운행거리", width="small"), 
                    "출발_배터리_차량": st.column_config.TextColumn("시작 충전량(%)", width="small"),
                    "종료_배터리_차량": st.column_config.TextColumn("종료 충전량(%)", width="small"),
                    "특이사항": st.column_config.TextColumn("특이(이슈)사항", width="large")
                }, 
                key="drive_editor"
            )
            
            if st.button("💾 운행일지 수정 적용", key="btn_save_drive", type="primary"):
                orig_d = set(d_edit_df['doc_id'].dropna())
                curr_d = set(edited_d['doc_id'].dropna())
                for d_id in (orig_d - curr_d): fm.delete_driving_log(d_id)
                    
                for _, row in edited_d.iterrows():
                    if pd.isna(row['doc_id']) or str(row['doc_id']).strip() == "": continue
                    orig_row = d_edit_df[d_edit_df['doc_id'] == row['doc_id']].iloc[0]
                    updates = {col: row[col] for col in ['날짜', '차량번호', 'Safe_Guard', '출발_km', '종료_km', '총주행거리(km)', '출발_배터리_차량', '종료_배터리_차량', '특이사항'] if col in row and str(row[col]) != str(orig_row.get(col))}
                    if updates: fm.update_driving_log(row['doc_id'], updates)
                        
                st.success("운행 일지 수정 완료!")
                time.sleep(1)
                st.rerun()
