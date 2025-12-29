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
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

IGNORED_AGS = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"]  # excluded from candidate list display
INSIGNIFICANT_AGS = ["Lea", "Lua", "Leb", "P1"]          # cold/insignificant bucket
GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]

# Enzyme hint: (per your instruction: remove 's' from enzyme list)
ENZYME_DESTROY = ["M", "N", "S", "Fya", "Fyb"]  # guidance only (not changing grading)

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
# 4. LOGIC ENGINE (UPDATED)
#     - Stage 1: Rule-out + Candidate extraction (no confirmation yet)
#     - Stage 2: Resolve (separate) per antibody
#     - Stage 3: Confirm only for resolved antibodies
# --------------------------------------------------------------------------
def normalize_grade(val):
    s = str(val).lower().strip()
    return 0 if s in ["0", "neg"] else 1

def grade_to_level(val):
    # For caution note only (strength spread)
    s = str(val).strip().lower()
    if s == "0": return 0
    if s == "hemolysis": return 4
    if s.startswith("+"):
        try:
            return int(s.replace("+",""))
        except Exception:
            return 1
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
                # treat any '+' OR 'w' OR 'pos' as positive in paste
                v = 1 if any(x in str(p).lower() for x in ['+', 'pos', 'w', '1']) else 0
                vals.append(v)
            if len(vals) > 26: vals=vals[-26:]
            while len(vals) < 26: vals.append(0)
            d = {"ID": f"C{c+1}" if limit==11 else f"Scn"}
            for i, ag in enumerate(AGS): d[ag] = vals[i]
            data.append(d)
            c += 1
        return pd.DataFrame(data), f"Updated {c} rows."
    except Exception as e:
        return None, str(e)

def _all_cells_iter(extra_cells):
    # yields tuples: (label, phenotype_row_dict_or_series, reaction_0_1)
    # Panel
    for i in range(1, 12):
        yield (f"Panel {i}", st.session_state.p11.iloc[i-1], None)
    # Screen
    sc_lbls = ["I","II","III"]
    for i in range(3):
        yield (f"Screen {sc_lbls[i]}", st.session_state.p3.iloc[i], None)
    # Extras
    for j, ex in enumerate(extra_cells):
        yield (f"Selected {j+1}", ex["ph"], None)

def _get_cell_ph(label, extra_cells):
    if label.startswith("Panel "):
        idx = int(label.split()[-1])
        return st.session_state.p11.iloc[idx-1]
    if label.startswith("Screen "):
        s = label.split()[-1]
        mp={"I":0,"II":1,"III":2}
        return st.session_state.p3.iloc[mp[s]]
    if label.startswith("Selected "):
        idx = int(label.split()[-1]) - 1
        return extra_cells[idx]["ph"]
    return None

def _get_cell_rx(label, in_p, in_s, extra_cells):
    if label.startswith("Panel "):
        idx = int(label.split()[-1])
        return normalize_grade(in_p[idx])
    if label.startswith("Screen "):
        s = label.split()[-1]
        return normalize_grade(in_s[s])
    if label.startswith("Selected "):
        idx = int(label.split()[-1]) - 1
        return normalize_grade(extra_cells[idx]["res"])
    return 0

def _is_dosage_safe(ag, ph):
    # For dosage antigens: only count homozygous positive as safe for rule-out (as per your policy)
    if ag in DOSAGE:
        pair = PAIRS.get(ag)
        if pair and ph.get(pair,0)==1:
            return False  # heterozygous -> not safe to rule out
    return True

def compute_ruled_out(in_p, in_s, extra_cells):
    ruled_out = set()

    # Panel exclusion: eliminate antigens present homozygous on NONreactive cells
    for i in range(1, 12):
        if normalize_grade(in_p[i]) == 0:
            ph = st.session_state.p11.iloc[i-1]
            for ag in AGS:
                if ph.get(ag,0)==1 and _is_dosage_safe(ag, ph):
                    ruled_out.add(ag)

    # Screen exclusion
    smap={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        if normalize_grade(in_s[k]) == 0:
            ph = st.session_state.p3.iloc[smap[k]]
            for ag in AGS:
                if ph.get(ag,0)==1 and _is_dosage_safe(ag, ph):
                    ruled_out.add(ag)

    # Extra exclusion
    for ex in extra_cells:
        if normalize_grade(ex["res"]) == 0:
            ph = ex["ph"]
            for ag in AGS:
                if ph.get(ag,0)==1:
                    ruled_out.add(ag)

    return ruled_out

def compute_fit(ag, in_p, in_s, extra_cells):
    """
    Pattern fit score (0-100) to avoid nonsense candidates (e.g. Xga appearing without pattern support).
    We do NOT "confirm" here; only approximate fit.
    """
    total = 0
    match = 0

    # Panel
    for i in range(1, 12):
        rx = normalize_grade(in_p[i])
        ph = st.session_state.p11.iloc[i-1]
        h = ph.get(ag,0)
        # if dosage antigen and hetero, we down-weight exclusion logic,
        # but for fit we still count it normally (pattern can be affected by dosage).
        total += 1
        if (rx==1 and h==1) or (rx==0 and h==0):
            match += 1

    # Screen
    mp={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        rx = normalize_grade(in_s[k])
        ph = st.session_state.p3.iloc[mp[k]]
        h = ph.get(ag,0)
        total += 1
        if (rx==1 and h==1) or (rx==0 and h==0):
            match += 1

    # Extras
    for ex in extra_cells:
        rx = normalize_grade(ex["res"])
        h = ex["ph"].get(ag,0)
        total += 1
        if (rx==1 and h==1) or (rx==0 and h==0):
            match += 1

    if total == 0:
        return 0
    return int(round((match/total)*100))

def extract_candidates(in_p, in_s, extra_cells):
    ruled_out = compute_ruled_out(in_p, in_s, extra_cells)
    cands = [x for x in AGS if x not in ruled_out and x not in IGNORED_AGS]

    # Fit-based ranking to prevent spurious “identified” antigens (Xga bug symptom)
    scored = []
    for ag in cands:
        scored.append((ag, compute_fit(ag, in_p, in_s, extra_cells)))

    scored.sort(key=lambda x: x[1], reverse=True)

    # Keep list but we will not "identify" anything here.
    # We only show for subsequent resolve step.
    notes = []

    # Anti-G hint (keep as a warning note, not an identification)
    g_indices = [1,2,3,4,8]
    is_G_pattern = True
    for idx in g_indices:
        if normalize_grade(in_p[idx]) == 0:
            is_G_pattern = False
            break
    if is_G_pattern and ("D" in [x[0] for x in scored]):
        # only suggest if C/E also remain possible
        notes.append("anti_G_suspect")

    return scored, notes  # list of tuples (ag, fit)

def split_significant(scored):
    sigs = [(a,f) for (a,f) in scored if a not in INSIGNIFICANT_AGS]
    cold = [(a,f) for (a,f) in scored if a in INSIGNIFICANT_AGS]
    return sigs, cold

def find_matching_cells_in_inventory(target_ab, conflicts):
    found_list = []
    # Panel
    for i in range(11):
        cell = st.session_state.p11.iloc[i]
        if cell.get(target_ab,0)==1:
            clean = True
            for bad in conflicts:
                if cell.get(bad,0)==1:
                    clean = False
                    break
            if clean:
                found_list.append(f"Panel #{i+1}")
    # Screen
    sc_lbls = ["I","II","III"]
    for i in range(3):
        cell = st.session_state.p3.iloc[i]
        if cell.get(target_ab,0)==1:
            clean = True
            for bad in conflicts:
                if cell.get(bad,0)==1:
                    clean = False
                    break
            if clean:
                found_list.append(f"Screen {sc_lbls[i]}")
    return found_list

def is_resolved(ag, significant_list, in_p, in_s, extra_cells):
    """
    Resolved = we have at least one 'separating witness' cell:
      reactive AND ag+ AND all other significant antibodies negative in that cell.
    If only one significant antibody: resolved True by default.
    """
    others = [x for x in significant_list if x != ag]
    if len(significant_list) <= 1:
        return True, None

    # Build universe of cells
    labels = []
    for i in range(1, 12): labels.append(f"Panel {i}")
    for s in ["I","II","III"]: labels.append(f"Screen {s}")
    for j in range(len(extra_cells)): labels.append(f"Selected {j+1}")

    for lb in labels:
        rx = _get_cell_rx(lb, in_p, in_s, extra_cells)
        if rx != 1:
            continue
        ph = _get_cell_ph(lb, extra_cells)
        if ph is None:
            continue
        if ph.get(ag,0) != 1:
            continue
        clean = True
        for o in others:
            if ph.get(o,0) == 1:
                clean = False
                break
        if clean:
            return True, lb

    return False, None

def check_rule_3(cand, in_p, in_s, extras):
    p, n = 0, 0
    # Panel
    for i in range(1, 12):
        s=normalize_grade(in_p[i]); h=st.session_state.p11.iloc[i-1].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    si={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        s=normalize_grade(in_s[k]); h=st.session_state.p3.iloc[si[k]].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Extras
    for c in extras:
        s=normalize_grade(c['res']); h=c['ph'].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1

    full = (p>=3 and n>=3)
    mod  = (p>=2 and n>=3)
    if full:
        return True, "Full Rule (3+3)", p, n
    if mod:
        return True, "Modified Rule (2+3)", p, n
    return False, "Unconfirmed", p, n

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

                # Strength caution (your requirement: only warn if spread > 2 grades)
                levels = [grade_to_level(v) for v in list(i_p.values()) + [s1,s2,s3] if str(v)!="0"]
                if levels:
                    if (max(levels) - min(levels)) > 2:
                        st.warning("⚠️ Strength variation > 2 grades detected. Consider dosage effect / cell condition / mixed antibodies. Do NOT rely on strength alone.")

                cnt = sum([normalize_grade(x) for x in i_p.values()])

                # Panreactivity with negative AC
                if cnt >= 11:
                    st.markdown("""<div class='clinical-alert'>⚠️ <b>High Incidence Antigen suspected.</b><br>
                    Pan-reactivity with Neg AC.<br>
                    Action: Search compatible donors (consider first-degree relatives) / Reference Lab.</div>""", unsafe_allow_html=True)
                else:
                    scored, notes = extract_candidates(i_p, i_s, st.session_state.ext)
                    sigs_scored, cold_scored = split_significant(scored)

                    sigs = [a for a,_ in sigs_scored]
                    cold = [a for a,_ in cold_scored]

                    st.subheader("Conclusion")

                    if not sigs and not cold:
                        st.error("No Match Found / Inconclusive.")
                    else:
                        # Notes (Anti-G)
                        if "anti_G_suspect" in notes:
                            st.warning("⚠️ **Anti-G / Anti-D+C possibility**: Pattern suggests Anti-G. If clinically needed: Adsorption/Elution to differentiate (guidance only).")

                        # -------- Stage 1: Rule-in / Rule-out outcome (NO confirmation yet) --------
                        resolved = {}
                        witness = {}

                        for a in sigs:
                            ok, lb = is_resolved(a, sigs, i_p, i_s, st.session_state.ext)
                            resolved[a] = ok
                            witness[a] = lb

                        resolved_list = [a for a in sigs if resolved.get(a)]
                        unresolved_list = [a for a in sigs if not resolved.get(a)]

                        # Display buckets
                        if resolved_list:
                            st.success(f"**Rule-in (Resolved):** Anti-{', '.join(resolved_list)}")
                        if unresolved_list:
                            st.info(f"**Not excluded yet (Unresolved):** Anti-{', '.join(unresolved_list)}")

                        if cold:
                            st.info(f"**Cold/Insignificant not excluded yet:** Anti-{', '.join(cold)}")

                        # -------- Stage 2: Separation guidance for UNRESOLVED only --------
                        if unresolved_list:
                            st.write("---")
                            st.markdown("**🧪 What is needed to resolve (Separation / Selected cells):**")
                            for t in unresolved_list:
                                conf = [x for x in sigs if x != t]
                                found = find_matching_cells_in_inventory(t, conf)
                                if found:
                                    st.write(f"- **Anti-{t}**: Try cell(s) **{', '.join(found)}** → need ({t}+ / others neg).")
                                else:
                                    st.write(f"- **Anti-{t}**: No suitable cell found in current panel/screen → **Search external / different lot**.")

                                # Enzyme hint if target is in enzyme destroy list
                                if t in ENZYME_DESTROY:
                                    st.caption(f"Enzyme note: If separation is blocked by {t} antigen presence on needed cells, enzyme treatment may help (guidance only).")

                        # -------- Stage 3: Confirmation ONLY for RESOLVED --------
                        st.write("---")
                        st.markdown("### Confirmation (Rule of Three) — **Resolved only**")

                        confirmed = []
                        confirm_details = []
                        all_ok = True

                        for ab in resolved_list:
                            ok, mode, p_cnt, n_cnt = check_rule_3(ab, i_p, i_s, st.session_state.ext)
                            fit = dict(sigs_scored + cold_scored).get(ab, None)
                            fit_txt = f"{fit}%" if fit is not None else "—"
                            icon = "✅" if ok else "⚠️"
                            st.write(f"**{icon} Anti-{ab}:** {mode} | Fit: {fit_txt} | (P:{p_cnt} / N:{n_cnt})")
                            if witness.get(ab):
                                st.caption(f"Resolved by separating witness: {witness[ab]}")
                            if ok:
                                confirmed.append(ab)
                                confirm_details.append((ab, mode, fit_txt, p_cnt, n_cnt))
                            else:
                                all_ok = False

                        if unresolved_list:
                            st.warning("⚠️ Unresolved antibodies are **not** confirmed and will not appear as 'identified'. Resolve them first using the guidance above.")

                        # Official report only if we have at least one confirmed AND no unresolved AND all resolved are confirmed
                        if confirmed and not unresolved_list and all_ok:
                            if st.button("Generate Official Report"):
                                rpt=f"""<div class='print-only'>
                                <center><h2>Maternity & Children Hospital - Tabuk</h2><h3>Serology Report</h3></center>
                                <div class='result-sheet'>
                                <b>Pt:</b> {nm} ({mr})<br>
                                <b>Tech:</b> {tc} | <b>Lot:</b> {st.session_state.lot_p}<hr>
                                <b>Confirmed Antibody(ies):</b> Anti-{', '.join(confirmed)}<br>
                                <b>Validation:</b> Rule of Three satisfied (p≤0.05) where applicable.<br><br>
                                <b>Consultant Verified:</b> _____________
                                </div>
                                <div class='print-footer'>Dr. Haitham Ismail | Consultant</div>
                                </div>
                                <script>window.print()</script>"""
                                st.markdown(rpt, unsafe_allow_html=True)
                        else:
                            st.info("ℹ️ Official report will be available only after: (1) no unresolved antibodies AND (2) confirmation completed for resolved ones.")

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
                st.warning("👉 **Mostly WAIHA** (Warm Autoimmune Hemolytic Anemia).")
                st.write("- Refer to Blood Bank Physician.")
                st.write("- Consider Elution / Adsorption (as per policy/workflow).")
                st.markdown("<div class='clinical-waiha'><b>⚠️ Critical Note:</b> If recently transfused, consider <b>DHTR</b>. Elution is important.</div>", unsafe_allow_html=True)
            elif c3d=="Positive" and igg=="Negative":
                st.info("👉 **CAS** (Cold Agglutinin Syndrome).")
                st.write("- Use Pre-warm Technique.")
                st.write("- Refer to Blood Bank Physician if clinically indicated.")
            else:
                st.info("DAT monospecific pattern does not strongly suggest WAIHA/CAS. Correlate clinically and consult physician if needed.")

    # ---------------- ADD SELECTED CELL ----------------
    if not st.session_state.dat_mode:
        with st.expander("➕ Add Selected Cell (From Library)"):
            id_x=st.text_input("ID")
            rs_x=st.selectbox("R",GRADES,key="exr")
            ag_col=st.columns(6)
            new_p={}
            for i,ag in enumerate(AGS):
                if ag_col[i%6].checkbox(ag): new_p[ag]=1
                else: new_p[ag]=0
            if st.button("Confirm Add"):
                st.session_state.ext.append({"res":normalize_grade(rs_x),"res_txt":rs_x,"ph":new_p})
                st.success("Added! Re-run Analysis.")

    if st.session_state.ext:
        st.table(pd.DataFrame(st.session_state.ext)[['res_txt']])
