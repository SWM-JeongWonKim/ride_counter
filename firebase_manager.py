import firebase_admin
from firebase_admin import credentials, firestore
import streamlit as st
import time
import os
import datetime

def init_firebase():
    KST = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(KST)
    
    switch_time = datetime.datetime(2026, 7, 30, 6, 0, 0, tzinfo=KST)
    
    if now < switch_time:
        target_secret = "firebase"
        app_name = "legacy_db"
    else:
        target_secret = "firebase_new"
        app_name = "new_db"

    try:
        app = firebase_admin.get_app(app_name)
    except ValueError:
        firebase_credentials = dict(st.secrets[target_secret])
        app = firebase_admin.initialize_app(credentials.Certificate(firebase_credentials), name=app_name)
        
    return firestore.client(app=app)

def get_latest_update_time():
    try:
        doc = init_firebase().collection('system').document('status').get()
        if doc.exists:
            return doc.to_dict().get('last_updated', 0)
    except Exception as e:
        print(f"Firestore get() error: {e}")
    return 0

@st.cache_resource(ttl=60)
def fetch_collection(col_name, last_updated_time):
    try:
        return {doc.id: doc.to_dict() for doc in init_firebase().collection(col_name).stream()}
    except Exception as e:
        print(f"Firestore stream() error: {e}")
        return {}

def load_data(col_name):
    return fetch_collection(col_name, get_latest_update_time())

def trigger_db_update():
    try:
        init_firebase().collection('system').document('status').set({'last_updated': time.time()})
    except Exception as e:
        pass

def force_sync_from_firebase():
    st.cache_resource.clear()
    trigger_db_update()
    return True, "데이터 전체 동기화 완료"

def sync_only_new_data(force_full=False):
    if force_full:
        st.cache_resource.clear()
    trigger_db_update()
    return True

def db_set(col_name, doc_id, data):
    init_firebase().collection(col_name).document(doc_id).set(data)
    col_data = load_data(col_name)
    col_data[doc_id] = data

def db_update(col_name, doc_id, updates):
    init_firebase().collection(col_name).document(doc_id).update(updates)
    col_data = load_data(col_name)
    if doc_id in col_data:
        col_data[doc_id].update(updates)

def db_delete(col_name, doc_id):
    init_firebase().collection(col_name).document(doc_id).delete()
    col_data = load_data(col_name)
    if doc_id in col_data:
        del col_data[doc_id]

def delete_driving_log(doc_id): 
    db_update('driving_logs', doc_id, {'is_deleted': True})

def update_driving_log(doc_id, updates): 
    db_update('driving_logs', doc_id, updates)

def delete_ride_log(doc_id): 
    db_update('ride_logs', doc_id, {'is_deleted': True})

def update_master_data(cars, drivers):
    db_update('settings', 'master_data', {'cars': cars, 'drivers': drivers, 'last_updated': time.time()})
    return True

def update_user_permissions(uid, dash, admin, driver, support):
    db_update('users', uid, {
        'can_view_dashboard': dash, 
        'is_admin': admin, 
        'is_driver': driver, 
        'is_support': support
    })

def apply_draft_schedules(draft_dict, s_dt, e_dt):
    db = init_firebase()
    batch = db.batch()
    col_data = load_data('schedules')
    
    updates_count = 0
    for (d, n), t in draft_dict.items():
        doc_id = next((k for k, v in col_data.items() if str(v.get('date', '')).startswith(d) and v.get('name') == n), None)
        
        if t == 'DELETE':
            if doc_id:
                batch.delete(db.collection('schedules').document(doc_id))
                del col_data[doc_id]
                updates_count += 1
        else:
            if doc_id:
                batch.update(db.collection('schedules').document(doc_id), {'type': t, 'updated_at': int(time.time())})
                col_data[doc_id]['type'] = t
                col_data[doc_id]['updated_at'] = int(time.time())
                updates_count += 1
            else:
                new_doc_id = f"{d}_{n}"
                new_ref = db.collection('schedules').document(new_doc_id)
                new_data = {'date': f"{d}T00:00:00", 'name': n, 'type': t, 'updated_at': int(time.time())}
                batch.set(new_ref, new_data)
                col_data[new_doc_id] = new_data
                updates_count += 1
                
        if updates_count >= 490:
            batch.commit()
            batch = db.batch()
            updates_count = 0
            
    if updates_count > 0:
        batch.commit()

def authenticate_user(u_id, u_pw):
    users = load_data('users')
    if u_id in users:
        u = users[u_id]
        if str(u.get('password')) == str(u_pw):
            if u.get('is_approved', False):
                return True, u, "로그인 성공"
            return False, None, "승인 대기 중인 계정입니다."
        return False, None, "비밀번호가 일치하지 않습니다."
    return False, None, "등록되지 않은 아이디입니다."

def create_user(user_id, password, role, name, position, shift='주간 (08:00~17:30)', region='상암', is_approved=False):
    if not user_id.strip().endswith("@swm.ai"):
        return False, "아이디는 반드시 @swm.ai 로 끝나는 회사 계정이어야 합니다."
    if user_id.strip() in load_data('users'):
        return False, "이미 존재하는 아이디입니다."
    
    db_set('users', user_id.strip(), {
        'password': password, 
        'role': role, 
        'name': name, 
        'position': position,
        'shift': shift, 
        'region': region, 
        'is_approved': is_approved,
        'can_view_dashboard': False, 
        'is_driver': False, 
        'is_support': False, 
        'is_admin': False,
        'created_at': time.time()
    })
    return True, "가입 신청이 완료되었습니다."

def request_account_change(name, old_id, new_id, new_pw):
    new_doc_ref = init_firebase().collection('account_requests').document()
    db_set('account_requests', new_doc_ref.id, {
        'name': name, 
        'old_id': old_id, 
        'new_id': new_id, 
        'new_pw': new_pw,
        'status': 'pending', 
        'requested_at': time.time()
    })
    return True, "변경 신청이 접수되었습니다."

def approve_account_request(req_id, old_id, new_id, new_pw):
    users = load_data('users')
    if old_id not in users: 
        return False, "기존 계정을 찾을 수 없습니다."
    
    u_data = users[old_id].copy()
    if new_pw: 
        u_data['password'] = new_pw
    
    if new_id and new_id != old_id:
        db_set('users', new_id, u_data)
        db_delete('users', old_id)
    else:
        if new_pw: 
            db_update('users', old_id, {'password': new_pw})
        
    db_update('account_requests', req_id, {'status': 'approved'})
    return True, "요청이 성공적으로 승인되었습니다."

def reject_account_request(req_id):
    db_update('account_requests', req_id, {'status': 'rejected'})
    return True, "요청이 반려되었습니다."

def get_master_data():
    s = load_data('settings')
    if 'master_data' in s:
        return True, s['master_data']
    return False, {}

def get_all_users():
    users = []
    for i, d in load_data('users').items():
        u = {**d, 'id': i, 'user_id': i, 'email': i, '아이디(ID)': i}
        if not u.get('shift') or str(u.get('shift')) == 'None': 
            u['shift'] = '주간 (08:00~17:30)'
        if not u.get('position') or str(u.get('position')) == 'None': 
            u['position'] = '미정'
        if not u.get('created_at'): 
            u['created_at'] = time.time()
        users.append(u)
    return users

def get_ride_logs(): 
    return [{**d, 'id': i, 'doc_id': i} for i, d in load_data('ride_logs').items()]

def get_driving_logs(): 
    return [{**d, 'id': i, 'doc_id': i} for i, d in load_data('driving_logs').items()]

def get_schedules(): 
    return [{**d, 'id': i} for i, d in load_data('schedules').items()]

def get_all_schedules(): 
    return get_schedules()

def get_account_requests(): 
    return [{**d, 'id': i, 'req_id': i} for i, d in load_data('account_requests').items() if d.get('status') == 'pending']

def update_user_approval(user_id, is_approved):
    db_update('users', user_id, {'is_approved': is_approved})
    return True

def delete_user(user_id):
    db_delete('users', user_id)
    return True