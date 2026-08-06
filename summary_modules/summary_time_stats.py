import streamlit as st
import pandas as pd
import plotly.express as px
from chart_utils import apply_modern_theme

def draw_time_stats_view(cdf, ism):
    if cdf.empty: 
        st.info("💡 해당 조건의 탑승 기록이 없습니다.")
        return
    
    # [최적화] 명시적인 타입 변환을 통해 차트 렌더링 에러(문자열/숫자 혼재) 방지
    cdf = cdf.copy()
    cdf['callCount'] = pd.to_numeric(cdf['callCount'], errors='coerce').fillna(0)
    cdf['revenue'] = pd.to_numeric(cdf['revenue'], errors='coerce').fillna(0)

    vd = cdf[cdf['duration_min'] > 0].copy()
    if not vd.empty:
        td = vd.groupby('time_bracket')['duration_min'].mean().round(1).reset_index()
    else:
        td = pd.DataFrame(columns=['time_bracket', 'duration_min'])

    th = [22, 23, 0, 1, 2, 3, 4]
    bh = pd.DataFrame({'hour': th})
    hr = cdf.groupby(['hour', 'is_manual'])['callCount'].sum().reset_index()
    hm = pd.merge(bh, hr, on='hour', how='left').fillna({'callCount': 0, 'is_manual': '🚕 정상 운행'})
    
    def format_hour(h):
        return f"{h:02d}시~{0 if h==23 else h+1:02d}시"
        
    hm['시간표시'] = hm['hour'].apply(format_hour)
    co = [f"{h:02d}시~{0 if h==23 else h+1:02d}시" for h in th]
    
    fhs = px.bar(
        hm, 
        x='시간표시', 
        y='callCount', 
        color='is_manual', 
        text_auto=True, 
        color_discrete_map={'🚕 정상 운행': '#4F46E5', '📦 일괄 입력': '#F59E0B'}, 
        category_orders={"시간표시": co}
    )
    fhs.update_layout(dragmode=False, xaxis_title="시간", yaxis_title="호출 수 (건)", xaxis_tickangle=0, margin=dict(t=10, b=10))
    fhs.update_traces(textfont=dict(weight="bold"), textposition="outside")
    fhs.update_yaxes(fixedrange=True)

    tbd = cdf.groupby(['time_bracket', 'is_manual'])['callCount'].sum().reset_index()
    fb = px.bar(
        tbd, 
        x='time_bracket', 
        y='callCount', 
        color='is_manual', 
        text_auto=True, 
        color_discrete_map={'🚕 정상 운행': '#10B981', '📦 일괄 입력': '#64748B'}, 
        category_orders={"time_bracket": ["04~22시(4,800원)", "22~23시(5,800원)", "23~02시(6,700원)", "02~04시(5,800원)"]}
    )
    fb.update_layout(dragmode=False, xaxis_title="시간구간", yaxis_title="호출 수 (건)", margin=dict(t=10, b=10))
    fb.update_traces(textfont=dict(weight="bold"), textposition="outside")
    fb.update_yaxes(fixedrange=True)

    pd_df = cdf.groupby('chart_category')['callCount'].sum().reset_index()
    fp = px.pie(pd_df, values='callCount', names='chart_category', hole=0.5)
    fp.update_traces(textposition='inside', textinfo='percent+label', textfont=dict(weight="bold", color="white"), marker=dict(line=dict(color='#ffffff', width=2)))
    fp.update_layout(showlegend=False, margin=dict(t=10, b=10, l=10, r=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", dragmode=False)

    wm = {0: '월요일', 1: '화요일', 2: '수요일', 3: '목요일', 4: '금요일', 5: '토요일', 6: '일요일'}
    cdf['weekday'] = pd.to_datetime(cdf['shift_date']).dt.dayofweek.map(wm)
    wd = cdf.groupby(['weekday', 'is_manual'])['callCount'].sum().reset_index()
    fw = px.bar(
        wd, 
        x='weekday', 
        y='callCount', 
        color='is_manual', 
        text_auto=True, 
        color_discrete_map={'🚕 정상 운행': '#8B5CF6', '📦 일괄 입력': '#CBD5E1'}, 
        category_orders={"weekday": ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']}
    )
    fw.update_layout(dragmode=False, xaxis_title="요일", yaxis_title="호출 수 (건)", margin=dict(t=10, b=10))
    fw.update_traces(textfont=dict(weight="bold"), textposition="outside")
    fw.update_yaxes(fixedrange=True)

    eff_df = cdf.groupby(['weekday', 'hour'])['revenue'].sum().reset_index()
    eff_df['hour_str'] = eff_df['hour'].apply(lambda x: f"{x:02d}시")
    pivot_df = eff_df.pivot(index='weekday', columns='hour_str', values='revenue').fillna(0)

    w_order = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']
    pivot_df = pivot_df.reindex(w_order)

    all_h = [f"{h:02d}시" for h in th]
    for c in pivot_df.columns:
        if c not in all_h: 
            all_h.append(c)
            
    valid_h = [c for c in all_h if c in pivot_df.columns]
    pivot_df = pivot_df.reindex(columns=valid_h).fillna(0)

    fh_map = px.imshow(
        pivot_df, 
        text_auto=True, 
        aspect="auto", 
        color_continuous_scale='YlOrRd', 
        labels=dict(x="시간대", y="요일", color="총 수입금(원)")
    )
    fh_map.update_traces(texttemplate="%{z:,.0f}")
    fh_map.update_layout(xaxis_title="시간대", yaxis_title="요일", margin=dict(t=10, b=10), dragmode=False, coloraxis_showscale=False)

    if ism:
        st.markdown("#### ⏰ 현행 요금 구간별")
        st.plotly_chart(apply_modern_theme(fb), use_container_width=True, config={'displayModeBar': False})
        
        st.divider()
        st.markdown("#### 🌙 야간 호출 패턴")
        st.plotly_chart(apply_modern_theme(fhs), use_container_width=True, config={'displayModeBar': False})
        
        st.divider()
        st.markdown("#### 📅 요일별 호출 추이")
        st.plotly_chart(apply_modern_theme(fw), use_container_width=True, config={'displayModeBar': False})
        
        st.divider()
        st.markdown("#### 💎 요일 및 시간대별 수입 효율")
        st.caption("💡 진한 붉은색일수록 총 수입금이 높습니다.")
        st.plotly_chart(apply_modern_theme(fh_map), use_container_width=True, config={'displayModeBar': False})
        
        st.divider()
        st.markdown("#### ⏱️ 소요시간")
        if not td.empty: 
            st.dataframe(td.rename(columns={'time_bracket': '구간', 'duration_min': '평균(분)'}), hide_index=True, use_container_width=True)
        else: 
            st.caption("기록 없음")
            
        st.divider()
        st.markdown("<h5 style='text-align:center;'>🥧 탑승인원</h5>", unsafe_allow_html=True)
        st.plotly_chart(fp, use_container_width=True, config={'displayModeBar': False})
        
    else:
        r1c1, r1c2 = st.columns([2, 3])
        with r1c1: 
            st.markdown("<div style='font-size:16px;font-weight:800;margin-bottom:10px;'>⏰ 요금 구간별 통계</div>", unsafe_allow_html=True)
            st.plotly_chart(apply_modern_theme(fb), use_container_width=True, config={'displayModeBar': False})
        with r1c2: 
            st.markdown("<div style='font-size:16px;font-weight:800;margin-bottom:10px;'>🌙 시간별 통계</div>", unsafe_allow_html=True)
            st.plotly_chart(apply_modern_theme(fhs), use_container_width=True, config={'displayModeBar': False})
        
        st.divider()
        
        st.markdown("<div style='font-size:16px;font-weight:800;margin-bottom:10px;'>💎 요일 및 시간대별 수입 효율</div>", unsafe_allow_html=True)
        st.caption("💡 진한 붉은색(🔥) 일 수록, 해당 요일과 시간대의 수입이 높았습니다")
        st.plotly_chart(apply_modern_theme(fh_map), use_container_width=True, config={'displayModeBar': False})

        st.divider()
        
        r2c1, r2c2 = st.columns([1.5, 1.5])
        with r2c1:
            st.markdown("<div style='font-size:16px;font-weight:800;margin-bottom:12px;'>⏱️ 구간별 평균 소요시간</div>", unsafe_allow_html=True)
            if not td.empty:
                ht = "<div style='background:white;border-radius:12px;border:1px solid #e2e8f0;padding:5px;'><table style='width:100%;border-collapse:collapse;font-size:13px;text-align:center;'><thead><tr><th style='background:#f8fafc;padding:12px 5px;border-bottom:2px solid #e2e8f0;font-weight:700;'>시간대 구간</th><th style='background:#f8fafc;padding:12px 5px;border-bottom:2px solid #e2e8f0;font-weight:700;'>평균 소요</th></tr></thead><tbody>"
                for _, r in td.iterrows(): 
                    ht += f"<tr><td style='padding:12px 5px;border-bottom:1px solid #f1f5f9;font-weight:600;'>{r['time_bracket']}</td><td style='padding:12px 5px;border-bottom:1px solid #f1f5f9;'><span style='color:#2563EB;font-weight:800;font-size:14px;'>{r['duration_min']}</span> 분</td></tr>"
                st.markdown(ht + "</tbody></table></div>", unsafe_allow_html=True)
            else: 
                st.caption("기록 없음")
                
        with r2c2: 
            st.markdown("<div style='text-align:center;font-size:16px;font-weight:800;margin-bottom:10px;'>🥧 탑승인원 분포</div>", unsafe_allow_html=True)
            st.plotly_chart(fp, use_container_width=True, config={'displayModeBar': False})
        
        st.divider()
        
        st.markdown("<div style='font-size:16px;font-weight:800;margin-bottom:10px;'>📅 요일별 탑승 통계 (한눈에 보기)</div>", unsafe_allow_html=True)
        st.plotly_chart(apply_modern_theme(fw), use_container_width=True, config={'displayModeBar': False})
