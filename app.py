import streamlit as st
import pandas as pd
import io

# 1. CONFIG
st.set_page_config(page_title="MCH Logic Debugger", layout="wide", page_icon="🩸")
st.markdown("""<style>.print-only{display:none} .report-box{border:2px solid #333;padding:15px;}</style>""", unsafe_allow_html=True)

# 2. DEFINITIONS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
# Homozygous Only Exclusion for these:
DOSAGE_SYSTEMS = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"] 
# Pairs for dosage check
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# 3. STATE
if 'db_panel' not in st.session_state:
    st.session_state.db_panel = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'db_screen' not in st.session_state:
    st.session_state.db_screen = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])

# 4. LOGIC FUNCTIONS
def parse_paste(txt, limit=11):
    # This parser is designed for Excel Copy-Paste
    try:
        lines = txt.strip().split('\n')
        data = []
        for i, line in enumerate(lines):
            if i >= limit: break
            parts = line.split('\t')
            # Extract just numbers/symbols
            vals = []
            for p in parts:
                clean = str(p).lower().strip()
                v = 1 if any(x in clean for x in ['1','+','w','pos','yes']) else 0
                vals.append(v)
            
            # Auto-Trim: Assume user copied exactly 26 columns of Antigens. 
            # If not, take last 26 or pad 0
            if len(vals) > 26: vals = vals[-26:]
            while len(vals) < 26: vals.append(0)
            
            row = {"ID": f"Row {i+1}"}
            for idx, ag in enumerate(AGS):
                row[ag] = vals[idx]
            data.append(row)
        return pd.DataFrame(data)
    except Exception as e: return None

# DEBUGGED EXCLUSION FUNCTION
def can_exclude(ag, cell_pheno):
    # Rule: Check if Antigen Present
    if cell_pheno.get(ag, 0) == 0:
        return False, "Ag Absent" # Cannot exclude if Ag not on cell
    
    # Dosage Rule: 
    if ag in DOSAGE_SYSTEMS:
        partner = PAIRS.get(ag)
        if partner and cell_pheno.get(partner, 0) == 1:
            return False, "Heterozygous (Dosage)" # Do not exclude
            
    return True, "Valid Rule Out" # Homozygous or Single -> EXCLUDE

# 5. UI
with st.sidebar:
    st.title("Menu")
    mode = st.radio("Go:", ["Workstation", "Admin"])
    if st.button("RESET"): st.rerun()

if mode == "Admin":
    st.title("Admin Data Paste")
    if st.text_input("Pwd",type="password")=="admin123":
        t1,t2 = st.tabs(["Panel 11","Screen"])
        with t1:
            txt1 = st.text_area("Paste Panel 11 (26 cols numbers only)", height=200)
            if st.button("Load Panel"):
                df = parse_paste(txt1, 11)
                if df is not None: st.session_state.db_panel=df; st.success("Loaded!")
            st.data_editor(st.session_state.db_panel, hide_index=True)
            
        with t2:
            txt2 = st.text_area("Paste Screen 3", height=150)
            if st.button("Load Screen"):
                df = parse_paste(txt2, 3)
                if df is not None: st.session_state.db_screen=df; st.success("Loaded!")
            st.data_editor(st.session_state.db_screen, hide_index=True)

else:
    st.markdown("<h2 style='text-align:center'>Tabuk Serology - Debug Mode</h2>", unsafe_allow_html=True)
    c1,c2,c3,c4=st.columns(4)
    nm=c1.text_input("Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    
    st.divider()
    
    with st.form("inputs"):
        L, R = st.columns([1, 2])
        with L:
            st.write("Controls")
            ac=st.radio("Auto", ["Neg","Pos"])
            si=st.selectbox("S-I",["Neg","Pos"]); sii=st.selectbox("S-II",["Neg","Pos"]); siii=st.selectbox("S-III",["Neg","Pos"])
            ins=[si,sii,siii]
        with R:
            st.write("Panel")
            cols=st.columns(6)
            inp=[]
            for i in range(11):
                inp.append(cols[i%6].selectbox(f"{i+1}",["Neg","Pos","w+"]))
        
        run = st.form_submit_button("🔎 Analyze with Debugger")
    
    if run:
        if ac=="Pos": st.error("DAT Required")
        else:
            # 1. Map Inputs to 0/1
            pmap = [1 if x!="Neg" else 0 for x in inp]
            smap = [1 if x!="Neg" else 0 for x in ins]
            
            # 2. THE DETECTIVE LOGIC (Why is it ruled out?)
            ruled_out_log = {} # {"D": "Excluded by Cell 3"}
            survivors = []
            
            p11 = st.session_state.db_panel.to_dict('records')
            
            # Exclusion Loop (Verbose)
            for ag in AGS:
                is_out = False
                reason = ""
                
                # Check Panel
                for i, res in enumerate(pmap):
                    if res == 0: # User said Neg
                        cell_pheno = p11[i]
                        status, msg = can_exclude(ag, cell_pheno)
                        if status:
                            is_out = True
                            reason = f"Ruled out by Panel Cell {i+1} ({msg})"
                            break # Killed it
                
                # If not out yet, check screen (skip for brevity logic here)
                
                if is_out:
                    ruled_out_log[ag] = reason
                else:
                    survivors.append(ag)
            
            # 3. Matching Loop (Verbose)
            final_matches = []
            mismatch_log = []
            
            for cand in survivors:
                mis_list = []
                # Check where User said POS, does Cell have Ag?
                for i, res in enumerate(pmap):
                    if res == 1: # User Pos
                        has_ag = p11[i].get(cand, 0)
                        if has_ag == 0:
                            mis_list.append(f"Cell {i+1}")
                
                if mis_list:
                    mismatch_log.append(f"Anti-{cand}: Rejected (User +ve on {mis_list} but Cell is Ag-negative)")
                else:
                    final_matches.append(cand)

            # 4. REPORTING THE CRIME SCENE
            if not final_matches:
                st.error("❌ No Matches Found!")
                
                with st.expander("🕵️ Why did the analysis fail?", expanded=True):
                    st.write("#### 1. Why antibodies were ruled out (Crossed out):")
                    # Show reason for common antibodies D, C, c, E, e, K
                    common = ["D", "C", "c", "E", "e", "K"]
                    for c in common:
                        if c in ruled_out_log:
                            st.warning(f"**Anti-{c}**: {ruled_out_log[c]}")
                        else:
                            st.success(f"**Anti-{c}**: Survived exclusion.")

                    if mismatch_log:
                        st.write("#### 2. Survivors that failed Pattern Match:")
                        for log in mismatch_log:
                            st.error(log)
            
            else:
                st.success(f"✅ Identified: {', '.join(final_matches)}")
                with st.expander("See Exclusion Details"):
                    st.json(ruled_out_log)

            # Raw Data check
            if st.checkbox("Show Table Data Used for Calculation"):
                st.dataframe(st.session_state.db_panel)
