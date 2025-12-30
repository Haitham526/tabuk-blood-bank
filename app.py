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
    repo  = st.secrets.get("GITHUB_REPO", None)   # e.g. "Haitham526/tabuk-blood-bank"
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
# 1) SETUP & BRANDING
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
    .small-note { font-size: 0.92em; color:#444; }

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
# 2) DEFINITIONS
# --------------------------------------------------------------------------
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]

# Dosage systems (pairs matter)
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# Rules for display
IGNORED_AGS = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"]
INSIGNIFICANT_AGS = ["Lea", "Lua", "Leb", "P1"]

GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]

# Enzyme-sensitive (per your rule: exclude 's')
ENZYME_SENSITIVE = set(["M","N","S","Fya","Fyb"])

# --------------------------------------------------------------------------
# 3) STATE (load defaults from local repo files if present)
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
# 4) CORE HELPERS
# --------------------------------------------------------------------------
def normalize_grade(val) -> int:
    """Binary for elimination logic: 0=nonreactive, 1=reactive."""
    s = str(val).lower().strip()
    return 0 if s in ["0", "neg", "negative", "nonreactive", "non-reactive"] else 1

def grade_to_strength(val) -> int:
    """Strength mapping for advisory notes only. Hemolysis treated as 4 (tube concept)."""
    s = str(val).strip()
    if s.lower() == "hemolysis":
        return 4
    if s.startswith("+"):
        try:
            return int(s.replace("+",""))
        except Exception:
            return 0
    if s in ["0","neg","Negative"]:
        return 0
    return 0

def parse_paste(txt, limit=11):
    """
    Smart paste:
    - Accept Excel copied block.
    - Extract 26 antigen columns reliably to avoid column shift (fixes Xga false hits).
    """
    try:
        rows = [r for r in txt.strip().split('\n') if r.strip()]
        data = []
        c = 0
        for line in rows:
            if c >= limit:
                break
            parts = line.split('\t')

            # Convert each token to 0/1 (based on presence of + / pos / w etc.)
            raw_vals = []
            for p in parts:
                p_s = str(p).lower().strip()
                v = 1 if any(x in p_s for x in ['+', 'pos', 'positive', 'w', 'wk']) else 0
                # also treat explicit "1" or "x" as positive if the lab uses them
                if p_s in ["1", "x", "y", "yes"]:
                    v = 1
                raw_vals.append(v)

            # Heuristic: if first column looks like an ID (C1/Cell#/1) drop it
            # We want exactly 26 antigen flags.
            if len(raw_vals) >= 27:
                raw_vals = raw_vals[1:]

            # If still longer than 26 -> take FIRST 26 (critical fix vs old "last 26")
            if len(raw_vals) > 26:
                raw_vals = raw_vals[:26]

            # If shorter -> pad
            while len(raw_vals) < 26:
                raw_vals.append(0)

            d = {"ID": f"C{c+1}" if limit == 11 else (["I","II","III"][c] if limit == 3 else f"X{c+1}")}
            for i, ag in enumerate(AGS):
                d[ag] = raw_vals[i]
            data.append(d)
            c += 1

        return pd.DataFrame(data), f"Updated {c} rows."
    except Exception as e:
        return None, str(e)

def is_homozygous(cell_row: pd.Series, ag: str) -> bool:
    """
    Homozygous definition only for dosage antigens:
    ag present (1) and its pair absent (0).
    """
    if ag not in DOSAGE:
        return False
    pair = PAIRS.get(ag)
    if not pair:
        return False
    return (cell_row.get(ag,0)==1 and cell_row.get(pair,0)==0)

def eliminate_from_nonreactive_cell(ruled_out: set, cell_row: pd.Series):
    """
    Rule-out based on NEGATIVE cells:
    - Cross out antigens represented HOMOZYGOUS on that NEGATIVE cell (dosage systems).
    - For non-dosage antigens: if antigen is present on a NEGATIVE cell => can be ruled out.
    """
    for ag in AGS:
        if ag in DOSAGE:
            if is_homozygous(cell_row, ag):
                ruled_out.add(ag)
        else:
            if cell_row.get(ag,0)==1:
                ruled_out.add(ag)

def find_matching_cells_in_inventory(target_ab, conflicts):
    """
    Suggest internal selected cells (from current panel + screen) ONLY.
    Cell must be target_ab positive AND all conflict abs negative.
    """
    found_list = []
    # P11
    for i in range(11):
        cell = st.session_state.p11.iloc[i]
        if cell.get(target_ab,0)==1:
            if all(cell.get(bad,0)==0 for bad in conflicts):
                found_list.append(f"Panel #{i+1}")
    # P3
    sc_lbls = ["I","II","III"]
    for i in range(3):
        cell = st.session_state.p3.iloc[i]
        if cell.get(target_ab,0)==1:
            if all(cell.get(bad,0)==0 for bad in conflicts):
                found_list.append(f"Screen {sc_lbls[i]}")
    return found_list

# --------------------------------------------------------------------------
# 5) MAIN ALLO ENGINE (2-stage: rule-out/rule-in -> confirmation)
# --------------------------------------------------------------------------
def stage1_candidates(in_p, in_s, extra_cells):
    """
    STAGE 1 = RULE-OUT only (strict):
    - Use NEGATIVE cells
    - For dosage antigens: rule-out only if homozygous on NEGATIVE cell
    - Others: present on NEGATIVE cell => rule-out
    """
    ruled_out = set()

    # Panel NEG cells
    for i in range(1, 12):
        if normalize_grade(in_p[i]) == 0:
            ph = st.session_state.p11.iloc[i-1]
            eliminate_from_nonreactive_cell(ruled_out, ph)

    # Screen NEG cells
    smap = {"I":0, "II":1, "III":2}
    for k in ["I","II","III"]:
        if normalize_grade(in_s[k]) == 0:
            ph = st.session_state.p3.iloc[smap[k]]
            eliminate_from_nonreactive_cell(ruled_out, ph)

    # Extra NEG cells
    for ex in extra_cells:
        if normalize_grade(ex['res']) == 0:
            sr = pd.Series(ex['ph'])
            eliminate_from_nonreactive_cell(ruled_out, sr)

    candidates = [x for x in AGS if x not in ruled_out and x not in IGNORED_AGS]
    return candidates, ruled_out

def antiG_flag(in_p, candidates):
    """
    Keep your original anti-G logic but safer:
    - If D is a candidate AND pattern cells 1,2,3,4,8 are reactive => anti-G suspected.
    """
    g_indices = [1,2,3,4,8]
    if "D" not in candidates:
        return False
    for idx in g_indices:
        if normalize_grade(in_p[idx]) == 0:
            return False
    return True

def confirmation_counts_for_ab(ab, in_p, in_s, extras, block_abs):
    """
    Rule-of-three counts but ONLY on 'clean' evidence when there is interference.
    A cell is counted for ab only if ALL other unresolved/competing abs are NEGATIVE on that cell.
    """
    p, n = 0, 0

    # Panel
    for i in range(1, 12):
        cell = st.session_state.p11.iloc[i-1]
        r = normalize_grade(in_p[i])

        # interference filter
        if any(cell.get(x,0)==1 for x in block_abs):
            continue

        h = cell.get(ab,0)
        if r==1 and h==1: p += 1
        if r==0 and h==0: n += 1

    # Screen
    si={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        cell = st.session_state.p3.iloc[si[k]]
        r = normalize_grade(in_s[k])

        if any(cell.get(x,0)==1 for x in block_abs):
            continue

        h = cell.get(ab,0)
        if r==1 and h==1: p += 1
        if r==0 and h==0: n += 1

    # Extra
    for c in extras:
        cell = pd.Series(c['ph'])
        r = normalize_grade(c['res'])

        if any(cell.get(x,0)==1 for x in block_abs):
            continue

        h = cell.get(ab,0)
        if r==1 and h==1: p += 1
        if r==0 and h==0: n += 1

    ok_full = (p>=3 and n>=3)
    ok_mod  = (p>=2 and n>=3)  # accepted modified rule
    return p, n, ok_full, ok_mod

def need_selected_cells(ab, candidates, in_p, in_s, extras):
    """
    Decide if ab is 'unresolved due to interference':
    - If there are other candidates that frequently co-exist on reactive cells such that
      no clean confirming evidence can be counted (p/n too low after interference filter).
    """
    others = [x for x in candidates if x != ab]
    p, n, ok_full, ok_mod = confirmation_counts_for_ab(ab, in_p, in_s, extras, block_abs=others)
    # If cannot reach even modified, then we need selected cells.
    return (not ok_mod), p, n, ok_full, ok_mod

def analyze_allo_workflow(in_p, in_s, extra_cells):
    """
    Full workflow output:
    - confirmed_abs: list
    - pending_abs: list (not excluded; need workup/selected cells)
    - notes: list of note flags
    - strategies: dict pending_ab -> strategy info
    """
    candidates, ruled_out = stage1_candidates(in_p, in_s, extra_cells)
    notes = []

    # Anti-G detection (note only)
    is_G = antiG_flag(in_p, candidates)

    # Special masking behavior (keep your intent, but never invent)
    # If D is candidate, we do NOT auto-claim C/E.
    # We only flag Anti-G suspicion if pattern fits; otherwise C/E remain as candidates if not ruled out.
    # (This avoids hiding true anti-E in some cases.)
    # However, user liked "silent masking" earlier; we keep minimal: do NOT add C/E automatically.
    if is_G:
        notes.append("anti_G_suspect")

    # Anti-c clinical note
    if "c" in candidates:
        notes.append("anti-c_risk")

    # Determine confirmed vs pending using interference-aware confirmation
    confirmed = []
    pending = []
    strategies = {}  # pending_ab -> details

    for ab in candidates:
        others = [x for x in candidates if x != ab]
        p, n, ok_full, ok_mod = confirmation_counts_for_ab(ab, in_p, in_s, extra_cells, block_abs=others)

        if ok_mod:
            # Confirmed, because evidence is clean (other candidates negative on counted cells)
            confirmed.append({
                "ab": ab,
                "p": p, "n": n,
                "status": "CONFIRMED_FULL" if ok_full else "CONFIRMED_MOD"
            })
        else:
            pending.append({
                "ab": ab,
                "p": p, "n": n,
                "status": "PENDING"
            })

            # Suggest selected cells only for pending (NOT for confirmed)
            found = find_matching_cells_in_inventory(ab, conflicts=others)
            enzyme_hint = None

            # Enzyme suggestion: only if ab needs a cell where some enzyme-sensitive antigen must be "effectively negative"
            # We present it as an optional tactic when conflicts include enzyme-sensitive antigens.
            sens_conf = [x for x in others if x in ENZYME_SENSITIVE]
            if sens_conf:
                enzyme_hint = f"If the only available discriminating cells are positive for ({', '.join(sens_conf)}), consider enzyme-treated cells to destroy these antigens."

            strategies[ab] = {
                "conflicts": others,
                "internal_cells": found,
                "enzyme_hint": enzyme_hint
            }

    # Separate significant vs insignificant at display time
    return candidates, confirmed, pending, notes, strategies

def reaction_strength_warning(i_p, i_s):
    """
    Advisory note ONLY:
    - If positives have spread >=2 grades (e.g., +1 vs +3), show caution note.
    """
    strengths = []
    for k, v in i_p.items():
        if normalize_grade(v) == 1:
            strengths.append(grade_to_strength(v))
    for k in ["I","II","III"]:
        if normalize_grade(i_s[k]) == 1:
            strengths.append(grade_to_strength(i_s[k]))

    if not strengths:
        return None

    mx, mn = max(strengths), min(strengths)
    if (mx - mn) >= 2:
        return "⚠️ Reaction strength varies ≥2 grades (e.g., +1 vs +3). Consider dosage effect / cell condition / technical factors. Do not conclude 'multiple antibodies' based on strength alone."
    return None

# --------------------------------------------------------------------------
# 6) UI
# --------------------------------------------------------------------------
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Menu", ["Workstation", "Supervisor"])
    if st.button("RESET DATA"):
        st.session_state.ext = []
        st.session_state.dat_mode = False
        st.rerun()

# ------------------ SUPERVISOR ------------------
if nav == "Supervisor":
    st.title("Config")

    if st.text_input("Password", type="password") == "admin123":
        st.subheader("1. Lot Setup")
        c1, c2 = st.columns(2)
        lp = c1.text_input("ID Panel Lot#", value=st.session_state.lot_p)
        ls = c2.text_input("Screen Panel Lot#", value=st.session_state.lot_s)

        if st.button("Save Lots (Local)"):
            st.session_state.lot_p = lp
            st.session_state.lot_s = ls
            st.success("Saved locally. Now press **Save to GitHub** to publish to all devices.")

        st.subheader("2. Grid Data (Copy-Paste)")
        t1, t2 = st.tabs(["Panel (11)", "Screen (3)"])

        with t1:
            p_txt = st.text_area("Paste Panel Numbers", height=150)
            if st.button("Upd P11"):
                d, m = parse_paste(p_txt, 11)
                if d is not None:
                    st.session_state.p11 = d
                    st.success(m)
                else:
                    st.error(m)
            st.dataframe(st.session_state.p11.iloc[:, :15])

        with t2:
            s_txt = st.text_area("Paste Screen Numbers", height=100)
            if st.button("Upd Scr"):
                d, m = parse_paste(s_txt, 3)
                if d is not None:
                    st.session_state.p3 = d
                    st.success(m)
                else:
                    st.error(m)
            st.dataframe(st.session_state.p3.iloc[:, :15])

        st.write("---")
        st.subheader("3. Publish to ALL devices (Save to GitHub)")
        st.info("بعد ما تحدّث البانل/السكرين واللوت، اضغط الزر ده مرة واحدة. "
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

    cA, cB, cC, cD = st.columns(4)
    nm = cA.text_input("Name")
    mr = cB.text_input("MRN")
    tc = cC.text_input("Tech")
    dt = cD.date_input("Date")

    with st.form("main"):
        st.write("### Reaction Entry")
        L, R = st.columns([1, 2.5])
        with L:
            st.write("Controls")
            ac_res = st.radio("Auto Control (AC)", ["Negative", "Positive"])
            st.write("Screening")
            s1 = st.selectbox("Scn I", GRADES)
            s2 = st.selectbox("Scn II", GRADES)
            s3 = st.selectbox("Scn III", GRADES)
        with R:
            st.write("Panel Reactions")
            g1, g2 = st.columns(2)
            with g1:
                c1 = st.selectbox("1", GRADES, key="1")
                c2 = st.selectbox("2", GRADES, key="2")
                c3 = st.selectbox("3", GRADES, key="3")
                c4 = st.selectbox("4", GRADES, key="4")
                c5 = st.selectbox("5", GRADES, key="5")
                c6 = st.selectbox("6", GRADES, key="6")
            with g2:
                c7 = st.selectbox("7", GRADES, key="7")
                c8 = st.selectbox("8", GRADES, key="8")
                c9 = st.selectbox("9", GRADES, key="9")
                c10 = st.selectbox("10", GRADES, key="10")
                c11 = st.selectbox("11", GRADES, key="11")

        run = st.form_submit_button("🚀 Run Analysis")

    # ---- RUN ----
    if run:
        if not st.session_state.lot_p or not st.session_state.lot_s:
            st.error("⛔ Action Blocked: Lots not configured by Supervisor.")
        else:
            i_p = {1:c1,2:c2,3:c3,4:c4,5:c5,6:c6,7:c7,8:c8,9:c9,10:c10,11:c11}
            i_s = {"I":s1,"II":s2,"III":s3}

            all_panel_pos  = all(normalize_grade(v)==1 for v in i_p.values())
            all_screen_pos = all(normalize_grade(i_s[k])==1 for k in ["I","II","III"])

            # 1) AUTO CONTROL PATH (priority)
            if ac_res == "Positive":
                # Always DAT mode. Do not proceed with allo logic now.
                st.session_state.dat_mode = True
                st.warning("⚠️ Auto Control is POSITIVE → Proceed to Monospecific DAT Workup below. Alloantibodies cannot be excluded.")
            else:
                st.session_state.dat_mode = False

                # 2) HIGH INCIDENCE ANTIGEN PATH (only if ALL panel + ALL screen reactive & AC negative)
                if all_panel_pos and all_screen_pos:
                    st.markdown("""
                    <div class='clinical-alert'>
                    ⚠️ <b>Suspect antibody to a HIGH-INCiDENCE antigen.</b><br>
                    Pan-reactivity with <b>Negative Auto Control</b>.<br><br>
                    <b>Action:</b> Search compatible donor from <b>1st-degree relatives</b> and refer to Blood Bank Physician / Reference Lab.
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    # 3) NORMAL ALLO WORKFLOW (strict stage1 -> confirm/pending)
                    strength_note = reaction_strength_warning(i_p, i_s)
                    if strength_note:
                        st.info(strength_note)

                    candidates, confirmed, pending, notes, strategies = analyze_allo_workflow(i_p, i_s, st.session_state.ext)

                    # Display split: significant vs insignificant
                    def is_insig(ab): return ab in INSIGNIFICANT_AGS

                    confirmed_sig = [x for x in confirmed if not is_insig(x["ab"])]
                    confirmed_ins = [x for x in confirmed if is_insig(x["ab"])]
                    pending_sig   = [x for x in pending if not is_insig(x["ab"])]
                    pending_ins   = [x for x in pending if is_insig(x["ab"])]

                    st.subheader("Conclusion")

                    if not candidates:
                        st.error("No Match Found / Inconclusive.")
                    else:
                        # NOTES
                        if "anti_G_suspect" in notes:
                            st.warning("⚠️ Anti-G / Anti-D+C suspected: Pattern (Cells 1,2,3,4,8 reactive) supports Anti-G. Perform Adsorption/Elution to differentiate.")
                        if "anti-c_risk" in notes:
                            st.markdown("<div class='clinical-alert'>🛑 <b>Anti-c candidate:</b> Consider R1R1 (E- c-) units to reduce risk of Anti-E formation.</div>", unsafe_allow_html=True)

                        # CONFIRMED
                        if confirmed_sig or confirmed_ins:
                            if confirmed_sig:
                                st.success("**Confirmed (Clinically significant):** " + ", ".join([f"Anti-{x['ab']}" for x in confirmed_sig]))
                            if confirmed_ins:
                                st.info("**Confirmed (Usually insignificant/cold):** " + ", ".join([f"Anti-{x['ab']}" for x in confirmed_ins]))

                            # Show confirmation mode
                            for x in confirmed_sig + confirmed_ins:
                                mode = "Full Rule of 3" if x["status"]=="CONFIRMED_FULL" else "Modified Rule (p≤0.05 supported)"
                                st.write(f"✅ **Anti-{x['ab']}** confirmed — {mode} (P:{x['p']} / N:{x['n']})")

                        # PENDING (NOT EXCLUDED YET)  -> show as pending + plan (this is where selected cells is allowed)
                        if pending_sig or pending_ins:
                            st.warning("**Not excluded yet (needs workup / separation):** " + ", ".join([f"Anti-{x['ab']}" for x in (pending_sig+pending_ins)]))

                            st.write("---")
                            st.markdown("### 🧪 Selected Cell Strategy (ONLY when needed)")
                            for x in pending_sig + pending_ins:
                                ab = x["ab"]
                                s = strategies.get(ab, {})
                                conf = s.get("conflicts", [])
                                found = s.get("internal_cells", [])
                                enzyme_hint = s.get("enzyme_hint", None)

                                if found:
                                    hint = f"<span class='cell-hint'>{', '.join(found)}</span>"
                                else:
                                    hint = "<span style='color:red'>No suitable internal cells → Use external selected cells (different lot)</span>"

                                st.markdown(
                                    f"- **Anti-{ab}**: Need cell (**{ab}+**) and (**{' / '.join([c+'-' for c in conf])}**) {hint}",
                                    unsafe_allow_html=True
                                )

                                if enzyme_hint:
                                    st.caption("🧬 " + enzyme_hint)

                            st.caption("Note: Selected cells are suggested ONLY because the antibody is not excluded/confirmed due to interference with other unresolved candidates.")

                        # If everything pending with no confirmed and no plan -> still show candidates
                        if (not confirmed_sig and not confirmed_ins) and (not pending_sig and not pending_ins):
                            st.info("Candidates present but no conclusion could be produced. Add selected cells and re-run.")

                        # OFFICIAL REPORT: only if there is at least one confirmed significant AND no pending significant
                        if confirmed_sig and not pending_sig:
                            if st.button("Generate Official Report"):
                                sig_list = ", ".join([x["ab"] for x in confirmed_sig])
                                ins_list = ", ".join([x["ab"] for x in confirmed_ins]) if confirmed_ins else ""
                                rpt = f"""
                                <div class='print-only'>
                                <center>
                                    <h2>Maternity & Children Hospital - Tabuk</h2>
                                    <h3>Serology Report</h3>
                                </center>
                                <div class='result-sheet'>
                                    <b>Pt:</b> {nm} ({mr})<br>
                                    <b>Tech:</b> {tc} | <b>ID Panel Lot:</b> {st.session_state.lot_p} | <b>Screen Lot:</b> {st.session_state.lot_s}
                                    <hr>
                                    <b>Confirmed:</b> Anti-{sig_list}<br>
                                    {'<b>Other:</b> Anti-'+ins_list+'<br>' if ins_list else ''}
                                    <b>Method:</b> Rule of three / Modified rule (p≤0.05 supported).<br>
                                    <b>Clinical:</b> Provide antigen-negative compatible units as applicable.<br><br>
                                    <b>Consultant Verified:</b> _____________
                                </div>
                                <div class='footer-print'>Dr. Haitham Ismail | Consultant</div>
                                </div>
                                <script>window.print()</script>
                                """
                                st.markdown(rpt, unsafe_allow_html=True)

    # ----------------------------------------------------------------------
    # DAT MODULE (persistent whenever dat_mode True)
    # ----------------------------------------------------------------------
    if st.session_state.dat_mode:
        st.write("---")
        st.subheader("🧪 Monospecific DAT Workup")

        c_d1, c_d2, c_d3 = st.columns(3)
        igg = c_d1.selectbox("IgG", ["Negative","Positive"], key="dig")
        c3d = c_d2.selectbox("C3d", ["Negative","Positive"], key="dc3")
        ctl = c_d3.selectbox("Control", ["Negative","Positive"], key="dct")

        st.markdown("**Interpretation:**")
        if ctl == "Positive":
            st.error("Invalid DAT: Control Positive.")
        else:
            if igg == "Positive":
                st.warning("👉 **Mostly WAIHA** (Warm Autoimmune Hemolytic Anemia).")
                st.write("- Refer to Blood Bank Physician.")
                st.write("- Consider Elution / Adsorption (as available).")
                st.markdown(
                    "<div class='clinical-waiha'><b>⚠️ Critical:</b> If recently transfused, consider <b>DHTR</b> (Delayed Hemolytic Transfusion Reaction). Elution is strongly recommended.</div>",
                    unsafe_allow_html=True
                )
            elif c3d == "Positive" and igg == "Negative":
                st.info("👉 **Suggestive of CAS** (Cold Agglutinin Syndrome).")
                st.write("- Use Pre-warm technique.")
            else:
                st.caption("DAT interpretation depends on clinical context. If suspicion remains, refer to Blood Bank Physician.")

    # ----------------------------------------------------------------------
    # ADD SELECTED CELLS (manual library) - only when not in DAT mode
    # ----------------------------------------------------------------------
    if not st.session_state.dat_mode:
        with st.expander("➕ Add Selected Cell (From Library)"):
            id_x = st.text_input("ID")
            rs_x = st.selectbox("R", GRADES, key="exr")
            ag_col = st.columns(6)
            new_p = {}
            for i, ag in enumerate(AGS):
                new_p[ag] = 1 if ag_col[i % 6].checkbox(ag) else 0

            if st.button("Confirm Add"):
                st.session_state.ext.append({"res": normalize_grade(rs_x), "res_txt": rs_x, "ph": new_p})
                st.success("Added! Re-run Analysis.")

    if st.session_state.ext:
        st.table(pd.DataFrame(st.session_state.ext)[['res_txt']])
