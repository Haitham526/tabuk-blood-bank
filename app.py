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

    # Get SHA if file exists
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
# 1. SETUP & BRANDING
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
    .clinical-cold { background-color: #cff4fc; border-left: 5px solid #0dcaf0; padding: 15px; margin: 10px 0; color: #055160; }
    .clinical-alert { background-color: #fff3cd; border: 2px solid #ffca2c; padding: 10px; color: #000; font-weight: bold; margin: 8px 0;}
    .clinical-danger { background-color: #f8d7da; border: 2px solid #dc3545; padding: 10px; color: #721c24; font-weight: bold; margin: 8px 0;}

    .cell-hint { font-size: 0.9em; color: #155724; background: #d4edda; padding: 2px 6px; border-radius: 4px; }

    .dr-signature {
        position: fixed; bottom: 10px; right: 15px;
        background: rgba(255,255,255,0.95);
        padding: 8px 15px; border: 2px solid #8B0000; border-radius: 8px; z-index:99; box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
        text-align: center; font-family: 'Georgia', serif;
    }
    .dr-name { color: #8B0000; font-size: 15px; font-weight: bold; display: block;}
    .dr-title { color: #333; font-size: 11px; }

    div[data-testid="stDataEditor"] table { width: 100% !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class='dr-signature no-print'>
    <span class='dr-name'>Dr. Haitham Ismail</span>
    <span class='dr-title'>Clinical Hematology/Oncology &<br>BM Transplantation & Transfusion Medicine Consultant</span>
</div>
""", unsafe_allow_html=True)

# --------------------------------------------------------------------------
# 2. DEFINITIONS
# --------------------------------------------------------------------------
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]

# Dosage antigens (pairs where heterozygous expression can weaken reaction)
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# Not used for routine identification in your workflow (as you defined)
IGNORED_AGS = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"]

# Cold/insignificant group (kept as you had)
INSIGNIFICANT_AGS = ["Lea", "Lua", "Leb", "P1"]

GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]

# --------------------------------------------------------------------------
# 3. STATE (load defaults from local repo files if present)
# --------------------------------------------------------------------------
default_p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
default_p3  = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])

if 'p11' not in st.session_state:
    st.session_state.p11 = load_csv_if_exists("data/p11.csv", default_p11)

if 'p3' not in st.session_state:
    st.session_state.p3 = load_csv_if_exists("data/p3.csv", default_p3)

default_lots = {"lot_p": "", "lot_s": ""}
lots_obj = load_json_if_exists("data/lots.json", default_lots)

if 'lot_p' not in st.session_state:
    st.session_state.lot_p = lots_obj.get("lot_p", "")

if 'lot_s' not in st.session_state:
    st.session_state.lot_s = lots_obj.get("lot_s", "")

if 'dat_mode' not in st.session_state: st.session_state.dat_mode = False
if 'ext' not in st.session_state: st.session_state.ext = []

# --------------------------------------------------------------------------
# 4. LOGIC HELPERS
# --------------------------------------------------------------------------
def normalize_grade(val):
    s = str(val).lower().strip()
    return 0 if s in ["0", "neg", "negative"] else 1

def grade_to_num(val):
    s = str(val).lower().strip()
    if s in ["0", "neg", "negative"]: return 0
    if s == "hemolysis": return 4
    if s.startswith("+"):
        try: return int(s.replace("+",""))
        except: return 1
    # fallback
    return 1

def parse_paste(txt, limit=11):
    try:
        rows = txt.strip().split('\n')
        data = []
        c = 0
        for line in rows:
            if c >= limit: break
            parts = line.split('\t')
            vals = []
            for p in parts:
                v = 1 if any(x in str(p).lower() for x in ['+', '1', 'pos', 'w']) else 0
                vals.append(v)
            if len(vals) > len(AGS): vals = vals[-len(AGS):]
            while len(vals) < len(AGS): vals.append(0)
            d = {"ID": f"C{c+1}" if limit==11 else f"Scn{c+1}"}
            for i, ag in enumerate(AGS): d[ag] = vals[i]
            data.append(d)
            c+=1
        return pd.DataFrame(data), f"Updated {c} rows."
    except Exception as e:
        return None, str(e)

def high_incidence_suspected(i_p, i_s, ac_negative=True):
    # STRICT definition (your requirement):
    # All 11 panel reactive + all 3 screen reactive + AC negative
    if not ac_negative:
        return False
    p_pos = sum([normalize_grade(i_p[i]) for i in range(1,12)])
    s_pos = sum([normalize_grade(i_s[k]) for k in ["I","II","III"]])
    return (p_pos == 11 and s_pos == 3)

def reaction_strength_warning(i_p, i_s):
    # only guidance: if range >= 2 grades (e.g. +1 and +3)
    nums = []
    for i in range(1,12):
        nums.append(grade_to_num(i_p[i]))
    for k in ["I","II","III"]:
        nums.append(grade_to_num(i_s[k]))
    mx, mn = max(nums), min(nums)
    if (mx - mn) >= 2 and mx > 0:
        return True
    return False

def find_matching_cells_in_inventory(target_ag, conflicts):
    found_list = []
    # Panel
    for i in range(11):
        cell = st.session_state.p11.iloc[i]
        if cell.get(target_ag,0)==1:
            clean = True
            for bad in conflicts:
                if cell.get(bad,0)==1:
                    clean=False; break
            if clean:
                found_list.append(f"Panel #{i+1}")
    # Screen
    sc_lbls = ["I","II","III"]
    for i in range(3):
        cell = st.session_state.p3.iloc[i]
        if cell.get(target_ag,0)==1:
            clean = True
            for bad in conflicts:
                if cell.get(bad,0)==1:
                    clean=False; break
            if clean:
                found_list.append(f"Screen {sc_lbls[i]}")
    return found_list

def compute_rule_out(i_p, i_s, extra_cells):
    """
    Rule-out strictly follows your policy:
    - Use ONLY nonreactive cells.
    - Rule-out antigen if antigen is present homozygous on a NONreactive cell.
    - For non-dosage antigens: any antigen present on nonreactive cell rules it out.
    """
    ruled_out = set()

    # Panel exclusion
    for idx in range(1, 12):
        if normalize_grade(i_p[idx]) == 0:
            ph = st.session_state.p11.iloc[idx-1]
            for ag in AGS:
                safe = True
                # dosage: must be homozygous (partner absent)
                if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1:
                    safe = False
                if ph.get(ag,0)==1 and safe:
                    ruled_out.add(ag)

    # Screen exclusion
    smap={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        if normalize_grade(i_s[k]) == 0:
            ph = st.session_state.p3.iloc[smap[k]]
            for ag in AGS:
                if ag not in ruled_out:
                    safe = True
                    if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1:
                        safe = False
                    if ph.get(ag,0)==1 and safe:
                        ruled_out.add(ag)

    # Extra selected cells exclusion
    for ex in extra_cells:
        if normalize_grade(ex['res_txt']) == 0:
            for ag in AGS:
                # selected cell is assumed chosen intentionally; we allow it to rule-out if antigen present
                if ex['ph'].get(ag,0)==1:
                    ruled_out.add(ag)

    return ruled_out

def compute_fit(ag, i_p, i_s, extra_cells):
    """
    Rule-in (pattern fit) — makes E/K become RESOLVED when pattern fits.
    Counts:
    - TP: reactive & Ag+
    - TN: nonreactive & Ag-
    - FP: reactive & Ag-
    - FN: nonreactive & Ag+
    Fit% = (TP+TN)/(TP+TN+FP+FN)
    """
    TP=TN=FP=FN=0

    # Panel
    for idx in range(1,12):
        r = normalize_grade(i_p[idx])
        h = st.session_state.p11.iloc[idx-1].get(ag,0)
        if r==1 and h==1: TP+=1
        elif r==0 and h==0: TN+=1
        elif r==1 and h==0: FP+=1
        elif r==0 and h==1: FN+=1

    # Screen
    smap={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        r = normalize_grade(i_s[k])
        h = st.session_state.p3.iloc[smap[k]].get(ag,0)
        if r==1 and h==1: TP+=1
        elif r==0 and h==0: TN+=1
        elif r==1 and h==0: FP+=1
        elif r==0 and h==1: FN+=1

    # Extras
    for ex in extra_cells:
        r = normalize_grade(ex['res_txt'])
        h = ex['ph'].get(ag,0)
        if r==1 and h==1: TP+=1
        elif r==0 and h==0: TN+=1
        elif r==1 and h==0: FP+=1
        elif r==0 and h==1: FN+=1

    total = TP+TN+FP+FN
    fit = (TP+TN)/total if total>0 else 0.0
    return fit, TP, TN, FP, FN

def check_rule_3(ag, i_p, i_s, extras):
    p, n = 0, 0
    # Panel
    for i in range(1, 12):
        s=normalize_grade(i_p[i]); h=st.session_state.p11.iloc[i-1].get(ag,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    si={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        s=normalize_grade(i_s[k]); h=st.session_state.p3.iloc[si[k]].get(ag,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Extras
    for c in extras:
        s=normalize_grade(c['res_txt']); h=c['ph'].get(ag,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1

    full = (p>=3 and n>=3)
    modified = (p>=2 and n>=3)
    ok = full or modified
    rule = "Full Rule (3+3)" if full else ("Modified Rule (2+3)" if modified else "Not met")
    return ok, rule, p, n

def analyze_step1(i_p, i_s, extra_cells):
    """
    Step 1 output:
    - ruled_out set
    - candidates (not excluded)
    - resolved list (rule-in by fit)
    - not_resolved list (still not excluded)
    IMPORTANT: Do NOT confirm anything here.
    """
    ruled_out = compute_rule_out(i_p, i_s, extra_cells)

    candidates = [x for x in AGS if x not in ruled_out and x not in IGNORED_AGS]

    resolved = []
    not_resolved = []

    # Rule-in threshold:
    # - fit >= 0.80 AND (TP>=2) AND (TN>=2)
    # This makes clear patterns (E/K/Jka etc) become "Resolved".
    for ag in candidates:
        fit, TP, TN, FP, FN = compute_fit(ag, i_p, i_s, extra_cells)
        # Minimum evidence to call it "resolved"
        if fit >= 0.80 and TP >= 2 and TN >= 2 and FP <= 1:
            resolved.append({"ag": ag, "fit": fit, "TP": TP, "TN": TN, "FP": FP, "FN": FN})
        else:
            not_resolved.append({"ag": ag, "fit": fit, "TP": TP, "TN": TN, "FP": FP, "FN": FN})

    # Sort: resolved by fit desc, then TP desc
    resolved.sort(key=lambda x: (x["fit"], x["TP"]), reverse=True)
    not_resolved.sort(key=lambda x: (x["fit"], x["TP"]), reverse=True)

    return ruled_out, resolved, not_resolved

def show_selected_cells_suggestions(not_excluded):
    """
    Suggest separation cells for all NOT-EXCLUDED antibodies
    even when there is no resolved specificity yet.
    """
    if not not_excluded:
        return

    names = [x["ag"] for x in not_excluded]
    st.write("---")
    st.subheader("🧩 Suggested Selected Cells (Separation / Resolution)")

    for target in names:
        conflicts = [x for x in names if x != target]
        found = find_matching_cells_in_inventory(target, conflicts)
        if found:
            st.markdown(
                f"- **Resolve Anti-{target}**: need **{target}+** and **{', '.join(conflicts) if conflicts else 'no conflicts'} −** → "
                f"<span class='cell-hint'>{', '.join(found)}</span>",
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f"- **Resolve Anti-{target}**: need **{target}+** and **{', '.join(conflicts) if conflicts else 'no conflicts'} −** → "
                f"<span style='color:red'>Not available in current Panel/Screen → use external selected cells / different lot.</span>",
                unsafe_allow_html=True
            )

# --------------------------------------------------------------------------
# 5. UI
# --------------------------------------------------------------------------
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Menu", ["Workstation", "Supervisor"])
    if st.button("RESET DATA"):
        st.session_state.ext=[]; st.session_state.dat_mode=False
        st.rerun()

# ------------------ SUPERVISOR ------------------
if nav == "Supervisor":
    st.title("Config")

    if st.text_input("Password",type="password")=="admin123":
        st.subheader("1. Lot Setup (Separate)")
        c1, c2 = st.columns(2)
        lp = c1.text_input("ID Panel Lot#", value=st.session_state.lot_p)
        ls = c2.text_input("Screen Panel Lot#", value=st.session_state.lot_s)

        if st.button("Save Lots (Local)"):
            st.session_state.lot_p=lp
            st.session_state.lot_s=ls
            st.success("Saved locally. Now press **Save to GitHub** to publish to all devices.")

        st.subheader("2. Grid Data (Copy-Paste)")
        t1, t2 = st.tabs(["Panel (11)", "Screen (3)"])
        with t1:
            p_txt=st.text_area("Paste Panel Numbers",height=150)
            if st.button("Upd P11"):
                d,m=parse_paste(p_txt,11)
                if d is not None:
                    st.session_state.p11=d
                    st.success(m)
            st.dataframe(st.session_state.p11.iloc[:,:15])

        with t2:
            s_txt=st.text_area("Paste Screen Numbers",height=100)
            if st.button("Upd Scr"):
                d,m=parse_paste(s_txt,3)
                if d is not None:
                    st.session_state.p3=d
                    st.success(m)
            st.dataframe(st.session_state.p3.iloc[:,:15])

        st.write("---")
        st.subheader("3. Publish to ALL devices (Save to GitHub)")

        st.info("بعد ما تحدث البانل/السكرين واللوت، اضغط الزر ده مرة واحدة. "
                "هيعمل Commit تلقائي في GitHub، وأي جهاز يفتح اللينك هيشوف نفس الجداول.")

        if st.button("💾 Save to GitHub (Commit)"):
            try:
                lots_json = json.dumps(
                    {"lot_p": st.session_state.lot_p, "lot_s": st.session_state.lot_s},
                    ensure_ascii=False, indent=2
                )
                github_upsert_file("data/p11.csv", st.session_state.p11.to_csv(index=False), "Update monthly p11 panel")
                github_upsert_file("data/p3.csv",  st.session_state.p3.to_csv(index=False),  "Update monthly p3 screen")
                github_upsert_file("data/lots.json", lots_json, "Update monthly lots")
                st.success("✅ Done. Published to GitHub. Now ALL devices will see the updated tables.")
            except Exception as e:
                st.error(f"❌ Save failed: {e}")

# ------------------ WORKSTATION ------------------
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

    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")

    with st.form("main"):
        st.write("### Reaction Entry")
        L, R = st.columns([1, 2.5])
        with L:
            st.write("Controls")
            ac_res = st.radio("Auto Control (AC)", ["Negative", "Positive"])
            st.write("Screening")
            s1=st.selectbox("Scn I", GRADES)
            s2=st.selectbox("Scn II", GRADES)
            s3=st.selectbox("Scn III", GRADES)
        with R:
            st.write("Panel Reactions")
            g1,g2=st.columns(2)
            with g1:
                p1=st.selectbox("1",GRADES,key="p1"); p2=st.selectbox("2",GRADES,key="p2"); p3=st.selectbox("3",GRADES,key="p3"); p4=st.selectbox("4",GRADES,key="p4"); p5=st.selectbox("5",GRADES,key="p5"); p6=st.selectbox("6",GRADES,key="p6")
            with g2:
                p7=st.selectbox("7",GRADES,key="p7"); p8=st.selectbox("8",GRADES,key="p8"); p9=st.selectbox("9",GRADES,key="p9"); p10=st.selectbox("10",GRADES,key="p10"); p11=st.selectbox("11",GRADES,key="p11")

        run = st.form_submit_button("🚀 Run Analysis")

    # DAT mode trigger
    if run:
        if not st.session_state.lot_p or not st.session_state.lot_s:
            st.error("⛔ Action Blocked: Lots not configured by Supervisor.")
        else:
            if ac_res == "Positive":
                st.session_state.dat_mode = True
            else:
                st.session_state.dat_mode = False

                i_p = {1:p1,2:p2,3:p3,4:p4,5:p5,6:p6,7:p7,8:p8,9:p9,10:p10,11:p11}
                i_s = {"I":s1,"II":s2,"III":s3}

                if reaction_strength_warning(i_p, i_s):
                    st.markdown(
                        "<div class='clinical-alert'>⚠️ <b>Reaction strength varies (≥2 grades).</b> "
                        "This may reflect dosage effect, cell quality, or technical factors. Interpret multiple-antibody suspicion with caution.</div>",
                        unsafe_allow_html=True
                    )

                # High incidence strict
                if high_incidence_suspected(i_p, i_s, ac_negative=True):
                    st.markdown(
                        "<div class='clinical-danger'>🛑 <b>Antibody against High-Incidence Antigen suspected.</b><br>"
                        "Pattern: all Panel & Screen reactive with Negative AC.<br>"
                        "Action: search compatible donors (consider first-degree relatives) / refer to reference lab.</div>",
                        unsafe_allow_html=True
                    )
                else:
                    # ---------------- STEP 1 ----------------
                    ruled_out, resolved, not_excluded = analyze_step1(i_p, i_s, st.session_state.ext)

                    st.subheader("Conclusion (Step 1: Rule-out / Rule-in)")

                    if not resolved:
                        st.markdown(
                            "<div class='clinical-danger'>No resolved specificity from current data. Proceed with Selected Cells / Enhancement as needed.</div>",
                            unsafe_allow_html=True
                        )
                    else:
                        resolved_names = [x["ag"] for x in resolved if x["ag"] not in INSIGNIFICANT_AGS]
                        cold_names = [x["ag"] for x in resolved if x["ag"] in INSIGNIFICANT_AGS]
                        if resolved_names:
                            st.success(f"Resolved (Pattern fit): Anti-{', '.join(resolved_names)}")
                        if cold_names:
                            st.info(f"Resolved Cold/Insignificant: Anti-{', '.join(cold_names)}")

                    # Not excluded list (DO NOT confirm)
                    if not_excluded:
                        sigs = [x for x in not_excluded if x["ag"] not in INSIGNIFICANT_AGS]
                        colds = [x for x in not_excluded if x["ag"] in INSIGNIFICANT_AGS]

                        st.markdown("### ⚠️ Not excluded yet (Needs more work — DO NOT confirm now):")
                        if sigs:
                            st.write("- Clinically significant possibilities: " + ", ".join([x["ag"] for x in sigs[:10]]))
                        if colds:
                            st.write("- Cold/Insignificant not excluded: " + ", ".join([x["ag"] for x in colds[:10]]))

                        # ALWAYS show Selected Cells suggestions for not-excluded
                        show_selected_cells_suggestions(not_excluded)

                    # ---------------- STEP 2 ----------------
                    st.write("---")
                    st.subheader("Confirmation (Rule of Three) — Resolved only")

                    if not resolved:
                        st.info("No resolved antibody yet → do NOT apply Rule of Three. Add selected cells / repeat with different lot as needed.")
                    else:
                        # Confirm only resolved
                        for item in resolved:
                            ag = item["ag"]
                            ok, rule, p_cnt, n_cnt = check_rule_3(ag, i_p, i_s, st.session_state.ext)
                            icon = "✅" if ok else "⚠️"
                            fit_pct = int(round(item["fit"]*100))
                            st.write(f"**{icon} Anti-{ag}:** {rule} | Fit: {fit_pct}% | (P:{p_cnt} / N:{n_cnt})")
                            if not ok:
                                st.markdown(
                                    "<div class='clinical-alert'>Rule-of-Three not met yet → add selected cells (different lot) or additional cells.</div>",
                                    unsafe_allow_html=True
                                )

                    # Generate report only if ALL resolved are confirmed
                    all_ok = True
                    for item in resolved:
                        ok, _, _, _ = check_rule_3(item["ag"], i_p, i_s, st.session_state.ext)
                        if not ok:
                            all_ok = False
                            break

                    if resolved and all_ok:
                        if st.button("Generate Official Report"):
                            resolved_names = [x["ag"] for x in resolved]
                            rpt=f"""
                            <div class='print-only'>
                              <center>
                                <h2>Maternity & Children Hospital - Tabuk</h2>
                                <h3>Serology Report</h3>
                              </center>
                              <div class='result-sheet'>
                                <b>Pt:</b> {nm} ({mr})<br>
                                <b>Tech:</b> {tc}<br>
                                <b>ID Panel Lot:</b> {st.session_state.lot_p} | <b>Screen Lot:</b> {st.session_state.lot_s}
                                <hr>
                                <b>Resolved Antibody(ies):</b> Anti-{", ".join(resolved_names)}<br>
                                <b>Confirmation:</b> Rule of Three satisfied (p ≤ 0.05 criteria supported).<br><br>
                                <b>Recommendation:</b> Transfuse antigen-negative, crossmatch compatible units as per policy.<br><br>
                                <b>Consultant Verified:</b> ______________________
                              </div>
                              <div class='footer-print'>Dr. Haitham Ismail | Consultant</div>
                            </div>
                            <script>window.print()</script>
                            """
                            st.markdown(rpt, unsafe_allow_html=True)

    # ---------------- DAT MODE ----------------
    if st.session_state.dat_mode:
        st.write("---")
        st.subheader("🧪 Monospecific DAT Workup")

        c_d1, c_d2, c_d3 = st.columns(3)
        igg = c_d1.selectbox("IgG", ["Negative","Positive"], key="dig")
        c3d = c_d2.selectbox("C3d", ["Negative","Positive"], key="dc3")
        ctl = c_d3.selectbox("Control", ["Negative","Positive"], key="dct")

        st.markdown("**Interpretation:**")
        if ctl == "Positive":
            st.error("Invalid. Control Positive.")
        else:
            if igg=="Positive":
                st.warning("👉 **WAIHA** (Warm Autoimmune Hemolytic Anemia) is most likely.")
                st.write("- Refer to Blood Bank Physician.")
                st.write("- Consider Elution/Adsorption as per policy.")
                st.markdown("<div class='clinical-waiha'><b>⚠️ Critical Note:</b> If recently transfused, assess for <b>Delayed Hemolytic Transfusion Reaction (DHTR)</b>. Elution should be considered.</div>", unsafe_allow_html=True)
            elif c3d=="Positive" and igg=="Negative":
                st.info("👉 **CAS** (Cold Agglutinin Syndrome) is most likely.")
                st.write("- Use Pre-warm Technique as per policy.")
                st.write("- Consider cold workup / physician referral as needed.")
            else:
                st.info("DAT monospecific pattern does not strongly suggest WAIHA/CAS. Follow policy and clinical context.")

    # ---------------- EXTRA SELECTED CELLS ----------------
    if not st.session_state.dat_mode:
        with st.expander("➕ Add Selected Cell (From Library)"):
            id_x=st.text_input("ID (free text)")
            rs_x=st.selectbox("Reaction (Selected Cell)", GRADES, key="exr")
            ag_col=st.columns(6)
            new_p={}
            for i,ag in enumerate(AGS):
                if ag_col[i%6].checkbox(ag, key=f"cb_{ag}"):
                    new_p[ag]=1
                else:
                    new_p[ag]=0
            if st.button("Confirm Add"):
                st.session_state.ext.append({"id": id_x, "res_txt": rs_x, "ph": new_p})
                st.success("Added! Re-run Analysis.")

    if st.session_state.ext:
        st.write("---")
        st.subheader("Selected Cells Added")
        st.table(pd.DataFrame(st.session_state.ext)[['id','res_txt']])
