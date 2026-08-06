import streamlit as st

def parse_bool(val):
    if isinstance(val, bool):
        return val
    if val is None:
        return False
    
    val_str = str(val).strip().lower()
    if val_str in ['nan', 'none', 'null', '']:
        return False
    return val_str in ['true', '1', 't', 'y', 'yes']

def get_premium_header(icon, title, color="#4F46E5"):
    return f"""
    <div style='display: flex; align-items: center; margin-top: 10px; margin-bottom: 20px; padding-bottom: 12px; border-bottom: 2px solid #f1f5f9;'>
        <div style='background: linear-gradient(135deg, {color}cc 0%, {color} 100%); color: white; width: 38px; height: 38px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 20px; margin-right: 12px; box-shadow: 0 4px 10px {color}40;'>
            {icon}
        </div>
        <h3 style='margin: 0; color: #0f172a; font-size: 22px; font-weight: 800; letter-spacing: -0.5px;'>
            {title}
        </h3>
    </div>
    """
