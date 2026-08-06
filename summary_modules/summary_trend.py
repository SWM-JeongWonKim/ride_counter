import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from chart_utils import apply_modern_theme

def draw_trend_view(clean_df, df_drive_merged, is_mobile):
    st.markdown("**📈 일일 운행 및 운영 효율 추이**")
    
    if clean_df.empty:
        st.info("💡 해당 기간에 콜 탑승 기록이 없습니다.")
        return

    ride_daily = clean_df.groupby('shift_date').agg(
        callCount=('callCount', 'sum'), 
        carCount=('carNumber', 'nunique'), 
        paxCount=('passengers', 'sum'), 
        revenue=('revenue', 'sum')
    ).reset_index()
    ride_daily['shift_date'] = pd.to_datetime(ride_daily['shift_date'])
    
    if not df_drive_merged.empty and 'shift_date' in df_drive_merged.columns:
        # [최적화] 명시적 데이터 복사 및 타입 처리로 경고 방지
        drive_df_safe = df_drive_merged.copy()
        drive_df_safe['date_dt'] = pd.to_datetime(drive_df_safe['shift_date'], errors='coerce')
        drive_daily = drive_df_safe.groupby('date_dt')['총주행거리(km)'].sum().reset_index()
        merged_daily = pd.merge(ride_daily, drive_daily, left_on='shift_date', right_on='date_dt', how='outer')
        merged_daily['shift_date'] = merged_daily['shift_date'].combine_first(merged_daily['date_dt'])
        merged_daily['shift_date'] = pd.to_datetime(merged_daily['shift_date'])
        merged_daily = merged_daily.fillna(0) 
    else:
        merged_daily = ride_daily.copy()
        merged_daily['총주행거리(km)'] = 0

    valid_dur = clean_df[clean_df['duration_min'] > 0].copy()
    if not valid_dur.empty:
        dur_daily = valid_dur.groupby('shift_date')['duration_min'].mean().round(1).reset_index(name='평균소요분')
        dur_daily['shift_date'] = pd.to_datetime(dur_daily['shift_date'])
        
        df_idle = valid_dur.sort_values(['driverName', 'shift_date', 'dt_obj']).copy()
        df_idle['end_time'] = df_idle['dt_obj'] + pd.to_timedelta(df_idle['duration_min'], unit='m')
        df_idle['next_start'] = df_idle.groupby(['driverName', 'shift_date'])['dt_obj'].shift(-1)
        df_idle['idle_min'] = (df_idle['next_start'] - df_idle['end_time']).dt.total_seconds() / 60
        
        valid_idle = df_idle[(df_idle['idle_min'] >= 0) & (df_idle['idle_min'] <= 180)]
        idle_daily = valid_idle.groupby('shift_date')['idle_min'].mean().round(1).reset_index(name='평균대기분')
        idle_daily['shift_date'] = pd.to_datetime(idle_daily['shift_date'])
        
        merged_daily = pd.merge(merged_daily, dur_daily, on='shift_date', how='left')
        merged_daily = pd.merge(merged_daily, idle_daily, on='shift_date', how='left')
    else:
        merged_daily['평균소요분'] = 0
        merged_daily['평균대기분'] = 0

    merged_daily = merged_daily.fillna(0)
    
    # [최적화] ZeroDivisionError 방지
    merged_daily['carCount'] = merged_daily['carCount'].replace(0, 1)
    merged_daily['calls_per_car'] = (merged_daily['callCount'] / merged_daily['carCount']).round(1)
    merged_daily = merged_daily.sort_values('shift_date')

    plot_df = merged_daily.copy()
    plot_df['x_label'] = plot_df['shift_date'].dt.strftime('%m/%d')
    plot_df['callCount_line'] = np.where(plot_df['callCount'] <= 0, np.nan, plot_df['callCount'])
    plot_df['calls_per_car_line'] = np.where(plot_df['calls_per_car'] <= 0, np.nan, plot_df['calls_per_car'])
    plot_df['평균소요분_line'] = np.where(plot_df['평균소요분'] <= 0, np.nan, plot_df['평균소요분'])
    plot_df['평균대기분_line'] = np.where(plot_df['평균대기분'] <= 0, np.nan, plot_df['평균대기분'])
    
    plot_df['text_dist'] = plot_df['총주행거리(km)'].apply(lambda x: f"{int(x)}" if x > 0 else "")
    plot_df['text_car'] = plot_df['carCount'].apply(lambda x: f"{int(x)}" if x > 0 else "")
    plot_df['text_c1'] = plot_df['callCount'].apply(lambda x: f"{int(x)}" if x > 0 else "")
    plot_df['text_cpc'] = plot_df['calls_per_car'].apply(lambda x: f"{x}" if x > 0 else "")
    plot_df['text_dur'] = plot_df['평균소요분'].apply(lambda x: f" {x} " if x > 0 else "")
    plot_df['text_idle'] = plot_df['평균대기분'].apply(lambda x: f" {x} " if x > 0 else "")

    def get_trendline(y_series):
        y_array = np.array(y_series, dtype=float)
        idx = np.arange(len(y_array))
        mask = ~np.isnan(y_array) & (y_array > 0)
        res = np.full(len(y_array), np.nan)
        if mask.sum() > 1:
            z = np.polyfit(idx[mask], y_array[mask], 1)
            p = np.poly1d(z)
            res[np.where(mask)[0][0]:np.where(mask)[0][-1]+1] = p(idx[np.where(mask)[0][0]:np.where(mask)[0][-1]+1])
        return res

    plot_df['call_trend'] = get_trendline(plot_df['callCount_line'])
    plot_df['cpc_trend'] = get_trendline(plot_df['calls_per_car_line'])
    plot_df['idle_trend'] = get_trendline(plot_df['평균대기분_line'])
    plot_df['dur_trend'] = get_trendline(plot_df['평균소요분_line'])

    if is_mobile:
        st.caption("🚕 [총 호출 수 vs 총 주행거리]")
        fig1 = make_subplots(specs=[[{"secondary_y": True}]])
        fig1.add_trace(go.Bar(x=plot_df['x_label'], y=plot_df['총주행거리(km)'], name="주행거리(km)", marker_color="#3B82F6"), secondary_y=False)
        fig1.add_trace(go.Scatter(x=plot_df['x_label'], y=plot_df['callCount_line'], name="호출건수", mode="lines+markers", line=dict(color="#F97316", width=3)), secondary_y=True)
        fig1.update_layout(plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=1.1), dragmode=False, margin=dict(t=10, b=10))
        st.plotly_chart(fig1, use_container_width=True, config={'displayModeBar': False})
        
        st.caption("📈 [운행 차량 대수 vs 대당 평균 호출]")
        fig2 = make_subplots(specs=[[{"secondary_y": True}]])
        fig2.add_trace(go.Bar(x=plot_df['x_label'], y=plot_df['carCount'], name="운행차량", marker_color="#10B981"), secondary_y=False)
        fig2.add_trace(go.Scatter(x=plot_df['x_label'], y=plot_df['calls_per_car_line'], name="대당호출", mode="lines+markers", line=dict(color="#8B5CF6", width=3)), secondary_y=True)
        fig2.update_layout(plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=1.1), dragmode=False, margin=dict(t=10, b=10))
        st.plotly_chart(fig2, use_container_width=True, config={'displayModeBar': False})
        
        st.caption("⏱️ [공차시간 vs 소요시간]")
        fig3 = make_subplots(specs=[[{"secondary_y": True}]])
        fig3.add_trace(go.Scatter(x=plot_df['x_label'], y=plot_df['평균대기분_line'], name="대기(분)", mode="lines+markers", line=dict(color="#EF4444", width=3)), secondary_y=False)
        fig3.add_trace(go.Scatter(x=plot_df['x_label'], y=plot_df['평균소요분_line'], name="소요(분)", mode="lines+markers", line=dict(color="#2563EB", width=3)), secondary_y=True)
        fig3.update_layout(plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=1.1), dragmode=False, margin=dict(t=10, b=10))
        st.plotly_chart(fig3, use_container_width=True, config={'displayModeBar': False})
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.caption("🚕 [총 호출 수 vs 총 주행거리]")
            max_dist = plot_df['총주행거리(km)'].max() if not plot_df.empty else 100
            max_call = plot_df['callCount'].max() if not plot_df.empty else 10
            
            fig1 = make_subplots(specs=[[{"secondary_y": True}]])
            fig1.add_trace(go.Bar(x=plot_df['x_label'], y=plot_df['총주행거리(km)'], name="주행거리(km)", marker_color="#3B82F6", text=plot_df['text_dist'], textposition="outside", textfont=dict(color="#2563EB", size=12, weight="bold")), secondary_y=False)
            fig1.add_trace(go.Scatter(x=plot_df['x_label'], y=plot_df['callCount_line'], name="호출건수", mode="lines+markers+text", text=plot_df['text_c1'], textposition="top center", textfont=dict(color="#C2410C", size=13, weight="bold"), line=dict(color="#F97316", width=3), marker=dict(size=8), connectgaps=True), secondary_y=True)
            fig1.add_trace(go.Scatter(x=plot_df['x_label'], y=plot_df['call_trend'], name="호출 추세", mode="lines", line=dict(color="#C2410C", width=2, dash="dot"), hoverinfo="skip"), secondary_y=True)
            
            fig1.update_layout(plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=1.1), dragmode=False, margin=dict(t=20, b=20), height=450) 
            fig1.update_yaxes(title_text="주행거리(km)", secondary_y=False, showgrid=False, range=[0, max_dist * 2.5 if max_dist>0 else 10], fixedrange=True)
            fig1.update_yaxes(title_text="호출 건수", secondary_y=True, showgrid=True, gridcolor="#E2E8F0", range=[0, max_call * 1.3 if max_call>0 else 10], fixedrange=True)
            st.plotly_chart(fig1, use_container_width=True, config={'displayModeBar': False})

        with c2:
            st.caption("📈 [운행 차량 대수 vs 대당 평균 호출]")
            max_car = plot_df['carCount'].max() if not plot_df.empty else 10
            max_cpc = plot_df['calls_per_car'].max() if not plot_df.empty else 10
            
            fig2 = make_subplots(specs=[[{"secondary_y": True}]])
            fig2.add_trace(go.Bar(x=plot_df['x_label'], y=plot_df['carCount'], name="운행차량(대)", marker_color="#10B981", text=plot_df['text_car'], textposition="outside", textfont=dict(color="#059669", size=12, weight="bold")), secondary_y=False)
            fig2.add_trace(go.Scatter(x=plot_df['x_label'], y=plot_df['calls_per_car_line'], name="대당호출(건)", mode="lines+markers+text", text=plot_df['text_cpc'], textposition="top center", textfont=dict(color="#312E81", size=13, weight="bold"), line=dict(color="#8B5CF6", width=3), marker=dict(size=8), connectgaps=True), secondary_y=True)
            fig2.add_trace(go.Scatter(x=plot_df['x_label'], y=plot_df['cpc_trend'], name="대당호출 추세", mode="lines", line=dict(color="#6D28D9", width=2, dash="dot"), hoverinfo="skip"), secondary_y=True)
            
            fig2.update_layout(plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=1.1), margin=dict(t=20, b=20), dragmode=False, height=450) 
            fig2.update_yaxes(title_text="운행차량(대)", secondary_y=False, showgrid=False, range=[0, max_car * 2.5 if max_car>0 else 10], fixedrange=True)
            fig2.update_yaxes(title_text="대당 호출(건)", secondary_y=True, showgrid=True, gridcolor="#E2E8F0", range=[0, max_cpc * 1.3 if max_cpc>0 else 10], fixedrange=True)
            st.plotly_chart(fig2, use_container_width=True, config={'displayModeBar': False})

        st.divider()
        
        c3, c4 = st.columns(2)
        with c3:
            st.caption("⏱️ [공차시간 vs 소요시간]")
            st.markdown("<div style='font-size:12px; color:#64748b; margin-top:-10px; margin-bottom:10px;'>💡 <b>공차:</b> 하차 ▶ 다음 탑승  |  <b>소요:</b> 탑승 ▶ 하차</div>", unsafe_allow_html=True)
            max_idle = plot_df['평균대기분'].max() if not plot_df.empty else 10
            max_dur = plot_df['평균소요분'].max() if not plot_df.empty else 10
            
            fig3 = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05)
            fig3.add_trace(go.Scatter(x=plot_df['x_label'], y=plot_df['평균대기분_line'], name="대기시간(분)", mode="lines+markers+text", text=plot_df['text_idle'], textposition="top center", textfont=dict(color="#991B1B", size=13, weight="bold"), line=dict(color="#EF4444", width=3), marker=dict(size=8), connectgaps=True), row=1, col=1)
            fig3.add_trace(go.Scatter(x=plot_df['x_label'], y=plot_df['idle_trend'], name="대기 추세", mode="lines", line=dict(color="#991B1B", width=2, dash="dot"), hoverinfo="skip"), row=1, col=1)
            fig3.add_trace(go.Scatter(x=plot_df['x_label'], y=plot_df['평균소요분_line'], name="소요시간(분)", mode="lines+markers+text", text=plot_df['text_dur'], textposition="top center", textfont=dict(color="#1E3A8A", size=13, weight="bold"), line=dict(color="#2563EB", width=3), marker=dict(size=8), connectgaps=True), row=2, col=1)
            fig3.add_trace(go.Scatter(x=plot_df['x_label'], y=plot_df['dur_trend'], name="소요 추세", mode="lines", line=dict(color="#1E3A8A", width=2, dash="dot"), hoverinfo="skip"), row=2, col=1)
            
            fig3.update_layout(plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=1.12), dragmode=False, margin=dict(t=20, b=20), height=450) 
            fig3.update_yaxes(title_text="대기(분)", showgrid=True, gridcolor="#E2E8F0", range=[0, max_idle * 1.4 if max_idle>0 else 10], fixedrange=True, row=1, col=1)
            fig3.update_yaxes(title_text="소요(분)", showgrid=True, gridcolor="#E2E8F0", range=[0, max_dur * 1.4 if max_dur>0 else 10], fixedrange=True, row=2, col=1)
            fig3.update_xaxes(showgrid=False, fixedrange=True)
            st.plotly_chart(fig3, use_container_width=True, config={'displayModeBar': False})

        with c4:
            st.caption("🚕 [호출 건수 vs 평균 소요시간 추이]")
            max_call_4 = plot_df['callCount'].max() if not plot_df.empty else 10
            max_dur_4 = plot_df['평균소요분'].max() if not plot_df.empty else 10
            
            fig4 = make_subplots(specs=[[{"secondary_y": True}]])
            fig4.add_trace(go.Bar(x=plot_df['x_label'], y=plot_df['callCount'], name="호출건수(건)", text=plot_df['text_c1'], textposition="outside", textfont=dict(color="#7C3AED", size=12, weight="bold"), marker_color="#8B5CF6"), secondary_y=False)
            fig4.add_trace(go.Scatter(x=plot_df['x_label'], y=plot_df['평균소요분_line'], name="소요시간(분)", mode="lines+markers+text", text=plot_df['text_dur'], textposition="top center", textfont=dict(color="#854D0E", size=13, weight="bold"), line=dict(color="#EAB308", width=3), marker=dict(size=8), connectgaps=True), secondary_y=True)
            fig4.add_trace(go.Scatter(x=plot_df['x_label'], y=plot_df['dur_trend'], name="소요 추세", mode="lines", line=dict(color="#A16207", width=2, dash="dot"), hoverinfo="skip"), secondary_y=True)
            
            fig4.update_layout(plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=1.12), dragmode=False, margin=dict(t=20, b=20), height=450) 
            fig4.update_yaxes(title_text="호출건수(건)", secondary_y=False, showgrid=False, range=[0, max_call_4 * 2.5 if max_call_4>0 else 10], fixedrange=True)
            fig4.update_yaxes(title_text="소요시간(분)", secondary_y=True, showgrid=True, gridcolor="#E2E8F0", range=[0, max_dur_4 * 1.3 if max_dur_4>0 else 10], fixedrange=True)
            st.plotly_chart(fig4, use_container_width=True, config={'displayModeBar': False})
