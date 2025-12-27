import streamlit as st
import pandas as pd
from datetime import date

# ==========================================
# 1. SETUP & STYLE
# ==========================================
st.set_page_config(page_title="MCH Tabuk - Serology Expert", layout="wide", page_icon="🏥")

st.markdown("""
<style>
    @media print { 
        .stApp > header, .sidebar, footer, .no-print { display: none !important; } 
        .print-only { display: block !important; }
        .result-sheet { border: 3px solid #b30000; padding: 25px; font-family: 'Times New Roman'; }
        .footer-sig { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 2px solid #ccc; padding: 10px; font-weight:bold;}
    }
    .print-only { display: none; }
    
    .hospital-logo { color: #b30000; text-align: center; border-bottom: 5px solid #b30000; padding-bottom: 5px; font-family: sans-serif; }
    .lot-badge { background-color: #ffebee; color: #b71c1c; padding: 5px 10px; border-radius: 5px; font-weight: bold; margin-bottom: 20px;}
    
    /* Logic Status Boxes */
    .logic-pass { background-color: #e8f5e9; border-left: 5px solid #2e7d32; padding: 10px; color: #1b5e20; }
    .logic-d-mask { background-color: #e3f2fd; border-left: 5px solid #1565c0; padding: 10px; color: #0d47a1; margin-bottom: 5px; }
    .logic-c-warn { background-color: #fff8e1; border-left: 5px solid #ff6f00; padding: 10px; color: #bf360c; font-weight: bold; }
    .logic-critical { background-color: #ffebee; border-left: 5px solid #c62828; padding: 10px; color: #b71c1c; }
    
    .signature-badge { 
        position: fixed; bottom: 10px; right: 15px; background: rgba(255,255,255,0.95); 
        padding: 8px 15px; border: 2px solid #e0e0e0; border-radius: 10px; z-index:99; 
        font-family: serif; color: #8B0000;
    }
    div[data-testid="stDataEditor"] table { width: 100% !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("""<div class='signature-badge no-print'>Dr. Haitham Ismail<br>Clinical Hematology/Oncology &<br>BM Transplantation & Transfusion Consultant</div>""", unsafe_allow_html=True)

# 2. DEFINITIONS & RULES
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# ** قائمة التجاهل (Ignore List) **
# البرنامج هيحسبهم بس هيخفيهم من النتيجة النهائية عشان ميشوشرش على الفني
IGNORED_AGS = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"] 

# Correct Grades
GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]

# 3. STATE (Memory Stability)
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'lot' not in st.session_state: st.session_state.lot = "Not Set"

# 4. LOGIC ENGINE
def normalize_grade(val):
    s = str(val).lower().strip()
    return 0 if s in ["0", "neg"] else 1

def parse_paste(txt, limit=11):
    try:
        lines = txt.strip().split('\n')
        data = []
        c = 0
        for line in lines:
            if c >= limit: break
            parts = line.split('\t')
            row_v = []
            for p in parts:
                v_clean = str(p).lower().strip()
                val = 1 if any(x in v_clean for x in ['+', '1', 'pos', 'w']) else 0
                row_v.append(val)
            if len(row_v)>26: row_v=row_v[-26:]
            while len(row_v)<26: row_v.append(0)
            
            d_row = {"ID": f"C{c+1}" if limit==11 else f"S{c}"}
            for i, ag in enumerate(AGS): d_row[ag] = row_v[i]
            data.append(d_row)
            c+=1
        return pd.DataFrame(data), f"Updated {c} rows."
    except Exception as e: return None, str(e)

def get_ruled_out(panel, inputs, screen, inputs_screen):
    out = set()
    # Panel Check
    for i in range(1, 12):
        score = normalize_grade(inputs[i])
        if score == 0:
            ph = panel.iloc[i-1]
            for ag in AGS:
                if ph.get(ag, 0) == 1:
                    is_safe = True
                    if ag in DOSAGE:
                        partner = PAIRS.get(ag)
                        if partner and ph.get(partner, 0) == 1: is_safe = False 
                    if is_safe: out.add(ag)
    # Screen Check
    idx_map = {"I":0, "II":1, "III":2}
    for k in ["I", "II", "III"]:
        score = normalize_grade(inputs_screen[k])
        if score == 0:
            ph = screen.iloc[idx_map[k]]
            for ag in AGS:
                if ag not in out:
                    if ph.get(ag, 0) == 1:
                        is_safe = True
                        if ag in DOSAGE:
                            partner = PAIRS.get(ag)
                            if partner and ph.get(partner, 0) == 1: is_safe=False
                        if is_safe: out.add(ag)
    return out

# 5. UI SIDEBAR
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("System Mode", ["Workstation", "Supervisor"])
    if st.button("RESET SYSTEM"): st.rerun()

# --- ADMIN PANEL ---
if nav == "Supervisor":
    st.title("Admin Config")
    if st.text_input("Passcode", type="password") == "admin123":
        st.subheader("1. Active Panel Details")
        st.session_state.lot = st.text_input("Enter Lot Number:", value=st.session_state.lot)
        st.subheader("2. Data Entry")
        t1, t2 = st.tabs(["Panel 11", "Screen 3"])
        with t1:
            txt_p = st.text_area("Paste Excel Numbers (11 rows)", height=150)
            if st.button("Update Panel"):
                df, m = parse_paste(txt_p, 11)
                if df is not None: st.session_state.p11=df; st.success(m)
            st.dataframe(st.session_state.p11.iloc[:, :15])
        with t2:
            txt_s = st.text_area("Paste Screen", height=100)
            if st.button("Update Screen"):
                df, m = parse_paste(txt_s, 3)
                if df is not None: st.session_state.p3=df; st.success(m)
            st.dataframe(st.session_state.p3.iloc[:, :15])

# --- WORKSTATION ---
else:
    # Header
    st.markdown(f"""
    <div class='hospital-logo'>
        <h2>Maternity & Children Hospital - Tabuk</h2>
        <h4 style='color:grey'>Serology Unit | Workstation</h4>
        <div class='lot-badge'>Active Panel Lot: {st.session_state.lot}</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Inputs
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Patient Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    
    # ------------------ STABLE FORM INPUT ------------------
    with st.form("main_form"):
        st.write("### Test Results Entry")
        
        col_ctrl, col_panel = st.columns([1, 2.5])
        
        with col_ctrl:
            st.info("Screening & Auto")
            ac_res = st.radio("Auto Control (AC)", ["Negative", "Positive"])
            
            s1 = st.selectbox("Scn I", GRADES)
            s2 = st.selectbox("Scn II", GRADES)
            s3 = st.selectbox("Scn III", GRADES)
            
        with col_panel:
            st.info("Identification Panel (11 Cells)")
            g1, g2 = st.columns(2)
            with g1:
                c1=st.selectbox("1", GRADES, key="k1")
                c2=st.selectbox("2", GRADES, key="k2")
                c3=st.selectbox("3", GRADES, key="k3")
                c4=st.selectbox("4", GRADES, key="k4")
                c5=st.selectbox("5", GRADES, key="k5")
                c6=st.selectbox("6", GRADES, key="k6")
            with g2:
                c7=st.selectbox("7", GRADES, key="k7")
                c8=st.selectbox("8", GRADES, key="k8")
                c9=st.selectbox("9", GRADES, key="k9")
                c10=st.selectbox("10", GRADES, key="k10")
                c11=st.selectbox("11", GRADES, key="k11")
        
        submit = st.form_submit_button("🚀 Run Analysis")
    
    # ------------------ EXPERT LOGIC ENGINE V201 ------------------
    if submit:
        # Check Critical DAT first
        if ac_res == "Positive":
             st.markdown("""<div class='logic-critical'><h3>🚨 Auto-Control POSITIVE</h3>Analysis Stopped. Perform DAT Workup Below.</div>""", unsafe_allow_html=True)
             st.session_state.show_dat_form = True # Trigger Flag
        
        else:
            st.session_state.show_dat_form = False # Reset Flag
            
            # 1. Map Inputs
            inputs_p = {1:c1, 2:c2, 3:c3, 4:c4, 5:c5, 6:c6, 7:c7, 8:c8, 9:c9, 10:c10, 11:c11}
            inputs_s = {"I":s1, "II":s2, "III":s3}
            pos_cnt = sum([normalize_grade(x) for x in inputs_p.values()])
            
            # 2. Pan-Agglutination
            if pos_cnt == 11:
                st.markdown("""
                <div class='logic-critical'>
                <h3>⚠️ Pan-Reactivity (All Positive + AC Neg)</h3>
                <b>Conclusion:</b> Likely antibody to <b>High Incidence Antigen</b>.<br>
                <b>Protocol:</b> Check patient phenotype. Screen 1st degree relatives. Refer to reference lab.
                </div>
                """, unsafe_allow_html=True)
            else:
                # 3. Allo-Ab Logic
                ruled = get_ruled_out(st.session_state.p11, inputs_p, st.session_state.p3, inputs_s)
                
                # --- [RULE] Filter IGNORED AGS from Display ---
                initial_candidates = [x for x in AGS if x not in ruled]
                display_candidates = [x for x in initial_candidates if x not in IGNORED_AGS]
                
                # --- [RULE] Anti-D Masking Effect ---
                is_anti_D = "D" in display_candidates
                
                final_results = []
                warnings = []
                
                for cand in display_candidates:
                    # Apply Masking Rules
                    if is_anti_D and (cand == "C" or cand == "E"):
                         # Ignore C and E if D is present (masked)
                         continue 
                    final_results.append(cand)

                # Output
                if not final_results:
                    st.error("No common antibodies detected. Possible technical error or low-frequency.")
                else:
                    res_str = ", ".join([f"Anti-{x}" for x in final_results])
                    
                    st.subheader("📝 Investigation Conclusion")
                    st.success(f"✅ **Identity:** {res_str}")
                    
                    # 4. Expert Notes Section
                    if is_anti_D:
                         st.markdown(f"<div class='logic-d-mask'>ℹ️ <b>Note:</b> Anti-D is present. Anti-C and Anti-E are ignored in this list (Likely masked by D).</div>", unsafe_allow_html=True)
                    
                    if "c" in final_results:
                        st.markdown("""
                        <div class='logic-c-warn'>
                        ⚠️ CRITICAL ALERT: Anti-c Detected.<br>
                        Anti-E CANNOT be excluded easily. It must be considered present.<br>
                        👉 <b>Transfuse R1R1 (CDe/CDe) Units [E-Negative / c-Negative].</b>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    if "Cw" not in ruled:
                        st.caption("* Note: Anti-Cw to be considered (Low frequency).")
                        
                    # Standard Action
                    st.info(f"🧬 **Action:** Phenotype patient for {res_str} (Must be Negative).")
                    
                    # 5. Smart Strategy (If Multiple)
                    if len(final_results) > 1:
                        st.write("---")
                        st.markdown("**🔬 Selected Cells Strategy (To Separate Mixture):**")
                        for target in final_results:
                             others = [o for o in final_results if o!=target]
                             st.write(f"- To confirm **Anti-{target}**: Need Cell **{target}+ / {' & '.join([x+'-' for x in others])}**")
    
    # ------------------ DAT MODULE (Reactive outside form) ------------------
    if st.session_state.get('show_dat_form', False):
        st.write("---")
        st.subheader("🧪 Monospecific DAT Workup")
        
        # New independent Form for DAT to prevent refresh loops
        with st.container(border=True):
            d1, d2, d3 = st.columns(3)
            r_igg = d1.selectbox("Anti-IgG", ["Negative", "Positive", "Microscopic +"])
            r_c3d = d2.selectbox("Anti-C3d", ["Negative", "Positive"])
            r_ctrl = d3.selectbox("Control", ["Negative", "Positive"])
            
            if r_ctrl == "Positive":
                st.error("Invalid Test (Control Positive). Check Pan-agglutination/Spontaneous.")
            else:
                is_igg = r_igg != "Negative"
                is_c3d = r_c3d == "Positive"
                
                st.write("#### 👨‍⚕️ Clinical Guide:")
                
                if is_igg and not is_c3d:
                    st.warning("**Diagnostic: Probable WAIHA** (Warm Autoimmune Hemolytic Anemia).")
                    st.markdown("- Auto-antibody may mask Allo-antibodies.\n- **Action:** Perform Adsorption (Auto/Allo) and Elution.")
                
                elif is_c3d and not is_igg:
                    st.info("**Diagnostic: Probable CAS** (Cold Agglutinin Syndrome).")
                    st.markdown("- **Action:** Use Pre-warm Technique. Wash cells with warm saline.")
                
                elif is_igg and is_c3d:
                    st.warning("**Diagnostic: Mixed Type AIHA** (WAIHA + CAS) or severe WAIHA.")
                    st.markdown("- **Action:** Refer to Blood Bank Medical Director.")
                    
                st.markdown("**👉 Refer result to: Blood Bank Physician.**")
