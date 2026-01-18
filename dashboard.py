import streamlit as st
import mysql.connector
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import random

# ==============================
# 1. CONFIGURATION & CONSTANTS
# ==============================
DUREE_EXAM = 90
CRENEAUX = ["08:30", "11:00", "14:00"]
DATE_DEBUT = datetime(2026, 1, 10)
DATE_FIN = datetime(2026, 1, 25)
MAX_SALLES_PER_SLOT = 40 # بما أن عندك 100 قاعة، 40 هو رقم متوازن جداً

ROLES = {
    "vice_doyen": "Vice-Doyen / Doyen",
    "admin_exams": "Administrateur Examens",
    "chef_dept": "Chef de Département",
    "enseignant": "Enseignant",
    "etudiant": "Étudiant"
}

st.set_page_config(page_title="🎓 Plateforme Examens Pro v2.0", layout="wide", initial_sidebar_state="expanded")

# ==============================
# 2. STYLES CSS
# ==============================
st.markdown("""
    <style>
    .main-header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 15px; color: white; text-align: center; margin-bottom: 20px; }
    .role-badge { background: rgba(255,255,255,0.2); padding: 5px 15px; border-radius: 15px; font-size: 0.9em; }
    .metric-card { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-left: 5px solid #667eea; }
    </style>
""", unsafe_allow_html=True)

# ==============================
# 3. DATABASE CONNECTION
# ==============================
def get_connection():
    try:
        return mysql.connector.connect(
            host=st.secrets["mysql"]["host"],
            user=st.secrets["mysql"]["user"],
            password=st.secrets["mysql"]["password"],
            database=st.secrets["mysql"]["database"],
            port=st.secrets["mysql"]["port"]
        )
    except Exception as e:
        st.error(f"❌ Erreur connexion: {e}")
        return None

# ==============================
# 4. CORE ENGINE: THE GENERATOR
# ==============================
def generer_edt_optimiser():
    conn = get_connection()
    if not conn: return 0, 0
    cur = conn.cursor(dictionary=True)

    try:
        # أ) التنظيف
        cur.execute("DELETE FROM examens")
        
        # ب) جلب البيانات الأساسية (فقط الموديلات النشطة)
        cur.execute("""
            SELECT m.id AS module_id, m.nom AS module, f.id AS formation_id, 
                   f.dept_id, COUNT(i.etudiant_id) AS nb_etudiants
            FROM modules m
            JOIN formations f ON f.id = m.formation_id
            INNER JOIN inscriptions i ON i.module_id = m.id
            GROUP BY m.id ORDER BY nb_etudiants DESC
        """)
        modules = cur.fetchall()
        
        cur.execute("SELECT id, capacite, nom FROM lieux_examen ORDER BY capacite DESC")
        salles = cur.fetchall()
        
        cur.execute("SELECT id, nom FROM professeurs")
        profs = cur.fetchall()

        # ج) ميموار الطلبة (لـ 13,000 طالب)
        etudiants_par_module = {}
        cur.execute("SELECT module_id, etudiant_id FROM inscriptions")
        for row in cur.fetchall():
            if row['module_id'] not in etudiants_par_module:
                etudiants_par_module[row['module_id']] = []
            etudiants_par_module[row['module_id']].append(row['etudiant_id'])

        # د) أدوات المراقبة في الواجهة
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # هـ) ميموار القيود
        formation_jour = {}
        salle_horaire = {}
        etudiant_jour = {}
        salles_occupees_par_slot = {}
        prof_exams_count = {p["id"]: 0 for p in profs}
        
        success, failed = 0, 0
        exams_to_insert = []

        # و) الخوارزمية
        for i, module in enumerate(modules):
            progress = (i + 1) / len(modules)
            progress_bar.progress(progress)
            status_text.text(f"⏳ معالجة: {module['module']} ({i+1}/{len(modules)})")

            planifie = False
            # توزيع دوري للأوقات
            start_idx = i % len(CRENEAUX)
            priority_slots = CRENEAUX[start_idx:] + CRENEAUX[:start_idx]

            for jour_offset in range((DATE_FIN - DATE_DEBUT).days + 1):
                if planifie: break
                date_exam = (DATE_DEBUT + timedelta(days=jour_offset)).date()

                if (module["formation_id"], date_exam) in formation_jour: continue

                for heure in priority_slots:
                    if planifie: break
                    dt = datetime.strptime(f"{date_exam} {heure}", "%Y-%m-%d %H:%M")

                    if salles_occupees_par_slot.get(dt, 0) >= MAX_SALLES_PER_SLOT: continue

                    # فحص تضارب الطلبة المسجلين فقط
                    etuds = etudiants_par_module.get(module["module_id"], [])
                    if any((e_id, date_exam) in etudiant_jour for e_id in etuds): continue

                    for salle in salles:
                        if salle["capacite"] < module["nb_etudiants"]: continue
                        if (salle["id"], dt) in salle_horaire: continue

                        # اختيار أستاذ بالعدل
                        prof_trouve = sorted(profs, key=lambda p: prof_exams_count[p["id"]])[0]

                        # إضافة للقائمة
                        exams_to_insert.append((module["module_id"], prof_trouve["id"], salle["id"], dt, DUREE_EXAM))
                        
                        # تحديث الميموار
                        salle_horaire[(salle["id"], dt)] = True
                        formation_jour[(module["formation_id"], date_exam)] = True
                        salles_occupees_par_slot[dt] = salles_occupees_par_slot.get(dt, 0) + 1
                        prof_exams_count[prof_trouve["id"]] += 1
                        for e_id in etuds: etudiant_jour[(e_id, date_exam)] = True
                        
                        planifie = True
                        success += 1
                        break
            
            if not planifie: failed += 1

        # ز) الحفظ النهائي
        if exams_to_insert:
            cur.executemany("INSERT INTO examens (module_id, prof_id, lieu_id, date_heure, duree_minutes) VALUES (%s, %s, %s, %s, %s)", exams_to_insert)
            conn.commit()

        progress_bar.empty()
        status_text.empty()
        return success, failed

    except Exception as e:
        st.error(f"❌ حدث خطأ: {e}")
        return 0, 0
    finally:
        conn.close()

# ==============================
# 5. ADMIN DASHBOARD
# ==============================
def dashboard_admin_examens():
    st.markdown(f'<div class="main-header"><h1>🛠️ إدارة وبرمجة الامتحانات</h1><span class="role-badge">{st.session_state.user_name}</span></div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🚀 توليد الجدول (1500 موديل)", use_container_width=True):
            s, f = generer_edt_optimiser()
            st.success(f"✅ تمت البرمجة: {s} موديل بنجاح | ⚠️ فشل: {f}")
            st.balloons()
            st.cache_data.clear()

    with col2:
        if st.button("🔄 تحديث البيانات", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    with col3:
        if st.button("🗑️ مسح الجدول الحالي", use_container_width=True):
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM examens")
            conn.commit()
            conn.close()
            st.warning("تم مسح الجدول الزمني")
            st.cache_data.clear()
            st.rerun()

    # عرض النتائج
    st.divider()
    conn = get_connection()
    if conn:
        query = """
            SELECT e.date_heure, m.nom as module, f.nom as formation, l.nom as salle, p.nom as prof
            FROM examens e 
            JOIN modules m ON e.module_id = m.id
            JOIN formations f ON m.formation_id = f.id
            JOIN lieux_examen l ON e.lieu_id = l.id
            JOIN professeurs p ON e.prof_id = p.id
            ORDER BY e.date_heure ASC
        """
        df = pd.read_sql(query, conn)
        st.dataframe(df, use_container_width=True, height=500)
        conn.close()

# ==============================
# 6. APP ENTRY POINT
# ==============================
def main():
    if "user_role" not in st.session_state:
        st.session_state.user_role = "admin_exams" # للتجربة فقط، يمكنك إعادة نظام الدخول
        st.session_state.user_name = "مدير الامتحانات"

    if st.session_state.user_role == "admin_exams":
        dashboard_admin_examens()

if __name__ == "__main__":
    main()
