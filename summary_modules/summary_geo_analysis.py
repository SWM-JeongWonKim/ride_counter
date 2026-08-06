import streamlit as st
import pandas as pd
import pydeck as pdk
import re
import datetime
import numpy as np
import requests

@st.cache_data(ttl=3600*24)
def get_korean_dong(lat, lng):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}&zoom=15&addressdetails=1"
        headers = {'User-Agent': 'RideCounterDashboard/1.0'}
        res = requests.get(url, headers=headers, timeout=3).json()
        addr = res.get('address', {})
        
        dong = addr.get('quarter', addr.get('suburb', addr.get('town', addr.get('village', ''))))
        gu = addr.get('borough', addr.get('city', ''))
        
        if dong and gu and dong != gu: return f"{gu} {dong}"
        elif dong: return dong
        elif gu: return f"{gu} 일대"
        else: return "상세주소 미상"
    except Exception: return "주소 변환 지연"

def draw_geo_view(clean_df, is_mobile):
    df = clean_df.copy()

    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(s))]

    def convert_ms_to_kst(ms_val):
        if pd.isna(ms_val) or ms_val == "": return pd.NaT
        try:
            val = float(ms_val)
            if val < 1e11: val *= 1000
            return pd.to_datetime(val, unit='ms', utc=True).tz_convert('Asia/Seoul')
        except Exception: return pd.NaT

    if 'ride_start_time' not in df.columns: df['ride_start_time'] = np.nan
    if 'ride_end_time' not in df.columns: df['ride_end_time'] = np.nan

    df['ride_start_kst'] = df['ride_start_time'].apply(convert_ms_to_kst)
    df['ride_end_kst'] = df['ride_end_time'].apply(convert_ms_to_kst)

    for col in ['latitude', 'longitude', 'end_latitude', 'end_longitude', 'route_path']:
        if col not in df.columns: df[col] = np.nan

    geo_df = df.dropna(subset=['latitude', 'longitude']).copy()
    if geo_df.empty:
        st.info("💡 GPS 위치가 기록된 운행 데이터가 없습니다.")
        return

    geo_df['latitude'] = pd.to_numeric(geo_df['latitude'], errors='coerce')
    geo_df['longitude'] = pd.to_numeric(geo_df['longitude'], errors='coerce')
    geo_df['end_latitude'] = pd.to_numeric(geo_df['end_latitude'], errors='coerce')
    geo_df['end_longitude'] = pd.to_numeric(geo_df['end_longitude'], errors='coerce')
    
    geo_df = geo_df.dropna(subset=['latitude', 'longitude'])

    # 5. 지도 호출 건수 포맷 변경 (Ride와 Issue 분리)
    def format_call_id(r):
        is_issue = str(r.get('status', '')).strip().upper() == 'ISSUE_ONLY'
        if is_issue:
            if pd.notna(r['ride_start_kst']):
                return f"🚨 [{r.get('carNumber', '차량미상')}] {r['ride_start_kst'].strftime('%Y-%m-%d %H:%M:%S')} 이슈 발생"
            return f"🚨 [{r.get('carNumber','차량미상')}] 이슈 발생 (시간 미상)"
        else:
            if pd.notna(r['ride_start_kst']):
                return f"🚕 [{r.get('carNumber', '차량미상')}] {r['ride_start_kst'].strftime('%Y-%m-%d %H:%M:%S')} 탑승 건"
            return f"🚕 [{r.get('carNumber','차량미상')}] 탑승 시간 미상 ({r.name}번)"
            
    geo_df['call_id'] = geo_df.apply(format_call_id, axis=1)
    
    mid_lat = float(geo_df['latitude'].mean())
    mid_lng = float(geo_df['longitude'].mean())

    unique_cars = sorted(geo_df['carNumber'].dropna().unique(), key=natural_sort_key)
    color_palette = [[227, 26, 28], [51, 160, 44], [31, 120, 180], [255, 127, 0], [106, 61, 154], [251, 154, 153], [177, 89, 40], [255, 215, 0]]
    car_color_map = {car: color_palette[i % len(color_palette)] for i, car in enumerate(unique_cars)}

    selected_cars = st.multiselect("🚗 조회할 차량을 선택하세요:", options=unique_cars, default=unique_cars)
    filtered_geo = geo_df[geo_df['carNumber'].isin(selected_cars)].copy()

    path_data = []
    for _, row in filtered_geo.iterrows():
        route = row.get('route_path')
        if isinstance(route, list) and len(route) > 1:
            path_coords = [[float(pt['lng']), float(pt['lat'])] for pt in route if isinstance(pt, dict) and 'lng' in pt and 'lat' in pt]
            if len(path_coords) > 1:
                path_data.append({
                    "call_id": str(row['call_id']), 
                    "path": path_coords, 
                    "carNumber": str(row['carNumber']), 
                    "color": car_color_map.get(row['carNumber'], [100, 100, 100])
                })
                
    path_df = pd.DataFrame(path_data)
    FREE_MAP_STYLE = 'https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json'

    map_tab1, map_tab2, map_tab3 = st.tabs(["📍 전체 위치", "🔥 밀집 구역", "🔦 상세 경로"])
    
    with map_tab1:
        if not filtered_geo.empty:
            layers = []
            safe_start_data = filtered_geo[['longitude', 'latitude', 'call_id', 'carNumber']].dropna().reset_index(drop=True)
            layers.append(pdk.Layer("ScatterplotLayer", data=safe_start_data, get_position='[longitude, latitude]', get_fill_color=[227, 26, 28, 200], get_radius=15, radius_min_pixels=3, pickable=True, auto_highlight=True))
            
            safe_end_data = filtered_geo[['end_longitude', 'end_latitude', 'call_id', 'carNumber']].dropna().reset_index(drop=True)
            if not safe_end_data.empty:
                layers.append(pdk.Layer("ScatterplotLayer", data=safe_end_data, get_position='[end_longitude, end_latitude]', get_fill_color=[31, 120, 180, 200], get_radius=15, radius_min_pixels=3, pickable=True, auto_highlight=True))
                
            if not path_df.empty:
                layers.append(pdk.Layer("PathLayer", data=path_df, pickable=True, get_color="color", width_scale=1, width_min_pixels=2, get_path="path", get_width=4))
                
            st.caption("🔴 빨간점: 탑승지/이슈위치 / 🔵 파란점: 하차지")
            st.pydeck_chart(pdk.Deck(map_style=FREE_MAP_STYLE, initial_view_state=pdk.ViewState(latitude=mid_lat, longitude=mid_lng, zoom=12, pitch=0, bearing=0), layers=layers, tooltip={"text": "{call_id}"}))
        else:
            st.warning("위치 데이터가 없습니다.")

    with map_tab2:
        if not filtered_geo.empty:
            safe_start_data = filtered_geo[['longitude', 'latitude', 'call_id']].dropna().reset_index(drop=True)
            ui_mode = st.radio("🎨 핫스팟 UI 스타일 선택", ["🔥 부드러운 그라데이션 (Heatmap)", "📊 3D 입체 빌딩 (Hexagon 3D)"], horizontal=True, key="hotspot_style_radio")
            
            cam_pitch = 0
            cam_bearing = 0
            
            if "Heatmap" in ui_mode:
                hotspot_layer = pdk.Layer("HeatmapLayer", data=safe_start_data, get_position='[longitude, latitude]', radius_pixels=45, intensity=0.9, threshold=0.03)
            else:
                cam_pitch = 50
                cam_bearing = -15
                hotspot_layer = pdk.Layer("HexagonLayer", data=safe_start_data, get_position='[longitude, latitude]', radius=70, elevation_scale=15, elevation_range=[0, 400], extruded=True, coverage=0.9, pickable=True, auto_highlight=True)
                
            st.pydeck_chart(pdk.Deck(map_style=FREE_MAP_STYLE, initial_view_state=pdk.ViewState(latitude=mid_lat, longitude=mid_lng, zoom=12.5, pitch=cam_pitch, bearing=cam_bearing), layers=[hotspot_layer]))
            
            st.markdown("<br>💡 밀집구역 분석", unsafe_allow_html=True)
            pickup_df = filtered_geo[['latitude', 'longitude']].dropna().copy()
            dropoff_df = filtered_geo[['end_latitude', 'end_longitude']].dropna().copy()
            
            if not pickup_df.empty:
                pickup_df['lat_bin'] = pickup_df['latitude'].round(3)
                pickup_df['lng_bin'] = pickup_df['longitude'].round(3)
                top_pickups = pickup_df.groupby(['lat_bin', 'lng_bin']).size().reset_index(name='count').sort_values('count', ascending=False).head(3)
                
            if not dropoff_df.empty:
                dropoff_df['lat_bin'] = dropoff_df['end_latitude'].round(3)
                dropoff_df['lng_bin'] = dropoff_df['end_longitude'].round(3)
                top_dropoffs = dropoff_df.groupby(['lat_bin', 'lng_bin']).size().reset_index(name='count').sort_values('count', ascending=False).head(3)

            hc1, hc2 = st.columns(2)
            with hc1:
                st.markdown("<div style='background: #f0fdf4; padding: 15px; border-radius: 12px; border: 1px solid #bbf7d0;'>", unsafe_allow_html=True)
                st.markdown("<strong style='color:#166534;'>🟢 가장 탑승/이슈가 많은 구역 TOP 3</strong>", unsafe_allow_html=True)
                if not pickup_df.empty:
                    for idx, r in enumerate(top_pickups.itertuples()):
                        st.markdown(f"{idx+1}. **{get_korean_dong(r.lat_bin, r.lng_bin)}** 주변 ({int(r.count)}건)")
                else:
                    st.caption("기록 없음")
                st.markdown("</div>", unsafe_allow_html=True)
                
            with hc2:
                st.markdown("<div style='background: #eff6ff; padding: 15px; border-radius: 12px; border: 1px solid #bfdbfe;'>", unsafe_allow_html=True)
                st.markdown("<strong style='color:#1e40af;'>🏁 가장 하차가 많은 구역 TOP 3</strong>", unsafe_allow_html=True)
                if not dropoff_df.empty:
                    for idx, r in enumerate(top_dropoffs.itertuples()):
                        st.markdown(f"{idx+1}. **{get_korean_dong(r.lat_bin, r.lng_bin)}** 주변 ({int(r.count)}건)")
                else:
                    st.caption("기록 없음")
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.warning("선택된 차량의 위치 데이터가 없습니다.")

    with map_tab3:
        if not filtered_geo.empty:
            f2, f3, f4 = st.columns(3)
            with f2: sel_drv = st.selectbox("👤 운행 요원", ["전체"] + sorted(filtered_geo['driverName'].dropna().unique().tolist()))
            tmp_df2 = filtered_geo if sel_drv == "전체" else filtered_geo[filtered_geo['driverName'] == sel_drv]
            with f3: sel_time = st.selectbox("⏰ 시간대", ["전체"] + sorted(tmp_df2['time_bracket'].dropna().unique().tolist()))
            tmp_df3 = tmp_df2 if sel_time == "전체" else tmp_df2[tmp_df2['time_bracket'] == sel_time]
            with f4: sel_issue = st.selectbox("🚨 이슈 필터", ["전체보기", "⚠️ 이슈 발생 건만 보기"])
            
            issue_mask_map = (tmp_df3['이슈건수'] > 0) | (tmp_df3['통합_이슈상세'].fillna('').astype(str).str.strip() != '') | (tmp_df3['status'].astype(str).str.strip().str.upper() == 'ISSUE_ONLY')
            tmp_df4 = tmp_df3 if sel_issue == "전체보기" else tmp_df3[issue_mask_map]
            
            sorted_call_ids = sorted(tmp_df4['call_id'].dropna().unique().tolist(), key=natural_sort_key)
            if not sorted_call_ids: 
                st.warning("조건에 맞는 호출/이슈 건이 없습니다.")
            else:
                call_options = ["전체보기"] + sorted_call_ids
                target_id = st.session_state.get("saved_call_id")
                default_idx = call_options.index(target_id) if target_id and target_id in call_options else 0
                    
                def on_call_select(): st.session_state["saved_call_id"] = st.session_state.call_id_selector

                selected_call = st.selectbox("🎯 표시할 호출/이슈 건 선택:", options=call_options, index=default_idx, key="call_id_selector", on_change=on_call_select)
                st.session_state["saved_call_id"] = selected_call
                
                spotlight_layers = []

                if selected_call == "전체보기":
                    st.success(f"**🗺️ 현재 필터 조건에 해당하는 총 {len(tmp_df4)}건의 호출 궤적과 이슈를 모두 표시합니다.**")
                    
                    safe_data = tmp_df4[['longitude', 'latitude', 'end_longitude', 'end_latitude', 'call_id', 'carNumber']].dropna(subset=['longitude', 'latitude']).copy().reset_index(drop=True)
                    safe_data['tooltip_text'] = safe_data['call_id']
                    
                    if not safe_data.empty:
                        spot_start = pdk.Layer("ScatterplotLayer", data=safe_data, get_position='[longitude, latitude]', get_fill_color=[16, 185, 129, 255], get_radius=15, radius_min_pixels=3, pickable=True)
                        spotlight_layers.append(spot_start)
                        
                        end_data = safe_data.dropna(subset=['end_longitude', 'end_latitude'])
                        if not end_data.empty:
                            spot_end = pdk.Layer("ScatterplotLayer", data=end_data, get_position='[end_longitude, end_latitude]', get_fill_color=[59, 130, 246, 255], get_radius=15, radius_min_pixels=3, pickable=True)
                            spotlight_layers.append(spot_end)

                    call_ids_in_tmp = tmp_df4['call_id'].tolist()
                    spot_path_df = path_df[path_df['call_id'].isin(call_ids_in_tmp)].reset_index(drop=True)
                    if not spot_path_df.empty:
                        spot_path_df['tooltip_text'] = spot_path_df['call_id']
                        spot_path = pdk.Layer("PathLayer", data=spot_path_df, get_color=[249, 115, 22, 150], width_min_pixels=3, get_path="path", pickable=True)
                        spotlight_layers.append(spot_path)

                    all_issues = []
                    for _, row in tmp_df4.iterrows():
                        pings = row.get('issue_pings', [])
                        memos = row.get('report_memos', {})
                        manual_issue = str(memos['ADMIN_EDIT']).strip() if isinstance(memos, dict) and 'ADMIN_EDIT' in memos else ""
                            
                        if isinstance(pings, list):
                            for p in pings:
                                if isinstance(p, dict) and 'lat' in p and 'lng' in p:
                                    ptime = p.get('time')
                                    if manual_issue: mtxt = f"{manual_issue} (admin)"
                                    else:
                                        m_val = "이슈 상세내용 미기입"
                                        if isinstance(memos, dict): m_val = memos.get(str(ptime), memos.get(int(ptime) if pd.notna(ptime) else 0, "이슈 상세내용 미기입"))
                                        elif isinstance(memos, list): m_val = " / ".join(str(x) for x in memos)
                                        mtxt = f"{m_val} (app)" if m_val != "이슈 상세내용 미기입" else m_val
                                    all_issues.append({"longitude": float(p['lng']), "latitude": float(p['lat']), "tooltip_text": f"[{row['call_id']}] 🚨 {mtxt}"})
                
                    if all_issues:
                        spot_issue = pdk.Layer("ScatterplotLayer", data=pd.DataFrame(all_issues), get_position='[longitude, latitude]', get_fill_color=[239, 68, 68, 255], get_radius=15, radius_min_pixels=4, pickable=True)
                        spotlight_layers.append(spot_issue)

                    mid_lat_s = float(safe_data['latitude'].mean()) if not safe_data.empty else mid_lat
                    mid_lng_s = float(safe_data['longitude'].mean()) if not safe_data.empty else mid_lng
                    
                    st.pydeck_chart(pdk.Deck(map_style=FREE_MAP_STYLE, initial_view_state=pdk.ViewState(latitude=mid_lat_s, longitude=mid_lng_s, zoom=12, pitch=0, bearing=0), layers=spotlight_layers, tooltip={"text": "{tooltip_text}"}))

                else:
                    spotlight_raw = tmp_df4[tmp_df4['call_id'] == selected_call]
                    
                    if not spotlight_raw.empty:
                        is_issue_only = str(spotlight_raw['status'].iloc[0]).strip().upper() == 'ISSUE_ONLY'
                        pickup_time_str = spotlight_raw['ride_start_kst'].iloc[0].strftime('%Y-%m-%d %H:%M:%S') if pd.notna(spotlight_raw['ride_start_kst'].iloc[0]) else "시간 미상"
                        dropoff_time_str = spotlight_raw['ride_end_kst'].iloc[0].strftime('%Y-%m-%d %H:%M:%S') if pd.notna(spotlight_raw['ride_end_kst'].iloc[0]) else "시간 미상"
                            
                        issue_pings = spotlight_raw['issue_pings'].iloc[0] if 'issue_pings' in spotlight_raw.columns else []
                        report_memos = spotlight_raw['report_memos'].iloc[0] if 'report_memos' in spotlight_raw.columns else {}
                        manual_issue = str(report_memos['ADMIN_EDIT']).strip() if isinstance(report_memos, dict) and 'ADMIN_EDIT' in report_memos else ""
                        
                        issue_times_str = ""
                        if spotlight_raw['이슈건수'].iloc[0] > 0:
                            times = []
                            if isinstance(issue_pings, list):
                                for ping in issue_pings:
                                    if isinstance(ping, dict) and 'time' in ping:
                                        try: times.append(pd.to_datetime(int(ping['time']), unit='ms', utc=True).tz_convert('Asia/Seoul').strftime('%H:%M:%S'))
                                        except: pass
                            issue_times_str = f" ➡️ :red[**🚨 이슈발생: {', '.join(times)}**]" if times else f" ➡️ :red[**🚨 이슈발생 (시간 미상)**]"

                        # [수정] 이슈 독립 마커 시 UI 메시지 변경
                        if is_issue_only:
                            st.error(f"**🚨 독립 이슈 마커:** {pickup_time_str} 발생")
                        else:
                            st.success(f"**🟢 탑승:** {pickup_time_str} ➡️ **🏁 하차:** {dropoff_time_str} {issue_times_str}")

                        g_start_lat = float(spotlight_raw['latitude'].iloc[0])
                        g_start_lng = float(spotlight_raw['longitude'].iloc[0])
                        
                        coords_html = "<div style='font-size: 13px; color: #475569; margin-top: 10px; margin-bottom: 15px; padding: 15px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; line-height: 1.8;'>"
                        
                        if is_issue_only:
                            coords_html += f"<div>🚨 <b>이슈발생 좌표:</b> <a href='https://www.google.com/maps/search/?api=1&query={g_start_lat},{g_start_lng}' target='_blank' style='color:#ef4444; text-decoration:none;'><b>{g_start_lat:.6f}, {g_start_lng:.6f}</b></a> <span style='color:#94a3b8; font-size:11px;'>(클릭 시 구글 맵 이동)</span></div>"
                        else:
                            coords_html += f"<div>🟢 <b>탑승지 좌표:</b> <a href='https://www.google.com/maps/search/?api=1&query={g_start_lat},{g_start_lng}' target='_blank' style='color:#2563eb; text-decoration:none;'><b>{g_start_lat:.6f}, {g_start_lng:.6f}</b></a> <span style='color:#94a3b8; font-size:11px;'>(클릭 시 구글 맵 이동)</span></div>"
                            if pd.notna(spotlight_raw['end_latitude'].iloc[0]):
                                g_end_lat = float(spotlight_raw['end_latitude'].iloc[0])
                                g_end_lng = float(spotlight_raw['end_longitude'].iloc[0])
                                coords_html += f"<div>🏁 <b>하차지 좌표:</b> <a href='https://www.google.com/maps/search/?api=1&query={g_end_lat},{g_end_lng}' target='_blank' style='color:#2563eb; text-decoration:none;'><b>{g_end_lat:.6f}, {g_end_lng:.6f}</b></a></div>"
                        
                        processed_issues = []
                        if isinstance(issue_pings, list) and len(issue_pings) > 0:
                            coords_html += "<hr style='margin: 8px 0; border: 0; border-top: 1px dashed #cbd5e1;'>"
                            for idx, ping in enumerate(issue_pings):
                                if isinstance(ping, dict) and 'lat' in ping and 'lng' in ping:
                                    lat, lng, ping_time = float(ping['lat']), float(ping['lng']), ping.get('time')
                                    
                                    if manual_issue: memo_text = f"{manual_issue} (admin)"
                                    else:
                                        m_val = "내용 미기입"
                                        if isinstance(report_memos, dict): m_val = report_memos.get(str(ping_time), report_memos.get(int(ping_time) if pd.notna(ping_time) else 0, "내용 미기입"))
                                        elif isinstance(report_memos, list): m_val = " / ".join([str(x) for x in report_memos])
                                        memo_text = f"{m_val} (app)" if m_val != "내용 미기입" else m_val
                                    
                                    coords_html += f"<div style='margin-top: 6px;'>🚨 <b>{idx+1}번 이슈 좌표:</b> <a href='https://www.google.com/maps/search/?api=1&query={lat},{lng}' target='_blank' style='color:#ef4444; text-decoration:none;'><b>{lat:.6f}, {lng:.6f}</b></a> <span style='margin-left: 8px; font-size: 13px; color: #b91c1c; font-weight: 600; background: #fee2e2; padding: 2px 8px; border-radius: 6px;'>📝 {memo_text}</span></div>"
                                    processed_issues.append({"longitude": lng, "latitude": lat, "tooltip_text": f"🚨 {idx+1}번 이슈: {memo_text}"})
                        
                        coords_html += "</div>"
                        st.markdown(coords_html, unsafe_allow_html=True)
                        
                        if isinstance(issue_pings, list) and len(issue_pings) > 0:
                            st.markdown("<div style='margin-top:15px; margin-bottom:5px; font-weight:700; color:#ef4444;'>📸 이슈 위치 (Google 로드뷰)</div>", unsafe_allow_html=True)
                            cols = st.columns(min(len(issue_pings), 4))
                            for idx, ping in enumerate(issue_pings[:4]):
                                if isinstance(ping, dict) and 'lat' in ping and 'lng' in ping:
                                    with cols[idx]: st.link_button(f"👁️ {idx+1}번 이슈 로드뷰", f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={ping['lat']},{ping['lng']}", use_container_width=True)

                        spotlight_safe = spotlight_raw[['longitude', 'latitude', 'end_longitude', 'end_latitude', 'call_id', 'carNumber']].copy().reset_index(drop=True)
                        spotlight_safe['tooltip_text'] = spotlight_safe['call_id']
                        
                        spot_start = pdk.Layer("ScatterplotLayer", data=spotlight_safe, get_position='[longitude, latitude]', get_fill_color=[16, 185, 129, 255] if not is_issue_only else [239, 68, 68, 255], get_radius=15, radius_min_pixels=3, pickable=True)
                        spotlight_layers.append(spot_start)
                        
                        if not is_issue_only:
                            spot_end = pdk.Layer("ScatterplotLayer", data=spotlight_safe, get_position='[end_longitude, end_latitude]', get_fill_color=[59, 130, 246, 255], get_radius=15, radius_min_pixels=3, pickable=True)
                            spotlight_layers.append(spot_end)
                        
                        if not path_df.empty and not is_issue_only:
                            spot_path_df = path_df[path_df['call_id'] == selected_call].reset_index(drop=True)
                            if not spot_path_df.empty:
                                spot_path_df['tooltip_text'] = spot_path_df['call_id']
                                spot_path = pdk.Layer("PathLayer", data=spot_path_df, get_color=[249, 115, 22, 220], width_min_pixels=4, get_path="path", pickable=True)
                                spotlight_layers.append(spot_path)

                        issue_df = pd.DataFrame(processed_issues)
                        if not issue_df.empty:
                            spot_issue = pdk.Layer("ScatterplotLayer", data=issue_df, get_position='[longitude, latitude]', get_fill_color=[239, 68, 68, 255], get_radius=15, radius_min_pixels=3, pickable=True)
                            spotlight_layers.append(spot_issue)

                        st.pydeck_chart(pdk.Deck(map_style=FREE_MAP_STYLE, initial_view_state=pdk.ViewState(latitude=g_start_lat, longitude=g_start_lng, zoom=14, pitch=0, bearing=0), layers=spotlight_layers, tooltip={"text": "{tooltip_text}"}))
