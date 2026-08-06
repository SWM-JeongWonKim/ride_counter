import os
# os.environ["GRPC_DNS_RESOLVER"] = "native"
# os.environ["GRPC_POLL_STRATEGY"] = "epoll1"

import warnings
warnings.filterwarnings("ignore") 

import streamlit as st
import pandas as pd
import time
import datetime
import ast
import json
import io
import streamlit.components.v1 as components

import firebase_manager as fm
import chart_utils as dc
import admin_manager as am
import admin_utils as utils
import summary_modules.tab_summary as tab_summary
import tab_safeguard
import tab_vehicle

st.set_page_config(layout="wide", page_title="운영 대시보드", page_icon="🚖")

@st.cache_resource
def get_global_sync_state():
    return {'last_sync_time': 0.0}

global_state = get_global_sync_state()

st.markdown("<style>.stApp { background-color: #f8fafc; } .stTabs [data-baseweb=\"tab-list\"] { gap: 8px; background-color: #ffffff; padding: 8px 12px; border-radius: 18px; box-shadow: 0 4px 10px rgba(0,0,0,0.03); } .stTabs [data-baseweb=\"tab\"] { background-color: transparent; border-radius: 12px; padding: 10px 20px; font-size: 16px; font-weight: 600; border: none; color: #64748b; } .stTabs [aria-selected=\"true\"] { background: linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%) !important; color: white !important; box-shadow: 0 4px 10px rgba(59, 130, 246, 0.4); } hr { border-color: #e2e8f0 !important; } [data-testid=\"stVerticalBlockBorderWrapper\"] { border-radius: 20px !important; box-shadow: 0 4px 20px rgba(0,0,0,0.03) !important; border: 1px solid #f1f5f9 !important; background-color: #ffffff !important; }</style>", unsafe_allow_html=True)

if 'logged_in' not in st.session_state:
    st.session_state.update({
        'logged_in': False, 
        'user_role': None, 
        'user_name': None, 
        'user_position': None, 
        'is_admin': False,
        'settings_unlocked': False, 
        'is_mobile': False, 
        'shift': '주간 (08:00~17:30)', 
        'region': '상암', 
        'view_region': '전체'
    })

if not st.session_state.logged_in:
    st.title("🚖 운영 대시보드")
    st.markdown("---")
    c1, c2, c3 = st.columns([1, 2, 1])
    
    with c2:
        t_login, t_signup, t_change = st.tabs(["🔑 로그인", "📝 회원 가입", "🔄 정보 변경 신청"])
        
        with t_login:
            st.markdown("<div style='margin-bottom: 5px; font-size: 14px; font-weight: 600; color: #475569;'>🖥️ 접속 환경 선택</div>", unsafe_allow_html=True)
            device_mode = st.radio("접속 기기", ["💻 PC / 태블릿", "📱 모바일 (스마트폰)"], horizontal=True, label_visibility="collapsed")
            u_id = st.text_input("아이디 (이메일 주소)", key="main_login_id")
            u_pw = st.text_input("비밀번호", type="password", key="main_login_pw")
            
            if st.button("로그인 🚀", use_container_width=True):
                if u_id and u_pw:
                    with st.spinner("DB 통신 중..."):
                        s, u_data, msg = fm.authenticate_user(u_id, u_pw)
                    if s:
                        st.session_state.update({
                            'logged_in': True, 
                            'user_id': u_id, 
                            'user_role': u_data.get('role', 'user'), 
                            'user_name': u_data.get('name'), 
                            'user_position': u_data.get('position', 'Safe Guard'), 
                            'is_admin': utils.parse_bool(u_data.get('is_admin', False)),
                            'is_mobile': "모바일" in device_mode, 
                            'shift': u_data.get('shift', '주간 (08:00~17:30)'), 
                            'region': u_data.get('region', '상암')
                        })
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.warning("입력해주세요.")
                    
        with t_signup:
            st.markdown("### 📝 신규 회원 가입")
            st.info("💡 가입 후 관리자의 권한 부여 및 승인이 완료되어야 대시보드를 열람할 수 있습니다.")
            with st.form("signup_form", clear_on_submit=True):
                n_id = st.text_input("아이디 (회사 이메일)*", placeholder="example@swm.ai")
                n_pw = st.text_input("비밀번호*", type="password")
                n_pwc = st.text_input("비밀번호 확인*", type="password")
                n_name = st.text_input("이름 (실명)*")
                n_pos = st.selectbox("직책/역할*", ["Area Manager", "Data Manager", "Safe Guard", "Shift Manager", "Engineer", "Others"])
                n_shift = st.selectbox("근무 시간(주/야간)*", ["주간 (08:00~17:30)", "야간 (21:00~06:00)"])
                n_region = st.selectbox("담당 지역*", ["상암", "강남"])
                
                if st.form_submit_button("가입 신청하기", type="primary", use_container_width=True):
                    if not n_id or not n_pw or not n_name:
                        st.warning("⚠️ 필수 항목을 모두 입력해주세요.")
                    elif not n_id.strip().endswith("@swm.ai"):
                        st.warning("⚠️ 아이디는 반드시 @swm.ai 로 끝나는 회사 이메일이어야 합니다.")
                    elif n_pw != n_pwc:
                        st.warning("⚠️ 비밀번호가 일치하지 않습니다.")
                    else:
                        with st.spinner("가입 처리 중..."):
                            s, msg = fm.create_user(n_id.strip(), n_pw.strip(), "user", n_name.strip(), n_pos, n_shift, n_region, False)
                        if s:
                            st.success(f"✅ {msg} (승인 대기 중)")
                            time.sleep(1.5)
                            st.rerun()
                        else:
                            st.error(f"🚨 {msg}")
                            
        with t_change:
            st.markdown("### 🔄 계정 정보 변경 신청")
            with st.form("req_change_form", clear_on_submit=True):
                r_name = st.text_input("👤 본인 이름 (필수)")
                r_oid = st.text_input("🔑 현재 아이디 (필수)")
                st.markdown("<br><small>👇 변경할 항목만 입력하세요.</small>", unsafe_allow_html=True)
                r_nid = st.text_input("🆕 새 아이디")
                r_npw = st.text_input("🔒 새 비밀번호", type="password")
                
                if st.form_submit_button("변경 신청 제출하기", type="primary", use_container_width=True):
                    if not r_name.strip() or not r_oid.strip():
                        st.warning("⚠️ 이름과 현재 아이디는 필수입니다.")
                    elif not r_nid.strip() and not r_npw.strip():
                        st.warning("⚠️ 새 정보가 없습니다.")
                    else:
                        s, msg = fm.request_account_change(r_name.strip(), r_oid.strip(), r_nid.strip(), r_npw.strip())
                        if s:
                            st.success(f"✅ {msg}")
                        else:
                            st.error(f"🚨 {msg}")                          
    st.stop()

try:
    tab_summary.render_weather_header()
except Exception:
    pass

KST = datetime.timezone(datetime.timedelta(hours=9))
kst_now = datetime.datetime.now(KST)

# ---------------------------------------------------------
# 메인 대시보드 타이틀
# ---------------------------------------------------------
st.title("🚖 운영 대시보드")

st.sidebar.success(f"👤 **{st.session_state.user_name}**님 ({st.session_state.user_position})\n\n🕒 {st.session_state.shift}\n\n📍 {st.session_state.region}")

if time.time() - global_state['last_sync_time'] > 60:
    with st.spinner("🔄 캐시 업데이트 중..."):
        try:
            fm.sync_only_new_data(force_full=False)
        except Exception:
            pass
        global_state['last_sync_time'] = time.time()

def get_dashboard_data():
    _, m = fm.get_master_data()
    
    raw_schedules = fm.get_schedules() if fm.get_schedules() else []
    merged_sched = pd.DataFrame(raw_schedules) if raw_schedules else pd.DataFrame(columns=['date', 'name', 'type'])

    st.session_state['sched_df'] = merged_sched

    return {
        'm_cars': m.get('cars', []), 
        'm_drivers': m.get('drivers', []), 
        'u_df': pd.DataFrame(fm.get_all_users()), 
        'df': pd.DataFrame([d for d in fm.get_ride_logs() if not d.get('is_deleted', False)]), 
        'df_drive': pd.DataFrame([d for d in fm.get_driving_logs() if not d.get('is_deleted', False)]), 
        'sched_df': merged_sched
    }

with st.spinner("🚀 화면 구성 중..."):
    d_data = get_dashboard_data()
    m_cars = d_data['m_cars']
    m_drivers = d_data['m_drivers']
    u_df = d_data['u_df'].copy()
    df = d_data['df'].copy()
    df_drive = d_data['df_drive'].copy()
    sched_df = d_data['sched_df'].copy()

if not u_df.empty:
    u_df['name'] = u_df['name'].astype(str).str.strip()
    
user_dict = u_df.set_index('name')[['region', 'shift']].to_dict('index') if not u_df.empty else {}

if not df.empty:
    def p_rt(r):
        t = r.get('ride_start_time')
        if pd.notna(t) and str(t).strip() not in ['','0','nan','None']:
            try:
                return pd.to_datetime(float(t), unit='ms', utc=True)
            except Exception:
                pass
        ts = r.get('timestamp')
        if pd.notna(ts):
            try:
                return pd.to_datetime(ts.timestamp(), unit='s', utc=True) if hasattr(ts, 'timestamp') else pd.to_datetime(str(ts), errors='coerce', utc=True)
            except Exception:
                pass
        return pd.Timestamp.utcnow()
    
    df['dt_obj'] = df.apply(p_rt, axis=1).dt.tz_convert('Asia/Seoul')
    df['driverName'] = df['driverName'].astype(str).str.strip()
    df['carNumber'] = df['carNumber'].astype(str).str.strip()
    df['shift_date'] = df['dt_obj'].apply(dc.get_shift_date)
    df = df.dropna(subset=['shift_date'])
    
    df['timestamp_str'] = df['dt_obj'].dt.strftime('%Y-%m-%d %H:%M:%S')
    df['date_str'] = df['dt_obj'].dt.strftime('%Y-%m-%d')
    df['status'] = df.get('status', '')
    df['region'] = df['driverName'].map(lambda x: user_dict.get(x, {}).get('region', '미정'))
    df['shift'] = df['driverName'].map(lambda x: user_dict.get(x, {}).get('shift', '주간 (08:00~17:30)'))
    
    df = df.sort_values('dt_obj', ascending=False)
else:
    df = pd.DataFrame(columns=['timestamp_str', 'date_str', 'shift_date', 'dt_obj', 'carNumber', 'driverName', 'passengers', 'callCount', 'remark', 'status', 'region', 'shift'])

if not df_drive.empty:
    def p_dt(r):
        v = r.get('timestamp') if pd.notna(r.get('timestamp')) else r.get('날짜')
        if pd.isna(v) or v == "":
            return pd.NaT
        try:
            return pd.to_datetime(v.timestamp(), unit='s', utc=True) if hasattr(v, 'timestamp') else (pd.to_datetime(v, unit='ms', utc=True) if isinstance(v, (int, float)) and v > 1e11 else pd.to_datetime(str(v), errors='coerce', utc=True))
        except Exception:
            return pd.NaT
            
    df_drive['dt_obj'] = df_drive.apply(p_dt, axis=1)
    df_drive['dt_obj'] = df_drive['dt_obj'].apply(lambda x: x.tz_localize('Asia/Seoul') if getattr(x, 'tz', None) is None else x.tz_convert('Asia/Seoul'))
    df_drive['Safe_Guard'] = df_drive['Safe_Guard'].astype(str).str.strip()
    df_drive['차량번호'] = df_drive.get('차량번호', '').astype(str).str.strip()
    df_drive['carNumber'] = df_drive['차량번호']
    
    df_drive = df_drive.sort_values(['차량번호', 'dt_obj']).reset_index(drop=True)
    df_drive['is_start'] = df_drive.get('유형', '').astype(str).str.replace(' ', '').str.strip().isin(['출발', '시작', '출근'])
    df_drive['shift_id'] = df_drive.groupby('차량번호')['is_start'].cumsum()
    
    s_map = df_drive[df_drive['is_start']].groupby(['차량번호', 'shift_id'])['dt_obj'].first().to_dict()
    df_drive['shift_start_dt'] = pd.to_datetime(df_drive.set_index(['차량번호', 'shift_id']).index.map(s_map).values)
    df_drive['shift_start_dt'] = df_drive['shift_start_dt'].fillna(df_drive['dt_obj'])
    df_drive['shift_date'] = df_drive['shift_start_dt'].apply(lambda d: pd.NaT if pd.isna(d) else ((d - datetime.timedelta(days=1)).date() if d.hour < 6 else d.date()))
    
    df_drive['region'] = df_drive['Safe_Guard'].map(lambda x: user_dict.get(x, {}).get('region', '미정'))
    df_drive['shift'] = df_drive['Safe_Guard'].map(lambda x: user_dict.get(x, {}).get('shift', '주간 (08:00~17:30)'))
    df_drive = df_drive.dropna(subset=['shift_date'])

st.sidebar.header("⚙️ Infor.")
st.sidebar.info("💡 1분 주기로 정보를 최신화합니다.")
el = time.time() - global_state['last_sync_time']

with st.sidebar:
    if el < 60:
        components.html(f"<div id='c' style='font-family:sans-serif;color:#dc2626;font-size:14px;font-weight:bold;text-align:center;padding:10px;border-radius:12px;background:#fee2e2;border:1px solid #fecaca;'>⏳ 다음 업데이트: <span id='t'></span></div><script>var tg={(global_state['last_sync_time']+60)*1000};var x=setInterval(function(){{var d=tg-new Date().getTime();if(d<=0){{clearInterval(x);document.getElementById('c').innerHTML='✅ 지금 새로고침 가능!';document.getElementById('c').style.cssText+='color:#059669;background:#d1fae5;border-color:#a7f3d0';}}else{{var m=Math.floor((d%(1000*60*60))/(1000*60)),s=Math.floor((d%(1000*60))/1000);document.getElementById('t').innerHTML=(m<10?'0'+m:m)+'분 '+(s<10?'0'+s:s)+'초';}}}},1000);</script>", height=50)
        
    if st.button("🔄 수동 동기화", use_container_width=True) and el >= 60:
        with st.spinner("동기화 중..."):
            try:
                fm.sync_only_new_data()
            except Exception:
                pass
            global_state['last_sync_time'] = time.time()
            st.rerun()

    if st.session_state.user_role in ['admin', 'DM']:
        st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)
        st.session_state.view_region = st.selectbox("🗺️ 화면 표시 지역 전환", ["전체", "상암", "강남"], index=0)
    else:
        st.session_state.view_region = st.session_state.region
    
    st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)
    st.header("🔍 조회 기간 설정")
    
    l_td = kst_now.date() if kst_now.hour >= 8 else (kst_now - datetime.timedelta(days=1)).date()
    dm = st.radio("🗓️ 기간", ["오늘", "이번 주", "이번 달", "전체", "직접 지정"], index=2) 
    
    if dm == "오늘":
        fs, fe = l_td, l_td
    elif dm == "이번 주":
        fs = l_td - datetime.timedelta(days=l_td.weekday())
        fe = fs + datetime.timedelta(days=6)
    elif dm == "이번 달":
        fs = l_td.replace(day=1)
        nm = fs.replace(day=28) + datetime.timedelta(days=4)
        fe = nm - datetime.timedelta(days=nm.day)
    elif dm == "전체":
        fs, fe = None, None
    else:
        cd = st.date_input("날짜 지정", [l_td, l_td])
        fs, fe = cd if len(cd) == 2 else (cd[0], cd[0])

    is_super = (st.session_state.get('user_id') == "syoh@swm.ai")
    is_auth_admin = st.session_state.get('is_admin', False) and st.session_state.get('user_position') in ['Area Manager', 'Data Manager']
    can_export = is_super or is_auth_admin

    if can_export:
        st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)
        st.header("📥 원시 데이터 추출")
        dl_dates = st.date_input("🗓️ 추출 기간", value=(kst_now.date(), kst_now.date()))
        dl_region = st.selectbox("📍 추출 지역", ["전체", "상암", "강남"], index=0)
        dl_type = st.selectbox("파일 분류", ["탑승 누적 (Ride)", "운행 일지 (Drive)", "이슈 발굴 (Issue)"])
        
        dl_s_date = dl_dates[0] if isinstance(dl_dates, tuple) else dl_dates
        dl_e_date = dl_dates[1] if isinstance(dl_dates, tuple) and len(dl_dates) == 2 else dl_s_date
        r_users = u_df[u_df['region'] == dl_region]['name'].tolist() if dl_region != "전체" else u_df['name'].tolist()
        
        dl_s_ts = pd.to_datetime(dl_s_date).tz_localize('Asia/Seoul')
        dl_e_ts = (pd.to_datetime(dl_e_date) + pd.Timedelta(hours=23, minutes=59, seconds=59)).tz_localize('Asia/Seoul')
        
        dl_cache_key = f"{dl_type}_{dl_region}_{dl_s_date}_{dl_e_date}"
        if st.session_state.get('dl_cache_key') != dl_cache_key:
            st.session_state['dl_excel_bytes'] = None
            st.session_state['dl_cache_key'] = dl_cache_key

        if st.session_state.get('dl_excel_bytes') is None:
            if st.button("🚀 데이터 추출 준비하기", use_container_width=True):
                with st.spinner("백그라운드에서 데이터를 추출하여 엑셀(.xlsx)을 만들고 있습니다..."):
                    excel_bytes = None
                    buffer = io.BytesIO()
                    
                    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                        if dl_type == "탑승 누적 (Ride)":
                            dl_df = df.copy()
                            dl_df = dl_df[(dl_df['dt_obj'] >= dl_s_ts) & (dl_df['dt_obj'] <= dl_e_ts)].copy()
                            dl_df = dl_df[dl_df['status'].astype(str).str.strip().str.upper() != 'ISSUE_ONLY']
                            
                            if dl_region != "전체":
                                dl_df = dl_df[dl_df['driverName'].isin(r_users)]
                                
                            if not dl_df.empty:
                                def fmt_time(ts):
                                    if pd.isna(ts) or str(ts).strip() in ['','0','nan','None']:
                                        return ""
                                    try:
                                        return pd.to_datetime(float(ts), unit='ms', utc=True).tz_convert('Asia/Seoul').strftime('%H:%M:%S')
                                    except Exception:
                                        return ""
                                        
                                dl_df['탑승시간'] = dl_df.get('ride_start_time', '').apply(fmt_time)
                                dl_df['하차시간'] = dl_df.get('ride_end_time', '').apply(fmt_time)
                                dl_df['실제_탑승일'] = dl_df['dt_obj'].dt.strftime('%Y-%m-%d')
                                dl_df['운행일자(Shift)'] = dl_df['shift_date'].astype(str)
                                dl_df['예상요금(원)'] = dl_df.apply(dc.calc_revenue, axis=1)
                                dl_df = dl_df[['실제_탑승일', '운행일자(Shift)', 'carNumber', 'driverName', '탑승시간', '하차시간', 'callCount', 'passengers', '예상요금(원)', 'region', 'shift', 'remark']]
                                dl_df.columns = ['실제_탑승일', '운행일자(Shift)', '차량번호', '운전자', '탑승시간', '하차시간', '호출(건)', '탑승객(명)', '예상요금(원)', '지역', '근무시간', '특이사항']
                                dl_df = dl_df.sort_values(by=['실제_탑승일', '탑승시간'], ascending=[True, True])
                                dl_df.to_excel(writer, index=False, sheet_name='Ride Data')
                                excel_bytes = True

                        elif dl_type == "운행 일지 (Drive)":
                            dl_df = df_drive.copy()
                            dl_df = dl_df[(dl_df['dt_obj'] >= dl_s_ts) & (dl_df['dt_obj'] <= dl_e_ts)].copy()
                            
                            if dl_region != "전체":
                                dl_df = dl_df[dl_df['Safe_Guard'].isin(r_users)]
                                
                            if not dl_df.empty:
                                merged_dl = dc.merge_driving_logs(dl_df)
                                merged_dl.to_excel(writer, index=False, sheet_name='Drive Data')
                                excel_bytes = True

                        else: # 이슈 발굴 (Issue)
                            dl_df = df.copy()
                            dl_df = dl_df[(dl_df['dt_obj'] >= dl_s_ts) & (dl_df['dt_obj'] <= dl_e_ts)].copy()
                            
                            if dl_region != "전체":
                                dl_df = dl_df[dl_df['driverName'].isin(r_users)]
                                
                            fr = []
                            try:
                                sw_db = fm.load_data('sw_versions')
                            except Exception:
                                sw_db = {}
                                
                            def safe_get_sw(row, key, fallback='-'):
                                if key in row.index:
                                    v = row[key]
                                    if pd.notna(v) and str(v).strip() not in ['', 'nan', 'NaN', 'None']:
                                        return str(v).strip()
                                return fallback
                                
                            for _, r in dl_df.iterrows():
                                d_name = str(r.get('driverName','')).strip()
                                c_num = str(r.get('carNumber','')).strip()
                                u_reg = user_dict.get(d_name, {}).get('region', '미정')
                                u_shf = user_dict.get(d_name, {}).get('shift', '주간')
                                mems = r.get('report_memos', {})
                                
                                if isinstance(mems, str):
                                    try:
                                        mems = ast.literal_eval(mems)
                                    except Exception:
                                        mems = {}
                                        
                                mems_items = mems.items() if isinstance(mems, dict) else (enumerate(mems) if isinstance(mems, list) else [])
                                
                                rst = r.get('ride_start_time')
                                ride_dt = pd.to_datetime(rst, unit='ms', utc=True).tz_convert('Asia/Seoul') if pd.notna(rst) and str(rst).strip() else None
                                sw_key = f"{ride_dt.strftime('%Y-%m-%d')}_{c_num}" if ride_dt else ""
                                sw = sw_db.get(sw_key, {})
                                
                                for k, v in mems_items:
                                    if isinstance(v, dict) and 'id' in v:
                                        memo_text = v.get('memo', str(v))
                                        k = v.get('id')
                                    else:
                                        memo_text = str(v)
                                        
                                    if not str(k).startswith('ADMIN_'):
                                        ds = pd.to_datetime(int(k), unit='ms', utc=True).tz_convert('Asia/Seoul') if str(k).isdigit() else None
                                        
                                        if ds:
                                            shift_d = dc.get_shift_date(ds)
                                            s_str = shift_d.strftime('%Y-%m-%d')
                                            d_str = ds.strftime('%Y-%m-%d')
                                            t_str = ds.strftime('%H:%M:%S')
                                            
                                            maj, min_cat, dtl = dc.split_issue_text_to_vars(memo_text)
                                            
                                            fr.append({
                                                '실제발생일자': d_str, 
                                                '발생시간': t_str, 
                                                '운행일자(Shift)': s_str, 
                                                '차량번호': c_num, 
                                                '운전자': d_name, 
                                                '대분류': maj, 
                                                '중분류': min_cat, 
                                                '상세내용': dtl, 
                                                '위도(Lat)': r.get('latitude',''), 
                                                '경도(Lng)': r.get('longitude',''),
                                                'Safeview': safe_get_sw(r, 'SW_Safeview', sw.get('Safeview', '-')),
                                                'CPU': safe_get_sw(r, 'SW_CPU', sw.get('CPU', '-')),
                                                'MCU': safe_get_sw(r, 'SW_MCU', sw.get('MCU', '-')),
                                                'V1': safe_get_sw(r, 'SW_VPU1', sw.get('VPU1', '-')),
                                                'V2': safe_get_sw(r, 'SW_VPU2', sw.get('VPU2', '-')),
                                                'V3': safe_get_sw(r, 'SW_VPU3', sw.get('VPU3', '-')),
                                                'V4': safe_get_sw(r, 'SW_VPU4', sw.get('VPU4', '-')),
                                                '지역': u_reg, 
                                                '근무시간': u_shf 
                                            })
                            if fr:
                                iss_df = pd.DataFrame(fr)
                                iss_df = iss_df.sort_values(by=['실제발생일자', '발생시간'])
                                iss_df.to_excel(writer, index=False, sheet_name='Issue Data')
                                excel_bytes = True

                    if excel_bytes:
                        st.session_state['dl_excel_bytes'] = buffer.getvalue()
                        st.rerun()
                    else:
                        st.warning("해당 조건의 데이터가 없습니다.")
        else:
            st.success("✅ 파일 준비 완료!")
            st.download_button(
                f"📥 {dl_type} 다운로드 (.xlsx)", 
                st.session_state['dl_excel_bytes'], 
                f"{dl_type.split(' ')[0]}_{dl_region}_{dl_s_date}_{dl_e_date}.xlsx", 
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                use_container_width=True
            )
            if st.button("🔄 조건 변경 및 새로고침", use_container_width=True):
                st.session_state['dl_excel_bytes'] = None
                st.rerun()

    st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)
    if st.button("로그아웃 🚪", use_container_width=True):
        st.session_state.clear()
        st.rerun()

f_df = df.copy()
f_drive = df_drive.copy()

if fs and fe:
    start_ts = pd.to_datetime(fs).tz_localize('Asia/Seoul')
    end_ts = (pd.to_datetime(fe) + pd.Timedelta(hours=23, minutes=59, seconds=59)).tz_localize('Asia/Seoul')
    
    if not f_df.empty: 
        f_df = f_df[(f_df['dt_obj'] >= start_ts) & (f_df['dt_obj'] <= end_ts)]
    if not f_drive.empty: 
        f_drive = f_drive[(f_drive['dt_obj'] >= start_ts) & (f_drive['dt_obj'] <= end_ts)]

clean_df = f_df.drop_duplicates(subset=['timestamp_str', 'carNumber'], keep='last').copy() if not f_df.empty else pd.DataFrame()

target_region = st.session_state.view_region
if 'region' not in u_df.columns:
    u_df['region'] = '미정' 

if target_region != "전체":
    region_users = u_df[u_df['region'] == target_region]['name'].dropna().tolist()
    if not region_users:
        region_users = ['__NO_USER__'] 
    if not clean_df.empty:
        clean_df = clean_df[clean_df['driverName'].isin(region_users)]
    if not f_drive.empty:
        f_drive = f_drive[f_drive['Safe_Guard'].isin(region_users)]

tc, tp, ti, tr, cc = 0, 0, 0, 0, 0

if not clean_df.empty:
    rr = clean_df[clean_df['status'] != 'ISSUE_ONLY'].copy()
    if not rr.empty:
        rr['revenue'] = rr.apply(dc.calc_revenue, axis=1)
        
    try:
        clean_df['duration_min'] = ((pd.to_datetime(clean_df['ride_end_time'], unit='ms', errors='coerce') - pd.to_datetime(clean_df['ride_start_time'], unit='ms', errors='coerce')).dt.total_seconds() / 60).fillna(0)
    except Exception:
        clean_df['duration_min'] = 0
        
    clean_df['이슈건수'] = clean_df.apply(dc.get_global_issue_count, axis=1)
    
    tc = int(rr['callCount'].sum()) if not rr.empty else 0
    tp = int(pd.to_numeric(rr['passengers'], errors='coerce').fillna(0).sum()) if not rr.empty else 0
    ti = int(clean_df['이슈건수'].sum())
    tr = int(rr['revenue'].sum()) if not rr.empty else 0
    cc = clean_df['carNumber'].nunique()

st.markdown(f"<div style='display: flex; gap: 15px; margin-bottom: 25px; flex-wrap: wrap;'><div style='flex: 1; min-width: 150px; background: #ffffff; padding: 20px; border-radius: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); border: 1px solid #f1f5f9;'><div style='font-size: 22px; margin-bottom: 8px;'>📞</div><div style='font-size: 13px; color: #64748b; font-weight: 600; margin-bottom: 2px;'>총 호출 수</div><div style='font-size: 26px; color: #0f172a; font-weight: 800; letter-spacing: -0.5px;'>{tc:,} <span style='font-size: 15px; color: #94a3b8; font-weight: 600;'>회</span></div></div><div style='flex: 1; min-width: 150px; background: #ffffff; padding: 20px; border-radius: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); border: 1px solid #f1f5f9;'><div style='font-size: 22px; margin-bottom: 8px;'>👥</div><div style='font-size: 13px; color: #64748b; font-weight: 600; margin-bottom: 2px;'>총 탑승객</div><div style='font-size: 26px; color: #0f172a; font-weight: 800; letter-spacing: -0.5px;'>{tp:,} <span style='font-size: 15px; color: #94a3b8; font-weight: 600;'>명</span></div></div><div style='flex: 1.2; min-width: 180px; background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%); padding: 20px; border-radius: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.06); border: 1px solid #bbf7d0;'><div style='font-size: 22px; margin-bottom: 8px;'>💰</div><div style='font-size: 13px; color: #166534; font-weight: 600; margin-bottom: 2px;'>(예상)누적 수입금</div><div style='font-size: 26px; color: #14532d; font-weight: 800; letter-spacing: -0.5px;'>{tr:,} <span style='font-size: 15px; color: #166534; font-weight: 600;'>원</span></div></div><div style='flex: 1; min-width: 150px; background: #ffffff; padding: 20px; border-radius: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); border: 1px solid #f1f5f9;'><div style='font-size: 22px; margin-bottom: 8px;'>🚕</div><div style='font-size: 13px; color: #64748b; font-weight: 600; margin-bottom: 2px;'>운행 차량</div><div style='font-size: 26px; color: #0f172a; font-weight: 800; letter-spacing: -0.5px;'>{cc} <span style='font-size: 15px; color: #94a3b8; font-weight: 600;'>대</span></div></div><div style='flex: 1; min-width: 150px; background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%); padding: 20px; border-radius: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.06); border: 1px solid #fecaca;'><div style='font-size: 22px; margin-bottom: 8px;'>🚨</div><div style='font-size: 13px; color: #991b1b; font-weight: 600; margin-bottom: 2px;'>발생 이슈</div><div style='font-size: 26px; color: #7f1d1d; font-weight: 800; letter-spacing: -0.5px;'>{ti} <span style='font-size: 15px; color: #991b1b; font-weight: 600;'>건</span></div></div></div>", unsafe_allow_html=True)

# ---------------------------------------------------------
# 탭 구성 및 권한별 분기
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
        # 🗺️ ADS Monitor (좌우 공백 완벽 제거: left: -238px, width: 127%)
        ads_url = "https://adtc.swm.ai/adsmonitor/#/map"
        
        components.html(f"""
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; font-family: sans-serif;">
                <h3 style="margin: 0; color: #0f172a; font-size: 1.25rem;">🗺️ ADS Monitor</h3>
                <div>
                    <button onclick="document.getElementById('ads_frame').src = '{ads_url}?t=' + new Date().getTime();" 
                            style="background: #ffffff; color: #334155; border: 1px solid #cbd5e1; padding: 8px 16px; border-radius: 8px; font-weight: 600; cursor: pointer; margin-right: 8px;"
                            onmouseover="this.style.background='#f1f5f9';" onmouseout="this.style.background='#ffffff';">
                        🔄 모니터 새로고침
                    </button>
                    <a href="{ads_url}" target="_blank" style="text-decoration: none;">
                        <button style="background: #3b82f6; color: #ffffff; border: none; padding: 8px 16px; border-radius: 8px; font-weight: 600; cursor: pointer;">
                            ↗️ 전체화면으로 보기
                        </button>
                    </a>
                </div>
            </div>
            
            <!-- top: -110px, left: -238px, width: 127% 로 좌우 공백 완전 제거 -->
            <div style="width: 100%; height: 540px; overflow: hidden; border-radius: 12px; border: 1px solid #1e293b; background-color: #0b132b; position: relative;">
                <iframe id="ads_frame" 
                        src="{ads_url}" 
                        style="width: 127%; height: 950px; border: none; position: absolute; top: -110px; left: -238px;"
                        allow="fullscreen; geolocation; accelerometer; gyroscope; magnetometer; VR; XR; webgl"
                        sandbox="allow-same-origin allow-scripts allow-popups allow-forms allow-modals allow-downloads allow-pointer-lock">
                </iframe>
            </div>
        """, height=600)
        
    with tbs[4]:
        am.draw_admin_tab(clean_df, f_drive, u_df, sched_df, m_cars, m_drivers, kst_now)