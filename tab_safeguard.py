import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from chart_utils import *
import numpy as np
import datetime
import firebase_manager as fm

def draw_safeguard_tab(clean_df, df_drive_raw, sched_df):
    if clean_df.empty:
        st.warning("💡 기록된 데이터가 없습니다.")
        return
        
    is_mobile = st.session_state.get('is_mobile', False)
    
    # [최적화] 명시적 .copy() 및 기본값 채우기
    cdf = clean_df[clean_df['driverName'].astype(str).str.strip().astype(bool) & (clean_df['driverName'].astype(str) != '0')].copy()
    
    if 'duration_min' not in cdf.columns: 
        cdf['duration_min'] = 0
        
    try: 
        cdf['dt_obj'] = pd.to_datetime(cdf['dt_obj']).dt.tz_convert('Asia/Seoul')
    except Exception: 
        cdf['dt_obj'] = pd.to_datetime(cdf['dt_obj'], utc=True).dt.tz_convert('Asia/Seoul')
        
    cdf['shift_date_str'] = cdf['dt_obj'].apply(lambda dt: (dt - datetime.timedelta(days=1)).strftime('%Y-%m-%d') if pd.notna(dt) and dt.hour < 6 else dt.strftime('%Y-%m-%d') if pd.notna(dt) else None)
    cdf['shift_date'] = cdf['shift_date_str'].apply(lambda x: pd.to_datetime(x).date() if x else None)
    cdf['carNumber'] = cdf['carNumber'].astype(str).str.strip()
    cdf['차량번호'] = cdf['carNumber']
    
    if '이슈건수' not in cdf.columns: 
        cdf['이슈건수'] = 0

    df_drive = df_drive_raw.copy()
    if not df_drive.empty:
        df_drive['총주행거리(km)'] = pd.to_numeric(df_drive.get('총주행거리(km)', 0), errors='coerce').fillna(0)
        df_drive['특이사항'] = df_drive.get('특이사항', '').astype(str).replace(['nan', 'None', 'NaN'], '').str.strip()
        df_drive['차량번호'] = df_drive.get('차량번호', '').astype(str).str.replace(' ', '').str.strip()
        df_drive['유형_clean'] = df_drive.get('유형', '').astype(str).str.replace(' ', '').str.strip()
        
        def pt_s(val):
            if pd.isna(val) or val == "": 
                return pd.NaT
            try: 
                if isinstance(val, (int, float)) or (isinstance(val, str) and val.isdigit()):
                    return pd.to_datetime(int(val), unit='ms', utc=True).tz_convert('Asia/Seoul')
                else:
                    parsed_dt = pd.to_datetime(str(val), errors='coerce')
                    return parsed_dt.tz_convert('Asia/Seoul') if parsed_dt.tzinfo else parsed_dt.tz_localize('Asia/Seoul')
            except Exception: 
                return pd.NaT
            
        if 'timestamp' in df_drive.columns:
            df_drive['dt_obj'] = df_drive['timestamp'].apply(pt_s)
        else:
            df_drive['dt_obj'] = df_drive['날짜'].apply(pt_s)
            
        df_drive = df_drive.sort_values(['차량번호', 'dt_obj']).reset_index(drop=True)
        df_drive['is_start'] = df_drive['유형_clean'].isin(['출발', '시작', '출근'])
        df_drive['shift_id'] = df_drive.groupby('차량번호')['is_start'].cumsum()
        
        s_map = df_drive[df_drive['is_start']].groupby(['차량번호', 'shift_id'])['dt_obj'].first().to_dict()
        shift_starts = pd.to_datetime(df_drive.set_index(['차량번호', 'shift_id']).index.map(s_map).values)
        df_drive['shift_start_dt'] = pd.Series(shift_starts, index=df_drive.index).fillna(df_drive['dt_obj'])
        
        def fs_d(dt): 
            if pd.isna(dt):
                return pd.NaT
            if dt.hour < 6:
                return (dt - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
            return dt.strftime('%Y-%m-%d')
            
        df_drive['shift_date_str'] = df_drive['shift_start_dt'].apply(fs_d)
        df_drive['shift_date'] = df_drive['shift_date_str'].apply(lambda x: pd.to_datetime(x).date() if pd.notna(x) else None)
        
        dfs = df_drive[df_drive['is_start']].sort_values('dt_obj').drop_duplicates(subset=['shift_date_str', '차량번호', 'shift_id'], keep='first').rename(columns={'Safe_Guard': '출발자', 'timestamp': '출발_시간'})
        dfs = dfs[[c for c in ['shift_date_str', '차량번호', 'shift_id', '출발자', '출발_시간', '출발_장소', '출발_km', '출발_배터리_차량'] if c in dfs.columns]]
        
        dfe = df_drive[df_drive['유형_clean'].isin(['종료', '복귀', '도착', '퇴근', '마감'])].sort_values('dt_obj').drop_duplicates(subset=['shift_date_str', '차량번호', 'shift_id'], keep='last').rename(columns={'Safe_Guard': '종료자', 'timestamp': '종료_시간'})
        dfe = dfe[[c for c in ['shift_date_str', '차량번호', 'shift_id', '종료자', '종료_시간', '종료_장소', '종료_km', '종료_배터리_차량', '총주행거리(km)', '특이사항'] if c in dfe.columns]]
        
        df_merged = pd.merge(dfs, dfe, on=['shift_date_str', '차량번호', 'shift_id'], how='outer')
        
        if not cdf.empty:
            ds = df_drive[df_drive['is_start']][['차량번호', 'dt_obj', 'shift_id']].dropna(subset=['dt_obj']).copy().rename(columns={'차량번호': 'carNumber'})
            cs = cdf.dropna(subset=['dt_obj']).copy()
            cs['carNumber'] = cs.get('carNumber', '알수없음').astype(str).str.strip()
            
            ds['dt_obj_merge'] = ds['dt_obj'].dt.tz_localize(None).astype('datetime64[ns]')
            cs['dt_obj_merge'] = cs['dt_obj'].dt.tz_localize(None).astype('datetime64[ns]')
            ds = ds.sort_values('dt_obj_merge')
            cs = cs.sort_values('dt_obj_merge')
            
            if not ds.empty and not cs.empty:
                cm = pd.merge_asof(cs, ds, on='dt_obj_merge', by='carNumber', direction='backward')
                r_inf = cm.groupby(['shift_date_str', 'carNumber', 'shift_id']).agg(
                    운행자=('driverName', lambda x: ', '.join(sorted(set(x[x != ''].dropna().astype(str))))),
                    일일호출=('callCount', 'sum'),
                    일일탑승=('passengers', 'sum')
                ).reset_index().rename(columns={'carNumber': '차량번호'})
                df_merged = pd.merge(df_merged, r_inf, on=['shift_date_str', '차량번호', 'shift_id'], how='left')
            else:
                df_merged['운행자'], df_merged['일일호출'], df_merged['일일탑승'] = '-', '-', '-'
        else:
            df_merged['운행자'], df_merged['일일호출'], df_merged['일일탑승'] = '-', '-', '-'
            
        df_merged['출발_km_num'] = pd.to_numeric(df_merged['출발_km'], errors='coerce').fillna(0)
        df_merged['종료_km_num'] = pd.to_numeric(df_merged['종료_km'], errors='coerce').fillna(0)
        mask = (df_merged['종료_km_num'] > 0) & (df_merged['출발_km_num'] > 0) & (df_merged['종료_km_num'] >= df_merged['출발_km_num'])
        df_merged.loc[mask, '총주행거리(km)'] = df_merged.loc[mask, '종료_km_num'] - df_merged.loc[mask, '출발_km_num']
        df_merged['총주행거리(km)'] = df_merged['총주행거리(km)'].fillna(0)
        df_merged['특이사항'] = df_merged['특이사항'].fillna('')
        daily_car = df_merged.groupby(['shift_date_str', '차량번호']).agg({'총주행거리(km)': 'sum'}).reset_index()
    else: 
        df_merged = pd.DataFrame()
        daily_car = pd.DataFrame(columns=['shift_date_str', '차량번호', '총주행거리(km)'])
    
    d_map = cdf.groupby(['shift_date_str', 'carNumber', 'driverName'])['callCount'].sum().reset_index()
    d_map = d_map[d_map['callCount'] > 0][['shift_date_str', 'carNumber', 'driverName']]
    m_info = pd.merge(d_map, daily_car, left_on=['shift_date_str', 'carNumber'], right_on=['shift_date_str', '차량번호'], how='left')
    m_info['총주행거리(km)'] = pd.to_numeric(m_info['총주행거리(km)'], errors='coerce').fillna(0)
    sg_dtot = m_info.groupby('driverName')['총주행거리(km)'].sum().reset_index()
    
    sg_list = ["🌟 전체 Safe Guard 종합 통계"] + sorted(cdf['driverName'].dropna().unique().tolist())
    
    if 'sg_view_state' not in st.session_state: 
        st.session_state['sg_view_state'] = "🌟 전체 Safe Guard 종합 통계"
        
    if st.session_state['sg_view_state'] not in sg_list: 
        st.session_state['sg_view_state'] = sg_list[0]
    
    st.selectbox("🔍 Safe Guard 선택", sg_list, index=sg_list.index(st.session_state['sg_view_state']), key="sg_view_widget", on_change=lambda: st.session_state.update({'sg_view_state': st.session_state['sg_view_widget']}))
    
    def avg_dur(x): 
        valid_x = pd.to_numeric(x, errors='coerce').fillna(0)
        return valid_x[valid_x > 0].mean() if len(valid_x[valid_x > 0]) > 0 else 0
        
    t_css = "<style>.premium-table-wrapper { overflow-x: auto; overflow-y: auto; max-height: 500px; margin-top: 15px; border-radius: 16px; border: 1px solid #e2e8f0; box-shadow: 0 4px 20px rgba(0,0,0,0.03); background: white; -webkit-overflow-scrolling: touch; } .premium-table { width: 100%; min-width: 800px; border-collapse: collapse; text-align: center; font-size: 13px; font-family: Pretendard, sans-serif; white-space: nowrap; } .premium-table th, .premium-table td { border-bottom: 1px solid #e2e8f0; border-right: 1px solid #f1f5f9; padding: 12px 10px; } .premium-table th:last-child, .premium-table td:last-child { border-right: none; } .premium-table th { background-color: #f8fafc; color: #334155; font-weight: 700; position: sticky; top: 0; z-index: 1; box-shadow: 0 1px 0 #e2e8f0; } .premium-table tbody tr:hover { background-color: #f1f5f9; transition: background-color 0.2s; }</style>"

    if st.session_state['sg_view_state'] == "🌟 전체 Safe Guard 종합 통계":
        draw_html_calendar_with_plan(cdf, sched_df, 'driverName', '근무 스케줄 현황 (달력)')
        st.divider()
        
        sg_r = cdf.groupby('driverName').agg(호출처리=('callCount','sum'), 탑승객처리=('passengers','sum'), 이슈발생=('이슈건수','sum'), 운행일수=('shift_date','nunique'), 평균소요분=('duration_min', avg_dur)).reset_index()
        m_sg = pd.merge(sg_r, sg_dtot, on='driverName', how='left').fillna(0)
        
        cdf['car_prefix'] = cdf['carNumber'].astype(str).str.strip().str[0].str.upper()
        e_days = cdf[cdf['car_prefix'] == 'E'].groupby('driverName')['shift_date'].nunique().reset_index(name='E_days')
        u_days = cdf[cdf['car_prefix'] == 'U'].groupby('driverName')['shift_date'].nunique().reset_index(name='U_days')
        
        m_sg = pd.merge(m_sg, e_days, on='driverName', how='left').fillna(0)
        m_sg = pd.merge(m_sg, u_days, on='driverName', how='left').fillna(0)
        
        m_sg = m_sg[m_sg['호출처리'] > 0].copy() 
        
        for c in ['운행일수', '호출처리', '탑승객처리', '이슈발생', '총주행거리(km)', 'E_days', 'U_days']: 
            m_sg[c] = pd.to_numeric(m_sg[c], errors='coerce').fillna(0).astype(int)
            
        m_sg['일평균_호출(건)'] = (m_sg['호출처리'] / m_sg['운행일수'].replace(0, 1)).replace([np.inf, -np.inf, np.nan], 0).round(1)
        m_sg['일평균_주행(km)'] = (m_sg['총주행거리(km)'] / m_sg['운행일수'].replace(0, 1)).replace([np.inf, -np.inf, np.nan], 0).round(1)
        m_sg['건당_소요(분)'] = m_sg['평균소요분'].round(1)
        
        m_sg['운행일수_표시'] = m_sg.apply(lambda r: f"{int(r['운행일수'])}일 (E:{int(r['E_days'])}, U:{int(r['U_days'])})", axis=1)
        
        m_sg = m_sg.sort_values(by='호출처리', ascending=False)
        st.markdown("### 🏆 인원 별 분석")
        
        mc = max(m_sg[['호출처리', '탑승객처리']].max().max() * 1.2, 10) if not m_sg.empty else 10
        ma = max(m_sg[['일평균_호출(건)', '일평균_주행(km)']].max().max() * 1.2, 10) if not m_sg.empty else 10
        
        if is_mobile:
            st.caption("누적 (호출/탑승객)")
            f_c = px.bar(m_sg.melt(id_vars='driverName', value_vars=['호출처리', '탑승객처리'], var_name='구분', value_name='값'), x='driverName', y='값', color='구분', barmode='group', text_auto=True, color_discrete_sequence=['#4F46E5', '#10B981'])
            f_c.update_traces(textposition="outside", cliponaxis=False, textfont=dict(weight="bold"))
            f_c.update_layout(dragmode=False, margin=dict(t=20, b=10), xaxis_title="")
            f_c.update_yaxes(range=[0, mc], fixedrange=True)
            st.plotly_chart(apply_modern_theme(f_c), use_container_width=True, config={'displayModeBar': False})
            
            st.caption("일평균 (호출/주행거리)")
            f_a = px.bar(m_sg.melt(id_vars='driverName', value_vars=['일평균_호출(건)', '일평균_주행(km)'], var_name='구분', value_name='값'), x='driverName', y='값', color='구분', barmode='group', text_auto=True, color_discrete_sequence=['#F59E0B', '#94A3B8'])
            f_a.update_traces(textposition="outside", cliponaxis=False, textfont=dict(weight="bold"))
            f_a.update_layout(dragmode=False, margin=dict(t=20, b=10), xaxis_title="")
            f_a.update_yaxes(range=[0, ma], fixedrange=True)
            st.plotly_chart(apply_modern_theme(f_a), use_container_width=True, config={'displayModeBar': False})
        else:
            c1, c2 = st.columns(2)
            with c1: 
                st.caption("누적 (호출/탑승객)")
                f_c = px.bar(m_sg.melt(id_vars='driverName', value_vars=['호출처리', '탑승객처리'], var_name='구분', value_name='값'), x='driverName', y='값', color='구분', barmode='group', text_auto=True, color_discrete_sequence=['#4F46E5', '#10B981'])
                f_c.update_traces(textposition="outside", cliponaxis=False, textfont=dict(weight="bold"))
                f_c.update_layout(dragmode=False, margin=dict(t=20, b=10), xaxis_title="")
                f_c.update_yaxes(range=[0, mc], fixedrange=True)
                st.plotly_chart(apply_modern_theme(f_c), use_container_width=True, config={'displayModeBar': False})
            with c2: 
                st.caption("일평균 (호출/주행거리)")
                f_a = px.bar(m_sg.melt(id_vars='driverName', value_vars=['일평균_호출(건)', '일평균_주행(km)'], var_name='구분', value_name='값'), x='driverName', y='값', color='구분', barmode='group', text_auto=True, color_discrete_sequence=['#F59E0B', '#94A3B8'])
                f_a.update_traces(textposition="outside", cliponaxis=False, textfont=dict(weight="bold"))
                f_a.update_layout(dragmode=False, margin=dict(t=20, b=10), xaxis_title="")
                f_a.update_yaxes(range=[0, ma], fixedrange=True)
                st.plotly_chart(apply_modern_theme(f_a), use_container_width=True, config={'displayModeBar': False})
        
        st.divider()
        st.markdown("### 📋 인원 별 상세 표")
        st.caption("💡 표의 열 제목을 클릭하시면 오름차순/내림차순 정렬이 가능합니다!")
        
        st.dataframe(
            m_sg[['driverName', '운행일수_표시', '호출처리', '탑승객처리', '총주행거리(km)', '일평균_호출(건)', '일평균_주행(km)', '건당_소요(분)', '이슈발생']], 
            hide_index=True, 
            use_container_width=True, 
            column_config={
                "driverName": st.column_config.TextColumn("요원명"), 
                "운행일수_표시": st.column_config.TextColumn("운행일수 (차량별)"), 
                "호출처리": st.column_config.NumberColumn("호출처리", format="%d 회"), 
                "탑승객처리": st.column_config.NumberColumn("탑승객처리", format="%d 명"), 
                "총주행거리(km)": st.column_config.NumberColumn("총주행거리", format="%d km"), 
                "일평균_호출(건)": st.column_config.NumberColumn("일평균 호출", format="%.1f 건"), 
                "일평균_주행(km)": st.column_config.NumberColumn("일평균 주행", format="%.1f km"), 
                "건당_소요(분)": st.column_config.NumberColumn("건당 소요", format="%.1f 분"), 
                "이슈발생": st.column_config.NumberColumn("이슈발생", format="%d 건")
            }
        )
        
    else:
        tsg = st.session_state['sg_view_state']
        sg_r = cdf[cdf['driverName'] == tsg].copy()
        sg_m = m_info[m_info['driverName'] == tsg].copy()
        sg_s = sched_df[sched_df['name'] == tsg] if not sched_df.empty and 'name' in sched_df.columns else pd.DataFrame(columns=['date', 'name', 'type'])
        
        dw = sg_r['shift_date'].nunique()
        tci = int(pd.to_numeric(sg_r['callCount'], errors='coerce').fillna(0).sum())
        tpi = int(pd.to_numeric(sg_r['passengers'], errors='coerce').fillna(0).sum())
        tki = int(pd.to_numeric(sg_m['총주행거리(km)'], errors='coerce').fillna(0).sum()) if not sg_m.empty else 0
        
        vsd = sg_r[sg_r['duration_min'] > 0]
        asd = round(vsd['duration_min'].mean(), 1) if not vsd.empty else 0
        adc = round(tci / dw, 1) if dw > 0 else 0
        adk = round(tki / dw, 1) if dw > 0 else 0
        aic = 0
        
        df_idle = sg_r[sg_r['duration_min'] > 0].sort_values(['shift_date', 'dt_obj']).copy()
        if not df_idle.empty:
            df_idle['end_time'] = df_idle['dt_obj'] + pd.to_timedelta(df_idle['duration_min'], unit='m')
            df_idle['next_start'] = df_idle.groupby('shift_date')['dt_obj'].shift(-1)
            df_idle['idle_min'] = (df_idle['next_start'] - df_idle['end_time']).dt.total_seconds() / 60
            vi = df_idle[(df_idle['idle_min'] >= 0) & (df_idle['idle_min'] <= 180)]
            if not vi.empty: 
                aic = round(vi['idle_min'].mean(), 1)
            
        if is_mobile: 
            st.markdown(f"<div style='display: flex; flex-direction: column; gap: 10px; margin-bottom: 20px;'><div style='background: white; padding: 15px; border-radius: 15px; border: 1px solid #f1f5f9;'><span style='font-size:20px;'>🗓️</span> <b style='color:#475569;'>운행 일수:</b> <span style='font-size:20px; font-weight:800; color:#0f172a; float:right;'>{dw} 일</span></div><div style='background: linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%); padding: 15px; border-radius: 15px; border: 1px solid #c7d2fe;'><span style='font-size:20px;'>📞</span> <b style='color:#3730a3;'>호출 처리:</b> <span style='font-size:20px; font-weight:800; color:#312e81; float:right;'>{tci:,} 회</span></div><div style='background: white; padding: 15px; border-radius: 15px; border: 1px solid #f1f5f9;'><span style='font-size:20px;'>📈</span> <b style='color:#475569;'>일평균 호출:</b> <span style='font-size:20px; font-weight:800; color:#0f172a; float:right;'>{adc} 회</span></div><div style='background: linear-gradient(135deg, #ecfdf5 0%, #dcfce7 100%); padding: 15px; border-radius: 15px; border: 1px solid #bbf7d0;'><span style='font-size:20px;'>👥</span> <b style='color:#166534;'>탑승객 처리:</b> <span style='font-size:20px; font-weight:800; color:#14532d; float:right;'>{tpi:,} 명</span></div><div style='background: white; padding: 15px; border-radius: 15px; border: 1px solid #f1f5f9;'><span style='font-size:20px;'>🚕</span> <b style='color:#475569;'>총 주행 거리:</b> <span style='font-size:20px; font-weight:800; color:#ea580c; float:right;'>{tki:,} km</span></div><div style='background: white; padding: 15px; border-radius: 15px; border: 1px solid #f1f5f9;'><span style='font-size:20px;'>🏎️</span> <b style='color:#475569;'>일평균 주행:</b> <span style='font-size:20px; font-weight:800; color:#ea580c; float:right;'>{adk} km</span></div><div style='background: white; padding: 15px; border-radius: 15px; border: 1px solid #f1f5f9;'><span style='font-size:20px;'>⏱️</span> <b style='color:#475569;'>평균 소요:</b> <span style='font-size:20px; font-weight:800; color:#2563eb; float:right;'>{asd} 분</span></div><div style='background: #fffbeb; padding: 15px; border-radius: 15px; border: 1px solid #fde68a;'><span style='font-size:20px;'>☕</span> <b style='color:#b45309;'>건당 평균 대기:</b> <span style='font-size:20px; font-weight:800; color:#92400e; float:right;'>{aic} 분</span></div></div>", unsafe_allow_html=True)
        else: 
            st.markdown(f"<div style='display: flex; gap: 15px; margin-bottom: 25px; flex-wrap: wrap;'><div style='flex: 1 1 20%; min-width: 200px; background: #ffffff; padding: 20px; border-radius: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); border: 1px solid #f1f5f9;'><div style='font-size: 22px; margin-bottom: 8px;'>🗓️</div><div style='font-size: 13px; color: #64748b; font-weight: 600; margin-bottom: 2px;'>운행 일수</div><div style='font-size: 26px; color: #0f172a; font-weight: 800;'>{dw} <span style='font-size: 15px; color: #94a3b8; font-weight: 600;'>일</span></div></div><div style='flex: 1 1 20%; min-width: 200px; background: linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%); padding: 20px; border-radius: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); border: 1px solid #c7d2fe;'><div style='font-size: 22px; margin-bottom: 8px;'>📞</div><div style='font-size: 13px; color: #3730a3; font-weight: 600; margin-bottom: 2px;'>총 호출 처리</div><div style='font-size: 26px; color: #312e81; font-weight: 800;'>{tci:,} <span style='font-size: 15px; color: #4338ca; font-weight: 600;'>회</span></div></div><div style='flex: 1 1 20%; min-width: 200px; background: linear-gradient(135deg, #ecfdf5 0%, #dcfce7 100%); padding: 20px; border-radius: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); border: 1px solid #bbf7d0;'><div style='font-size: 22px; margin-bottom: 8px;'>👥</div><div style='font-size: 13px; color: #166534; font-weight: 600; margin-bottom: 2px;'>총 탑승객 처리</div><div style='font-size: 26px; color: #14532d; font-weight: 800;'>{tpi:,} <span style='font-size: 15px; color: #16a34a; font-weight: 600;'>명</span></div></div><div style='flex: 1 1 20%; min-width: 200px; background: #ffffff; padding: 20px; border-radius: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); border: 1px solid #f1f5f9;'><div style='font-size: 22px; margin-bottom: 8px;'>🚕</div><div style='font-size: 13px; color: #64748b; font-weight: 600; margin-bottom: 2px;'>총 주행 거리</div><div style='font-size: 26px; color: #ea580c; font-weight: 800;'>{tki:,} <span style='font-size: 15px; color: #94a3b8; font-weight: 600;'>km</span></div></div><div style='flex: 1 1 20%; min-width: 200px; background: #f8fafc; padding: 20px; border-radius: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); border: 1px solid #e2e8f0;'><div style='font-size: 22px; margin-bottom: 8px;'>📈</div><div style='font-size: 13px; color: #475569; font-weight: 600; margin-bottom: 2px;'>일평균 호출 처리</div><div style='font-size: 26px; color: #0f172a; font-weight: 800;'>{adc} <span style='font-size: 15px; color: #64748b; font-weight: 600;'>회</span></div></div><div style='flex: 1 1 20%; min-width: 200px; background: #f8fafc; padding: 20px; border-radius: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); border: 1px solid #e2e8f0;'><div style='font-size: 22px; margin-bottom: 8px;'>🏎️</div><div style='font-size: 13px; color: #475569; font-weight: 600; margin-bottom: 2px;'>일평균 주행거리</div><div style='font-size: 26px; color: #c2410c; font-weight: 800;'>{adk} <span style='font-size: 15px; color: #64748b; font-weight: 600;'>km</span></div></div><div style='flex: 1 1 20%; min-width: 200px; background: #ffffff; padding: 20px; border-radius: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); border: 1px solid #f1f5f9;'><div style='font-size: 22px; margin-bottom: 8px;'>⏱️</div><div style='font-size: 13px; color: #64748b; font-weight: 600; margin-bottom: 2px;'>건당 평균 소요시간</div><div style='font-size: 26px; color: #2563eb; font-weight: 800;'>{asd} <span style='font-size: 15px; color: #94a3b8; font-weight: 600;'>분</span></div></div><div style='flex: 1 1 20%; min-width: 200px; background: #fffbeb; padding: 20px; border-radius: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); border: 1px solid #fde68a;'><div style='font-size: 22px; margin-bottom: 8px;'>☕</div><div style='font-size: 13px; color: #92400e; font-weight: 600; margin-bottom: 2px;'>건당 평균 대기시간</div><div style='font-size: 26px; color: #b45309; font-weight: 800;'>{aic} <span style='font-size: 15px; color: #d97706; font-weight: 600;'>분</span></div></div></div>", unsafe_allow_html=True)
        
        st.divider()
        draw_html_calendar_with_plan(sg_r, sg_s, 'carNumber', f"{tsg} 스케줄")
        
        st.divider()
        st.markdown(f"### 🚖 {tsg} 운행 일지")
        
        try: 
            sw_db = fm.load_data('sw_versions')
        except Exception: 
            sw_db = {}
        
        if not df_merged.empty:
            my_disp = df_merged[
                df_merged['출발자'].astype(str).str.contains(tsg) |
                df_merged['운행자'].astype(str).str.contains(tsg) |
                df_merged['종료자'].astype(str).str.contains(tsg)
            ].copy()
            
            if not my_disp.empty:
                def s_pt(v): 
                    if pd.isna(v) or v in ['-', '']:
                        return '-'
                    if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
                        return datetime.datetime.fromtimestamp(int(v)/1000).strftime('%H:%M:%S')
                    return pd.to_datetime(str(v), errors='coerce').strftime('%H:%M:%S')
                    
                my_disp['출발_시간'] = my_disp.apply(lambda r: s_pt(r.get('출발_시간')), axis=1)
                my_disp['종료_시간'] = my_disp.apply(lambda r: s_pt(r.get('종료_시간')), axis=1)
                my_disp = my_disp.fillna('-').sort_values(['shift_date_str', '차량번호', 'shift_id'], ascending=[False, True, True])
                
                for col in my_disp.columns:
                    if my_disp[col].dtype == object:
                        my_disp[col] = my_disp[col].astype(str).replace(['nan', 'NaN', 'None'], '-')

                h = ""
                h += "<div style='overflow-x: auto; overflow-y: auto; max-height: 500px; -webkit-overflow-scrolling: touch; margin-top: 15px; border-radius: 16px; border: 1px solid #e2e8f0; box-shadow: 0 4px 20px rgba(0,0,0,0.03); background: white;'>"
                h += "<style>.log-table { width: 100%; min-width: 1000px; border-collapse: collapse; text-align: center; font-size: 13px; font-family: Pretendard, sans-serif; white-space: nowrap; } .log-table th, .log-table td { border-bottom: 1px solid #e2e8f0; border-right: 1px solid #f1f5f9; padding: 12px 10px; } .log-table th:last-child, .log-table td:last-child { border-right: none; } .log-table th { background-color: #f8fafc; color: #334155; font-weight: 700; position: sticky; top: 0; z-index: 1; box-shadow: 0 1px 0 #e2e8f0; } .log-table tbody tr:hover { background-color: #f1f5f9; transition: background-color 0.2s; }</style>"
                h += "<table class='log-table'>"
                h += "<thead>"
                h += "<tr>"
                h += "<th rowspan='2' style='background:#f1f5f9; color:#475569; padding:12px 10px; border-bottom:2px solid #e2e8f0; border-right:1px solid #e2e8f0; font-weight:700;'>운행<br>일자</th>"
                h += "<th rowspan='2' style='background:#f1f5f9; color:#475569; padding:12px 10px; border-bottom:2px solid #e2e8f0; border-right:1px solid #e2e8f0; font-weight:700;'>차량<br>번호</th>"
                h += "<th colspan='3' style='background:#f8fafc; color:#475569; padding:8px 10px; border-bottom:1px solid #e2e8f0; border-right:1px solid #e2e8f0; font-weight:700;'>담당</th>"
                h += "<th colspan='2' style='background:#f8fafc; color:#475569; padding:8px 10px; border-bottom:1px solid #e2e8f0; border-right:1px solid #e2e8f0; font-weight:700;'>탑승 실적</th>"
                h += "<th colspan='3' style='background:#f8fafc; color:#475569; padding:8px 10px; border-bottom:1px solid #e2e8f0; border-right:1px solid #e2e8f0; font-weight:700;'>계기판 (km)</th>"
                h += "<th colspan='2' style='background:#f8fafc; color:#475569; padding:8px 10px; border-bottom:1px solid #e2e8f0; border-right:1px solid #e2e8f0; font-weight:700;'>시간</th>"
                h += "<th colspan='2' style='background:#f8fafc; color:#475569; padding:8px 10px; border-bottom:1px solid #e2e8f0; border-right:1px solid #e2e8f0; font-weight:700;'>차량 배터리(%)</th>"
                h += "<th colspan='7' style='background:#f8fafc; color:#475569; padding:8px 10px; border-bottom:1px solid #e2e8f0; border-right:1px solid #e2e8f0; font-weight:700;'>S/W 버전</th>"
                h += "<th rowspan='2' style='background:#f1f5f9; color:#475569; padding:12px 10px; border-bottom:2px solid #e2e8f0; font-weight:700;'>특이(이슈)사항</th>"
                h += "</tr>"
                h += "<tr>"
                h += "<th style='background:#f8fafc; color:#64748b; padding:8px 10px; border-bottom:2px solid #e2e8f0; border-right:1px solid #f1f5f9;'>출발자</th>"
                h += "<th style='background:#e0e7ff; color:#4338ca; padding:8px 10px; border-bottom:2px solid #e2e8f0; border-right:1px solid #f1f5f9; font-weight:700;'>운행자</th>"
                h += "<th style='background:#f8fafc; color:#64748b; padding:8px 10px; border-bottom:2px solid #e2e8f0; border-right:1px solid #e2e8f0;'>종료자</th>"
                h += "<th style='background:#fdf2f8; color:#be185d; padding:8px 10px; border-bottom:2px solid #e2e8f0; border-right:1px solid #f1f5f9; font-weight:700;'>호출(건)</th>"
                h += "<th style='background:#fdf2f8; color:#be185d; padding:8px 10px; border-bottom:2px solid #e2e8f0; border-right:1px solid #e2e8f0; font-weight:700;'>탑승(명)</th>"
                h += "<th style='background:#fffbeb; color:#854d0e; padding:8px 10px; border-bottom:2px solid #e2e8f0; border-right:1px solid #f1f5f9;'>시작</th>"
                h += "<th style='background:#fffbeb; color:#854d0e; padding:8px 10px; border-bottom:2px solid #e2e8f0; border-right:1px solid #f1f5f9;'>종료</th>"
                h += "<th style='background:#fffbeb; color:#ea580c; padding:8px 10px; border-bottom:2px solid #e2e8f0; border-right:1px solid #e2e8f0; font-weight:700;'>운행거리</th>"
                h += "<th style='background:#f8fafc; color:#64748b; padding:8px 10px; border-bottom:2px solid #e2e8f0; border-right:1px solid #f1f5f9;'>출발</th>"
                h += "<th style='background:#f8fafc; color:#64748b; padding:8px 10px; border-bottom:2px solid #e2e8f0; border-right:1px solid #e2e8f0;'>도착</th>"
                h += "<th style='background:#f0fdf4; color:#166534; padding:8px 10px; border-bottom:2px solid #e2e8f0; border-right:1px solid #f1f5f9; font-weight:700;'>시작</th>"
                h += "<th style='background:#f0fdf4; color:#166534; padding:8px 10px; border-bottom:2px solid #e2e8f0; border-right:1px solid #e2e8f0; font-weight:700;'>종료</th>"
                h += "<th style='background:#f8fafc; color:#64748b; padding:8px 10px; border-bottom:2px solid #e2e8f0; border-right:1px solid #f1f5f9;'>SV</th>"
                h += "<th style='background:#f8fafc; color:#64748b; padding:8px 10px; border-bottom:2px solid #e2e8f0; border-right:1px solid #f1f5f9;'>CPU</th>"
                h += "<th style='background:#f8fafc; color:#64748b; padding:8px 10px; border-bottom:2px solid #e2e8f0; border-right:1px solid #f1f5f9;'>MCU</th>"
                h += "<th style='background:#f8fafc; color:#64748b; padding:8px 10px; border-bottom:2px solid #e2e8f0; border-right:1px solid #f1f5f9;'>V1</th>"
                h += "<th style='background:#f8fafc; color:#64748b; padding:8px 10px; border-bottom:2px solid #e2e8f0; border-right:1px solid #f1f5f9;'>V2</th>"
                h += "<th style='background:#f8fafc; color:#64748b; padding:8px 10px; border-bottom:2px solid #e2e8f0; border-right:1px solid #f1f5f9;'>V3</th>"
                h += "<th style='background:#f8fafc; color:#64748b; padding:8px 10px; border-bottom:2px solid #e2e8f0; border-right:1px solid #e2e8f0;'>V4</th>"
                h += "</tr>"
                h += "</thead>"
                h += "<tbody>"
                
                for _, r in my_disp.iterrows():
                    dt_view = pd.to_datetime(r.get('shift_date_str')).strftime('%m/%d') if pd.notna(r.get('shift_date_str')) and r.get('shift_date_str') != '-' else '-'
                    sw_key = f"{r.get('shift_date_str', '')}_{r.get('차량번호', '')}"
                    sw = sw_db.get(sw_key, {})
                    sv, cpu, mcu, v1, v2, v3, v4 = sw.get('Safeview','-'), sw.get('CPU','-'), sw.get('MCU','-'), sw.get('VPU1','-'), sw.get('VPU2','-'), sw.get('VPU3','-'), sw.get('VPU4','-')
                    
                    ic = str(r.get('종료자', '-')) != '-' and str(r.get('종료자', '')).strip() != ''
                    cv = f"{int(float(r.get('일일호출', '-')))}" if ic and str(r.get('일일호출', '-')) != '-' else '-'
                    pv = f"{int(float(r.get('일일탑승', '-')))}" if ic and str(r.get('일일탑승', '-')) != '-' else '-'
                    
                    sk_v = f"{int(float(r.get('출발_km','-'))):,}" if r.get('출발_km','-') not in ['-',''] else r.get('출발_km','-')
                    ek_v = f"{int(float(r.get('종료_km','-'))):,}" if r.get('종료_km','-') not in ['-',''] else r.get('종료_km','-')
                    tk_v = f"{int(float(r.get('총주행거리(km)','-'))):,}" if r.get('총주행거리(km)','-') not in ['-',''] else r.get('총주행거리(km)','-')
                    
                    sbc = f"{int(float(r.get('출발_배터리_차량','-')))}%" if r.get('출발_배터리_차량','-') not in ['-',''] else r.get('출발_배터리_차량','-')
                    ebc = f"{int(float(r.get('종료_배터리_차량','-')))}%" if r.get('종료_배터리_차량','-') not in ['-',''] else r.get('종료_배터리_차량','-')
                    
                    h += f"<tr style=\"background:white; transition:background 0.2s;\" onmouseover=\"this.style.background='#f8fafc'\" onmouseout=\"this.style.background='white'\">"
                    h += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #f1f5f9; font-weight:700; color:#475569;'>{dt_view}</td>"
                    h += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #e2e8f0; font-weight:700; color:#0f172a;'>{r.get('차량번호', '-')}</td>"
                    h += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #f1f5f9; color:#64748b;'>{r.get('출발자', '-')}</td>"
                    h += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #f1f5f9; font-weight:700; color:#4f46e5;'>{r.get('운행자', '-')}</td>"
                    h += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #e2e8f0; color:#64748b;'>{r.get('종료자', '-')}</td>"
                    h += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #f1f5f9; font-weight:700; color:#be185d;'>{cv}</td>"
                    h += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #e2e8f0; font-weight:700; color:#be185d;'>{pv}</td>"
                    h += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #f1f5f9; color:#64748b;'>{sk_v}</td>"
                    h += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #f1f5f9; color:#64748b;'>{ek_v}</td>"
                    h += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #e2e8f0; font-weight:700; color:#ea580c;'>{tk_v}</td>"
                    h += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #f1f5f9; color:#64748b;'>{r.get('출발_시간', '-')}</td>"
                    h += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #e2e8f0; color:#64748b;'>{r.get('종료_시간', '-')}</td>"
                    h += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #f1f5f9; font-weight:700; color:#166534;'>{sbc}</td>"
                    h += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #e2e8f0; font-weight:700; color:#991b1b;'>{ebc}</td>"
                    h += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #f1f5f9; color:#64748b; font-size:11px;'>{sv}</td>"
                    h += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #f1f5f9; color:#64748b; font-size:11px;'>{cpu}</td>"
                    h += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #f1f5f9; color:#64748b; font-size:11px;'>{mcu}</td>"
                    h += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #f1f5f9; color:#64748b; font-size:11px;'>{v1}</td>"
                    h += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #f1f5f9; color:#64748b; font-size:11px;'>{v2}</td>"
                    h += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #f1f5f9; color:#64748b; font-size:11px;'>{v3}</td>"
                    h += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #e2e8f0; color:#64748b; font-size:11px;'>{v4}</td>"
                    h += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; text-align:left; white-space:normal; min-width:150px; color:#ef4444;'>{r.get('특이사항', '-')}</td>"
                    h += "</tr>"
                    
                h += "</tbody></table></div>"
                st.markdown(h, unsafe_allow_html=True)
            else: 
                st.info(f"💡 {tsg} 의 일지 기록이 없습니다.")
        else: 
            st.warning("기록된 운행 일지가 없습니다.")
        
        st.divider()
        st.markdown(f"### 📋 {tsg} 탑승 누적 기록")
        
        if is_mobile: 
            st.caption("👉 표를 옆으로 밀어서 확인하세요.")
        
        if not sg_r.empty:
            rides_df = sg_r[sg_r['status'] != 'ISSUE_ONLY'].sort_values('dt_obj', ascending=False).copy()
            for col in rides_df.columns:
                if rides_df[col].dtype == object:
                    rides_df[col] = rides_df[col].astype(str).replace(['nan', 'NaN', 'None'], '-')
                    
            if not rides_df.empty:
                hr = t_css + "<div class='premium-table-wrapper'><table class='premium-table'><thead><tr><th>기록 시간(YYYY-MM-DD HH:MM:SS)</th><th>차량</th><th>기사명</th><th>콜수</th><th>탑승객수</th><th>비고 (특이사항)</th></tr></thead><tbody>"
                for _, r in rides_df.iterrows():
                    rem = str(r.get('remark', '-')).strip()
                    rem = '-' if not rem or rem == 'nan' else rem
                    hr += f"<tr><td style='color:#64748b;'>{r['timestamp_str']}</td><td style='font-weight:700; color:#0f172a;'>{r['carNumber']}</td><td style='font-weight:700; color:#4F46E5;'>{r['driverName']}</td><td style='font-weight:700; color:#be185d;'>{r['callCount']}</td><td style='font-weight:700; color:#10B981;'>{r['passengers']}</td><td style='color:#64748b; text-align:left;'>{rem}</td></tr>"
                st.markdown(hr + "</tbody></table></div>", unsafe_allow_html=True)
            else: 
                st.info("기록된 탑승 누적 데이터가 없습니다.")
        else: 
            st.info("기록된 탑승 데이터가 없습니다.")
        
        st.divider()
        st.markdown(f"### 🚨 {tsg} 이슈 발굴 기록")
        issues_df = get_exploded_issues(sg_r)
        
        if not issues_df.empty:
            for col in issues_df.columns:
                if issues_df[col].dtype == object:
                    issues_df[col] = issues_df[col].astype(str).replace(['nan', 'NaN', 'None'], '-')
                    
            hi = t_css + "<div class='premium-table-wrapper'><table class='premium-table'><thead><tr><th>발생시간</th><th>차량번호</th><th>대분류</th><th>중분류</th><th>내용 상세</th><th>위도</th><th>경도</th></tr></thead><tbody>"
            for _, r in issues_df.iterrows(): 
                hi += f"<tr><td>{r['발생시간']}</td><td>{r['차량']}</td><td style='color:#b91c1c; font-weight:bold;'>{r['대분류']}</td><td>{r['중분류']}</td><td style='text-align:left; white-space:normal; min-width:200px;'>{r['📝상세']}</td><td>{r['위도(Lat)']}</td><td>{r['경도(Lng)']}</td></tr>"
            st.markdown(hi + "</tbody></table></div>", unsafe_allow_html=True)
        else: 
            st.info("기록된 이슈 발굴 데이터가 없습니다.")
        
        st.divider()
        st.markdown(f"### 📊 {tsg} 일일 업무 추이")
        
        if not sg_r.empty:
            daily_stats = sg_r.groupby('shift_date').agg(calls=('callCount', 'sum'), issues=('이슈건수', 'sum')).reset_index()
            daily_stats['shift_date'] = pd.to_datetime(daily_stats['shift_date'])
            
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Bar(x=daily_stats['shift_date'], y=daily_stats['calls'], name='호출(건)', marker_color='#4F46E5', text=daily_stats['calls'].apply(lambda x: f"{int(x)}" if x>0 else ""), textposition='outside'), secondary_y=False)
            fig.add_trace(go.Bar(x=daily_stats['shift_date'], y=daily_stats['issues'], name='이슈발굴(건)', marker_color='#EF4444', text=daily_stats['issues'].apply(lambda x: f"{int(x)}" if x>0 else ""), textposition='outside'), secondary_y=False)
            
            mask_c = daily_stats['calls'] > 0
            if mask_c.sum() > 1:
                idx = np.arange(len(daily_stats))
                z = np.polyfit(idx[mask_c], daily_stats['calls'][mask_c], 1)
                p = np.poly1d(z)
                fig.add_trace(go.Scatter(x=daily_stats['shift_date'], y=p(idx), name='호출 추세', mode='lines', line=dict(color='#312E81', dash='dot')), secondary_y=False)
            
            mask_i = daily_stats['issues'] > 0
            if mask_i.sum() > 1:
                idx = np.arange(len(daily_stats))
                z = np.polyfit(idx[mask_i], daily_stats['issues'][mask_i], 1)
                p = np.poly1d(z)
                fig.add_trace(go.Scatter(x=daily_stats['shift_date'], y=p(idx), name='이슈 추세', mode='lines', line=dict(color='#7F1D1D', dash='dot')), secondary_y=False)
                
            fig.update_layout(barmode='group', plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=1.12), margin=dict(t=30, b=20), height=450)
            mc = max(daily_stats[['calls', 'issues']].max().max() * 1.3, 10)
            fig.update_yaxes(title_text="건수", showgrid=True, gridcolor="#E2E8F0", range=[0, mc], fixedrange=True, secondary_y=False)
            fig.update_xaxes(showgrid=False, fixedrange=True)
            fig.update_traces(cliponaxis=False)
            
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        else:
            st.info("차트를 생성할 데이터가 없습니다.")
