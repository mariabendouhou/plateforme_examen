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
MAX_SALLES_PER_SLOT = 35  # لضمان التوزيع على 45 حصة (15 يوم * 3 أوقات)

st.set_page_config(page_title="🎓 Examens Pro v2.0", layout="wide")

# ==============================
# 2. DATABASE CONNECTION
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
# 3. CORE LOGIC: OPTIMIZED GENERATION
# ==============================
def generer_edt_optimiser():
    conn = get_connection()
    if not conn: return 0, 0
    cur = conn.cursor(dictionary=True)

    try:
        # أ) تنظيف الـ EDT القديم
        cur.execute("DELETE FROM examens")
        conn.commit()

        # ب) جلب البيانات (فقط الموديلات اللي فيها طلبة فعليين)
        cur.execute("""
            SELECT m.id AS module_id, m.nom AS module, f.id AS formation_id, 
                   COUNT(i.etudiant_id) AS nb_etudiants
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

        # ج) تحضير "كناش" الطلبة (Pre-filtering لـ 13,000 طالب)
        etudiants_par_module = {}
        cur.execute("SELECT module_id, etudiant_id FROM inscriptions")
        for row in cur.fetchall():
            if row['module_id'] not in etudiants_par_module:
                etudiants_par_module[row['module_id']] = []
            etudiants_par_module[row['module_id']].append(row['etudiant_id'])

        # د) أدوات المراقبة
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # هـ) ميموار القيود (Constraints Memory)
        formation_jour = {}
        salle_horaire = {}
        etudiant_jour = {}
        salles_occupees_par_slot = {}
        prof_exams_count = {p["id"]: 0 for p in profs}

        success, failed = 0, 0
        exams_to_insert = []

        # و) الدورة الرئيسية (The Algorithm)
        for i, module in enumerate(modules):
            # تحديث الواجهة
            progress = (i + 1) / len(modules)
            progress_bar.progress(progress)
            status_text.text(f"⏳ برمجة: {module['module']} ({i+1}/{len(modules)})")

            planifie = False
            
            # توزيع الأولوية دورياً (Round Robin) باش ما يتعمرش غير الصباح
            start_idx = i % len(CRENEAUX)
            creneaux_priority = CRENEAUX[start_idx:] + CRENEAUX[:start_idx]

            for jour_offset in range((DATE_FIN - DATE_DEBUT).days + 1):
                if planifie: break
                date_exam = (DATE_DEBUT + timedelta(days=jour_offset)).date()

                # شرط: امتحان واحد للتخصص في اليوم
                if (module["formation_id"], date_exam) in formation_jour: continue

                for heure in creneaux_priority:
                    if planifie: break
                    dt = datetime.strptime(f"{date_exam} {heure}", "%Y-%m-%d %H:%M")

                    # شرط التوزيع المتوازن (Max 35 salles/slot)
                    if salles_occupees_par_slot.get(dt, 0) >= MAX_SALLES_PER_SLOT: continue

                    # فحص تضارب الطلبة (للمسجلين فقط)
                    etuds = etudiants_par_module.get(module["module_id"], [])
                    if any((e_id, date_exam) in etudiant_jour for e_id in etuds): continue

                    for salle in salles:
                        if salle["capacite"] < module["nb_etudiants"]: continue
                        if (salle["id"], dt) in salle_horaire: continue

                        # اختيار أستاذ (الأقل شغلاً)
                        prof_trouve = sorted(profs, key=lambda p: prof_exams_count[p["id"]])[0]

                        # سجل البيانات في القائمة (Batch)
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

        # ز) تسجيل كل شيء دفعة واحدة (Fast Insert)
        if exams_to_insert:
            cur.executemany("""
                INSERT INTO examens (module_id, prof_id, lieu_id, date_heure, duree_minutes)
                VALUES (%s, %s, %s, %s, %s)
            """, exams_to_insert)
            conn.commit()

        progress_bar.empty()
        status_text.empty()
        return success, failed

    except Exception as e:
        st.error(f"❌ Erreur: {e}")
        return 0, 0
    finally:
        conn.close()

# ==============================
# 4. MAIN INTERFACE
# ==============================
def main():
    st.title("🎓 إدارة امتحانات الجامعة - 1500 موديل")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🚀 توليد الجدول الزمني", use_container_width=True):
            with st.spinner("جاري الحساب..."):
                s, f = generer_edt_optimiser()
                st.success(f"✅ اكتملت العملية: {s} موديل مبرمج، {f} لم يجدوا مكاناً.")
                st.balloons()

    # عرض النتائج
    st.divider()
    conn = get_connection()
    if conn:
        df = pd.read_sql("""
            SELECT e.date_heure, m.nom as module, l.nom as salle, p.nom as prof
            FROM examens e 
            JOIN modules m ON e.module_id = m.id
            JOIN lieux_examen l ON e.lieu_id = l.id
            JOIN professeurs p ON e.prof_id = p.id
            ORDER BY e.date_heure
        """, conn)
        st.dataframe(df, use_container_width=True)
        conn.close()

if __name__ == "__main__":
    main()
