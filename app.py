import streamlit as st
import pandas as pd
from datetime import date
import json
import base64
import requests
from pathlib import Path

# --------------------------------------------------------------------------
# 0) GitHub Save Engine (uses Streamlit Secrets)
# --------------------------------------------------------------------------
def _gh_get_cfg():
    token = st.secrets.get("GITHUB_TOKEN", None)
    repo  = st.secrets.get("GITHUB_REPO", None)  # e.g. "Haitham526/tabuk-blood-bank"
    branch = st.secrets.get("GITHUB_BRANCH", "main")
    return token, repo, branch

def github_upsert_file(path_in_repo: str, content_text: str, commit_message: str):
    token, repo, branch = _gh_get_cfg()
    if not token or not repo:
        raise RuntimeError("Missing Streamlit Secrets: GITHUB_TOKEN / GITHUB_REPO")

    api = f"https://api.github.com/repos/{repo}/contents/{path_in_repo}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}

    sha = None
    r = requests.get(api, headers=headers, params={"ref": branch}, timeout=30)
    if r.status_code == 200:
        sha = r.json().get("sha")
    elif r.status_code != 404:
        raise RuntimeError(f"GitHub GET error {r.status_code}: {r.text}")

    payload = {
        "message": commit_message,
        "content": base64.b64encode(content_text.encode("utf-8")).decode("utf-8"),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    w = requests.put(api, headers=headers, json=payload, timeout=30)
    if w.status_code not in (200, 201):
        raise RuntimeError(f"GitHub PUT error {w.status_code}: {w.text}")

def load_csv_if_exists(local_path: str, default_df: pd.DataFrame) -> pd.DataFrame:
    p = Path(local_path)
    if p.exists():
        try:
            return pd.read_csv(p)
        except Exception:
            return default_df
    return default_df

def load_json_if_exists(local_path: str, default_obj: dict) -> dict:
    p = Path(local_path)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return default_obj
    return default_obj

# --------------------------------------------------------------------------
# 1) PAGE SETUP & CSS
# --------------------------------------------------------------------------
st.set_page_config(page_title="MCH Tabuk - Serology Expert", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print {
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; }
        .print-only { display: block !important; }
        .result-sheet { border: 4px double #8B0000; padding: 25px; font-family: 'Times New Roman'; font-size:14px; }
        .footer-print {
            position: fixed; bottom: 0; width: 100%; text-align: center;
            color: #8B0000; font-weight: bold; border-top: 1px solid #ccc; padding: 10px; font-family: serif;
        }
    }
    .print-only { display: none; }
    .hospital-logo { color: #8B0000; text-align: center; border-bottom: 5px solid #8B0000; padding-bottom: 5px; font-family: 'Arial'; }
    .lot-bar {
        display: flex; justify-content: space-around; background-color: #f1f8e9;
        border: 1px solid #81c784; padding: 8px; border-radius: 5px; margin-bottom: 20px; font-weight: bold; color: #1b5e20;
    }
    .clinical-waiha { background-color: #f8d7da; border-left: 5px solid #dc3545; padding: 15px; margin: 10px 0; color: #721c24; }
    .clinical-alert { background-color: #fff3cd; border: 2px solid #ffca2c; padding: 10px; color: #000; font-weight: bold; margin: 5px 0;}
    .cell-hint { font-size: 0.9em; color: #155724; background: #d4edda; padding: 2px 6px; border-radius: 4px; }
    .dr-signature {
        position: fixed; bottom: 10px; right: 15px;
        background: rgba(255,255,255,0.95);
        padding: 8px 15px; border: 2px solid #8B0000; border-radius: 8px; z-index:99; box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
        text-align: center; font-family: 'Georgia', serif;
    }
    .dr-name { color: #8B0000; font-size: 15px; font-weight: bold; display: block;}
    .dr-title { color: #333; font-size: 11px; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class='dr-signature no-print'>
    <span class='dr-name'>Dr. Haitham Ismail</span>
    <span class='dr-title'>Clinical Hematology/Oncology &<br>BM Transplantation & Transfusion Medicine Consultant</span>
</div>
""", unsafe_allow_html=True)

# --------------------------------------------------------------------------
# 2) CONSTANTS
# --------------------------------------------------------------------------
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}
IGNORED_AGS = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"]
INSIGNIFICANT_AGS = ["Lea", "Lua", "Leb", "P1"]
ENZYME_SENSITIVE = ["Fya","Fyb","M","N","S"]
GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]

# --------------------------------------------------------------------------
# 3) STATE (FIXED NAMES)  ✅ IMPORTANT
# --------------------------------------------------------------------------
default_panel11_df = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
default_screen3_df = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])

if "panel11_df" not in st.session_state:
    st.session_state.panel11_df = load_csv_if_exists("data/p11.csv", default_panel11_df)

if "screen3_df" not in st.session_state:
    st.session_state.screen3_df = load_csv_if_exists("data/p3.csv", default_screen3_df)

default_lots = {"lot_p": "", "lot_s": ""}
lots_obj = load_json_if_exists("data/lots.json", default_lots)

if "lot_p" not in st.session_state:
    st.session_state.lot_p = lots_obj.get("lot_p", "")
if "lot_s" not in st.session_state:
    st.session_state.lot_s = lots_obj.get("lot_s", "")

if "dat_mode" not in st.session_state:
    st.session_state.dat_mode = False
if "ext" not in st.session_state:
    st.session_state.ext = []

# --------------------------------------------------------------------------
# 4) ENGINE
# --------------------------------------------------------------------------
def normalize_grade(val) -> int:
    s = str(val).lower().strip()
    if s in ["0", "neg", "negative", "none"]:
        return 0
    return 1

def grade_to_int(val) -> int:
    s = str(val).strip()
    if s == "Hemolysis":
        return 4
    if s.startswith("+"):
        try:
            return int(s.replace("+",""))
        except:
            return 1
    if s == "0":
        return 0
    return 1

def is_homozygous_row(ph_row: pd.Series, ag: str) -> bool:
    if ag not in DOSAGE:
        return True
    pair = PAIRS.get(ag)
    if not pair:
        return True
    return (ph_row.get(ag,0)==1 and ph_row.get(pair,0)==0)

def get_all_cells_dataset(in_p: dict, in_s: dict, extras: list):
    out = []
    for i in range(1,12):
        out.append({"label": f"Panel #{i}", "react": normalize_grade(in_p[i]), "ph": st.session_state.panel11_df.iloc[i-1]})
    sc_lbls = ["I","II","III"]
    for idx,k in enumerate(sc_lbls):
        out.append({"label": f"Screen {k}", "react": normalize_grade(in_s[k]), "ph": st.session_state.screen3_df.iloc[idx]})
    for ex in extras:
        out.append({"label": f"Selected: {ex.get('id','(no-id)')}", "react": int(ex.get("res",0)), "ph": ex.get("ph",{})})
    return out

def rule_out_candidates(in_p: dict, in_s: dict, extras: list):
    ruled_out = set()
    cells = get_all_cells_dataset(in_p, in_s, extras)
    for c in cells:
        if c["react"] == 0:
            ph = c["ph"]
            for ag in AGS:
                if ag in IGNORED_AGS:
                    continue
                if isinstance(ph, dict):
                    ag_present = ph.get(ag,0)==1
                    homo = True
                    if ag in DOSAGE:
                        pair = PAIRS.get(ag)
                        homo = (ph.get(ag,0)==1 and ph.get(pair,0)==0) if pair else True
                else:
                    ag_present = ph.get(ag,0)==1
                    homo = is_homozygous_row(ph, ag)
                if ag_present and homo:
                    ruled_out.add(ag)
    return ruled_out

def fit_score_for_antigen(ag: str, in_p: dict, in_s: dict, extras: list):
    cells = get_all_cells_dataset(in_p, in_s, extras)
    pos_cells = [c for c in cells if c["react"]==1]
    if not pos_cells:
        return 0.0, 0, 0
    contradictions = 0
    for c in pos_cells:
        ph = c["ph"]
        ag_pos = ph.get(ag,0)==1 if isinstance(ph, dict) else (ph.get(ag,0)==1)
        if not ag_pos:
            contradictions += 1
    total_pos = len(pos_cells)
    fit = (total_pos - contradictions)/max(total_pos,1)
    return fit, total_pos, contradictions

def separate_candidates(in_p: dict, in_s: dict, extras: list):
    ruled_out = rule_out_candidates(in_p, in_s, extras)
    candidates = [ag for ag in AGS if ag not in ruled_out and ag not in IGNORED_AGS]
    resolved = []
    not_excluded = []
    for ag in candidates:
        fit, total_pos, contradictions = fit_score_for_antigen(ag, in_p, in_s, extras)
        if fit == 1.0 and total_pos >= 2:
            resolved.append((ag, fit, total_pos, contradictions))
        else:
            not_excluded.append((ag, fit, total_pos, contradictions))

    resolved.sort(key=lambda x: ((x[0] in INSIGNIFICANT_AGS), x[0]))
    not_excluded.sort(key=lambda x: (-x[1], (x[0] in INSIGNIFICANT_AGS), x[0]))
    return resolved, not_excluded, ruled_out

def check_rule_of_three(ag: str, in_p: dict, in_s: dict, extras: list):
    cells = get_all_cells_dataset(in_p, in_s, extras)
    p = 0; n = 0
    for c in cells:
        ph = c["ph"]
        ag_pos = ph.get(ag,0)==1 if isinstance(ph, dict) else (ph.get(ag,0)==1)
        if c["react"]==1 and ag_pos:
            p += 1
        if c["react"]==0 and (not ag_pos):
            n += 1
    full = (p>=3 and n>=3)
    mod  = (p>=2 and n>=3)
    return full, mod, p, n

def suggest_selected_cells(target_ag: str, conflicts: list):
    suggestions = []

    def cell_ok(ph_row, ag, conflicts_list):
        if ph_row.get(ag,0)!=1:
            return False
        for bad in conflicts_list:
            if ph_row.get(bad,0)==1:
                return False
        return True

    for i in range(11):
        ph = st.session_state.panel11_df.iloc[i]
        if cell_ok(ph, target_ag, conflicts):
            note = "OK"
            if target_ag in DOSAGE:
                note = "Homozygous preferred" if is_homozygous_row(ph, target_ag) else "Heterozygous (dosage caution)"
            suggestions.append((f"Panel #{i+1}", note))

    sc_lbls = ["I","II","III"]
    for i in range(3):
        ph = st.session_state.screen3_df.iloc[i]
        if cell_ok(ph, target_ag, conflicts):
            note = "OK"
            if target_ag in DOSAGE:
                note = "Homozygous preferred" if is_homozygous_row(ph, target_ag) else "Heterozygous (dosage caution)"
            suggestions.append((f"Screen {sc_lbls[i]}", note))

    return suggestions

def detect_high_incidence(in_p: dict, in_s: dict, ac_negative: bool):
    if not ac_negative:
        return False
    all_panel = all(normalize_grade(in_p[i])==1 for i in range(1,12))
    all_screen = all(normalize_grade(in_s[k])==1 for k in ["I","II","III"])
    return all_panel and all_screen

def strength_caution(in_p: dict, in_s: dict):
    grades = []
    for i in range(1,12):
        if normalize_grade(in_p[i])==1:
            grades.append(grade_to_int(in_p[i]))
    for k in ["I","II","III"]:
        if normalize_grade(in_s[k])==1:
            grades.append(grade_to_int(in_s[k]))
    if len(grades) < 2:
        return False
    return (max(grades) - min(grades)) > 2

# --------------------------------------------------------------------------
# 5) SIDEBAR
# --------------------------------------------------------------------------
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Menu", ["Workstation", "Supervisor"], key="nav_menu")
    if st.button("RESET DATA", key="btn_reset"):
        st.session_state.ext = []
        st.session_state.dat_mode = False
        st.rerun()

# --------------------------------------------------------------------------
# 6) SUPERVISOR
# --------------------------------------------------------------------------
if nav == "Supervisor":
    st.title("Config")
    if st.text_input("Password", type="password", key="sup_pass") == "admin123":

        st.subheader("1) Lot Setup (Separate)")
        colA, colB = st.columns(2)
        lp = colA.text_input("ID Panel Lot#", value=st.session_state.lot_p, key="lot_p_in")
        ls = colB.text_input("Screen Panel Lot#", value=st.session_state.lot_s, key="lot_s_in")

        if st.button("Save Lots (Local)", key="save_lots_local"):
            st.session_state.lot_p = lp
            st.session_state.lot_s = ls
            st.success("Saved locally. Now press **Save to GitHub** to publish.")

        st.subheader("2) Grid Data (Copy-Paste)")
        t1, t2 = st.tabs(["Panel (11)", "Screen (3)"])

        def parse_paste(txt, limit=11):
            rows = txt.strip().split('\n')
            data = []
            c = 0
            for line in rows:
                if c >= limit:
                    break
                parts = line.split('\t')
                vals = []
                for p in parts:
                    v = 1 if any(x in str(p).lower() for x in ['+', 'pos', 'w']) else 0
                    vals.append(v)
                if len(vals) > len(AGS):
                    vals = vals[-len(AGS):]
                while len(vals) < len(AGS):
                    vals.append(0)
                d = {"ID": f"C{c+1}" if limit==11 else f"S{c+1}"}
                for i, ag in enumerate(AGS):
                    d[ag] = vals[i]
                data.append(d)
                c += 1
            return pd.DataFrame(data), f"Updated {c} rows."

        with t1:
            p_txt = st.text_area("Paste Panel Numbers", height=150, key="paste_p11")
            if st.button("Update Panel 11", key="upd_p11"):
                d, m = parse_paste(p_txt, 11)
                st.session_state.panel11_df = d
                st.success(m)
            st.dataframe(st.session_state.panel11_df)

        with t2:
            s_txt = st.text_area("Paste Screen Numbers", height=100, key="paste_s3")
            if st.button("Update Screen 3", key="upd_s3"):
                d, m = parse_paste(s_txt, 3)
                d["ID"] = ["SI","SII","SIII"]
                st.session_state.screen3_df = d
                st.success(m)
            st.dataframe(st.session_state.screen3_df)

        st.write("---")
        st.subheader("3) Publish to ALL devices (Save to GitHub)")
        if st.button("💾 Save to GitHub (Commit)", key="save_gh"):
            try:
                lots_json = json.dumps({"lot_p": st.session_state.lot_p, "lot_s": st.session_state.lot_s},
                                       ensure_ascii=False, indent=2)
                github_upsert_file("data/p11.csv", st.session_state.panel11_df.to_csv(index=False), "Update monthly p11 panel")
                github_upsert_file("data/p3.csv",  st.session_state.screen3_df.to_csv(index=False), "Update monthly p3 screen")
                github_upsert_file("data/lots.json", lots_json, "Update monthly lots")
                st.success("✅ Published to GitHub successfully.")
            except Exception as e:
                st.error(f"❌ Save failed: {e}")

# --------------------------------------------------------------------------
# 7) WORKSTATION
# --------------------------------------------------------------------------
else:
    st.markdown("""
    <div class='hospital-logo'>
        <h2>Maternity & Children Hospital - Tabuk</h2>
        <h4 style='color:#555'>Blood Bank Serology Unit</h4>
    </div>
    """, unsafe_allow_html=True)

    lp_txt = st.session_state.lot_p if st.session_state.lot_p else "⚠️ REQUIRED"
    ls_txt = st.session_state.lot_s if st.session_state.lot_s else "⚠️ REQUIRED"
    st.markdown(f"<div class='lot-bar'><span>ID Panel Lot: {lp_txt}</span> | <span>Screen Lot: {ls_txt}</span></div>",
                unsafe_allow_html=True)

    top1, top2, top3, top4 = st.columns(4)
    pt_name = top1.text_input("Name", key="pt_name")
    pt_mrn  = top2.text_input("MRN", key="pt_mrn")
    tech_nm = top3.text_input("Tech", key="tech_nm")
    run_dt  = top4.date_input("Date", value=date.today(), key="run_dt")

    with st.form("main_form", clear_on_submit=False):
        st.write("### Reaction Entry")
        L, R = st.columns([1, 2.5])

        with L:
            st.write("Controls")
            ac_res = st.radio("Auto Control (AC)", ["Negative", "Positive"], key="rx_ac")

            st.write("Screening")
            s_I   = st.selectbox("Scn I", GRADES, key="rx_sI")
            s_II  = st.selectbox("Scn II", GRADES, key="rx_sII")
            s_III = st.selectbox("Scn III", GRADES, key="rx_sIII")

        with R:
            st.write("Panel Reactions")
            g1, g2 = st.columns(2)
            with g1:
                p1 = st.selectbox("1", GRADES, key="rx_p1")
                p2 = st.selectbox("2", GRADES, key="rx_p2")
                p3 = st.selectbox("3", GRADES, key="rx_p3")
                p4 = st.selectbox("4", GRADES, key="rx_p4")
                p5 = st.selectbox("5", GRADES, key="rx_p5")
                p6 = st.selectbox("6", GRADES, key="rx_p6")
            with g2:
                p7  = st.selectbox("7", GRADES, key="rx_p7")
                p8  = st.selectbox("8", GRADES, key="rx_p8")
                p9  = st.selectbox("9", GRADES, key="rx_p9")
                p10 = st.selectbox("10", GRADES, key="rx_p10")
                p11 = st.selectbox("11", GRADES, key="rx_p11")

        run_btn = st.form_submit_button("🚀 Run Analysis", use_container_width=True)

    if run_btn:
        if not st.session_state.lot_p or not st.session_state.lot_s:
            st.error("⛔ Lots not configured by Supervisor.")
        else:
            ac_negative = (ac_res == "Negative")
            st.session_state.dat_mode = (ac_res == "Positive")

            in_p = {1:p1,2:p2,3:p3,4:p4,5:p5,6:p6,7:p7,8:p8,9:p9,10:p10,11:p11}
            in_s = {"I": s_I, "II": s_II, "III": s_III}

            if strength_caution(in_p, in_s):
                st.warning("⚠️ Caution: reaction strength varies >2 grades (possible dosage / mixed antibodies).")

            if detect_high_incidence(in_p, in_s, ac_negative):
                st.markdown("""
                <div class='clinical-alert'>
                ⚠️ <b>High Incidence Antigen suspected</b><br>
                Only shown when ALL panel + ALL screen reactive with NEG AC.
                </div>
                """, unsafe_allow_html=True)
            else:
                resolved, not_excluded, ruled_out = separate_candidates(in_p, in_s, st.session_state.ext)

                st.subheader("Conclusion (Step 1: Rule-out / Rule-in)")
                resolved_list = [x[0] for x in resolved]
                ne_list = [x[0] for x in not_excluded if x[0] not in resolved_list]

                ne_sig = [a for a in ne_list if a not in INSIGNIFICANT_AGS]
                ne_cold = [a for a in ne_list if a in INSIGNIFICANT_AGS]

                if not resolved_list:
                    st.error("No resolved specificity from current data. Proceed with Selected Cells / Enhancement.")
                else:
                    st.success("Resolved (Rule-in supported): " + ", ".join([f"Anti-{a}" for a in resolved_list]))

                if ne_sig or ne_cold:
                    st.markdown("### ⚠️ Not excluded yet (Needs more work — DO NOT confirm now):")
                    if ne_sig:
                        st.write("**Clinically significant possibilities:** " + ", ".join([f"Anti-{a}" for a in ne_sig]))
                    if ne_cold:
                        st.info("Cold/Insignificant not excluded yet: " + ", ".join([f"Anti-{a}" for a in ne_cold]))

                if ne_sig:
                    st.write("---")
                    st.markdown("### 🧪 Suggested Selected Cells (from current inventory)")
                    conflicts = resolved_list.copy()
                    for target in ne_sig:
                        sugg = suggest_selected_cells(target, conflicts)
                        if sugg:
                            st.write(f"**For Anti-{target}:**")
                            for lab, note in sugg[:8]:
                                st.write(f"- {lab}  <span class='cell-hint'>{note}</span>", unsafe_allow_html=True)
                        else:
                            st.write(f"**For Anti-{target}:** No suitable cell in current 11+screen → use another lot / external panel.")

                st.write("---")
                st.subheader("Confirmation (Rule of Three) — Resolved only")
                if not resolved_list:
                    st.info("No resolved antibody yet → do NOT apply Rule of Three.")
                else:
                    for ag in resolved_list:
                        full, mod, p, n = check_rule_of_three(ag, in_p, in_s, st.session_state.ext)
                        if full:
                            st.write(f"✅ **Anti-{ag}**: Full Rule (3+3) met (P:{p} / N:{n})")
                        elif mod:
                            st.write(f"✅ **Anti-{ag}**: Modified Rule (2+3) met (P:{p} / N:{n})")
                        else:
                            st.write(f"⚠️ **Anti-{ag}**: Not confirmed yet (P:{p} / N:{n})")

    # Selected cells (extras)
    with st.expander("➕ Add Selected Cell (From Library)"):
        ex_id = st.text_input("ID", key="ex_id")
        ex_res = st.selectbox("Reaction", GRADES, key="ex_res")
        ag_cols = st.columns(6)
        new_ph = {}
        for i, ag in enumerate(AGS):
            new_ph[ag] = 1 if ag_cols[i%6].checkbox(ag, key=f"ex_{ag}") else 0

        if st.button("Confirm Add", key="btn_add_ex"):
            st.session_state.ext.append({"id": ex_id.strip() if ex_id else "", "res": normalize_grade(ex_res), "ph": new_ph})
            st.success("Added! Re-run Analysis.")

    if st.session_state.ext:
        st.table(pd.DataFrame(st.session_state.ext)[["id","res"]])
