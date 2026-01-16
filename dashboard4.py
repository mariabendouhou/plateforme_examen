import streamlit as st
import mysql.connector
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==============================
# CONFIGURATION
# ==============================


DUREE_EXAM = 90
CRENEAUX = ["08:30", "11:00", "14:00"]
DATE_DEBUT = datetime(2026, 1, 10)
DATE_FIN = datetime(2026, 1,25)

# Configuration des rôles
ROLES = {
    "vice_doyen": "Vice-Doyen / Doyen",
    "admin_exams": "Administrateur Examens",
    "chef_dept": "Chef de Département",
    "enseignant": "Enseignant",
    "etudiant": "Étudiant"
}

st.set_page_config(
    page_title="🎓 Plateforme Examens Pro",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==============================
# STYLES CSS PROFESSIONNELS
# ==============================
st.markdown("""
    <style>
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 15px;
        color: white;
        text-align: center;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .role-badge {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        padding: 8px 20px;
        border-radius: 20px;
        color: white;
        font-weight: bold;
        display: inline-block;
        margin: 10px 0;
    }
    .metric-card {
        background: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        border-left: 4px solid #667eea;
    }
    .success-alert {
        background-color: #d4edda;
        border-left: 5px solid #28a745;
        padding: 15px;
        border-radius: 5px;
        margin: 10px 0;
    }
    .warning-alert {
        background-color: #fff3cd;
        border-left: 5px solid #ffc107;
        padding: 15px;
        border-radius: 5px;
        margin: 10px 0;
    }
    .danger-alert {
        background-color: #f8d7da;
        border-left: 5px solid #dc3545;
        padding: 15px;
        border-radius: 5px;
        margin: 10px 0;
    }
    .dept-section {
        background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        padding: 15px;
        border-radius: 10px;
        color: white;
        font-weight: bold;
        margin: 15px 0;
    }
    .kpi-container {
        background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
        padding: 20px;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .validation-box {
        background: #e3f2fd;
        border: 2px solid #2196f3;
        padding: 20px;
        border-radius: 10px;
        margin: 15px 0;
    }
    </style>
""", unsafe_allow_html=True)

# ==============================
# GESTION SESSION & AUTHENTIFICATION
# ==============================
if "user_role" not in st.session_state:
    st.session_state.user_role = None
if "user_name" not in st.session_state:
    st.session_state.user_name = None
if "user_dept_id" not in st.session_state:
    st.session_state.user_dept_id = None

# ==============================
# CONNEXION BDD
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
    except mysql.connector.Error as err:
        st.error(f"❌ Erreur de connexion : {err}")
        return None

def execute_query(query, params=None):
    conn = get_connection()
    if not conn:
        return pd.DataFrame()
    try:
        # Convert numpy types to Python native types
        if params:
            import numpy as np
            params = tuple(
                int(p) if isinstance(p, np.integer) else 
                float(p) if isinstance(p, np.floating) else 
                p for p in params
            )
        df = pd.read_sql(query, conn, params=params)
        return df
    except Exception as e:
        st.error(f"❌ Erreur requête : {e}")
        return pd.DataFrame()
    finally:
        conn.close()

# ==============================
# REQUÊTES DONNÉES
# ==============================
@st.cache_data(ttl=30)
def get_departements():
    query = "SELECT id, nom FROM departements ORDER BY nom"
    return execute_query(query)

@st.cache_data(ttl=30)
def get_formations_by_dept(dept_id=None):
    if dept_id:
        query = "SELECT id, nom FROM formations WHERE dept_id = %s ORDER BY nom"
        return execute_query(query, params=(dept_id,))
    query = "SELECT id, nom, dept_id FROM formations ORDER BY nom"
    return execute_query(query)

@st.cache_data(ttl=30)
def get_professeurs_by_dept(dept_id=None):
    if dept_id:
        query = "SELECT id, nom FROM professeurs WHERE dept_id = %s ORDER BY nom"
        return execute_query(query, params=(dept_id,))
    query = "SELECT id, nom, dept_id FROM professeurs ORDER BY nom"
    return execute_query(query)

@st.cache_data(ttl=30)
def load_edt_complete(dept_id=None, formation_id=None, date_filter=None):
    query = """
    SELECT 
        e.id,
        m.nom AS module,
        f.nom AS formation,
        f.id AS formation_id,
        p.nom AS professeur,
        l.nom AS salle,
        l.capacite,
        e.date_heure,
        e.duree_minutes,
        COUNT(DISTINCT i.etudiant_id) AS nb_inscrits,
        d.nom AS departement,
        d.id AS departement_id
    FROM examens e
    JOIN modules m ON m.id = e.module_id
    JOIN formations f ON f.id = m.formation_id
    JOIN departements d ON d.id = f.dept_id
    JOIN professeurs p ON p.id = e.prof_id
    JOIN lieux_examen l ON l.id = e.lieu_id
    LEFT JOIN inscriptions i ON i.module_id = e.module_id
    WHERE 1=1
    """
    params = []
    if dept_id:
        query += " AND d.id = %s"
        params.append(dept_id)
    if formation_id:
        query += " AND f.id = %s"
        params.append(formation_id)
    if date_filter:
        query += " AND DATE(e.date_heure) = %s"
        params.append(date_filter)
    
    query += """
    GROUP BY e.id, m.nom, f.nom, f.id, p.nom, l.nom, l.capacite, 
             e.date_heure, e.duree_minutes, d.nom, d.id
    ORDER BY e.date_heure, f.nom
    """
    return execute_query(query, params=tuple(params) if params else None)

@st.cache_data(ttl=30)
def get_kpis_globaux():
    """KPIs pour Vue Stratégique"""
    queries = {
        "nb_examens": "SELECT COUNT(*) as val FROM examens",
        "nb_salles": "SELECT COUNT(*) as val FROM lieux_examen",
        "nb_profs": "SELECT COUNT(*) as val FROM professeurs",
        "nb_etudiants": "SELECT COUNT(*) as val FROM etudiants",
        "nb_conflits_salles": """
            SELECT COUNT(*) as val FROM (
                SELECT e1.id FROM examens e1
                JOIN examens e2 ON e1.lieu_id = e2.lieu_id AND e1.id < e2.id
                WHERE e1.date_heure < DATE_ADD(e2.date_heure, INTERVAL e2.duree_minutes MINUTE)
                AND DATE_ADD(e1.date_heure, INTERVAL e1.duree_minutes MINUTE) > e2.date_heure
            ) conflicts
        """,
        "nb_conflits_profs": """
            SELECT COUNT(*) as val FROM (
                SELECT e1.id FROM examens e1
                JOIN examens e2 ON e1.prof_id = e2.prof_id AND e1.id < e2.id
                WHERE e1.date_heure < DATE_ADD(e2.date_heure, INTERVAL e2.duree_minutes MINUTE)
                AND DATE_ADD(e1.date_heure, INTERVAL e1.duree_minutes MINUTE) > e2.date_heure
            ) conflicts
        """
    }
    
    kpis = {}
    for key, query in queries.items():
        result = execute_query(query)
        kpis[key] = float(result.iloc[0, 0]) if not result.empty else 0
    return kpis

@st.cache_data(ttl=30)
def get_occupation_globale():
    query = """
    SELECT 
        l.nom AS salle,
        l.capacite,
        COUNT(e.id) AS nb_examens,
        ROUND(AVG(CASE 
            WHEN ins.nb_inscrits IS NOT NULL 
            THEN (ins.nb_inscrits / l.capacite) * 100 
            ELSE 0 
        END), 1) AS taux_occupation
    FROM lieux_examen l
    LEFT JOIN examens e ON e.lieu_id = l.id
    LEFT JOIN (
        SELECT module_id, COUNT(etudiant_id) AS nb_inscrits
        FROM inscriptions
        GROUP BY module_id
    ) ins ON ins.module_id = e.module_id
    GROUP BY l.id, l.nom, l.capacite
    ORDER BY taux_occupation DESC
    """
    return execute_query(query)

@st.cache_data(ttl=30)
def get_stats_par_departement():
    query = """
    SELECT 
        d.nom AS departement,
        COUNT(DISTINCT e.id) AS nb_examens,
        COUNT(DISTINCT m.id) AS nb_modules,
        COUNT(DISTINCT f.id) AS nb_formations
    FROM departements d
    LEFT JOIN formations f ON f.dept_id = d.id
    LEFT JOIN modules m ON m.formation_id = f.id
    LEFT JOIN examens e ON e.module_id = m.id
    GROUP BY d.id, d.nom
    ORDER BY nb_examens DESC
    """
    return execute_query(query)

@st.cache_data(ttl=30)
def get_heures_enseignement():
    query = """
    SELECT 
        p.nom AS professeur,
        d.nom AS departement,
        COUNT(e.id) AS nb_examens,
        SUM(e.duree_minutes) / 60 AS heures_totales,
        COUNT(s.examen_id) AS nb_surveillances
    FROM professeurs p
    JOIN departements d ON d.id = p.dept_id
    LEFT JOIN examens e ON e.prof_id = p.id
    LEFT JOIN surveillances s ON s.prof_id = p.id
    GROUP BY p.id, p.nom, d.nom
    ORDER BY heures_totales DESC
    """
    return execute_query(query)

@st.cache_data(ttl=30)
def get_edt_etudiant(formation_id):
    """Retourne les examens d'une formation (examens auquel les étudiants sont inscrits)"""
    query = """
    SELECT DISTINCT
        e.id,
        m.nom AS module,
        f.nom AS formation,
        f.id AS formation_id,
        p.nom AS professeur,
        l.nom AS salle,
        l.capacite,
        e.date_heure,
        e.duree_minutes,
        COUNT(DISTINCT i.etudiant_id) AS nb_inscrits,
        d.nom AS departement,
        d.id AS departement_id
    FROM examens e
    JOIN modules m ON m.id = e.module_id
    JOIN formations f ON f.id = m.formation_id
    JOIN departements d ON d.id = f.dept_id
    JOIN professeurs p ON p.id = e.prof_id
    JOIN lieux_examen l ON l.id = e.lieu_id
    LEFT JOIN inscriptions i ON i.module_id = e.module_id
    WHERE f.id = %s
    GROUP BY e.id, m.nom, f.nom, f.id, p.nom, l.nom, l.capacite, 
             e.date_heure, e.duree_minutes, d.nom, d.id
    ORDER BY e.date_heure, f.nom
    """
    return execute_query(query, params=(formation_id,))

# ==============================
# FONCTIONS MÉTIER
# ==============================
def valider_examen(examen_id, type_validation):
    """Valide un examen (chef ou doyen)"""
    conn = get_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        if type_validation == "chef":
            cur.execute("UPDATE examens SET valide_chef = 1 WHERE id = %s", (examen_id,))
        elif type_validation == "doyen":
            cur.execute("UPDATE examens SET valide_doyen = 1 WHERE id = %s", (examen_id,))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"❌ Erreur validation : {e}")
        return False
    finally:
        conn.close()

def generer_edt_optimiser():
    conn = get_connection()
    if not conn:
        return 0, 0

    cur = conn.cursor(dictionary=True)

    try:
        # Nettoyer l'EDT existant
        cur.execute("DELETE FROM examens")
        conn.commit()

        # Charger modules avec formation, département et promo + nombre d'étudiants
        cur.execute("""
            SELECT 
                m.id AS module_id,
                m.nom AS module,
                f.id AS formation_id,
                f.dept_id AS dept_id,
                COALESCE(MIN(e.promo), 2024) AS promo,
                COUNT(DISTINCT i.etudiant_id) AS nb_etudiants
            FROM modules m
            JOIN formations f ON f.id = m.formation_id
            LEFT JOIN inscriptions i ON i.module_id = m.id
            LEFT JOIN etudiants e ON e.id = i.etudiant_id
            GROUP BY m.id, m.nom, f.id, f.dept_id
            ORDER BY nb_etudiants DESC
        """)
        modules = cur.fetchall()

        # Salles par capacité
        cur.execute("SELECT id, capacite, nom FROM lieux_examen ORDER BY capacite DESC")
        salles = cur.fetchall()

        # Professeurs par département
        cur.execute("SELECT id, dept_id, nom FROM professeurs ORDER BY dept_id")
        profs = cur.fetchall()

        if not modules or not salles or not profs:
            st.error("❌ Données insuffisantes (modules / salles / professeurs)")
            return 0, 0

        success = 0
        failed = 0
        failed_modules = []

        # Mémoire pour contraintes
        formation_jour = {}
        salle_jour_promo_formation = {}
        prof_jour = {}
        etudiant_jour = {}
        salle_horaire = {}
        
        # Compteur global d'examens par professeur pour équité
        prof_exams_count = {prof["id"]: 0 for prof in profs}

        # Charger les étudiants par module
        etudiants_par_module = {}
        for module in modules:
            cur.execute("""
                SELECT etudiant_id 
                FROM inscriptions 
                WHERE module_id = %s
            """, (module["module_id"],))
            etudiants_par_module[module["module_id"]] = [r["etudiant_id"] for r in cur.fetchall()]

        for module in modules:
            planifie = False

            for jour_offset in range((DATE_FIN - DATE_DEBUT).days + 1):
                if planifie:
                    break
                    
                date_exam = (DATE_DEBUT + timedelta(days=jour_offset)).date()

                # 1 examen par formation par jour
                if (module["formation_id"], date_exam) in formation_jour:
                    continue

                for heure in CRENEAUX:
                    if planifie:
                        break
                        
                    dt = datetime.strptime(f"{date_exam} {heure}", "%Y-%m-%d %H:%M")

                    # Vérifier conflits étudiants
                    etudiants_module = etudiants_par_module.get(module["module_id"], [])
                    conflit_etudiant = False
                    for etud_id in etudiants_module:
                        if (etud_id, date_exam) in etudiant_jour:
                            conflit_etudiant = True
                            break
                    
                    if conflit_etudiant:
                        continue

                    for salle in salles:
                        # Capacité suffisante
                        if salle["capacite"] < module["nb_etudiants"]:
                            continue

                        # Salle pour une seule formation/promo par jour
                        salle_key = (salle["id"], date_exam)
                        if salle_key in salle_jour_promo_formation:
                            existing_promo, existing_formation = salle_jour_promo_formation[salle_key]
                            if existing_promo != module["promo"] or existing_formation != module["formation_id"]:
                                continue

                        # Disponibilité horaire
                        if (salle["id"], dt) in salle_horaire:
                            continue

                        # Trouver prof disponible avec distribution équitable
                        prof_trouve = None
                        
                        # Trier les profs par nombre total d'examens (équité globale)
                        profs_tries = sorted(profs, key=lambda p: prof_exams_count[p["id"]])
                        
                        for prof in profs_tries:
                            nb_exams_prof = prof_jour.get((prof["id"], date_exam), 0)
                            if nb_exams_prof < 3:  # Max 3 examens par jour
                                prof_trouve = prof
                                break
                        
                        if not prof_trouve:
                            continue

                        # INSERTION
                        try:
                            cur.execute("""
                                INSERT INTO examens
                                (module_id, prof_id, lieu_id, date_heure, duree_minutes)
                                VALUES (%s, %s, %s, %s, %s)
                            """, (
                                module["module_id"],
                                prof_trouve["id"],
                                salle["id"],
                                dt,
                                DUREE_EXAM
                            ))
                            conn.commit()

                            # Mise à jour contraintes
                            formation_jour[(module["formation_id"], date_exam)] = True
                            salle_jour_promo_formation[salle_key] = (module["promo"], module["formation_id"])
                            prof_jour[(prof_trouve["id"], date_exam)] = nb_exams_prof + 1
                            prof_exams_count[prof_trouve["id"]] += 1  # Mise à jour compteur global
                            salle_horaire[(salle["id"], dt)] = True
                            
                            for etud_id in etudiants_module:
                                etudiant_jour[(etud_id, date_exam)] = True

                            success += 1
                            planifie = True
                            break
                            
                        except mysql.connector.Error:
                            conn.rollback()
                            continue

            if not planifie:
                failed += 1
                failed_modules.append(module["module"])

        # Afficher modules non planifiés
        if failed_modules:
            with st.expander(f"⚠️ Modules non planifiés ({failed})"):
                for mod in failed_modules:
                    st.write(f"- {mod}")

        return success, failed

    except Exception as e:
        conn.rollback()
        st.error(f"❌ Erreur génération EDT : {e}")
        import traceback
        st.error(traceback.format_exc())
        return 0, 0

    finally:
        conn.close()


# ==============================
# PAGE DE CONNEXION
# ==============================
def page_connexion():
    st.markdown('<div class="main-header"><h1>🎓 Plateforme de Gestion des Examens</h1><p>Connexion Multi-Acteurs</p></div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("### 🔐 Authentification")
        
        role = st.selectbox("Sélectionnez votre rôle", list(ROLES.values()))
        
        if role == ROLES["vice_doyen"]:
            if st.button("Se connecter", use_container_width=True):
                st.session_state.user_role = "vice_doyen"
                st.session_state.user_name = "Vice-Doyen"
                st.rerun()
        
        elif role == ROLES["admin_exams"]:
            if st.button("Se connecter", use_container_width=True):
                st.session_state.user_role = "admin_exams"
                st.session_state.user_name = "Administrateur Examens"
                st.rerun()
        
        elif role == ROLES["chef_dept"]:
            depts = get_departements()
            if not depts.empty:
                dept_nom = st.selectbox("Département", depts["nom"].tolist())
                
                if st.button("Se connecter", use_container_width=True):
                    dept_id = depts[depts["nom"] == dept_nom]["id"].values[0]
                    st.session_state.user_role = "chef_dept"
                    st.session_state.user_name = f"Chef {dept_nom}"
                    st.session_state.user_dept_id = dept_id
                    st.rerun()
# ==============================
# DASHBOARD VICE-DOYEN / DOYEN
# ==============================
def dashboard_vice_doyen():
    st.markdown(f'<div class="main-header"><h1>📊 Vue Stratégique Globale</h1><div class="role-badge">{ROLES["vice_doyen"]} - {st.session_state.user_name}</div></div>', unsafe_allow_html=True)
    
    # KPIs Globaux
    kpis = get_kpis_globaux()
    
    st.markdown("### 📈 Indicateurs Clés de Performance")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("📘 Examens Planifiés", int(kpis["nb_examens"]))
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("🏫 Salles Utilisées", int(kpis["nb_salles"]))
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col3:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("👨‍🏫 Professeurs", int(kpis["nb_profs"]))
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col4:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("🎓 Étudiants", int(kpis["nb_etudiants"]))
        st.markdown('</div>', unsafe_allow_html=True)
    
    st.divider()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown('<div class="kpi-container">', unsafe_allow_html=True)
        st.metric("⚠️ Conflits Salles", int(kpis["nb_conflits_salles"]))
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        st.markdown('<div class="kpi-container">', unsafe_allow_html=True)
        st.metric("⚠️ Conflits Professeurs", int(kpis["nb_conflits_profs"]))
        st.markdown('</div>', unsafe_allow_html=True)
    
    st.divider()
    
    # Occupation globale des salles
    st.markdown("### 🏢 Occupation Globale des Amphithéâtres et Salles")
    occupation = get_occupation_globale()
    
    if not occupation.empty:
        fig = px.bar(
            occupation,
            x="salle",
            y="taux_occupation",
            color="taux_occupation",
            color_continuous_scale="RdYlGn_r",
            labels={"salle": "Salle", "taux_occupation": "Taux d'occupation (%)"},
            title="Taux d'occupation par salle"
        )
        st.plotly_chart(fig, use_container_width=True)
        
        st.dataframe(occupation, use_container_width=True)
    
    st.divider()
    
    # Stats par département
    st.markdown("### 📊 Statistiques par Département")
    stats_dept = get_stats_par_departement()
    
    if not stats_dept.empty:
        fig = px.bar(
            stats_dept,
            x="departement",
            y="nb_examens",
            title="Examens par Département",
            labels={"departement": "Département", "nb_examens": "Nombre d'examens"}
        )
        st.plotly_chart(fig, use_container_width=True)
        
        st.dataframe(stats_dept, use_container_width=True)
    
    st.divider()
    
    # Heures d'enseignement
    st.markdown("### ⏰ Charge de Travail Professeurs")
    heures = get_heures_enseignement()
    
    if not heures.empty:
        fig = px.scatter(
            heures,
            x="nb_examens",
            y="heures_totales",
            size="nb_surveillances",
            color="departement",
            hover_name="professeur",
            labels={"nb_examens": "Nombre d'examens", "heures_totales": "Heures totales"}
        )
        st.plotly_chart(fig, use_container_width=True)
        
        st.dataframe(heures, use_container_width=True)
    
    st.divider()
    
    # Validation finale EDT
    st.markdown("### ✅ Validation Finale de l'Emploi du Temps")
    st.markdown('<div class="validation-box">', unsafe_allow_html=True)
    
    edt = load_edt_complete()
    
    if not edt.empty:
        st.info(f"📋 Total: {len(edt)} examens planifiés")
    else:
        st.info("Aucun examen planifié")
    
    st.markdown('</div>', unsafe_allow_html=True)

# ==============================
# DASHBOARD ADMIN EXAMENS
# ==============================
def dashboard_admin_examens():
    st.markdown(f'<div class="main-header"><h1>🛠️ Administration et Planification</h1><div class="role-badge">{ROLES["admin_exams"]} - {st.session_state.user_name}</div></div>', unsafe_allow_html=True)
    
    # Actions principales
    st.markdown("### ⚙️ Actions de Planification")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🚀 Générer EDT Complet", use_container_width=True):
            with st.spinner("⏳ Génération en cours (tous les modules)..."):
                import time
                start = time.time()
                success, failed = generer_edt_optimiser()
                elapsed = time.time() - start
                
                total = success + failed
                taux = (success / total * 100) if total > 0 else 0
                
                st.success(f"✅ {success}/{total} modules planifiés ({taux:.1f}%) en {elapsed:.2f}s")
                
                if failed > 0:
                    st.warning(f"⚠️ {failed} modules non planifiés (capacité insuffisante)")
                else:
                    st.balloons()
                    
                st.cache_data.clear()
                st.rerun()
    
    with col2:
        if st.button("🔄 Actualiser Données", use_container_width=True):
            st.cache_data.clear()
            st.success("✅ Données actualisées")
            st.rerun()
    
    with col3:
        if st.button("🗑️ Réinitialiser EDT", use_container_width=True):
            conn = get_connection()
            if conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM examens")
                conn.commit()
                conn.close()
                st.success("✅ EDT réinitialisé")
                st.cache_data.clear()
                st.rerun()
    
    st.divider()
    
    # Vue complète EDT
    st.markdown("### 📋 Emploi du Temps Complet")
    
    edt = load_edt_complete()
    
    if not edt.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Examens", len(edt))
        col2.metric("Départements", edt["departement"].nunique())
        col3.metric("Formations", edt["formation"].nunique())
        
        st.dataframe(edt, use_container_width=True, height=400)
        
        csv = edt.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Télécharger CSV", csv, "edt_complet.csv", "text/csv")
    else:
        st.info("Aucun examen planifié")

# ==============================
# DASHBOARD CHEF DE DÉPARTEMENT
# ==============================
def dashboard_chef_dept():
    st.markdown(f'<div class="main-header"><h1>📂 Gestion Département</h1><div class="role-badge">{ROLES["chef_dept"]} - {st.session_state.user_name}</div></div>', unsafe_allow_html=True)
    
    dept_id = st.session_state.user_dept_id
    
    # EDT du département
    edt_dept = load_edt_complete(dept_id=dept_id)
    
    if not edt_dept.empty:
        st.markdown(f'<div class="dept-section">🏢 Département : {edt_dept.iloc[0]["departement"]}</div>', unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("📘 Examens", len(edt_dept))
        col2.metric("📚 Formations", edt_dept["formation"].nunique())
        col3.metric("✅ Planifiés", len(edt_dept))
        
        st.divider()
        
        # Validation par formation
        st.markdown("### ✅ Examens par Formation")
        
        for formation in edt_dept["formation"].unique():
            st.markdown(f"#### 📚 {formation}")
            
            formation_data = edt_dept[edt_dept["formation"] == formation]
            
            for _, exam in formation_data.iterrows():
                col1, col2, col3 = st.columns([3, 1, 1])
                
                with col1:
                    st.write(f"**{exam['module']}**")
                    st.write(f"📅 {exam['date_heure']} | 🏫 {exam['salle']} | 👨‍🏫 {exam['professeur']}")
                
                with col2:
                    st.write(f"👥 {int(exam['nb_inscrits'])} étudiants")
                
                st.divider()
        
        st.divider()
        
        # Statistiques département
        st.markdown("### 📊 Statistiques du Département")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Examens par jour
            edt_dept["date"] = pd.to_datetime(edt_dept["date_heure"]).dt.date
            exams_par_jour = edt_dept.groupby("date").size().reset_index(name="nb_examens")
            
            fig = px.bar(exams_par_jour, x="date", y="nb_examens", title="Examens par jour")
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Examens par formation
            exams_par_formation = edt_dept.groupby("formation").size().reset_index(name="nb_examens")
            
            fig = px.pie(exams_par_formation, values="nb_examens", names="formation", title="Répartition par formation")
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Aucun examen planifié pour ce département")

# ==============================
# DASHBOARD ENSEIGNANT
# ==============================
def dashboard_enseignant():
    st.markdown(f'<div class="main-header"><h1>👨‍🏫 Mon Planning</h1><div class="role-badge">{ROLES["enseignant"]} - {st.session_state.user_name}</div></div>', unsafe_allow_html=True)
    
    # Récupérer les examens de l'enseignant
    query = """
    SELECT 
        e.id,
        m.nom AS module,
        f.nom AS formation,
        d.nom AS departement,
        l.nom AS salle,
        e.date_heure,
        COUNT(DISTINCT i.etudiant_id) AS nb_inscrits
    FROM examens e
    JOIN modules m ON m.id = e.module_id
    JOIN formations f ON f.id = m.formation_id
    JOIN departements d ON d.id = f.dept_id
    JOIN lieux_examen l ON l.id = e.lieu_id
    JOIN professeurs p ON p.id = e.prof_id
    LEFT JOIN inscriptions i ON i.module_id = m.id
    WHERE p.nom = %s
    GROUP BY e.id, m.nom, f.nom, d.nom, l.nom, e.date_heure
    ORDER BY e.date_heure
    """
    
    mes_examens = execute_query(query, params=(st.session_state.user_name,))
    
    if not mes_examens.empty:
        st.metric("📘 Mes Examens à Surveiller", len(mes_examens))
        
        st.divider()
        
        st.markdown("### 📅 Planning de Mes Examens")
        
        for _, exam in mes_examens.iterrows():
            st.markdown(f'<div class="validation-box">', unsafe_allow_html=True)
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.markdown(f"#### 📖 {exam['module']}")
                st.write(f"**Formation:** {exam['formation']} ({exam['departement']})")
                st.write(f"📅 **Date:** {exam['date_heure']}")
                st.write(f"🏫 **Salle:** {exam['salle']}")
            
            with col2:
                st.metric("👥 Inscrits", int(exam['nb_inscrits']))
            
            st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("Aucun examen planifié pour le moment")

# ==============================
# DASHBOARD ÉTUDIANT
# ==============================
def dashboard_etudiant():
    st.markdown(f'<div class="main-header"><h1>🎓 Mon Calendrier d\'Examens</h1><div class="role-badge">{ROLES["etudiant"]} - {st.session_state.user_name}</div></div>', unsafe_allow_html=True)
    
    # Filtres
    formations = get_formations_by_dept(st.session_state.user_dept_id)
    
    if not formations.empty:
        formation_selected = st.selectbox("Ma Formation", formations["nom"].tolist())
        formation_id = formations[formations["nom"] == formation_selected]["id"].values[0]
        
        st.divider()
        
        # Examens de la formation
        edt_formation = get_edt_etudiant(formation_id)
        
        if not edt_formation.empty:
            st.metric("📘 Mes Examens", len(edt_formation))
            
            st.divider()
            
            st.markdown("### 📅 Calendrier de Mes Examens")
            
            edt_formation["date"] = pd.to_datetime(edt_formation["date_heure"]).dt.date
            
            for date in sorted(edt_formation["date"].unique()):
                st.markdown(f"#### 📅 {date.strftime('%A %d %B %Y')}")
                
                examens_jour = edt_formation[edt_formation["date"] == date]
                
                for _, exam in examens_jour.iterrows():
                    st.markdown(f'<div class="validation-box">', unsafe_allow_html=True)
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.write(f"**⏰ {exam['date_heure'].strftime('%H:%M')}**")
                        st.write(f"📖 {exam['module']}")
                    
                    with col2:
                        st.write(f"🏫 Salle: {exam['salle']}")
                        st.write(f"👨‍🏫 Prof: {exam['professeur']}")
                    
                    with col3:
                        st.write(f"👥 {int(exam['nb_inscrits'])} étudiants")
                        st.write(f"⏱️ Durée: {int(exam['duree_minutes'])} min")
                    
                    st.markdown('</div>', unsafe_allow_html=True)
                
                st.divider()
            
            # Export personnel
            csv = edt_formation.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Télécharger Mon Calendrier", csv, "mes_examens.csv", "text/csv")
        else:
            st.info("Aucun examen planifié pour cette formation")
    else:
        st.warning("Aucune formation disponible")

# ==============================
# NAVIGATION PRINCIPALE
# ==============================
def main():
    # Sidebar
    with st.sidebar:
        if st.session_state.user_role:
            st.markdown(f"### 👤 Connecté en tant que:")
            st.markdown(f'<div class="role-badge">{ROLES[st.session_state.user_role]}</div>', unsafe_allow_html=True)
            st.write(f"**{st.session_state.user_name}**")
            
            st.divider()
            
            if st.button("🚪 Déconnexion", use_container_width=True):
                st.session_state.user_role = None
                st.session_state.user_name = None
                st.session_state.user_dept_id = None
                st.rerun()
    
    # Routing selon le rôle
    if not st.session_state.user_role:
        page_connexion()
    elif st.session_state.user_role == "vice_doyen":
        dashboard_vice_doyen()
    elif st.session_state.user_role == "admin_exams":
        dashboard_admin_examens()
    elif st.session_state.user_role == "chef_dept":
        dashboard_chef_dept()
    elif st.session_state.user_role == "enseignant":
        dashboard_enseignant()
    elif st.session_state.user_role == "etudiant":
        dashboard_etudiant()

if __name__ == "__main__":
    main()


