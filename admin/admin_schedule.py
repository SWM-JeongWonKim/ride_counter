import streamlit as st
import pandas as pd
import datetime
import time
import random
import os
import json
import firebase_manager as fm
import chart_utils as dc
import admin_utils as utils
import re
from collections import defaultdict

def get_car_type(car_name):
    c = str(car_name).upper()
    if 'E100' in c: return 'E100'
    if 'U100' in c: return 'U100'
    return 'OTHER'

def generate_auto_schedule(target_date, target_drivers, m_cars, clean_df, sched_df, draft_dict):
    history = {} 
    kst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    cutoff_str = (kst_now - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    
    # 1. 실제 운행 완료 기록 (과거의 확실한 팩트, 최우선 신뢰)
    if clean_df is not None and not clean_df.empty:
        for _, r in clean_df.iterrows():
            try: d_str = r['shift_date'].strftime('%Y-%m-%d')
            except: d_str = str(r['shift_date'])[:10]
            nm = str(r['driverName']).strip()
            if (d_str, nm) not in history:
                history[(d_str, nm)] = str(r['carNumber']).strip()
                
    # 2. DB 확정 스케줄 (오늘 이후의 "예정된" 배차만 보조 사용, 과거 미운행 스케줄 무시)
    if sched_df is not None and not sched_df.empty:
        for _, r in sched_df.iterrows():
            d_str = str(r['date'])[:10]
            nm = str(r['name']).strip()
            t = str(r['type'])
            if (d_str, nm) not in history and d_str >= cutoff_str:
                if any(x in t for x in ['배정', '지정배차', '특수배차']):
                    m = re.search(r'\((.*?)\)', t)
                    if m: history[(d_str, nm)] = m.group(1).strip()

    # 3. 화면 미리보기 상태 (가장 우선)
    for (d_str, nm), t in draft_dict.items():
        if t == 'DELETE' or '휴무' in t:
            if (d_str, nm) in history:
                del history[(d_str, nm)]
        elif any(x in t for x in ['배정', '지정배차', '특수배차']):
            m = re.search(r'\((.*?)\)', t)
            if m: history[(d_str, nm)] = m.group(1).strip()

    consecutive_days = {d: 0 for d in target_drivers}
    last_driven_type = {d: None for d in target_drivers}
    consecutive_type_days = {d: 0 for d in target_drivers}
    driven_counts_30d = {d: defaultdict(int) for d in target_drivers}

    target_d_str = target_date.strftime('%Y-%m-%d')
    thirty_days_ago_str = (target_date - datetime.timedelta(days=30)).strftime('%Y-%m-%d')

    for d in target_drivers:
        d_dates = sorted([date for (date, drv) in history.keys() if drv == d and date < target_d_str], reverse=True)
        
        cons_type = 0
        curr_type = None
        for dt_str in d_dates:
            car_num = history[(dt_str, d)].upper()
            t = 'E100' if ('E100' in car_num or 'E' in car_num) else ('U100' if ('U100' in car_num or 'U' in car_num) else None)
            if not t: continue
            
            if not curr_type:
                curr_type = t
                cons_type = 1
                last_driven_type[d] = t
            elif t == curr_type:
                cons_type += 1
            else:
                break
        consecutive_type_days[d] = cons_type
        
        cons = 0
        curr_d = target_date - datetime.timedelta(days=1)
        while True:
            curr_str = curr_d.strftime('%Y-%m-%d')
            if (curr_str, d) in history and history[(curr_str, d)]:
                cons += 1
                curr_d -= datetime.timedelta(days=1)
            else:
                break
        consecutive_days[d] = cons
        
        for dt_str in d_dates:
            if dt_str >= thirty_days_ago_str:
                car_num = history[(dt_str, d)]
                driven_counts_30d[d][car_num] += 1

    type_counts_30d = {d: {'E100': 0, 'U100': 0, 'OTHER': 0} for d in target_drivers}
    for d in target_drivers:
        for car, count in driven_counts_30d[d].items():
            c_type = get_car_type(car)
            if c_type in type_counts_30d[d]:
                type_counts_30d[d][c_type] += count

    num_cars = len(m_cars)
    drivers_sorted = sorted(target_drivers, key=lambda x: consecutive_days[x], reverse=True)
    
    assignments = {}
    if len(target_drivers) > num_cars:
        num_rest = len(target_drivers) - num_cars
        rest_drivers = set(drivers_sorted[:num_rest])
        assign_drivers = drivers_sorted[num_rest:]
    else:
        rest_drivers = set()
        assign_drivers = drivers_sorted[:]

    for d in rest_drivers:
        assignments[d] = ("DELETE", f"차량 부족으로 연속 {consecutive_days[d]}일 운행자 배정 제외")

    available_cars = list(m_cars)
    E_cars = [c for c in available_cars if get_car_type(c) == 'E100']
    U_cars = [c for c in available_cars if get_car_type(c) == 'U100']
    
    need_E, need_U = [], []
    for d in assign_drivers:
        last_t = last_driven_type[d]
        if last_t == 'E100': need_U.append(d)
        elif last_t == 'U100': need_E.append(d)
        else:
            if len(need_U) < len(U_cars): need_U.append(d)
            else: need_E.append(d)
            
    random.shuffle(need_U)
    need_U.sort(key=lambda x: (type_counts_30d[x]['U100'], -consecutive_type_days[x]))
    
    random.shuffle(need_E)
    need_E.sort(key=lambda x: (type_counts_30d[x]['E100'], -consecutive_type_days[x]))

    while len(need_U) > len(U_cars) and len(E_cars) > len(need_E):
        forced_driver = need_U.pop() 
        need_E.append(forced_driver)
        
    while len(need_E) > len(E_cars) and len(U_cars) > len(need_U):
        forced_driver = need_E.pop()
        need_U.append(forced_driver)

    final_needs = {}
    for d in need_U: final_needs[d] = 'U100'
    for d in need_E: final_needs[d] = 'E100'

    for d in assign_drivers:
        needed_type = final_needs.get(d, 'OTHER')
        type_cars = [c for c in available_cars if get_car_type(c) == needed_type]
        
        forced_fail = False
        if not type_cars: 
            type_cars = available_cars 
            forced_fail = True
            
        if not type_cars:
            assignments[d] = ("배정 불가", "남은 가용 차량이 없습니다.")
            continue
            
        random.shuffle(type_cars)
        best_car = min(type_cars, key=lambda c: driven_counts_30d[d].get(str(c), 0))
        
        original_need = 'U100' if last_driven_type[d] == 'E100' else ('E100' if last_driven_type[d] == 'U100' else needed_type)
        reason_str = f"이전:{last_driven_type[d] or '없음'} 👉 교대:{original_need} | 해당차종 {type_counts_30d[d].get(original_need, 0)}회 탑승 (배정차량 {driven_counts_30d[d].get(str(best_car), 0)}회)"
        
        if get_car_type(best_car) != original_need or forced_fail:
            reason_str += " (⚠️차량 수량 부족으로 교차 실패 및 차순위 배정)"
            
        assignments[d] = (f"일반 배정 ({best_car})", reason_str)
        available_cars.remove(best_car)
        
    return assignments

def draw_schedule_management(clean_df, sched_df, u_df, m_cars, m_drivers, kst_now):
    st.markdown(utils.get_premium_header("🗓️", "배차 및 휴무 스케줄 관리", "#10B981"), unsafe_allow_html=True)
    
    if 'draft_dict' not in st.session_state: st.session_state.draft_dict = {}
    if 'sim_range' not in st.session_state: st.session_state.sim_range = None
    if 'auto_sched_reasons' not in st.session_state: st.session_state.auto_sched_reasons = {}
        
    col_auto, col_assign, col_manual = st.columns(3)
    
    pure_drivers = [str(r.get('name')).strip() for _, r in u_df.iterrows() if utils.parse_bool(r.get('can_view_dashboard')) and utils.parse_bool(r.get('is_driver')) and not utils.parse_bool(r.get('is_admin')) and not utils.parse_bool(r.get('is_support')) and pd.notna(r.get('name'))]
    assignable_all_drivers = [str(r.get('name')).strip() for _, r in u_df.iterrows() if utils.parse_bool(r.get('can_view_dashboard')) and (utils.parse_bool(r.get('is_driver')) or utils.parse_bool(r.get('is_support'))) and pd.notna(r.get('name'))]
    assignable_all_drivers = sorted(list(set(assignable_all_drivers)))

    with col_auto:
        st.markdown("<h4 style='color:#0f172a; font-weight:700; margin-bottom:15px;'>🤖 자동 배차</h4>", unsafe_allow_html=True)
        with st.expander("💡 자동 배차 규칙", expanded=False):
            st.info("""
            1. **우선 교대 배정**: 전날 E100을 탔다면 U100 우선 배정. (차량이 부족할 경우 해당 차종을 가장 적게 탄 사람에게 우선권 부여)
            2. **최소 탑승 우선**: 배정될 차종 내에서 최근 30일 가장 적게 운행한 개별 차량 우선.
            3. **무작위 셔플**: 위 조건이 동일한 차량/인원이면 랜덤 배정.
            4. **배정 제외**: 차량 수보다 인원이 많을 경우 가장 많이 '연속 운행'한 인원 부터 배정 없음.
            """)
            
        with st.form("auto_sched_form"):
            a_dates = st.date_input("배정 기간 (시작일~종료일)", value=(kst_now.date(), kst_now.date() + datetime.timedelta(days=7)))
            
            st.markdown("<div style='background-color:#f1f5f9; padding:10px; border-radius:10px; margin: 10px 0;'><b>📍 배정 대상 필터링</b></div>", unsafe_allow_html=True)
            a_region = st.selectbox("지역 선택", ["상암", "강남", "안양", "전체"], index=0)
            a_shift = st.selectbox("주/야간 선택", ["주간", "야간", "전체"], index=0)
            
            a_avail_cars = st.multiselect("🚗 서비스 운영 차량 (일반 가용)", options=m_cars, default=m_cars[:5] if len(m_cars)>=3 else m_cars)
            
            st.markdown("<div style='background-color:#eff6ff; padding:10px; border-radius:10px; margin: 10px 0;'><b>🛠️ 서비스 외 배차 (특수 임무 전담)</b></div>", unsafe_allow_html=True)
            ns_car = st.selectbox("특수 차량 선택", options=["선택안함"] + m_cars)
            ns_purpose = st.text_input("사용 목적 기입 (달력 카드에 표시됩니다)", placeholder="예: 데이터수집, VIP시승")
            ns_drivers = st.multiselect("전담 요원 지정 (지정 인원이 모두 동시 탑승합니다)", options=pure_drivers)
            
            a_exclude = st.multiselect("배차 제외 인원", options=pure_drivers)
            a_exclude_direct = st.text_input("제외 직접 입력 (쉼표로 구분)")
            a_weekdays = st.checkbox("☑️ 평일(공휴일 제외)만 배정", value=True)
            
            if st.form_submit_button("🔎 미리보기에 오토 추가", type="primary", use_container_width=True):
                if not a_avail_cars and ns_car == "선택안함": 
                    st.warning("차량을 최소 1대 이상 설정해주세요.")
                elif ns_car != "선택안함" and not ns_purpose.strip():
                    st.warning("서비스 외 배차의 '사용 목적'을 입력해주세요.")
                elif isinstance(a_dates, tuple) and len(a_dates) == 2:
                    d_start, d_end = a_dates
                    
                    if st.session_state.sim_range:
                        st.session_state.sim_range = (min(st.session_state.sim_range[0], d_start.strftime('%Y-%m-%d')), max(st.session_state.sim_range[1], d_end.strftime('%Y-%m-%d')))
                    else:
                        st.session_state.sim_range = (d_start.strftime('%Y-%m-%d'), d_end.strftime('%Y-%m-%d'))
                        
                    final_excludes = a_exclude + [n.strip() for n in a_exclude_direct.split(',') if n.strip()]
                    
                    target_drivers = []
                    for d in pure_drivers:
                        if d in final_excludes: continue
                        if u_df.empty: 
                            target_drivers.append(d)
                            continue
                        d_row = u_df[u_df['name'] == d]
                        if d_row.empty: continue
                        d_reg = d_row.iloc[0].get('region', '상암')
                        d_sh = d_row.iloc[0].get('shift', '주간')
                        
                        if a_region != "전체" and str(d_reg) != a_region: continue
                        if a_shift != "전체" and a_shift not in str(d_sh): continue
                        
                        target_drivers.append(d)
                    
                    curr_d = d_start
                    while curr_d <= d_end:
                        d_str = curr_d.strftime('%Y-%m-%d')
                        if d_str in st.session_state.auto_sched_reasons:
                            del st.session_state.auto_sched_reasons[d_str]
                        curr_d += datetime.timedelta(days=1)

                    curr = d_start
                    while curr <= d_end:
                        hols = dc.get_korean_holidays(curr.year)
                        if a_weekdays and (curr.weekday() >= 5 or curr in hols): 
                            curr += datetime.timedelta(days=1)
                            continue
                            
                        d_str = curr.strftime('%Y-%m-%d')
                        if d_str not in st.session_state.auto_sched_reasons:
                            st.session_state.auto_sched_reasons[d_str] = {'selected': [], 'unselected': [], 'excluded': []}
                        
                        today_targets = list(target_drivers)
                        cars_today = list(a_avail_cars)
                        
                        if ns_car != "선택안함":
                            if ns_car in cars_today: 
                                cars_today.remove(ns_car)
                            avail_ns = [n for n in ns_drivers if n in today_targets]
                            for sel_ns in avail_ns:
                                st.session_state.draft_dict[(d_str, sel_ns)] = f'특수배차({ns_car}) [{ns_purpose}]'
                                st.session_state.auto_sched_reasons[d_str]['selected'].append({'name': sel_ns, 'car': ns_car, 'reason': f"⭐특수배차[{ns_purpose}]"})
                                today_targets.remove(sel_ns)
                        
                        assignments = generate_auto_schedule(curr, today_targets, cars_today, clean_df, sched_df, st.session_state.draft_dict)
                        
                        for drv, (res, reason) in assignments.items():
                            if res == "DELETE":
                                st.session_state.draft_dict[(d_str, drv)] = "DELETE"
                                st.session_state.auto_sched_reasons[d_str]['unselected'].append({'name': drv, 'reason': reason})
                            elif res.startswith("배정 불가"):
                                st.session_state.draft_dict[(d_str, drv)] = "DELETE"
                                st.session_state.auto_sched_reasons[d_str]['unselected'].append({'name': drv, 'reason': reason})
                            else:
                                st.session_state.draft_dict[(d_str, drv)] = res
                                m = re.search(r'\((.*?)\)', res)
                                car = m.group(1).strip() if m else "알수없음"
                                st.session_state.auto_sched_reasons[d_str]['selected'].append({'name': drv, 'car': car, 'reason': reason})

                        curr += datetime.timedelta(days=1)
                    st.success("선택하신 기간의 공정 자동 배정이 완료되었습니다!")
                    time.sleep(1.5)
                    st.rerun()

    with col_assign:
        st.markdown("<h4 style='color:#0f172a; font-weight:700; margin-bottom:15px;'>🎯 지정 배차 (수동)</h4>", unsafe_allow_html=True)
        with st.form("manual_assign_form", clear_on_submit=True):
            m_dates = st.date_input("지정 배차 기간", value=(kst_now.date(), kst_now.date()))
            m_names = st.multiselect("배정할 요원 (기사 + 지원파트)", options=assignable_all_drivers)
            m_car = st.selectbox("고정할 차량", options=m_cars if m_cars else ["차량없음"])
            m_purpose = st.text_input("지정 목적 기입 (달력 표시용)", placeholder="예: 지정배차, VIP수행 등 (기본값: 지정배차)")
            
            if st.form_submit_button("➕ 미리보기에 지정 배차 추가", use_container_width=True, type="primary"):
                if not m_names:
                    st.warning("배정할 요원을 선택해주세요.")
                else:
                    if isinstance(m_dates, tuple) and len(m_dates) == 2: d_start, d_end = m_dates
                    elif isinstance(m_dates, tuple) and len(m_dates) == 1: d_start = d_end = m_dates[0]
                    else: d_start = d_end = m_dates
                    
                    if st.session_state.sim_range:
                        st.session_state.sim_range = (min(st.session_state.sim_range[0], d_start.strftime('%Y-%m-%d')), max(st.session_state.sim_range[1], d_end.strftime('%Y-%m-%d')))
                    else:
                        st.session_state.sim_range = (d_start.strftime('%Y-%m-%d'), d_end.strftime('%Y-%m-%d'))
                        
                    curr = d_start
                    while curr <= d_end:
                        d_str = curr.strftime('%Y-%m-%d')
                        for nm in m_names:
                            d_purpose = m_purpose.strip() if m_purpose.strip() else "지정배차"
                            st.session_state.draft_dict[(d_str, nm)] = f'지정배차({m_car}) [{d_purpose}]'
                        curr += datetime.timedelta(days=1)
                    st.success("미리보기에 지정 배차가 추가되었습니다!")
                    time.sleep(1)
                    st.rerun()

    with col_manual:
        st.markdown("<h4 style='color:#0f172a; font-weight:700; margin-bottom:15px;'>🏖️ 일정 추가/삭제</h4>", unsafe_allow_html=True)
        with st.form("manual_schedule_form", clear_on_submit=True):
            s_dates = st.date_input("기간 선택", value=(kst_now.date(), kst_now.date()))
            s_names = st.multiselect("등록 요원 선택", assignable_all_drivers)
            s_direct = st.text_input("직접 입력 (쉼표로 구분)")
            s_type = st.selectbox("일정 종류 선택", ["일정 완전 삭제(초기화)", "휴가/반차 등 입력"])
            s_custom_type = st.text_input("일정 종류 직접 입력", placeholder="예비군, 반차 등 (직접 입력 선택 시)")
            s_skip_weekend = st.checkbox("☑️ 휴일(주말/공휴일) 제외", value=True)
            
            if st.form_submit_button("➕ 미리보기에 일정 반영", use_container_width=True):
                final_names = s_names + [n.strip() for n in s_direct.split(',') if n.strip()]
                if not final_names: 
                    st.warning("인원을 지정해주세요.")
                else:
                    final_type = "DELETE" if s_type == "일정 완전 삭제(초기화)" else (s_custom_type if s_custom_type else "휴무/휴가")
                    if isinstance(s_dates, tuple) and len(s_dates) == 2: d_start, d_end = s_dates
                    elif isinstance(s_dates, tuple) and len(s_dates) == 1: d_start = d_end = s_dates[0]
                    else: d_start = d_end = s_dates
                    
                    if st.session_state.sim_range:
                        st.session_state.sim_range = (min(st.session_state.sim_range[0], d_start.strftime('%Y-%m-%d')), max(st.session_state.sim_range[1], d_end.strftime('%Y-%m-%d')))
                    else:
                        st.session_state.sim_range = (d_start.strftime('%Y-%m-%d'), d_end.strftime('%Y-%m-%d'))
                    
                    curr = d_start
                    while curr <= d_end:
                        hols = dc.get_korean_holidays(curr.year)
                        if s_skip_weekend and (curr.weekday() >= 5 or curr in hols): 
                            curr += datetime.timedelta(days=1)
                            continue
                            
                        for nm in final_names: 
                            st.session_state.draft_dict[(curr.strftime('%Y-%m-%d'), nm)] = final_type
                        curr += datetime.timedelta(days=1)
                    st.success("미리보기에 일정이 반영되었습니다!")
                    time.sleep(1)
                    st.rerun()

    st.divider()
    c_title, c_btn1, c_btn2, c_btn3 = st.columns([2.5, 1.5, 1.5, 1.5])
    c_title.markdown(utils.get_premium_header("👀", "스케줄 미리보기", "#8B5CF6"), unsafe_allow_html=True)
    
    if c_btn1.button("🔄 자동/지정배차 미리보기 초기화", use_container_width=True): 
        st.session_state.draft_dict = {}
        st.session_state.auto_sched_reasons = {} 
        st.session_state.sim_range = None
        st.rerun()
        
    if c_btn2.button("🗑️ 선택기간 DB 배차 완전 삭제", use_container_width=True):
        if st.session_state.sim_range:
            s_dt, e_dt = st.session_state.sim_range
            fm.apply_draft_schedules({}, s_dt, e_dt)
            st.session_state.draft_dict = {}
            st.session_state.auto_sched_reasons = {} 
            st.session_state.sim_range = None
            st.success(f"{s_dt} ~ {e_dt} 기간의 모든 배차가 삭제되었습니다.")
            time.sleep(1.5)
            st.rerun()
        else:
            st.warning("먼저 위쪽 폼에서 기간을 선택하고 미리보기를 한번 실행해주세요.")

    if c_btn3.button("✅ 변경사항 DB 최종 적용", type="primary", use_container_width=True):
        if not st.session_state.draft_dict: 
            st.warning("변경사항이 없습니다.")
        else:
            fm.apply_draft_schedules(st.session_state.draft_dict, st.session_state.sim_range[0] if st.session_state.sim_range else None, "2099-12-31" if st.session_state.sim_range else None)
            st.session_state.draft_dict = {}
            st.session_state.sim_range = None
            st.session_state.auto_sched_reasons = {} 
            st.success("스케줄이 DB에 성공적으로 저장되었습니다!")
            time.sleep(1.5)
            st.rerun()
    
    draft_entries = []
    deleted_keys = set()
    for (d, n), t in st.session_state.draft_dict.items():
        d_clean = str(d).strip()[:10]
        n_clean = str(n).strip()
        if t == 'DELETE': 
            deleted_keys.add((d_clean, n_clean))
        else: 
            draft_entries.append({'date': d_clean, 'name': n_clean, 'type': str(t).strip()})
            
    draft_df = pd.DataFrame(draft_entries)

    min_date_str = kst_now.date().strftime('%Y-%m-%d')
    if st.session_state.sim_range and st.session_state.sim_range[0] < min_date_str:
        min_date_str = st.session_state.sim_range[0]

    if not sched_df.empty:
        preview_base = sched_df.copy()
        preview_base['date'] = preview_base['date'].astype(str).str.strip().str[:10]
        preview_base['name'] = preview_base['name'].astype(str).str.strip()
        
        preview_base = preview_base[preview_base['date'] >= min_date_str] 
        preview_base = preview_base[~preview_base.apply(lambda x: (str(x['date']), str(x['name'])) in deleted_keys, axis=1)]
        
        if not draft_df.empty:
            draft_keys = set(zip(draft_df['date'], draft_df['name']))
            preview_base = preview_base[~preview_base.apply(lambda x: (str(x['date']), str(x['name'])) in draft_keys, axis=1)]
            final_preview_df = pd.concat([preview_base, draft_df], ignore_index=True)
        else:
            final_preview_df = preview_base
    else:
        final_preview_df = draft_df

    min_date_obj = kst_now.date()
    if st.session_state.sim_range and st.session_state.sim_range[0] < min_date_obj.strftime('%Y-%m-%d'):
        min_date_obj = datetime.datetime.strptime(st.session_state.sim_range[0], '%Y-%m-%d').date()

    dc.draw_admin_preview_calendar(min_date_obj, final_preview_df, clean_df, u_df)
    
    if st.session_state.get('auto_sched_reasons'):
        with st.expander("🤖 현재 작성 중인 배차 선정 근거 (미리보기)", expanded=False):
            st.info("💡 가장 최근에 [미리보기에 추가]를 누른 건의 사유만 확인 가능합니다.")
            for d_str, logs in sorted(st.session_state.auto_sched_reasons.items()):
                st.markdown(f"##### 📅 {d_str} 배차 결과")
                st.markdown("**✅ 배정 완료**")
                for log in logs.get('selected', []): 
                    st.markdown(f"- 👤 **{log['name']}** (🚗 {log['car']}) 👉 {log['reason']}")
                if logs.get('unselected'):
                    st.markdown("**⏸️ 배정 없음 (초과 인원)**")
                    for log in logs['unselected']: 
                        st.markdown(f"- 👤 <span style='color:gray'>{log['name']}</span> 👉 {log['reason']}", unsafe_allow_html=True)
                if logs.get('excluded'):
                    st.markdown("**🚫 배정 제외**")
                    for log in logs['excluded']: 
                        st.markdown(f"- 👤 <span style='color:#ef4444'>{log['name']}</span> 👉 {log['reason']}", unsafe_allow_html=True)
                st.markdown("---")

    st.divider()
    st.markdown(utils.get_premium_header("✏️", "기존 DB 스케줄 개별 수정/삭제", "#64748B"), unsafe_allow_html=True)
    if not sched_df.empty:
        show_cols = ['date', 'name', 'type']
        s_edit_df = sched_df[[c for c in show_cols if c in sched_df.columns]].copy()
        s_edit_df['date'] = s_edit_df['date'].astype(str).str[:10]
        
        edited_sched = st.data_editor(
            s_edit_df.sort_values('date', ascending=False), 
            hide_index=True, 
            use_container_width=True, 
            num_rows="dynamic", 
            column_config={
                "date": st.column_config.TextColumn("날짜 (YYYY-MM-DD)", width="medium"), 
                "name": st.column_config.TextColumn("이름", width="medium"), 
                "type": st.column_config.TextColumn("일정 종류", width="large")
            }, 
            key="sched_editor"
        )
        if st.button("💾 스케줄 표 수정/삭제 DB 즉시 반영", type="primary"):
            db_draft = {}
            orig_keys = set(zip(s_edit_df['date'], s_edit_df['name']))
            curr_keys = set(zip(edited_sched['date'], edited_sched['name']))
            for d, n in (orig_keys - curr_keys): 
                db_draft[(d, n)] = 'DELETE'
            for _, r in edited_sched.iterrows():
                if pd.notna(r['date']) and pd.notna(r['name']): 
                    db_draft[(str(r['date']), str(r['name']))] = str(r['type'])
            fm.apply_draft_schedules(db_draft, None, None)
            st.success("반영되었습니다!")
            time.sleep(1)
            st.rerun()
