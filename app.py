import streamlit as st
import pandas as pd
import json
import base64
import requests
from pathlib import Path
from datetime import date

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
# 1) PAGE
# --------------------------------------------------------------------------
st.set_page_config(page_title="MCH Tabuk - Serology Expert", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    .hospital-logo { color: #8B0000; text-align: center; border-bottom: 5px solid #8B0000; padding-bottom: 5px; font-family: 'Arial'; }
    .lot-bar { display: flex; justify-content: space-around; background-color: #f1f8e9; border: 1px solid #81c784; padding: 8px; border-radius: 5px; margin-bottom: 20px; font-weight: bold; color: #1b5e20; }
    .clinical-alert { background-color: #fff3cd; border: 2px solid #ffca2c; padding: 10px; color: #000; font-weight: bold; margin: 8px 0;}
    .clinical-danger { background-color: #f8d7da; border: 2px solid #dc3545; padding: 10px; color: #721c24; font-weight: bold; margin: 8px 0;}

    .dr-signature {
        position: fixed; bottom: 10px; right: 15px;
        background: rgba(255,255,255,0.95);
        padding: 8px 15px; border: 2px solid #8B0000; border-radius: 8px; z-index:99;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
        text-align: center; font-family: 'Georgia', serif;
    }
    .dr-name { color: #8B0000; font-size: 15px; font-weight: bold; display: block;}
    .dr-title { color: #333; font-size: 11px; }

    .cell-hint { font-size: 0.9em; color: #155724; background: #d4edda; padding: 2px 6px; border-radius: 4px; }
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
GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]

# --------------------------------------------------------------------------
# 3) LOAD TABLES
# --------------------------------------------------------------------------
default_p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
default_p3  = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])

if "p11" not in st.session_state:
    st.session_state.p11 = load_csv_if_exists("data/p11.csv", default_p11)

if "p3" not in st.session_state:
    st.session_state.p3 = load_csv_if_exists("data/p3.csv", default_p3)

default_lots = {"lot_p": "", "lot_s": ""}
lots_obj = load_json_if_exists("data/lots.json", default_lots)

if "lot_p" not in st.session_state:
    st.session_state.lot_p = lots_obj.get("lot_p", "")

if "lot_s" not in st.session_state:
    st.session_state.lot_s = lots_obj.get("lot_s", "")

if "ext" not in st.session_state:
    st.session_state.ext = []

if "dat_mode" not in st.session_state:
    st.session_state.dat_mode = False

# --------------------------------------------------------------------------
# 4) HELPERS
# --------------------------------------------------------------------------
def normalize_grade(val):
    s = str(val).lower().strip()
    return 0 if s in ["0", "neg", "negative"] else 1

def compute_rule_out(i_p, i_s):
    ruled_out = set()

    # Panel: nonreactive cells rule-out
    for idx in range(1, 12):
        if normalize_grade(i_p[idx]) == 0:
            ph = st.session_state.p11.iloc[idx-1]
            for ag in AGS:
                safe = True
                if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1:
                    safe = False
                if ph.get(ag,0)==1 and safe:
                    ruled_out.add(ag)

    # Screen: nonreactive cells rule-out
    smap={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        if normalize_grade(i_s[k]) == 0:
            ph = st.session_state.p3.iloc[smap[k]]
            for ag in AGS:
                safe = True
                if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1:
                    safe = False
                if ph.get(ag,0)==1 and safe:
                    ruled_out.add(ag)

    return ruled_out

def compute_fit(ag, i_p, i_s):
    TP=TN=FP=FN=0

    for idx in range(1,12):
        r = normalize_grade(i_p[idx])
        h = st.session_state.p11.iloc[idx-1].get(ag,0)
        if r==1 and h==1: TP+=1
        elif r==0 and h==0: TN+=1
        elif r==1 and h==0: FP+=1
        elif r==0 and h==1: FN+=1

    smap={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        r = normalize_grade(i_s[k])
        h = st.session_state.p3.iloc[smap[k]].get(ag,0)
        if r==1 and h==1: TP+=1
        elif r==0 and h==0: TN+=1
        elif r==1 and h==0: FP+=1
        elif r==0 and h==1: FN+=1

    total = TP+TN+FP+FN
    fit = (TP+TN)/total if total else 0.0
    return fit, TP, TN, FP, FN

def check_rule_3(ag, i_p, i_s):
    p=n=0
    for idx in range(1,12):
        r=normalize_grade(i_p[idx]); h=st.session_state.p11.iloc[idx-1].get(ag,0)
        if r==1 and h==1: p+=1
        if r==0 and h==0: n+=1

    smap={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        r=normalize_grade(i_s[k]); h=st.session_state.p3.iloc[smap[k]].get(ag,0)
        if r==1 and h==1: p+=1
        if r==0 and h==0: n+=1

    full = (p>=3 and n>=3)
    mod  = (p>=2 and n>=3)
    ok = full or mod
    rule = "Full Rule (3+3)" if full else ("Modified Rule (2+3)" if mod else "Not met")
    return ok, rule, p, n

def high_incidence_suspected(i_p, i_s, ac_negative=True):
    if not ac_negative:
        return False
    p_pos = sum([normalize_grade(i_p[i]) for i in range(1,12)])
    s_pos = sum([normalize_grade(i_s[k]) for k in ["I","II","III"]])
    return (p_pos == 11 and s_pos == 3)

def find_matching_cells_in_inventory(target_ag, conflicts):
    found_list = []
    for i in range(11):
        cell = st.session_state.p11.iloc[i]
        if cell.get(target_ag,0)==1:
            if all(cell.get(bad,0)==0 for bad in conflicts):
                found_list.append(f"Panel #{i+1}")
    sc_lbls = ["I","II","III"]
    for i in range(3):
        cell = st.session_state.p3.iloc[i]
        if cell.get(target_ag,0)==1:
            if all(cell.get(bad,0)==0 for bad in conflicts):
                found_list.append(f"Screen {sc_lbls[i]}")
    return found_list

# --------------------------------------------------------------------------
# 5) SIDEBAR
# --------------------------------------------------------------------------
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Menu", ["Workstation", "Supervisor"])
    if st.button("RESET DATA"):
        st.session_state.ext=[]
        st.session_state.dat_mode=False
        st.rerun()

# --------------------------------------------------------------------------
# 6) SUPERVISOR
# --------------------------------------------------------------------------
if nav == "Supervisor":
    st.title("Config")

    if st.text_input("Password", type="password") == "admin123":
        st.subheader("1. Lot Setup (Separate)")
        colA, colB = st.columns(2)
        lp = colA.text_input("ID Panel Lot#", value=st.session_state.lot_p)
        ls = colB.text_input("Screen Panel Lot#", value=st.session_state.lot_s)

        if st.button("Save Lots (Local)"):
            st.session_state.lot_p = lp
            st.session_state.lot_s = ls
            st.success("Saved locally. Now press **Save to GitHub** to publish to all devices.")

        st.subheader("2. Publish to ALL devices (Save to GitHub)")
        if st.button("💾 Save to GitHub (Commit)"):
            try:
                lots_json = json.dumps({"lot_p": st.session_state.lot_p, "lot_s": st.session_state.lot_s},
                                      ensure_ascii=False, indent=2)
                github_upsert_file("data/p11.csv", st.session_state.p11.to_csv(index=False), "Update monthly p11 panel")
                github_upsert_file("data/p3.csv",  st.session_state.p3.to_csv(index=False),  "Update monthly p3 screen")
                github_upsert_file("data/lots.json", lots_json, "Update monthly lots")
                st.success("✅ Done. Published to GitHub.")
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
    st.markdown(f"""
    <div class='lot-bar'>
        <span>ID Panel Lot: {lp_txt}</span> | <span>Screen Lot: {ls_txt}</span>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    nm = col1.text_input("Name")
    mr = col2.text_input("MRN")
    tech = col3.text_input("Tech")
    dte = col4.date_input("Date", value=date.today())

    # -------------------- FORM (SUBMIT BUTTON GUARANTEED) --------------------
    with st.form("main_form", clear_on_submit=False):
        st.subheader("Reaction Entry")

        left, right = st.columns([1.1, 2.4])

        with left:
            st.write("Controls")
            ac_res = st.radio("Auto Control (AC)", ["Negative", "Positive"], key="ac_res")

            st.write("Screening")
            s1 = st.selectbox("Scn I", GRADES, key="s1")
            s2 = st.selectbox("Scn II", GRADES, key="s2")
            s3 = st.selectbox("Scn III", GRADES, key="s3")

        with right:
            st.write("Panel Reactions")
            g1, g2 = st.columns(2)
            with g1:
                p1  = st.selectbox("1",  GRADES, key="p_1")
                p2  = st.selectbox("2",  GRADES, key="p_2")
                p3  = st.selectbox("3",  GRADES, key="p_3")
                p4  = st.selectbox("4",  GRADES, key="p_4")
                p5  = st.selectbox("5",  GRADES, key="p_5")
                p6  = st.selectbox("6",  GRADES, key="p_6")
            with g2:
                p7  = st.selectbox("7",  GRADES, key="p_7")
                p8  = st.selectbox("8",  GRADES, key="p_8")
                p9  = st.selectbox("9",  GRADES, key="p_9")
                p10 = st.selectbox("10", GRADES, key="p_10")
                p11 = st.selectbox("11", GRADES, key="p_11")

        # ✅ IMPORTANT: submit button INSIDE the form
        run = st.form_submit_button("🚀 Run Analysis")

    # -------------------- ANALYSIS (OUTSIDE FORM) --------------------
    if run:
        if not st.session_state.lot_p or not st.session_state.lot_s:
            st.error("⛔ Action Blocked: Lots not configured by Supervisor.")
        else:
            i_p = {1:p1,2:p2,3:p3,4:p4,5:p5,6:p6,7:p7,8:p8,9:p9,10:p10,11:p11}
            i_s = {"I":s1,"II":s2,"III":s3}

            if ac_res == "Positive":
                st.session_state.dat_mode = True
                st.warning("AC Positive → switch to Monospecific DAT Workup below.")
            else:
                st.session_state.dat_mode = False

                if high_incidence_suspected(i_p, i_s, ac_negative=True):
                    st.markdown(
                        "<div class='clinical-danger'>🛑 <b>Antibody against High-Incidence Antigen suspected.</b><br>"
                        "All Panel & Screen reactive with Negative AC.<br>"
                        "Action: search compatible donors (consider first-degree relatives) / refer to reference lab.</div>",
                        unsafe_allow_html=True
                    )
                else:
                    ruled_out = compute_rule_out(i_p, i_s)
                    candidates = [x for x in AGS if x not in ruled_out and x not in IGNORED_AGS]

                    resolved = []
                    not_excluded = []

                    for ag in candidates:
                        fit, TP, TN, FP, FN = compute_fit(ag, i_p, i_s)
                        if fit >= 0.80 and TP >= 2 and TN >= 2 and FP <= 1:
                            resolved.append((ag, fit))
                        else:
                            not_excluded.append((ag, fit))

                    resolved.sort(key=lambda x: x[1], reverse=True)
                    not_excluded.sort(key=lambda x: x[1], reverse=True)

                    st.subheader("Conclusion (Step 1: Rule-out / Rule-in)")
                    if resolved:
                        st.success("Resolved (Pattern fit): " + ", ".join([f"Anti-{a}" for a,_ in resolved]))
                    else:
                        st.markdown(
                            "<div class='clinical-danger'>No resolved specificity from current data. Proceed with Selected Cells / Enhancement.</div>",
                            unsafe_allow_html=True
                        )

                    if not_excluded:
                        st.markdown("### ⚠️ Not excluded yet (DO NOT confirm now):")
                        st.write(", ".join([f"Anti-{a}" for a,_ in not_excluded[:15]]))

                        st.subheader("🧩 Suggested Selected Cells")
                        names = [a for a,_ in not_excluded]
                        for target in names[:10]:
                            conflicts = [x for x in names if x != target][:6]
                            found = find_matching_cells_in_inventory(target, conflicts)
                            if found:
                                st.markdown(
                                    f"- Resolve **Anti-{target}**: need **{target}+ / {', '.join(conflicts) if conflicts else 'no conflicts'} −** → "
                                    f"<span class='cell-hint'>{', '.join(found)}</span>",
                                    unsafe_allow_html=True
                                )
                            else:
                                st.markdown(
                                    f"- Resolve **Anti-{target}**: need **{target}+ / {', '.join(conflicts) if conflicts else 'no conflicts'} −** → "
                                    f"<span style='color:red'>Not in current Panel/Screen → external selected cells / different lot.</span>",
                                    unsafe_allow_html=True
                                )

                    st.write("---")
                    st.subheader("Confirmation (Rule of Three) — Resolved only")
                    if not resolved:
                        st.info("No resolved antibody yet → do NOT apply Rule of Three.")
                    else:
                        for ag, fit in resolved:
                            ok, rule, p_cnt, n_cnt = check_rule_3(ag, i_p, i_s)
                            icon = "✅" if ok else "⚠️"
                            st.write(f"**{icon} Anti-{ag}:** {rule} | Fit: {int(round(fit*100))}% | (P:{p_cnt} / N:{n_cnt})")

    # -------------------- DAT MODE --------------------
    if st.session_state.dat_mode:
        st.write("---")
        st.subheader("🧪 Monospecific DAT Workup")
        c1, c2, c3 = st.columns(3)
        igg = c1.selectbox("IgG", ["Negative","Positive"])
        c3d = c2.selectbox("C3d", ["Negative","Positive"])
        ctl = c3.selectbox("Control", ["Negative","Positive"])

        st.markdown("**Interpretation:**")
        if ctl == "Positive":
            st.error("Invalid. Control Positive.")
        else:
            if igg == "Positive":
                st.warning("👉 Mostly **WAIHA** (Warm AIHA). Refer to Blood Bank Physician. Consider Elution/Adsorption.")
            elif c3d == "Positive" and igg == "Negative":
                st.info("👉 Mostly **CAS**. Use Pre-warm technique.")
            else:
                st.info("Follow policy + clinical correlation.")
