import streamlit as st
import pandas as pd
import datetime
from chart_utils import get_exploded_issues
import firebase_manager as fm

# [핵심 수정] UTC 타임스탬프를 KST(한국 표준시)로 완벽하게 변환하는 함수
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

def draw_data_table_view(clean_df, df_drive_merged, is_mobile):
    if is_mobile: 
        st.info("📱 모바일 환경에서는 데이터 표 스와이프(밀기)로 우측 숨겨진 데이터 확인이 가능합니다.")
        
    # ==========================================
    # 1. 탑승 누적 상세 (Ride Logs)
    # ==========================================
    st.markdown("### 📋 탑승 누적 상세")
    if not clean_df.empty:
        ride_df = clean_df[clean_df['status'] != 'ISSUE_ONLY'].copy()
        if not ride_df.empty:
            try: sw_db = fm.load_data('sw_versions')
            except: sw_db = {}
            
            def get_sw_val(r, key):
                rst = r.get('ride_start_time')
                if pd.notna(rst) and str(rst).strip() not in ['', '0', 'nan', 'None']:
                    try:
                        dt = pd.to_datetime(float(rst), unit='ms', utc=True).tz_convert('Asia/Seoul')
                        sw_key = f"{dt.strftime('%Y-%m-%d')}_{str(r.get('carNumber', '')).strip()}"
                        sw = sw_db.get(sw_key, {})
                        val = r.get(f'SW_{key}', sw.get(key, '-'))
                        if pd.isna(val) or str(val).strip() in ['', 'nan', 'NaN', 'None']: return '-'
                        return str(val).strip()
                    except: pass
                return "-"

            def fmt_time(ts):
                dt = safe_kst_dt(ts)
                return dt.strftime('%H:%M:%S') if dt is not None else "-"
            
            ride_df['탑승일자'] = ride_df['dt_obj'].dt.strftime('%Y-%m-%d')
            ride_df['탑승시간'] = ride_df['ride_start_time'].apply(fmt_time)
            ride_df['하차시간'] = ride_df['ride_end_time'].apply(fmt_time)
            
            def format_location(x):
                s_lat, s_lng = x.get('latitude'), x.get('longitude')
                e_lat, e_lng = x.get('end_latitude'), x.get('end_longitude')
                start_str = f"{s_lat}, {s_lng}" if pd.notna(s_lat) and str(s_lat).strip() not in ['', 'nan'] else "-"
                end_str = f"{e_lat}, {e_lng}" if pd.notna(e_lat) and str(e_lat).strip() not in ['', 'nan'] else "-"
                if start_str == "-" and end_str == "-": return "-"
                return f"{start_str} ➡️ {end_str}"

            ride_df['위치'] = ride_df.apply(format_location, axis=1)
            
            ride_df['SV'] = ride_df.apply(lambda r: get_sw_val(r, 'Safeview'), axis=1)
            ride_df['CPU'] = ride_df.apply(lambda r: get_sw_val(r, 'CPU'), axis=1)
            ride_df['MCU'] = ride_df.apply(lambda r: get_sw_val(r, 'MCU'), axis=1)
            ride_df['V1'] = ride_df.apply(lambda r: get_sw_val(r, 'VPU1'), axis=1)
            ride_df['V2'] = ride_df.apply(lambda r: get_sw_val(r, 'VPU2'), axis=1)
            ride_df['V3'] = ride_df.apply(lambda r: get_sw_val(r, 'VPU3'), axis=1)
            ride_df['V4'] = ride_df.apply(lambda r: get_sw_val(r, 'VPU4'), axis=1)

            raw_display_df = ride_df[['탑승일자', '탑승시간', '하차시간', 'carNumber', 'driverName', 'callCount', 'passengers', '위치', 'SV', 'CPU', 'MCU', 'V1', 'V2', 'V3', 'V4']].copy()
            raw_display_df.columns = ['탑승일자', '탑승시간', '하차시간', '차량 번호', '기사 명', '호출', '탑승객', '위치', 'SV', 'CPU', 'MCU', 'V1', 'V2', 'V3', 'V4']
            
            raw_display_df = raw_display_df.sort_values(['탑승일자', '탑승시간'], ascending=[False, False])
            st.dataframe(raw_display_df, use_container_width=True, hide_index=True)
        else: st.info("💡 기록된 탑승 누적 데이터가 없습니다.")
    else: st.info("💡 기록된 탑승 데이터가 없습니다.")

    st.divider()

    # ==========================================
    # 2. 이슈 현황 (Issue Logs)
    # ==========================================
    st.markdown("### 🚨 이슈 현황")
    if not clean_df.empty:
        issues_df = get_exploded_issues(clean_df)
        if not issues_df.empty:
            issues_df['운행일자'] = pd.to_datetime(issues_df['발생시간']).dt.strftime('%Y-%m-%d')
            issues_df['발생시간'] = pd.to_datetime(issues_df['발생시간']).dt.strftime('%H:%M:%S')
            issues_df['발생위치'] = issues_df.apply(lambda x: f"{x.get('위도(Lat)', '-')} , {x.get('경도(Lng)', '-')}", axis=1)
            
            issues_df = issues_df.rename(columns={'차량': '차량번호', '요원': '운행인원', '📝상세': '내용', 'VPU1': 'V1', 'VPU2': 'V2', 'VPU3': 'V3', 'VPU4': 'V4'})
            def safe_sw_str(v):
                if pd.isna(v) or str(v).strip() in ['', 'nan', 'NaN', 'None']: return '-'
                return str(v).strip()
            for c in ['Safeview', 'CPU', 'MCU', 'V1', 'V2', 'V3', 'V4']:
                if c in issues_df.columns: issues_df[c] = issues_df[c].apply(safe_sw_str)
            
            issues_display = issues_df[['운행일자', '발생시간', '발생위치', '차량번호', '운행인원', '대분류', '중분류', '내용', 'Safeview', 'CPU', 'MCU', 'V1', 'V2', 'V3', 'V4']]
            issues_display = issues_display.rename(columns={'Safeview': 'SV'})
            st.dataframe(issues_display.sort_values(['운행일자', '발생시간'], ascending=[False, False]), hide_index=True, use_container_width=True)
        else: st.info("💡 기록된 현장 특이사항이나 이슈가 없습니다.")
    else: st.info("💡 기록된 이슈 데이터가 없습니다.")

    st.divider()

    # ==========================================
    # 3. 차량 별 운행일지 (Drive Logs)
    # ==========================================
    st.markdown("### 🚖 차량 별 운행일지")
    if not df_drive_merged.empty:
        df_disp = df_drive_merged.copy()
        
        try:
            users_db = fm.load_data('users')
            driver_region_map = {v.get('name', ''): v.get('region', '상암') for k, v in users_db.items()}
        except: driver_region_map = {}

        # [핵심 수정] KST 시간 기준 주/야간 완벽 분리
        def get_disp_shift_type(t_str):
            dt = safe_kst_dt(t_str)
            if dt is not None:
                if 8 <= dt.hour < 20: return '주간'
                return '야간'
            return '주간'

        if not clean_df.empty:
            sync_clean = clean_df.copy()
            sync_clean['carNumber'] = sync_clean['carNumber'].astype(str).str.replace(' ', '').str.strip()
            
            def get_shift_type_from_dt(dt):
                if pd.isna(dt): return '주간'
                if 8 <= dt.hour < 20: return '주간'
                return '야간'
                
            sync_clean['shift_type'] = sync_clean['dt_obj'].apply(get_shift_type_from_dt)
            
            def get_shift_date_str(dt):
                if pd.notna(dt) and dt.hour < 6: return (dt - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
                elif pd.notna(dt): return dt.strftime('%Y-%m-%d')
                return None
                    
            sync_clean['shift_date_str'] = sync_clean['dt_obj'].apply(get_shift_date_str)
            df_disp['shift_date_str'] = pd.to_datetime(df_disp['shift_date']).dt.strftime('%Y-%m-%d')
            df_disp['shift_type'] = df_disp['출발_시간'].apply(get_disp_shift_type)

            def join_unique_names(x):
                valid_names = [str(v).strip() for v in x if pd.notna(v) and str(v).strip() not in ['', '-', 'nan', 'None']]
                return ', '.join(sorted(set(valid_names))) or '-'

            ride_info = sync_clean.groupby(['shift_date_str', 'carNumber', 'shift_type']).agg(
                운행자=('driverName', join_unique_names),
                일일호출=('callCount', 'sum'),
                일일탑승=('passengers', 'sum')
            ).reset_index()

            df_disp = pd.merge(df_disp, ride_info, left_on=['shift_date_str', '차량번호', 'shift_type'], right_on=['shift_date_str', 'carNumber', 'shift_type'], how='left')
        else:
            df_disp['shift_type'] = '주간'
            df_disp['운행자'] = '-'
            df_disp['일일호출'] = '-'
            df_disp['일일탑승'] = '-'
            
        def safe_parse_time(val):
            dt = safe_kst_dt(val)
            if dt is not None:
                return dt.strftime('%H:%M:%S')
            return '-'
            
        df_disp['출발_시간'] = df_disp.apply(lambda r: safe_parse_time(r.get('출발_시간')), axis=1)
        df_disp['종료_시간'] = df_disp.apply(lambda r: safe_parse_time(r.get('종료_시간')), axis=1)
        
        def assign_region(r):
            for target in [r.get('운행자'), r.get('출발자'), r.get('종료자')]:
                if pd.notna(target) and target not in ['-', '']:
                    first_person = str(target).split(',')[0].strip()
                    if first_person in driver_region_map:
                        return driver_region_map[first_person]
            return '상암'
            
        df_disp['지역'] = df_disp.apply(assign_region, axis=1)
        df_disp = df_disp.fillna('-').sort_values(['shift_date_str', '차량번호', 'shift_type'], ascending=[False, True, False]).rename(columns={'shift_date': '운행일자'})
        
        try: df_disp['운행일자'] = pd.to_datetime(df_disp['운행일자']).dt.strftime('%m/%d').fillna('-')
        except: pass

        def format_km(val):
            try: 
                if not pd.isna(val) and val not in ['-', '']: return f"{int(float(val)):,}"
                return str(val)
            except: return str(val)

        html = (
            "<div style='overflow-x: auto; overflow-y: auto; max-height: 500px; -webkit-overflow-scrolling: touch; margin-top: 5px; border-radius: 16px; border: 1px solid #e2e8f0; box-shadow: 0 4px 20px rgba(0,0,0,0.03); background: white;'>"
            "<style>.log-table { width: 100%; min-width: 1100px; border-collapse: collapse; text-align: center; font-size: 13px; font-family: Pretendard, sans-serif; white-space: nowrap; } .log-table th, .log-table td { border-bottom: 1px solid #e2e8f0; border-right: 1px solid #f1f5f9; padding: 12px 10px; } .log-table th:last-child, .log-table td:last-child { border-right: none; } .log-table th { background-color: #f8fafc; color: #334155; font-weight: 700; position: sticky; top: 0; z-index: 1; box-shadow: 0 1px 0 #e2e8f0; } .log-table tbody tr:hover { background-color: #f1f5f9; transition: background-color 0.2s; } .group-header { background-color: #e2e8f0 !important; }</style>"
            "<table class='log-table'><thead><tr>"
            "<th rowspan='2' class='group-header'>운행<br>일자</th>"
            "<th rowspan='2' class='group-header'>지역</th>"
            "<th rowspan='2' class='group-header'>근무조</th>"
            "<th rowspan='2' class='group-header'>차량<br>번호</th>"
            "<th colspan='3' class='group-header' style='background-color: #e0e7ff !important;'>담당</th>"
            "<th colspan='2' class='group-header' style='background-color: #fce7f3 !important;'>탑승 실적</th>"
            "<th colspan='3' class='group-header' style='background-color: #fef3c7 !important;'>계기판 (km)</th>"
            "<th colspan='2' class='group-header' style='background-color: #dbeafe !important;'>시간</th>"
            "<th colspan='2' class='group-header' style='background-color: #dcfce7 !important;'>충전량(%)</th>"
            "<th rowspan='2' class='group-header'>특이(이슈)사항</th>"
            "</tr><tr>"
            "<th style='background-color: #eef2ff;'>출발자</th>"
            "<th style='background-color: #eef2ff; color:#4F46E5;'>운행자</th>"
            "<th style='background-color: #eef2ff;'>종료자</th>"
            "<th style='background-color: #fdf2f8;'>호출(건)</th>"
            "<th style='background-color: #fdf2f8;'>탑승(명)</th>"
            "<th style='background-color: #fffbeb;'>시작</th>"
            "<th style='background-color: #fffbeb;'>종료</th>"
            "<th style='background-color: #fef3c7;'>운행거리</th>"
            "<th style='background-color: #eff6ff;'>출발시간</th>"
            "<th style='background-color: #eff6ff;'>도착시간</th>"
            "<th style='background-color: #f0fdf4;'>시작</th>"
            "<th style='background-color: #fef2f2;'>종료</th>"
            "</tr></thead><tbody>"
        )
        
        for _, row in df_disp.iterrows():
            is_completed = str(row.get('종료자', '-')) != '-' and str(row.get('종료자', '')).strip() != ''
            c_val = f"{int(float(row.get('일일호출', '-')))}" if is_completed and str(row.get('일일호출', '-')) != '-' else '-'
            p_val = f"{int(float(row.get('일일탑승', '-')))}" if is_completed and str(row.get('일일탑승', '-')) != '-' else '-'
                
            sk_v = format_km(row.get('출발_km', '-'))
            ek_v = format_km(row.get('종료_km', '-'))
            tk_v = format_km(row.get('총주행거리(km)', '-'))
            sbc = f"{int(float(row.get('출발_배터리_차량','-')))}" if row.get('출발_배터리_차량','-') not in ['-',''] else '-'
            ebc = f"{int(float(row.get('종료_배터리_차량','-')))}" if row.get('종료_배터리_차량','-') not in ['-',''] else '-'
            
            shift_t = row.get('shift_type', '-')
            shift_color = "#312E81" if shift_t == "야간" else "#EAB308"
            
            html += f"<tr style=\"background:white; transition:background 0.2s;\" onmouseover=\"this.style.background='#f8fafc'\" onmouseout=\"this.style.background='white'\">"
            html += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #f1f5f9; font-weight:700; color:#475569;'>{row.get('운행일자', '-')}</td>"
            html += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #f1f5f9; font-weight:700; color:#1e293b;'>{row.get('지역', '-')}</td>"
            html += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #f1f5f9; font-weight:800; color:{shift_color};'>{shift_t}</td>"
            html += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #e2e8f0; font-weight:700; color:#0f172a;'>{row.get('차량번호', '-')}</td>"
            html += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #f1f5f9; color:#64748b;'>{row.get('출발자', '-')}</td>"
            html += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #f1f5f9; font-weight:700; color:#4f46e5;'>{row.get('운행자', '-')}</td>"
            html += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #e2e8f0; color:#64748b;'>{row.get('종료자', '-')}</td>"
            html += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #f1f5f9; font-weight:700; color:#be185d;'>{c_val}</td>"
            html += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #e2e8f0; font-weight:700; color:#be185d;'>{p_val}</td>"
            html += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #f1f5f9; color:#64748b;'>{sk_v}</td>"
            html += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #f1f5f9; color:#64748b;'>{ek_v}</td>"
            html += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #e2e8f0; font-weight:700; color:#ea580c;'>{tk_v}</td>"
            html += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #f1f5f9; color:#64748b;'>{row.get('출발_시간', '-')}</td>"
            html += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #e2e8f0; color:#64748b;'>{row.get('종료_시간', '-')}</td>"
            html += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #f1f5f9; font-weight:700; color:#166534;'>{sbc}</td>"
            html += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; border-right:1px solid #e2e8f0; font-weight:700; color:#991b1b;'>{ebc}</td>"
            html += f"<td style='padding:12px 10px; border-bottom:1px solid #f1f5f9; text-align:left; white-space:normal; min-width:180px; color:#ef4444;'>{row.get('특이사항', '-')}</td>"
            html += "</tr>"

        html += "</tbody></table></div>"
        st.markdown(html, unsafe_allow_html=True)
    else: 
        st.warning("💡 기록된 운행 일지가 없습니다.")
