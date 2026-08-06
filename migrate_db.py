import firebase_admin
from firebase_admin import credentials, firestore
import streamlit as st

def main():
    print("🚀 secrets.toml 기반 Firebase DB 이관 작업을 시작합니다...")

    try:
        cred_old = credentials.Certificate(dict(st.secrets["firebase"]))
        app_old = firebase_admin.initialize_app(cred_old, name='migrate_old')
        db_old = firestore.client(app=app_old)
        print("✅ 기존 DB(Legacy) 연결 성공!")

        cred_new = credentials.Certificate(dict(st.secrets["firebase_new"]))
        app_new = firebase_admin.initialize_app(cred_new, name='migrate_new')
        db_new = firestore.client(app=app_new)
        print("✅ 새 DB(New) 연결 성공!")
        
    except Exception as e:
        print(f"❌ DB 연결 실패: {e}")
        return

    collections_to_copy = [
        'system', 'users', 'driving_logs', 'ride_logs', 
        'settings', 'schedules', 'account_requests', 'sw_versions'
    ]

    for col_name in collections_to_copy:
        print(f"\n📂 [{col_name}] 컬렉션 복사 중...")
        docs = db_old.collection(col_name).stream()
        
        count = 0
        batch = db_new.batch()
        
        for doc in docs:
            new_doc_ref = db_new.collection(col_name).document(doc.id)
            batch.set(new_doc_ref, doc.to_dict())
            count += 1
            
            if count % 100 == 0:
                batch.commit()
                batch = db_new.batch()
                print(f"  ⏳ {count}개 복사 완료...")
                
        if count % 100 != 0:
            batch.commit()
            
        print(f"✅ [{col_name}] 총 {count}개 문서 복사 완료!")

    print("\n🎉 데이터 이관 완료")

if __name__ == "__main__":
    main()