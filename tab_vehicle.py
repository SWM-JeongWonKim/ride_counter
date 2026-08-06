import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from chart_utils import *
import numpy as np
import datetime
import firebase_manager as fm

def draw_car_tab(clean_df, df_drive_raw):
    if clean_df.empty:
        st.warning("💡 기록된 데이터가 없습니다.")
        return
        
    is_mobile = st.session_state.get('is_mobile', False)
    
    # [최적화] 명시적 .copy() 적용
    cdf = clean_df[clean_df['carNumber'].astype(str).str.strip().astype(bool) & (clean_df['carNumber'].astype(str) != '0')].copy()
    
    if 'duration_min' not in cdf.columns: 
        cdf['duration_min'] = 0
        
    cdf['dt_obj'] = pd.to_datetime(cdf['dt_obj'], errors='coerce')
    cdf['shift_date_str'] = cdf['dt_obj'].apply(lambda dt: (dt - datetime.timedelta(days=1)).strftime('%Y-%m-%d') if pd.notna(dt) and dt.hour < 6 else dt.strftime('%Y-%m-%d') if pd.notna(dt) else None)
    cdf['shift_date'] = cdf['shift_date_str'].apply(lambda x: pd.to_datetime(x).date() if x else None)
    cdf['carNumber'] = cdf['carNumber'].astype(str).str.strip()
    
    if '이슈건수' not in cdf.columns: 
        cdf['이슈건수'] = 0

    df_drive = df_drive_raw.copy()
    if not df_drive.empty:
        df_drive['dt_obj'] = pd.to_datetime(df_drive['timestamp'] if 'timestamp' in df_drive.columns else df_drive['날짜'], errors='coerce')
        df_drive['차량번호'] = df_drive['차량번호'].astype(str).str.strip()
        df_drive['유형_clean'] = df_drive.get('유형', '').astype(str).str.replace(' ', '').str.strip()
        
        df_drive = df_drive.sort_values(['차량번호', 'dt_obj']).reset_index(drop=True)
        df_drive['is_start'] = df_drive['유형_clean'].isin(['출발', '시작', '출근'])
        df_drive['shift_id'] = df_drive.groupby('차량번호')['is_start'].cumsum()
        
        s_map = df_drive[df_drive['is_start']].groupby(['차량번호', 'shift_id'])['dt_obj'].first().to_dict()
        shift_starts = pd.to_datetime(df_drive.set_index(['차량번호', 'shift_id']).index.map(s_map).values)
        df_drive['shift_start_dt'] = pd.Series(shift_starts, index=df_drive.index).fillna(df_drive['dt_obj'])
        
        def fs_d(dt): 
            return pd.NaT if pd.isna(dt) else ((dt - datetime.timedelta(days=1)).strftime('%Y-%m-%d') if dt.hour < 6 else dt.strftime('%Y-%m-%d'))
            
        df_drive['shift_date_str'] = df_drive['shift_start_dt'].apply(fs_d)
        
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

    all_cars = sorted(list(set(['E100#1', 'E100#2', 'E100#3', 'E100#4', 'E100#5'] + cdf['carNumber'].dropna().unique().tolist())))
    car_list = ["🌟 전체 차량 종합 통계"] + all_cars
    
    if 'car_view_state' not in st.session_state: 
        st.session_state['car_view_state'] = "🌟 전체 차량 종합 통계"
        
    if st.session_state['car_view_state'] not in car_list: 
        st.session_state['car_view_state'] = car_list[0]
        
    tc = st.selectbox("🔍 분석할 차량 선택", car_list, index=car_list.index(st.session_state['car_view_state']), key="car_view_widget", on_change=lambda: st.session_state.update({'car_view_state': st.session_state['car_view_widget']}))
    
    def avg_dur(x): 
        return x[x > 0].mean() if len(x[x > 0]) > 0 else 0
        
    t_css = "<style>.premium-table-wrapper { overflow-x: auto; max-height: 500px; margin-top: 15px; border-radius: 16px; border: 1px solid #e2e8f0; box-shadow: 0 4px 20px rgba(0,0,0,0.03); background: white; -webkit-overflow-scrolling: touch; } .premium-table { width: 100%; min-width: 800px; border-collapse: collapse; text-align: center; font-size: 13px; font-family: Pretendard, sans-serif; white-space: nowrap; } .premium-table th, .premium-table td { border-bottom: 1px solid #e2e8f0; border-right: 1px solid #f1f5f9; padding: 12px 10px; } .premium-table th:last-child, .premium-table td:last-child { border-right: none; } .premium-table th { background-color: #f8fafc; color: #334155; font-weight: 700; position: sticky; top: 0; z-index: 1; box-shadow: 0 1px 0 #e2e8f0; } .premium-table tbody tr:hover { background-color: #f1f5f9; transition: background-color 0.2s; }</style>"

    if st.session_state['car_view_state'] == "🌟 전체 차량 종합 통계":
        draw_html_calendar(cdf, 'carNumber', '차량 운행 현황 (달력)')
        st.divider()
        hols = ['2026-03-01', '2026-05-01', '2026-05-05', '2026-05-25', '2026-06-06', '2026-08-15', '2026-09-24', '2026-09-25', '2026-09-26', '2026-10-03', '2026-10-09', '2026-12-25']
        
        try:
            mdt, mndt = pd.to_datetime(cdf['shift_date'].max()), pd.to_datetime(cdf['shift_date'].min())
            ms = mdt.replace(day=1)
            me = ms + pd.offsets.MonthEnd(1)
            
            if ms.year == 2026 and ms.month == 4: 
                ms = pd.to_datetime('2026-04-06')
            if mndt > me or mdt < ms: 
                ms, me = mndt, mdt
                
            tbd = np.busday_count(ms.date(), (me + pd.Timedelta(days=1)).date(), holidays=hols)
            pbd = np.busday_count(ms.date(), (max(ms, mdt) + pd.Timedelta(days=1)).date(), holidays=hols)
            aom = tbd - round(tbd * 0.9)
        except Exception:
            tbd, pbd, aom = 22, 22, 2
            ms = pd.to_datetime('today').replace(day=1)
        
        vtd = cdf[pd.to_datetime(cdf['shift_date']) >= ms]
        tos = vtd.groupby('carNumber')['shift_date'].nunique()
        base_df = pd.DataFrame({'carNumber': all_cars})
        c_r = cdf.groupby('carNumber').agg(호출처리=('callCount','sum'), 총탑승객=('passengers','sum'), 이슈발생=('이슈건수','sum'), 운행일수=('shift_date','nunique'), 평균소요분=('duration_min', avg_dur)).reset_index()
        c_d = daily_car.groupby('차량번호')['총주행거리(km)'].sum().reset_index() if not daily_car.empty else pd.DataFrame(columns=['차량번호', '총주행거리(km)'])
        
        mc = pd.merge(base_df, c_r, on='carNumber', how='left')
        mc = pd.merge(mc, c_d, left_on='carNumber', right_on='차량번호', how='left').fillna(0)
        
        for c in ['운행일수', '호출처리', '총탑승객', '이슈발생', '총주행거리(km)']: 
            mc[c] = pd.to_numeric(mc[c], errors='coerce').fillna(0).astype(int)
            
        mc['평균소요분'] = mc['평균소요분'].round(1)
        mc['운행일수_평가'] = mc['carNumber'].map(tos).fillna(0)
        mc['휴무일수'] = (pbd - mc['운행일수_평가']).apply(lambda x: max(0, int(x)))
        mc['일평균_호출(건)'] = (mc['호출처리'] / mc['운행일수'].replace(0, 1)).replace([np.inf, -np.inf, np.nan], 0).round(1)
        mc['일평균_주행(km)'] = (mc['총주행거리(km)'] / mc['운행일수'].replace(0, 1)).replace([np.inf, -np.inf, np.nan], 0).round(1)
        
        st.markdown("### 🏆 차량 전체 실적 분석")
        mca = max(mc[['호출처리', '총탑승객']].max().max() * 1.2, 10) if not mc.empty else 10
        mad = max(mc[['일평균_호출(건)', '일평균_주행(km)']].max().max() * 1.2, 10) if not mc.empty else 10
        
        if is_mobile:
            st.caption("누적 (호출/탑승객)")
            f_c = px.bar(mc.melt(id_vars='carNumber', value_vars=['호출처리', '총탑승객'], var_name='구분', value_name='값'), x='carNumber', y='값', color='구분', barmode='group', text_auto=True, color_discrete_sequence=['#4F46E5', '#10B981'])
            f_c.update_traces(textposition="outside", cliponaxis=False, textfont=dict(weight="bold"))
            f_c.update_layout(dragmode=False, margin=dict(t=10, b=10), xaxis_title="")
            f_c.update_yaxes(range=[0, mca], fixedrange=True)
            st.plotly_chart(apply_modern_theme(f_c), use_container_width=True, config={'displayModeBar': False})
            
            st.caption("일평균 (호출/주행거리)")
            f_a = px.bar(mc.melt(id_vars='carNumber', value_vars=['일평균_호출(건)', '일평균_주행(km)'], var_name='구분', value_name='값'), x='carNumber', y='값', color='구분', barmode='group', text_auto=True, color_discrete_sequence=['#F59E0B', '#94A3B8'])
            f_a.update_traces(textposition="outside", cliponaxis=False, textfont=dict(weight="bold"))
            f_a.update_layout(dragmode=False, margin=dict(t=10, b=10), xaxis_title="")
            f_a.update_yaxes(range=[0, mad], fixedrange=True)
            st.plotly_chart(apply_modern_theme(f_a), use_container_width=True, config={'displayModeBar': False})
        else:
            c1, c2 = st.columns(2)
            with c1: 
                st.caption("누적 (호출/탑승객)")
                f_c = px.bar(mc.melt(id_vars='carNumber', value_vars=['호출처리', '총탑승객'], var_name='구분', value_name='값'), x='carNumber', y='값', color='구분', barmode='group', text_auto=True, color_discrete_sequence=['#4F46E5', '#10B981'])
                f_c.update_traces(textposition="outside", cliponaxis=False, textfont=dict(weight="bold"))
                f_c.update_layout(dragmode=False, margin=dict(t=10, b=10), xaxis_title="")
                f_c.update_yaxes(range=[0, mca], fixedrange=True)
                st.plotly_chart(apply_modern_theme(f_c), use_container_width=True, config={'displayModeBar': False})
            with c2: 
                st.caption("일평균 (호출/주행거리)")
                f_a = px.bar(mc.melt(id_vars='carNumber', value_vars=['일평균_호출(건)', '일평균_주행(km)'], var_name='구분', value_name='값'), x='carNumber', y='값', color='구분', barmode='group', text_auto=True, color_discrete_sequence=['#F59E0B', '#94A3B8'])
                f_a.update_traces(textposition="outside", cliponaxis=False, textfont=dict(weight="bold"))
                f_a.update_layout(dragmode=False, margin=dict(t=10, b=10), xaxis_title="")
                f_a.update_yaxes(range=[0, mad], fixedrange=True)
                st.plotly_chart(apply_modern_theme(f_a), use_container_width=True, config={'displayModeBar': False})
        
        st.divider()
        st.markdown("### 📋 차량 별 운행 및 휴무 통계")
        st.info(f"💡 현재 월(**영업일={tbd}일**). 기준을 충족하려면 **{aom}일** 만 휴무 가능.")
        if is_mobile: 
            st.caption("👉 표를 옆으로 밀어서 확인하세요.")
        
        h = t_css + "<div class='premium-table-wrapper'><table class='premium-table'><thead><tr><th>차량</th><th>운행일수</th><th>휴무일수</th><th>호출처리</th><th>총탑승객</th><th>총주행거리(km)</th><th>일평균 호출(건)</th><th>일평균 주행(km)</th><th>평균소요분</th><th>이슈발생</th></tr></thead><tbody>"
        for _, r in mc.iterrows():
            off = r['휴무일수']
            opr = pbd - off
            ts, tc = "", "#0f172a"
            
            if off > aom: 
                ts, tc = "background-color: #fee2e2;", "#b91c1c"
            elif pbd > 0 and (opr / pbd < 0.9 or (off == aom and aom > 0)): 
                ts, tc = "background-color: #ffedd5;", "#c2410c"
                
            h += f"<tr style='{ts}'><td style='font-weight:700; color:{tc};'>{r['carNumber']}</td><td style='color:{tc};'>{r['운행일수']}일</td><td style='font-weight:700; color:{tc};'>{r['휴무일수']}일</td><td style='font-weight:700; color:{tc};'>{r['호출처리']}회</td><td style='font-weight:700; color:{tc};'>{r['총탑승객']}명</td><td style='color:{tc};'>{r['총주행거리(km)']}km</td><td style='color:{tc};'>{r['일평균_호출(건)']}건</td><td style='color:{tc};'>{r['일평균_주행(km)']}km</td><td style='color:{tc};'>{r['평균소요분']}분</td><td style='font-weight:700; color:{tc};'>{r['이슈발생']}건</td></tr>"
        
        st.markdown(h + "</tbody></table></div>", unsafe_allow_html=True)

    else:
        tc = st.session_state['car_view_state']
        cr = cdf[cdf['carNumber'] == tc].copy()
        cd = daily_car[daily_car['차량번호'] == tc] if not daily_car.empty else pd.DataFrame()
        
        dw = cr['shift_date'].nunique()
        # [최적화] NaN 안전 변환 처리
        tcc = int(pd.to_numeric(cr['callCount'], errors='coerce').fillna(0).sum())
        tpc = int(pd.to_numeric(cr['passengers'], errors='coerce').fillna(0).sum())
        tkc = int(pd.to_numeric(cd['총주행거리(km)'], errors='coerce').fillna(0).sum()) if not cd.empty else 0
        
        vcd = cr[cr['duration_min'] > 0]
        acd = round(vcd['duration_min'].mean(), 1) if not vcd.empty else 0
        
        if is_mobile: 
            st.markdown(f"<div style='display: flex; flex-direction: column; gap: 10px; margin-bottom: 20px;'><div style='background: white; padding: 15px; border-radius: 15px; border: 1px solid #f1f5f9;'><span style='font-size:20px;'>🗓️</span> <b style='color:#475569;'>운행 일수:</b> <span style='font-size:20px; font-weight:800; color:#0f172a; float:right;'>{dw} 일</span></div><div style='background: linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%); padding: 15px; border-radius: 15px; border: 1px solid #c7d2fe;'><span style='font-size:20px;'>📞</span> <b style='color:#3730a3;'>호출 처리:</b> <span style='font-size:20px; font-weight:800; color:#312e81; float:right;'>{tcc:,} 회</span></div><div style='background: linear-gradient(135deg, #ecfdf5 0%, #dcfce7 100%); padding: 15px; border-radius: 15px; border: 1px solid #bbf7d0;'><span style='font-size:20px;'>👥</span> <b style='color:#166534;'>탑승객 처리:</b> <span style='font-size:20px; font-weight:800; color:#14532d; float:right;'>{tpc:,} 명</span></div><div style='background: white; padding: 15px; border-radius: 15px; border: 1px solid #f1f5f9;'><span style='font-size:20px;'>🛣️</span> <b style='color:#475569;'>주행 거리:</b> <span style='font-size:20px; font-weight:800; color:#ea580c; float:right;'>{tkc:,} km</span></div><div style='background: white; padding: 15px; border-radius: 15px; border: 1px solid #f1f5f9;'><span style='font-size:20px;'>⏱️</span> <b style='color:#475569;'>평균 소요:</b> <span style='font-size:20px; font-weight:800; color:#2563eb; float:right;'>{acd} 분</span></div></div>", unsafe_allow_html=True)
        else: 
            st.markdown(f"<div style='display: flex; gap: 15px; margin-bottom: 25px; flex-wrap: wrap;'><div style='flex: 1; min-width: 130px; background: #ffffff; padding: 20px; border-radius: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); border: 1px solid #f1f5f9;'><div style='font-size: 22px; margin-bottom: 8px;'>🗓️</div><div style='font-size: 13px; color: #64748b; font-weight: 600; margin-bottom: 2px;'>운행 일수</div><div style='font-size: 26px; color: #0f172a; font-weight: 800;'>{dw} <span style='font-size: 15px; color: #94a3b8; font-weight: 600;'>일</span></div></div><div style='flex: 1; min-width: 130px; background: linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%); padding: 20px; border-radius: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); border: 1px solid #c7d2fe;'><div style='font-size: 22px; margin-bottom: 8px;'>📞</div><div style='font-size: 13px; color: #3730a3; font-weight: 600; margin-bottom: 2px;'>호출 처리</div><div style='font-size: 26px; color: #312e81; font-weight: 800;'>{tcc:,} <span style='font-size: 15px; color: #4338ca; font-weight: 600;'>회</span></div></div><div style='flex: 1; min-width: 130px; background: linear-gradient(135deg, #ecfdf5 0%, #dcfce7 100%); padding: 20px; border-radius: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); border: 1px solid #bbf7d0;'><div style='font-size: 22px; margin-bottom: 8px;'>👥</div><div style='font-size: 13px; color: #166534; font-weight: 600; margin-bottom: 2px;'>탑승객 처리</div><div style='font-size: 26px; color: #14532d; font-weight: 800;'>{tpc:,} <span style='font-size: 15px; color: #16a34a; font-weight: 600;'>명</span></div></div><div style='flex: 1; min-width: 130px; background: #ffffff; padding: 20px; border-radius: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); border: 1px solid #f1f5f9;'><div style='font-size: 22px; margin-bottom: 8px;'>🛣️</div><div style='font-size: 13px; color: #64748b; font-weight: 600; margin-bottom: 2px;'>총 주행 거리</div><div style='font-size: 26px; color: #ea580c; font-weight: 800;'>{tkc:,} <span style='font-size: 15px; color: #94a3b8; font-weight: 600;'>km</span></div></div><div style='flex: 1; min-width: 130px; background: #ffffff; padding: 20px; border-radius: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); border: 1px solid #f1f5f9;'><div style='font-size: 22px; margin-bottom: 8px;'>⏱️</div><div style='font-size: 13px; color: #64748b; font-weight: 600; margin-bottom: 2px;'>평균 소요시간</div><div style='font-size: 26px; color: #2563eb; font-weight: 800;'>{acd} <span style='font-size: 15px; color: #94a3b8; font-weight: 600;'>분</span></div></div></div>", unsafe_allow_html=True)
        
        st.divider()
        draw_html_calendar(cr, 'driverName', f"{tc} 운행 상세 (담당 Safe Guard)")
        
        st.divider()
        st.markdown(f"### 🚖 {tc} 차량 운행 일지")
        
        if not df_merged.empty:
            my_disp = df_merged[df_merged['차량번호'].astype(str) == tc].copy()
            
            if not my_disp.empty:
                def s_pt(v): 
                    return '-' if pd.isna(v) or v in ['-', ''] else (datetime.datetime.fromtimestamp(int(v)/1000).strftime('%H:%M:%S') if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()) else pd.to_datetime(str(v), errors='coerce').strftime('%H:%M:%S'))
                
                my_disp['출발_시간'] = my_disp.apply(lambda r: s_pt(r.get('출발_시간')), axis=1)
                my_disp['종료_시간'] = my_disp.apply(lambda r: s_pt(r.get('종료_시간')), axis=1)
                my_disp = my_disp.fillna('-').sort_values(['shift_date_str', 'shift_id'], ascending=[False, True])
                
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
                h += "</tr>"
                h += "</thead>"
                h += "<tbody>"
                
                for _, r in my_disp.iterrows():
                    dt_view = pd.to_datetime(r.get('shift_date_str')).strftime('%m/%d') if pd.notna(r.get('shift_date_str')) and r.get('shift_date_str') != '-' else '-'
                    
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
                    h += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; text-align:left; white-space:normal; min-width:150px; color:#ef4444;'>{r.get('특이사항', '-')}</td>"
                    h += "</tr>"
                    
                h += "</tbody></table></div>"
                st.markdown(h, unsafe_allow_html=True)
            else: 
                st.info(f"💡 {tc} 의 일지 기록이 없습니다.")
        else: 
            st.warning("기록된 운행 일지가 없습니다.")
        
        st.divider()
        st.markdown(f"### 📋 {tc} 탑승 누적 기록")
        
        if is_mobile: 
            st.caption("👉 표를 옆으로 밀어서 확인하세요.")
        
        if not cr.empty:
            rides_df = cr[cr['status'] != 'ISSUE_ONLY'].sort_values('dt_obj', ascending=False).copy()
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
        st.markdown(f"### 🚨 {tc} 차량 전용 이슈 리포트")
        issues_df = get_exploded_issues(cr)
        
        if not issues_df.empty:
            for col in issues_df.columns:
                if issues_df[col].dtype == object:
                    issues_df[col] = issues_df[col].astype(str).replace(['nan', 'NaN', 'None'], '-')
                    
            hi = t_css + "<div class='premium-table-wrapper'><table class='premium-table'><thead><tr><th>발생시간</th><th>차량번호</th><th>대분류</th><th>중분류</th><th>내용 상세</th><th>위도</th><th>경도</th></tr></thead><tbody>"
            for _, r in issues_df.iterrows(): 
                hi += f"<tr><td>{r['발생시간']}</td><td>{r['차량']}</td><td style='color:#b91c1c; font-weight:bold;'>{r['대분류']}</td><td>{r['중분류']}</td><td style='text-align:left; white-space:normal; min-width:200px;'>{r['📝상세']}</td><td>{r['위도(Lat)']}</td><td>{r['경도(Lng)']}</td></tr>"
            st.markdown(hi + "</tbody></table></div>", unsafe_allow_html=True)
        else: 
            st.success("🎉 기록된 특이사항이나 이슈가 없습니다!")
        
        st.divider()
        st.markdown(f"### 📊 {tc} 일일 업무 추이")
        
        if not cr.empty:
            daily_stats = cr.groupby('shift_date').agg(calls=('callCount', 'sum'), issues=('이슈건수', 'sum')).reset_index()
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
