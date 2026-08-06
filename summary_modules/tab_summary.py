import streamlit as st
import pandas as pd
import datetime
import urllib.parse
import os
import time
import requests
import numpy as np
import ast
import json
from chart_utils import *
from summary_modules import summary_trend, summary_time_stats, summary_data_table, summary_geo_analysis

def fetch_weather_block(r_name, nx, ny):
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    
    coords = {
        "상암": (37.579, 126.889),
        "강남": (37.497, 127.027),
        "안양": (37.394, 126.956)
    }
    lat, lon = coords.get(r_name, (37.5665, 126.9780))
    
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&hourly=temperature_2m,precipitation_probability,weathercode&timezone=Asia%2FSeoul"
    
    tmp, wnd_k, pty, rn = 22.0, 1.5, 0, 0.0
    forecast_html = ""
    
    try:
        res = requests.get(url, timeout=5).json()
        current = res.get('current_weather', {})
        hourly = res.get('hourly', {})
        
        tmp = current.get('temperature', 22.0)
        wnd_k = current.get('windspeed', 1.5)
        pty = current.get('weathercode', 0)
        
        if pty in [0, 1]: ic, dc, bg, tx, mg = "☀️", "맑음", "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)", "#ffffff", "쾌적한 운행 날씨!"
        elif pty in [2, 3]: ic, dc, bg, tx, mg = "⛅", "구름 많음", "linear-gradient(135deg, #64748b 0%, #475569 100%)", "#ffffff", "운행하기 좋습니다."
        elif pty in [51, 53, 55, 61, 63, 65, 80, 81, 82]: ic, dc, bg, tx, mg = "🌧️", "비", "linear-gradient(135deg, #1e293b 0%, #0f172a 100%)", "#ffffff", "안전 거리 확보!"
        elif pty in [71, 73, 75, 85, 86]: ic, dc, bg, tx, mg = "❄️", "눈/빙판", "linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%)", "#1e293b", "서행 운전 필수!"
        else: ic, dc, bg, tx, mg = "🌫️", "흐림", "linear-gradient(135deg, #94a3b8 0%, #64748b 100%)", "#ffffff", "시야 확보 주의!"

        times = hourly.get('time', [])
        temps = hourly.get('temperature_2m', [])
        pops = hourly.get('precipitation_probability', [])
        codes = hourly.get('weathercode', [])
        
        current_idx = min(range(len(times)), key=lambda i: abs(pd.to_datetime(times[i]).tz_localize('Asia/Seoul') - now))
        
        for i in range(current_idx + 1, min(current_idx + 13, len(times))):
            f_dt = pd.to_datetime(times[i])
            f_h = f_dt.strftime("%H시")
            ftm = temps[i]
            fpo = pops[i]
            fc = codes[i]
            
            if fc in [51, 53, 55, 61, 63, 65, 80, 81, 82]: fic = "🌧️"
            elif fc in [71, 73, 75, 85, 86]: fic = "❄️"
            elif fc in [0, 1]: fic = "☀️"
            elif fc in [2, 3]: fic = "⛅"
            else: fic = "🌫️"
            
            tc = tx if tx == "#ffffff" else "#3b82f6"
            forecast_html += f"<div style='text-align: center; min-width: 50px; background: rgba(255,255,255,0.1); padding: 6px 4px; border-radius: 8px;'><div style='font-size: 10px; color: {tx}; opacity:0.8;'>{f_h}</div><div style='font-size: 16px; margin: 2px 0;'>{fic}</div><div style='font-size: 11px; font-weight: 800; color: {tx};'>{ftm}℃</div><div style='font-size: 9px; color: {tc}; font-weight: 600;'>💧{fpo}%</div></div>"
            
    except Exception as e:
        ic, dc, bg, tx, mg = "☁️", "정보 없음", "linear-gradient(135deg, #64748b 0%, #475569 100%)", "#ffffff", "날씨 정보를 불러오지 못했습니다."

    h_html = "<style>.weather-scroll::-webkit-scrollbar{height:4px;} .weather-scroll::-webkit-scrollbar-track{background:rgba(255,255,255,0.1);border-radius:10px;} .weather-scroll::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.3);border-radius:10px;}</style>"
    h_html += f"<div class='weather-scroll' style='display: flex; gap: 6px; overflow-x: auto; margin-top: 12px; border-top: 1px solid rgba(255,255,255,0.2); padding-top: 10px; padding-bottom: 4px;'>{forecast_html}</div>"
    
    html = f"<div style='background: {bg}; padding: 18px; border-radius: 16px; box-shadow: 0 4px 15px rgba(0,0,0,0.06); color: {tx}; font-family: \"Pretendard\", sans-serif; margin-bottom: 15px;'><div style='font-size: 15px; font-weight: 800; margin-bottom: 6px;'>📍 {r_name}</div><div style='display: flex; align-items: center; justify-content: space-between;'><div style='display: flex; align-items: center; gap: 8px;'><div style='font-size: 32px;'>{ic}</div><div style='font-size: 26px; font-weight: 800;'>{tmp}<span style='font-size: 15px; opacity: 0.7;'>℃</span></div></div><div style='text-align: right;'><div style='font-size: 13px; font-weight: 700;'>{dc}</div><div style='font-size: 11px; opacity: 0.8;'>풍속: {wnd_k}km/h</div></div></div><div style='background: rgba(255,255,255,0.15); padding: 8px 12px; border-radius: 10px; font-size: 11px; line-height: 1.5; font-weight: 600; margin-top: 10px;'><div style='display:flex; justify-content:space-between;'><span>🚨 안내:</span><span>{mg}</span></div></div>{h_html}</div>"
    return html.replace('\n', '')

@st.cache_data(ttl=1800, show_spinner=False)
def get_cached_single_weather(r_name, nx, ny):
    return fetch_weather_block(r_name, nx, ny)

def render_weather_header():
    regions = [("상암", 59, 127), ("강남", 61, 125), ("안양", 58, 121)]
    cols = st.columns(3)
    for idx, (r_name, nx, ny) in enumerate(regions):
        with cols[idx]:
            card_html = get_cached_single_weather(r_name, nx, ny)
            if card_html:
                st.markdown(card_html, unsafe_allow_html=True)

def safe_kst_dt(v):
    if pd.isna(v) or str(v).strip() in ['-', '']: return None
    try:
        if isinstance(v, (int, float)) or (isinstance(v, str) and str(v).replace('.', '').isdigit()):
            val = float(v)
            if val < 1e11: val *= 1000
            return pd.to_datetime(val, unit='ms', utc=True).tz_convert('Asia/Seoul')
        dt = pd.to_datetime(str(v), errors='coerce')
        if pd.isna(dt): return None
        if dt.tzinfo is not None:
            return dt.tz_convert('Asia/Seoul')
        return dt.tz_localize('UTC').tz_convert('Asia/Seoul')
    except: return None

def draw_summary_tab(clean_df, df_drive_raw):
    mbl = st.session_state.get('is_mobile', False)
    
    if "init_call_id_done" not in st.session_state:
        r_id = st.query_params.get("call_id", st.session_state.get("saved_call_id", None))
        if r_id: st.session_state["saved_call_id"] = urllib.parse.unquote_plus(r_id).replace("+", " ")
        st.session_state["init_call_id_done"] = True
        
    if st.session_state.get("summary_view_state") not in ["🗺️ 위치 및 경로", None]:
        if "call_id" in st.query_params: del st.query_params["call_id"]
        if "saved_call_id" in st.session_state: del st.session_state["saved_call_id"]

    drv = df_drive_raw.copy()
    smg = pd.DataFrame()
    dmg = pd.DataFrame()
    
    if not drv.empty:
        drv['총주행거리(km)'] = pd.to_numeric(drv.get('총주행거리(km)', 0), errors='coerce').fillna(0)
        drv['특이사항'] = drv.get('특이사항', '').astype(str).replace(['nan', 'None', 'NaN'], '').str.strip()
        drv['유형_clean'] = drv['유형'].astype(str).str.replace(' ', '').str.strip() if '유형' in drv.columns else '알수없음'
        if '차량번호' in drv.columns: drv['차량번호'] = drv['차량번호'].astype(str).str.replace(' ', '').str.strip()
        
        def p_ts(v):
            if pd.isna(v) or v == "": return pd.NaT
            try: return pd.to_datetime(float(v), unit='ms', utc=True) if isinstance(v, (int, float)) or (isinstance(v, str) and str(v).replace('.', '').isdigit()) else pd.to_datetime(str(v), errors='coerce', utc=True)
            except: return pd.NaT
            
        drv['dt_obj'] = drv['timestamp'].apply(p_ts) if 'timestamp' in drv.columns else drv['날짜'].apply(p_ts)
        drv['dt_obj'] = pd.to_datetime(drv['dt_obj'], utc=True).dt.tz_convert('Asia/Seoul')
        drv = drv.sort_values(['차량번호', 'dt_obj']).reset_index(drop=True)
        drv['is_start'] = drv['유형_clean'].isin(['출발', '시작', '출근'])
        drv['shift_id'] = drv.groupby('차량번호')['is_start'].cumsum()
        s_map = drv[drv['is_start']].groupby(['차량번호', 'shift_id'])['dt_obj'].first().to_dict()
        drv['shift_start_dt'] = pd.to_datetime(drv.set_index(['차량번호', 'shift_id']).index.map(s_map).values)
        drv['shift_start_dt'] = drv['shift_start_dt'].fillna(drv['dt_obj'])
        
        def get_shift_date_str(d):
            return None if pd.isna(d) else ((d - datetime.timedelta(days=1)).strftime('%Y-%m-%d') if d.hour < 6 else d.strftime('%Y-%m-%d'))
                
        drv['shift_date'] = drv['shift_start_dt'].apply(get_shift_date_str)
        
        dfs = drv[drv['is_start']].copy().sort_values('dt_obj').rename(columns={'Safe_Guard': '출발자', 'timestamp': '출발_시간'})
        dfs_cols = [c for c in ['shift_date', '차량번호', 'shift_id', '출발자', '출발_시간', '출발_장소', '출발_km', '출발_배터리_차량', '출발_배터리_폰', '출발_배터리_앞탭', '출발_배터리_뒤탭'] if c in dfs.columns]
        dfs = dfs[dfs_cols].drop_duplicates(subset=['shift_date', '차량번호', 'shift_id'], keep='first')
        
        dfe = drv[drv['유형_clean'].isin(['종료', '복귀', '도착', '퇴근', '마감'])].copy().sort_values('dt_obj').rename(columns={'Safe_Guard': '종료자', 'timestamp': '종료_시간'})
        dfe_cols = [c for c in ['shift_date', '차량번호', 'shift_id', '종료자', '종료_시간', '종료_장소', '종료_km', '종료_배터리_차량', '종료_배터리_폰', '종료_배터리_앞탭', '종료_배터리_뒤탭', '총주행거리(km)', '특이사항'] if c in dfe.columns]
        dfe = dfe[dfe_cols].drop_duplicates(subset=['shift_date', '차량번호', 'shift_id'], keep='last')
        
        smg = pd.merge(dfs, dfe, on=['shift_date', '차량번호', 'shift_id'], how='outer')
        
        def g_hm(v):
            dt = safe_kst_dt(v)
            return dt.strftime('%H:%M') if dt is not None else ''
            
        smg['출발_hm'] = smg['출발_시간'].apply(g_hm)
        smg['종료_hm'] = smg['종료_시간'].apply(g_hm)
        smg['shift_count'] = smg.groupby(['shift_date', '차량번호'])['shift_id'].transform('nunique')
        
        def get_calendar_text(r):
            return f"{r['차량번호']} ({r['출발_hm']}~{r['종료_hm']})" if r['shift_count'] > 1 and r['출발_hm'] and r['종료_hm'] else str(r['차량번호'])
                
        smg['calendar_text'] = smg.apply(get_calendar_text, axis=1)
        
        def join_unique_names(x):
            valid_names = [str(v).strip() for v in x if pd.notna(v) and str(v).strip() not in ['', '-', 'nan', 'None']]
            return ', '.join(sorted(set(valid_names))) or '-'
            
        def join_unique_remarks(x):
            valid_remarks = [str(v).strip() for v in x if pd.notna(v) and str(v).strip() not in ['', '-', 'nan', 'None']]
            return ' / '.join(valid_remarks) or '-'

        dmg = smg.sort_values('shift_id').groupby(['shift_date', '차량번호']).agg(
            출발자=('출발자', join_unique_names),
            종료자=('종료자', join_unique_names),
            출발_시간=('출발_시간', 'first'), 
            종료_시간=('종료_시간', 'last'), 
            출발_km=('출발_km', 'first'), 
            종료_km=('종료_km', 'last'), 
            출발_배터리_차량=('출발_배터리_차량', 'first'),
            종료_배터리_차량=('종료_배터리_차량', 'last'),
            특이사항=('특이사항', join_unique_remarks)
        ).reset_index()
        
        for c in ['출발_km', '종료_km', '총주행거리(km)']:
            if c not in dmg.columns: dmg[c] = 0
                
        if '특이사항' not in dmg.columns: dmg['특이사항'] = ''
        
        dmg['s_k'] = pd.to_numeric(dmg['출발_km'], errors='coerce').fillna(0)
        dmg['e_k'] = pd.to_numeric(dmg['종료_km'], errors='coerce').fillna(0)
        msk = (dmg['e_k'] > 0) & (dmg['s_k'] > 0) & (dmg['e_k'] >= dmg['s_k'])
        dmg.loc[msk, '총주행거리(km)'] = dmg.loc[msk, 'e_k'] - dmg.loc[msk, 's_k']
        dmg['총주행거리(km)'] = dmg['총주행거리(km)'].fillna(0)
        dmg['특이사항'] = dmg['특이사항'].fillna('')

    if not clean_df.empty:
        cdf = clean_df.copy()
        
        def safe_dt_parse(v):
            if pd.isna(v) or str(v).strip() == '': return pd.NaT
            try: 
                if isinstance(v, (int, float)) or (isinstance(v, str) and str(v).replace('.', '').isdigit()):
                    return pd.to_datetime(float(v), unit='ms', utc=True).tz_convert('Asia/Seoul')
                else:
                    parsed = pd.to_datetime(str(v), errors='coerce')
                    return parsed.tz_convert('Asia/Seoul') if parsed.tzinfo else parsed.tz_localize('Asia/Seoul')
            except: return pd.NaT
            
        t_col = cdf['dt_obj'] if 'dt_obj' in cdf.columns else (cdf['timestamp'] if 'timestamp' in cdf.columns else cdf.get('ride_start_time', pd.Series(index=cdf.index, dtype=object)))
        cdf['dt_obj'] = t_col.apply(safe_dt_parse)
        
        c_num_col = 'carNumber' if 'carNumber' in cdf.columns else ('차량번호' if '차량번호' in cdf.columns else None)
        cdf['carNumber'] = cdf[c_num_col].astype(str).str.replace(' ', '').str.strip().replace(['nan', 'None', ''], '알수없음') if c_num_col else '알수없음'
        
        d_name_col = 'driverName' if 'driverName' in cdf.columns else ('운전자' if '운전자' in cdf.columns else None)
        cdf['driverName'] = cdf[d_name_col].fillna('알수없음').replace(['nan', 'None', ''], '알수없음') if d_name_col else '알수없음'
        
        cdf['callCount'] = pd.to_numeric(cdf.get('callCount', 0), errors='coerce').fillna(0)
        cdf['passengers'] = pd.to_numeric(cdf.get('passengers', 0), errors='coerce').fillna(0)
        
        def get_shift_date_cdf(d):
            return None if pd.isna(d) else ((d - datetime.timedelta(days=1)).date() if d.hour < 6 else d.date())
                
        cdf['shift_date'] = cdf['dt_obj'].apply(get_shift_date_cdf)
        
        def r_js(v):
            if isinstance(v, (dict, list)): return v
            if isinstance(v, str) and v.strip():
                try: return ast.literal_eval(v.strip())
                except:
                    try: return json.loads(v.strip())
                    except: return {}
            return {}
            
        if 'report_memos' in cdf.columns: cdf['report_memos'] = cdf['report_memos'].apply(r_js)
        if 'issue_pings' in cdf.columns: cdf['issue_pings'] = cdf['issue_pings'].apply(r_js)
        
        cdf['chart_category'] = cdf.apply(classify_data, axis=1)
        cdf['hour'] = cdf['dt_obj'].dt.hour
        cdf['time_bracket'] = cdf['hour'].apply(get_time_bracket)
        cdf['is_manual'] = cdf['chart_category'].apply(lambda x: '📦 일괄 입력' if '일괄' in x else '🚕 정상 운행')
        cdf['revenue'] = cdf.apply(calc_revenue, axis=1)
        cdf['이슈건수'] = cdf.apply(lambda r: int(r.get('report_memos', {}).get('ADMIN_ISSUE_COUNT', r.get('이슈건수', 0))) if isinstance(r.get('report_memos'), dict) else int(r.get('이슈건수', 0)), axis=1)
        
        if 'remark' not in cdf.columns: cdf['remark'] = ''
        
        def x_m(r):
            ms = r.get('report_memos', {})
            if isinstance(ms, dict):
                if 'ADMIN_EDIT' in ms and str(ms['ADMIN_EDIT']).strip(): return f"{str(ms['ADMIN_EDIT']).strip()} (admin)"
                ap = [str(v) for k, v in ms.items() if not str(k).startswith('ADMIN_') and str(v).strip()]
                if ap: return " / ".join(ap) + " (app)"
            elif isinstance(ms, list) and ms:
                ap = [str(x) for x in ms if str(x).strip()]
                if ap: return " / ".join(ap) + " (app)"
            return ""
            
        cdf['통합_이슈상세'] = cdf.apply(x_m, axis=1)
        cdf['calendar_text'] = cdf['carNumber']
        
        if not drv.empty and not smg.empty:
            ds = drv[drv['is_start']][['차량번호', 'dt_obj', 'shift_id']].dropna(subset=['dt_obj']).copy().rename(columns={'차량번호': 'carNumber'})
            if not ds.empty:
                ds['carNumber'] = ds['carNumber'].astype(str).str.strip()
                ds['dt_obj_merge'] = ds['dt_obj'].dt.tz_localize(None).astype('datetime64[ns]')
                ds = ds.dropna(subset=['dt_obj_merge']).sort_values('dt_obj_merge')
                
                cs = cdf.dropna(subset=['dt_obj']).copy()
                cs['carNumber'] = cs['carNumber'].astype(str).str.strip()
                cs['dt_obj_merge'] = cs['dt_obj'].dt.tz_localize(None).astype('datetime64[ns]')
                cs = cs.dropna(subset=['dt_obj_merge']).sort_values('dt_obj_merge')
                
                if not cs.empty:
                    cm = pd.merge_asof(cs, ds, on='dt_obj_merge', by='carNumber', direction='backward')
                    st_m = smg[['차량번호', 'shift_id', 'calendar_text']].rename(columns={'차량번호': 'carNumber'}).drop_duplicates()
                    st_m['carNumber'] = st_m['carNumber'].astype(str).str.strip()
                    if 'calendar_text' in cm.columns: cm = cm.drop(columns=['calendar_text'])
                    cm = pd.merge(cm, st_m, on=['carNumber', 'shift_id'], how='left')
                    cm.set_index(cs.index, inplace=True)
                    cdf.loc[cs.index, 'calendar_text'] = cm['calendar_text'].fillna(cm['carNumber'])
        clean_df = cdf
    else:
        clean_df = pd.DataFrame(columns=['timestamp_str', 'date_str', 'dt_obj', 'carNumber', 'driverName', 'passengers', 'callCount', 'remark', 'status', 'calendar_text', 'chart_category', 'hour', 'time_bracket', 'is_manual', 'revenue', '이슈건수', '통합_이슈상세', 'shift_date'])

    draw_html_calendar(clean_df, 'calendar_text', '운영 현황 (달력)')
    st.divider()
    st.markdown("### 📊 통합 운영 상세 분석")
    
    if "summary_view_state" not in st.session_state: 
        st.session_state["summary_view_state"] = "🗺️ 위치 및 경로" if st.session_state.get("saved_call_id") else "📈 시계열 트렌드"
        
    ops = ["📈 시계열 트렌드", "⏰ 시간대별 탑승객 통계", "📋 운행일지 및 탑승정보", "🗺️ 위치 및 경로"]
    idx = ops.index(st.session_state["summary_view_state"]) if st.session_state["summary_view_state"] in ops else 0
    
    st.radio("보기 옵션 선택", ops, index=idx, horizontal=not mbl, label_visibility="collapsed", key="summary_view_widget", on_change=lambda: st.session_state.update({"summary_view_state": st.session_state.summary_view_widget}))
    st.write("")

    if st.session_state["summary_view_state"] == "📈 시계열 트렌드": summary_trend.draw_trend_view(clean_df, dmg, mbl)
    elif st.session_state["summary_view_state"] == "⏰ 시간대별 탑승객 통계": summary_time_stats.draw_time_stats_view(clean_df, mbl)
    elif st.session_state["summary_view_state"] == "📋 운행일지 및 탑승정보": summary_data_table.draw_data_table_view(clean_df, dmg, mbl)
    elif st.session_state["summary_view_state"] == "🗺️ 위치 및 경로": summary_geo_analysis.draw_geo_view(clean_df, mbl)
