import streamlit as st
import pandas as pd
import datetime
import calendar
import time
import re
import ast
import json
import math
import holidays
from plotly import graph_objects as go

COLOR_MAP = {'호출건수': '#4F46E5', '탑승객수': '#10B981', '👤 1명': '#A5B4FC', '👤 2명': '#636EFA', '👤 3명': '#312E81', '📦 일괄 입력': '#F59E0B', '🚕 정상 운행': '#3B82F6'}

@st.cache_data(ttl=86400)
def get_korean_holidays(year):
    kr_holidays = holidays.KR(years=year)
    hols = {}
    events = {}
    
    for dt, name in kr_holidays.items():
        hols[dt] = name
        
    return hols, events

def classify_data(row):
    r = str(row.get('remark', ''))
    if '일괄' in r or '누락' in r or int(row.get('passengers', 0)) > 3:
        return '📦 일괄 입력'
    return f"👤 {int(row.get('passengers', 1))}명 탑승"

def classify_data(row):
    r = str(row.get('remark', ''))
    if '일괄' in r or '누락' in r or int(row.get('passengers', 0)) > 3:
        return '📦 일괄 입력'
    return f"👤 {int(row.get('passengers', 1))}명 탑승"

def get_time_bracket(h):
    if 4 <= h < 22:
        return "04~22시(4,800원)"
    if h == 22:
        return "22~23시(5,800원)"
    if h in [23, 0, 1]:
        return "23~02시(6,700원)"
    if h in [2, 3]:
        return "02~04시(5,800원)"
    return "기타"

def calc_revenue(row):
    try:
        rst = row.get('ride_start_time', 0)
        if pd.isna(rst) or str(rst).strip() == '' or float(rst) == 0:
            return 0
        dt = pd.to_datetime(float(rst), unit='ms', utc=True).tz_convert('Asia/Seoul')
        h, m = dt.hour, dt.minute
        if (8 < h < 17) or (h == 8) or (h == 17 and m <= 30):
            return 0
        if 4 <= h < 22:
            return 4800
        if h == 22:
            return 5800
        if h in [23, 0, 1]:
            return 6700
        if h in [2, 3]:
            return 5800
        return 0
    except Exception:
        return 0

def parse_memos(val):
    if pd.isna(val) or not val:
        return {}
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            return ast.literal_eval(val.strip())
        except Exception:
            try:
                return json.loads(val.strip().replace("'", '"'))
            except Exception:
                return {}
    return {}

def split_issue_text_to_vars(text):
    if pd.isna(text):
        return "", "", ""
    t = str(text).strip()
    maj, min_cat, dtl = "", "", t
    if t.startswith("["):
        ei = t.find("]")
        if ei != -1:
            cp = t[1:ei]
            dtl = t[ei+1:].strip()
            if ">" in cp:
                p = cp.split(">")
                maj, min_cat = p[0].strip(), p[1].strip()
            else:
                maj = cp.strip()
    return maj, min_cat, dtl

def get_global_issue_count(row):
    ms = parse_memos(row.get('report_memos', {}))
    if 'ADMIN_ISSUE_COUNT' in ms:
        return int(ms['ADMIN_ISSUE_COUNT'])
    ks = [k for k in ms.keys() if not str(k).startswith('ADMIN_')]
    if ks:
        return len(ks)
    return int(row.get('이슈건수', 0) if pd.notna(row.get('이슈건수')) else 0)

@st.cache_data(show_spinner=False, ttl=600)
def get_exploded_issues(df):
    import firebase_manager as fm
    try:
        sw_db = fm.load_data('sw_versions')
    except Exception:
        sw_db = {}
    irs = []
    for _, r in df.iterrows():
        ms = parse_memos(r.get('report_memos'))
        ks = [k for k in ms.keys() if not str(k).startswith('ADMIN_')]
        
        rst = r.get('ride_start_time')
        if pd.notna(rst):
            ride_dt = pd.to_datetime(rst, unit='ms', utc=True).tz_convert('Asia/Seoul')
        else:
            ride_dt = r.get('dt_obj', pd.NaT)
            
        if pd.notna(ride_dt):
            sw_key = f"{ride_dt.strftime('%Y-%m-%d')}_{str(r.get('carNumber', '')).strip()}"
        else:
            sw_key = ""
            
        sw = sw_db.get(sw_key, {})
        
        for k in ks:
            maj, min_cat, dtl = split_issue_text_to_vars(ms[k])
            try:
                dt_obj = pd.to_datetime(int(k), unit='ms').tz_localize('UTC').tz_convert('Asia/Seoul')
            except Exception:
                dt_obj = r.get('dt_obj', pd.NaT)
                
            if pd.notna(dt_obj):
                dt_str = dt_obj.strftime('%Y-%m-%d %H:%M:%S')
            else:
                dt_str = ""
                
            irs.append({
                '발생시간': dt_str,
                '차량': str(r.get('carNumber', '')).strip(),
                '요원': str(r.get('driverName', '')).strip(),
                '대분류': maj, 
                '중분류': min_cat, 
                '📝상세': dtl,
                '위도(Lat)': r.get('latitude', r.get('lat', '')),
                '경도(Lng)': r.get('longitude', r.get('lng', '')),
                'Safeview': r.get('Safeview', r.get('SW_Safeview', sw.get('Safeview', '-'))),
                'CPU': r.get('CPU', r.get('SW_CPU', sw.get('CPU', '-'))),
                'MCU': r.get('MCU', r.get('SW_MCU', sw.get('MCU', '-'))),
                'VPU1': r.get('VPU1', r.get('SW_VPU1', sw.get('VPU1', '-'))),
                'VPU2': r.get('VPU2', r.get('SW_VPU2', sw.get('VPU2', '-'))),
                'VPU3': r.get('VPU3', r.get('SW_VPU3', sw.get('VPU3', '-'))),
                'VPU4': r.get('VPU4', r.get('SW_VPU4', sw.get('VPU4', '-')))
            })
            
    if irs:
        return pd.DataFrame(irs).sort_values('발생시간', ascending=False)
    return pd.DataFrame()

def parse_time_to_kst(v):
    if pd.isna(v) or v in ['', '-']: return pd.NaT
    try:
        if isinstance(v, (int, float)) or (isinstance(v, str) and str(v).replace('.', '').isdigit()):
            val = float(v)
            if val < 1e11: val *= 1000
            return pd.to_datetime(val, unit='ms', utc=True).tz_convert('Asia/Seoul')
        dt = pd.to_datetime(str(v), errors='coerce')
        if pd.isna(dt): return pd.NaT
        if dt.tzinfo is None: dt = dt.tz_localize('UTC')
        return dt.tz_convert('Asia/Seoul')
    except: return pd.NaT

def merge_driving_logs(df):
    import firebase_manager as fm
    try:
        sw_db = fm.load_data('sw_versions')
    except Exception:
        sw_db = {}
    if df.empty:
        return pd.DataFrame()
        
    for c in ['출발_km', '종료_km', '총주행거리(km)', '출발_배터리_차량', '종료_배터리_차량']:
        df[c] = pd.to_numeric(df.get(c, 0), errors='coerce').fillna(0)
        
    res = []
    d_col = 'date_str' if 'date_str' in df.columns else '날짜'
    
    for (d, car, drv), g in df.groupby([d_col, '차량번호', 'Safe_Guard']):
        sk = g[g['유형'].str.contains('출발|시작', na=False)]['출발_km'].max()
        ek = g[g['유형'].str.contains('종료|끝', na=False)]['종료_km'].max()
        sb = g[g['유형'].str.contains('출발|시작', na=False)]['출발_배터리_차량'].max()
        eb = g[g['유형'].str.contains('종료|끝', na=False)]['종료_배터리_차량'].max()
        
        if pd.isna(sk): sk = g['출발_km'].max()
        if pd.isna(ek): ek = g['종료_km'].max()
        if pd.isna(sb): sb = g['출발_배터리_차량'].max()
        if pd.isna(eb): eb = g['종료_배터리_차량'].max()
            
        tk = g['총주행거리(km)'].max()
        if (pd.isna(tk) or tk == 0) and pd.notna(sk) and pd.notna(ek) and ek >= sk:
            tk = ek - sk
            
        rms = " | ".join(g['특이사항'].dropna().astype(str).str.strip()[lambda x: x != ''].unique())
        sw = sw_db.get(f"{d}_{car}", {})
        
        s_time_raw = g[g['유형'].str.contains('출발|시작', na=False)]['timestamp'].max()
        e_time_raw = g[g['유형'].str.contains('종료|끝', na=False)]['timestamp'].max()
        
        s_dt = parse_time_to_kst(s_time_raw)
        e_dt = parse_time_to_kst(e_time_raw)
        
        res.append({
            '날짜': d, 
            '차량': car, 
            '요원': drv,
            '출발_km': int(sk) if pd.notna(sk) else 0,
            '종료_km': int(ek) if pd.notna(ek) else 0,
            '주행거리': int(tk) if pd.notna(tk) else 0,
            '출발🔋': f"{int(sb)}%" if pd.notna(sb) and sb > 0 else "-",
            '종료🔋': f"{int(eb)}%" if pd.notna(eb) and eb > 0 else "-",
            '출발_시간': s_dt.strftime('%H:%M:%S') if pd.notna(s_dt) else "-",
            '종료_시간': e_dt.strftime('%H:%M:%S') if pd.notna(e_dt) else "-",
            'Safeview': sw.get('Safeview', ''), 
            'CPU': sw.get('CPU', ''), 
            'MCU': sw.get('MCU', ''),
            'VPU1': sw.get('VPU1', ''), 
            'VPU2': sw.get('VPU2', ''), 
            'VPU3': sw.get('VPU3', ''), 
            'VPU4': sw.get('VPU4', ''),
            '비고': rms
        })
        
    return pd.DataFrame(res).sort_values(['날짜', '차량'], ascending=[False, True])

def get_shift_date(dt):
    if pd.isna(dt):
        return None
    if isinstance(dt, pd.Timestamp):
        dt = dt.to_pydatetime()
    if dt.hour < 7:
        return (dt - datetime.timedelta(days=1)).date()
    return dt.date()

def apply_modern_theme(fig):
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)", 
        paper_bgcolor="rgba(0,0,0,0)", 
        margin=dict(t=50, b=20, l=10, r=10), 
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1), 
        font=dict(color="#334155", size=13)
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor="#E2E8F0")
    return fig

def create_calendar_header(title, default_date):
    tk = f"cal_date_{title}"
    vk = f"cal_view_{title}"
    
    if tk not in st.session_state:
        st.session_state[tk] = default_date
    if vk not in st.session_state:
        st.session_state[vk] = "월간"

    def p():
        if st.session_state[vk] == "주간":
            st.session_state[tk] -= datetime.timedelta(days=7)
        else:
            d = st.session_state[tk]
            st.session_state[tk] = (d.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)

    def n():
        if st.session_state[vk] == "주간":
            st.session_state[tk] += datetime.timedelta(days=7)
        else:
            d = st.session_state[tk]
            st.session_state[tk] = (d.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)

    c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 2.5, 1.5])
    c1.button("◀", key=f"bp_{title}", on_click=p, use_container_width=True)
    c2.button("▶", key=f"bn_{title}", on_click=n, use_container_width=True)
    c3.button("📅", key=f"bt_{title}", on_click=lambda: st.session_state.update({tk: datetime.date.today()}), use_container_width=True)
    st.session_state[vk] = c5.radio(
        "보기", 
        ["월간", "주간"], 
        horizontal=True, 
        label_visibility="collapsed", 
        key=f"v_rad_{title}", 
        index=0 if st.session_state[vk] == "월간" else 1
    )
    
    target_d = st.session_state[tk]
    if st.session_state[vk] == "주간":
        ws = target_d - datetime.timedelta(days=(target_d.weekday() + 1) % 7)
        we = ws + datetime.timedelta(days=6)
        c4.markdown(f"<div style='text-align:center; font-weight:800; padding-top:8px;'>{ws.strftime('%m/%d')} ~ {we.strftime('%m/%d')}</div>", unsafe_allow_html=True)
    else:
        c4.markdown(f"<div style='text-align:center; font-weight:800; padding-top:8px;'>{target_d.year}년 {target_d.month}월</div>", unsafe_allow_html=True)
    
    return target_d, st.session_state[vk]

PREMIUM_CAL_CSS = """
<style>
.cal-wrapper { margin-bottom: 25px; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); border: 1px solid #f1f5f9; overflow-x: auto; -webkit-overflow-scrolling: touch; background: white; }
.cal-table { min-width: 800px; width: 100%; border-collapse: collapse; table-layout: fixed; }
.cal-th { border-bottom: 1px solid #e2e8f0; padding: 12px; text-align: center; background-color: #f8fafc; color: #475569; font-weight: 700; border-right: 1px solid #e2e8f0; }
.cal-td { border-right: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0; vertical-align: top; min-height: 120px; padding: 8px; transition: background 0.2s; }
.cal-day-num { font-weight: 800; font-size: 15px; color: #334155; }
.cal-holi-name { color: #ef4444; font-size: 11px; font-weight: 700; background: #fef2f2; padding: 2px 6px; border-radius: 6px; margin-bottom: 2px; display: inline-block; border: 1px solid #fecaca; }
.cal-event-name { color: #15803d; font-size: 11px; font-weight: 700; background: #dcfce7; padding: 2px 6px; border-radius: 6px; margin-bottom: 2px; display: inline-block; border: 1px solid #bbf7d0; }

.cal-actual.day { background: #FEF08A; color: #1E3A8A; font-size: 11px; font-weight: 700; padding: 4px 8px; margin-top: 4px; border-radius: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; border: 1px solid #FDE047; }
.cal-actual.night { background: #312E81; color: #FFFFFF; font-size: 11px; font-weight: 700; padding: 4px 8px; margin-top: 4px; border-radius: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; border: 1px solid #1E1B4B; }
.cal-actual.issue.day { background: #FEE2E2; color: #991B1B; border: 2px dotted #EF4444; }
.cal-actual.issue.night { background: #4C1D95; color: #FCA5A5; border: 2px dotted #EF4444; }

.cal-plan { background: #f1f5f9; color: #64748b; font-size: 11px; font-weight: 600; padding: 4px 8px; margin-top: 4px; border-radius: 6px; border: 1px dashed #cbd5e1; }
.cal-assign { background: #dcfce7; color: #166534; font-size: 11px; font-weight: 600; padding: 4px 8px; margin-top: 4px; border-radius: 6px; border: 1px dashed #86efac; }
.cal-special { background: #fef08a; color: #854d0e; font-size: 11px; font-weight: 600; padding: 6px 8px; margin-top: 4px; border-radius: 6px; border: 1px dashed #fcd34d; }
.cal-off { background: #fee2e2; color: #991b1b; font-size: 11px; font-weight: 600; padding: 4px 8px; margin-top: 4px; border-radius: 6px; }
.cal-summary-box { margin-top: 8px; background: #f8fafc; border-radius: 6px; padding: 6px; font-size: 12px; font-weight: 700; color: #64748b; text-align: right; }
.cal-sun { color: #ef4444; } .cal-sat { color: #3b82f6; }
</style>
"""

@st.cache_data(show_spinner=False, ttl=600)
def get_ride_data_combined(df):
    if df.empty: return pd.DataFrame()
    if 'shift' in df.columns:
        g = df.groupby(['shift_date', 'carNumber', 'driverName', 'shift']).agg(calls=('callCount','sum'), pax=('passengers','sum'), iss=('이슈건수','sum')).reset_index()
        g['tag'] = g['shift'].apply(lambda x: "야" if "야간" in str(x) else "주")
    else:
        g = df.groupby(['shift_date', 'carNumber', 'driverName']).agg(calls=('callCount','sum'), pax=('passengers','sum'), iss=('이슈건수','sum')).reset_index()
        def gt(r):
            tdf = df[(df['shift_date'] == r['shift_date']) & (df['carNumber'] == r['carNumber']) & (df['driverName'] == r['driverName'])]
            if tdf.empty: return "주"
            hrs = pd.to_datetime(tdf['dt_obj']).dt.hour
            if (hrs >= 20).any() or (hrs < 8).any(): return "야"
            return "주"
        g['tag'] = g.apply(gt, axis=1)
    return g

def short_car(c):
    if not c or c == 'Unknown': return '?'
    if '#' in c:
        parts = c.split('#')
        return f"{parts[0][0]}{parts[-1]}"
    return c[:2]

def draw_html_calendar(clean_df, entity_col, title):
    st.markdown(f"### 📅 {title}")
    target_d, vm = create_calendar_header(title, datetime.date.today())
    hols, events = get_korean_holidays(target_d.year)
    rd = get_ride_data_combined(clean_df)
    
    cal = calendar.Calendar(firstweekday=6)
    ws = cal.monthdatescalendar(target_d.year, target_d.month)
    if vm == "주간":
        wk_start = target_d - datetime.timedelta(days=(target_d.weekday() + 1) % 7)
        ws = [[wk_start + datetime.timedelta(days=i) for i in range(7)]]
        
    h = PREMIUM_CAL_CSS + "<div class='cal-wrapper'><table class='cal-table'><tr><th class='cal-th cal-sun'>일</th><th class='cal-th'>월</th><th class='cal-th'>화</th><th class='cal-th'>수</th><th class='cal-th'>목</th><th class='cal-th'>금</th><th class='cal-th cal-sat'>토</th></tr>"
    for wk in ws:
        h += "<tr>"
        for i, d in enumerate(wk):
            dc = "cal-day-num " + ("cal-sun" if i == 0 or d in hols else "cal-sat" if i == 6 else "")
            h += f"<td class='cal-td'><div class='{dc}'>{d.day}</div>"
            
            if d in hols: h += f"<div class='cal-holi-name'>{hols[d]}</div>"
            if d in events: h += f"<div class='cal-event-name'>{events[d]}</div>"
            
            if not rd.empty:
                # [주/야간 우선, 차량번호 차선 정렬]
                da = rd[rd['shift_date'] == d].sort_values(by=['tag', 'carNumber', 'driverName'])
                for _, r in da.iterrows():
                    nc = " night" if r['tag'] == "야" else " day"
                    tag_str = f"[{r['tag']}]"
                    sc = short_car(r['carNumber'])
                    
                    if r['calls'] == 0 and r['iss'] > 0:
                        h += f"<div class='cal-actual issue{nc}'>🚨 [{sc}]{tag_str} {r['driverName']} (이슈 {int(r['iss'])})</div>"
                    else:
                        h += f"<div class='cal-actual{nc}'>🚕 [{sc}]{tag_str} {r['driverName']} ({int(r['calls'])}/{int(r['pax'])})</div>"
                if not da.empty:
                    h += f"<div class='cal-summary-box'>합: {int(da['calls'].sum())}건 / {int(da['pax'].sum())}명</div>"
            h += "</td>"
        h += "</tr>"
    st.markdown(h + "</table></div>", unsafe_allow_html=True)

def draw_html_calendar_with_plan(clean_df, sched_df, entity_col, title):
    st.markdown(f"### 📅 {title}")
    st.markdown("<div style='display:flex; gap:10px; flex-wrap:wrap; margin-bottom:10px;'><span class='cal-actual day' style='padding:4px 10px; border:none;'>☀️ 주간운행</span><span class='cal-actual night' style='padding:4px 10px; border:none;'>🌙 야간운행</span><span class='cal-assign' style='padding:4px 10px;'>🔒 지정배차</span><span class='cal-plan' style='padding:4px 10px;'>🚕 일반 배정</span><span class='cal-special' style='padding:4px 10px;'>⭐ 특수배차</span><span class='cal-off' style='padding:4px 10px;'>🏝️ 휴무/휴가</span></div>", unsafe_allow_html=True)
    
    target_d, vm = create_calendar_header(title, datetime.date.today())
    hols, events = get_korean_holidays(target_d.year)
    rd = get_ride_data_combined(clean_df)
    
    cal = calendar.Calendar(firstweekday=6)
    ws = cal.monthdatescalendar(target_d.year, target_d.month)
    now = datetime.date.today()
    
    if vm == "주간":
        wk_start = target_d - datetime.timedelta(days=(target_d.weekday() + 1) % 7)
        ws = [[wk_start + datetime.timedelta(days=i) for i in range(7)]]
        
    h = PREMIUM_CAL_CSS + "<div class='cal-wrapper'><table class='cal-table'><tr><th class='cal-th cal-sun'>일</th><th class='cal-th'>월</th><th class='cal-th'>화</th><th class='cal-th'>수</th><th class='cal-th'>목</th><th class='cal-th'>금</th><th class='cal-th cal-sat'>토</th></tr>"
    
    if not sched_df.empty:
        sched_df['clean_date'] = sched_df['date'].astype(str).str.strip().str[:10]
        
    for wk in ws:
        h += "<tr>"
        for i, d in enumerate(wk):
            dc = "cal-day-num " + ("cal-sun" if i == 0 or d in hols else "cal-sat" if i == 6 else "")
            h += f"<td class='cal-td'><div class='{dc}'>{d.day}</div>"
            
            if d in hols: h += f"<div class='cal-holi-name'>{hols[d]}</div>"
            if d in events: h += f"<div class='cal-event-name'>{events[d]}</div>"
            
            da = rd[rd['shift_date'] == d].sort_values(by=['tag', 'carNumber', 'driverName']) if not rd.empty else pd.DataFrame()
                
            wc = [str(x).strip().replace(" ", "") for x in da['carNumber'].unique() if pd.notna(x)] if not da.empty else []
            wd = [str(x).strip().replace(" ", "") for x in da['driverName'].unique() if pd.notna(x)] if not da.empty else []
            
            for _, r in da.iterrows():
                nc = " night" if r['tag'] == "야" else " day"
                tag_str = f"[{r['tag']}]"
                sc = short_car(r['carNumber'])
                
                if r['calls'] == 0 and r['iss'] > 0:
                    h += f"<div class='cal-actual issue{nc}'>🚨 [{sc}]{tag_str} {r['driverName']} (이슈 {int(r['iss'])})</div>"
                else:
                    h += f"<div class='cal-actual{nc}'>🚕 [{sc}]{tag_str} {r['driverName']} ({int(r['calls'])}/{int(r['pax'])})</div>"
            
            if not sched_df.empty:
                ts = sched_df[sched_df['clean_date'] == d.strftime('%Y-%m-%d')]
                pl, of, rt = [], [], set()
                
                for _, s in ts.iterrows():
                    stype = str(s['type']).strip()
                    sn = str(s['name']).strip().replace(" ", "")
                    
                    if any(x in stype for x in ['배정', '지정배차', '특수배차']):
                        ac = re.search(r'\((.*?)\)', stype).group(1).strip() if '(' in stype else ""
                        acc = ac.replace(" ", "")
                        if (d < now) or (sn in wd) or (acc in wc): continue
                            
                        pm = re.search(r'\[(.*?)\]', stype)
                        pr = pm.group(1).strip() if pm else ""
                        sac = short_car(ac)
                        
                        if '특수배차' in stype:
                            dt = f"⭐ [{sac}] {pr.split(' : 👥')[1].strip()}" if " : 👥" in pr else f"⭐ [{sac}] 전담팀"
                            tk = (ac, pr)
                            if tk not in rt:
                                pl.append({'car': ac, 'name': pr, 'html': f"<div class='cal-special'>{dt}</div>"})
                                rt.add(tk)
                        elif '지정배차' in stype:
                            pl.append({'car': ac, 'name': s['name'], 'html': f"<div class='cal-assign'>🔒 [{sac}] {s['name']}</div>"})
                        else:
                            pl.append({'car': ac, 'name': s['name'], 'html': f"<div class='cal-plan'>🚕 [{sac}] {s['name']}</div>"})
                    else:
                        of.append({'name': s['name'], 'html': f"<div class='cal-off'>🏝️ {s['name']}</div>"})
                        
                for p in sorted(pl, key=lambda x: (x['car'], x['name'])): h += p['html']
                for o in sorted(of, key=lambda x: x['name']): h += o['html']
                
            if not da.empty: h += f"<div class='cal-summary-box'>합: {int(da['calls'].sum())}건 / {int(da['pax'].sum())}명</div>"
            h += "</td>"
        h += "</tr>"
    st.markdown(h + "</table></div>", unsafe_allow_html=True)

def draw_admin_preview_calendar(base_date, combined, clean_df, u_df=None):
    target_d, vm = create_calendar_header("미리보기", base_date)
    hols, events = get_korean_holidays(target_d.year)
    rd = get_ride_data_combined(clean_df)
    
    cal = calendar.Calendar(firstweekday=6)
    ws = cal.monthdatescalendar(target_d.year, target_d.month)
    now = datetime.date.today()
    
    if vm == "주간":
        wk_start = target_d - datetime.timedelta(days=(target_d.weekday() + 1) % 7)
        ws = [[wk_start + datetime.timedelta(days=i) for i in range(7)]]
        
    h = PREMIUM_CAL_CSS + "<div class='cal-wrapper'><table class='cal-table'><tr><th class='cal-th cal-sun'>일</th><th class='cal-th'>월</th><th class='cal-th'>화</th><th class='cal-th'>수</th><th class='cal-th'>목</th><th class='cal-th'>금</th><th class='cal-th cal-sat'>토</th></tr>"
    if not combined.empty: combined['clean_date'] = combined['date'].astype(str).str.strip().str[:10]
        
    for wk in ws:
        h += "<tr>"
        for i, d in enumerate(wk):
            ip = d < base_date
            dc = "cal-day-num " + ("cal-sun" if i == 0 or d in hols else "cal-sat" if i == 6 else "")
            op_st = "opacity:0.3;" if ip else ""
            op_mid = "opacity:0.5;" if ip else ""
            
            h += f"<td class='cal-td'><div class='{dc}' style='{op_st}'>{d.day}</div>"
            if d in hols: h += f"<div class='cal-holi-name' style='{op_st}'>{hols[d]}</div>"
            if d in events: h += f"<div class='cal-event-name' style='{op_st}'>{events[d]}</div>"
            
            da = rd[rd['shift_date'] == d].sort_values(by=['tag', 'carNumber', 'driverName']) if not rd.empty else pd.DataFrame()
            wc = [str(x).strip().replace(" ", "") for x in da['carNumber'].unique() if pd.notna(x)] if not da.empty else []
            wd = [str(x).strip().replace(" ", "") for x in da['driverName'].unique() if pd.notna(x)] if not da.empty else []
            
            for _, r in da.iterrows():
                nc = " night" if r['tag'] == "야" else " day"
                tag_str = f"[{r['tag']}]"
                sc = short_car(r['carNumber'])
                if r['calls'] == 0 and r['iss'] > 0:
                    h += f"<div class='cal-actual issue{nc}' style='{op_mid}'>🚨 [{sc}]{tag_str} {r['driverName']} (이슈 {int(r['iss'])})</div>"
                else:
                    h += f"<div class='cal-actual{nc}' style='{op_mid}'>🚕 [{sc}]{tag_str} {r['driverName']} ({int(r['calls'])}/{int(r['pax'])})</div>"
                    
            if not ip and not combined.empty:
                tc = combined[combined['clean_date'] == d.strftime('%Y-%m-%d')]
                pl, of, rt = [], [], set()
                
                for _, s in tc.iterrows():
                    stype = str(s['type']).strip()
                    sn = str(s['name']).strip().replace(" ", "")
                    if any(x in stype for x in ['배정', '지정배차', '특수배차']):
                        ac = re.search(r'\((.*?)\)', stype).group(1).strip() if '(' in stype else ""
                        acc = ac.replace(" ", "")
                        if (d < now) or (sn in wd) or (acc in wc): continue
                            
                        pm = re.search(r'\[(.*?)\]', stype)
                        pr = pm.group(1).strip() if pm else ""
                        sac = short_car(ac)
                        
                        driver_shift = "주"
                        if u_df is not None and not u_df.empty:
                            u_row = u_df[u_df['name'].astype(str).str.strip() == s['name'].strip()]
                            if not u_row.empty:
                                if "야간" in str(u_row.iloc[0].get('shift', '주간')):
                                    driver_shift = "야"
                        
                        nc_plan = "night" if driver_shift == "야" else "day"
                        
                        if '특수배차' in stype:
                            dt = f"⭐ [{sac}][{driver_shift}] {pr.split(' : 👥')[1].strip()}" if " : 👥" in pr else f"⭐ [{sac}][{driver_shift}] 전담팀"
                            tk = (ac, pr)
                            if tk not in rt:
                                pl.append({'shift': driver_shift, 'car': ac, 'name': pr, 'html': f"<div class='cal-special'>{dt}</div>"})
                                rt.add(tk)
                        elif '지정배차' in stype:
                            pl.append({'shift': driver_shift, 'car': ac, 'name': s['name'], 'html': f"<div class='cal-assign'>🔒 [{sac}][{driver_shift}] {s['name']}</div>"})
                        else:
                            pl.append({'shift': driver_shift, 'car': ac, 'name': s['name'], 'html': f"<div class='cal-actual {nc_plan}'>🚕 [{sac}][{driver_shift}] {s['name']}</div>"})
                    else:
                        of.append({'name': s['name'], 'html': f"<div class='cal-off'>🏝️ {s['name']}</div>"})
                        
                for p in sorted(pl, key=lambda x: (x['shift'], x['car'], x['name'])): h += p['html']
                for o in sorted(of, key=lambda x: x['name']): h += o['html']
                
            if not da.empty: h += f"<div class='cal-summary-box' style='{op_mid}'>합: {int(da['calls'].sum())}건 / {int(da['pax'].sum())}명</div>"
            h += "</td>"
        h += "</tr>"
    st.markdown(h + "</table></div>", unsafe_allow_html=True)
