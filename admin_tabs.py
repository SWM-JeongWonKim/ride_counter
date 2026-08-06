import streamlit as st

try:
    from admin import admin_users, admin_schedule, admin_fleet, admin_data
except ImportError:
    import admin_users
    import admin_schedule
    import admin_fleet
    import admin_data

def draw_user_management(u_df, m_cars, m_drivers):
    """권한 및 사용자 관리 탭 렌더링"""
    admin_users.draw_user_management(u_df, m_cars, m_drivers)

def draw_schedule_management(clean_df, sched_df, u_df, m_cars, m_drivers, kst_now):
    """배차 및 스케줄 관리 탭 렌더링"""
    admin_schedule.draw_schedule_management(clean_df, sched_df, u_df, m_cars, m_drivers, kst_now)

def draw_fleet_management(m_cars, m_drivers):
    """운영 차량 목록 관리 탭 렌더링"""
    admin_fleet.draw_fleet_management(m_cars, m_drivers)

def draw_data_management(clean_df, df_drive, m_cars, m_drivers, kst_now):
    """운행/탑승 데이터 수정 및 백업 관리 탭 렌더링"""
    admin_data.draw_data_management(clean_df, df_drive, m_cars, m_drivers, kst_now)
