import streamlit as st
import pandas as pd
from datetime import date
import json
import base64
import requests
from pathlib import Path
from itertools import combinations

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

def ensure_data_dir():
    Path("data").mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# 1) PAGE SETUP & CSS
# --------------------------------------------------------------------------
st.set_page_config(page_title="MCH Tabuk - Serology Expert", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    .hospital-logo { color: #8B0000; text-align: center; border-bottom: 5px solid #8B0000; padding-bottom: 5px; font-family: 'Arial'; }
    .lot-bar {
        display: flex; justify-content: space-around; background-color: #f1f8e9;
        border: 1px solid #81c784; padding: 8px; border-radius: 5px; margin-bottom: 20px; font-weight: bold; color: #1b5e20;
    }
    .clinical-alert { background-color: #fff3cd; border: 2px solid #ffca2c; padding: 12px; color: #000; font-weight: 600; margin: 8px 0; border-radius: 6px;}
    .clinical-danger { background-color: #f8d7da; border: 2px solid #dc3545; padding: 12px; color: #000; font-weight: 700; margin: 8px 0; border-radius: 6px;}
    .clinical-info { background-color: #cff4fc; border: 2px solid #0dcaf0; padding: 12px; color: #000; font-weight: 600; margin: 8px 0; border-radius: 6px;}
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
ENZYME_DESTROYED = ["Fya","Fyb","M","N","S","s"]

GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]
DAT_OPT = ["Not done", "Negative", "Positive"]

# --------------------------------------------------------------------------
# 3) STATE
# --------------------------------------------------------------------------
ensure_data_dir()

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

if "ext" not in st.session_state:
    st.session_state.ext = []

# DAT persistent fields (for panreactive AC+)
if "dat_igg" not in st.session_state:
    st.session_state.dat_igg = "Not done"
if "dat_c3d" not in st.session_state:
    st.session_state.dat_c3d = "Not done"
if "dat_ctrl" not in st.session_state:
    st.session_state.dat_ctrl = "Not done"

# --------------------------------------------------------------------------
# 4) PASTE PARSERS (Excel -> program)
# --------------------------------------------------------------------------
def _split_table(text: str):
    t = (text or "").strip().replace("\r\n", "\n").replace("\r", "\n")
    if not t:
        return []
    rows = [r for r in t.split("\n") if r.strip() != ""]
    table = []
    for r in rows:
        # try tab first, else comma
        if "\t" in r:
            parts = [p.strip() for p in r.split("\t")]
        else:
            parts = [p.strip() for p in r.split(",")]
        table.append(parts)
    return table

def _coerce_01_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for ag in AGS:
        if ag in out.columns:
            out[ag] = pd.to_numeric(out[ag], errors="coerce").fillna(0).astype(int).clip(0, 1)
        else:
            out[ag] = 0
    if "ID" not in out.columns:
        out.insert(0, "ID", "")
    out = out[["ID"] + AGS]
    return out

def parse_paste_to_panel_df(paste_text: str, expected_rows: int, default_ids: list) -> pd.DataFrame:
    table = _split_table(paste_text)
    if not table:
        raise ValueError("Paste area is empty.")

    # Detect header row
    header = table[0]
    has_header = any(h in AGS or h == "ID" for h in header)
    if has_header:
        df = pd.DataFrame(table[1:], columns=header)
    else:
        df = pd.DataFrame(table)

    # If IDs not provided, create them
    if "ID" in df.columns:
        pass
    else:
        # if first col looks like IDs (non 0/1 values), treat as ID column
        if df.shape[1] >= (len(AGS)+1):
            # assume first column is ID
            df.columns = ["ID"] + AGS + [f"X{i}" for i in range(df.shape[1] - (len(AGS)+1))]
        elif df.shape[1] == len(AGS):
            df.insert(0, "ID", default_ids[:len(df)])
        else:
            # if fewer columns, user probably copied only part — reject clearly
            raise ValueError(f"Paste columns are {df.shape[1]}. Expected {len(AGS)} antigens (or {len(AGS)+1} including ID).")

    # Keep only needed columns if extra
    if "ID" not in df.columns:
        df.insert(0, "ID", default_ids[:len(df)])
    keep_cols = ["ID"] + [c for c in AGS if c in df.columns]
    df = df[keep_cols].copy()

    # Ensure all antigen columns exist
    for ag in AGS:
        if ag not in df.columns:
            df[ag] = 0

    df = df[["ID"] + AGS].copy()
    df = _coerce_01_df(df)

    # row count strict
    if len(df) != expected_rows:
        raise ValueError(f"Row count mismatch: got {len(df)} rows, expected {expected_rows}.")
    # fill empty IDs if needed
    for i in range(expected_rows):
        if not str(df.loc[i, "ID"]).strip():
            df.loc[i, "ID"] = default_ids[i]
    return df

# --------------------------------------------------------------------------
# 5) HELPERS / ENGINE
# --------------------------------------------------------------------------
def normalize_grade(val) -> int:
    s = str(val).lower().strip()
    if s in ["0", "neg", "negative", "none"]:
        return 0
    return 1

def is_homozygous(ph, ag: str) -> bool:
    if ag not in DOSAGE:
        return True
    pair = PAIRS.get(ag)
    if not pair:
        return True
    return (int(ph.get(ag,0))==1 and int(ph.get(pair,0))==0)

def ph_has(ph, ag: str) -> bool:
    try:
        return int(ph.get(ag,0)) == 1
    except Exception:
        try:
            return int(ph[ag]) == 1
        except Exception:
            return False

def get_cells(in_p: dict, in_s: dict, extras: list):
    cells = []
    for i in range(1,12):
        cells.append({
            "label": f"Panel #{i}",
            "react": normalize_grade(in_p[i]),
            "ph": st.session_state.panel11_df.iloc[i-1]
        })
    sc_lbls = ["I","II","III"]
    for idx,k in enumerate(sc_lbls):
        cells.append({
            "label": f"Screen {k}",
            "react": normalize_grade(in_s[k]),
            "ph": st.session_state.screen3_df.iloc[idx]
        })
    for ex in extras:
        cells.append({
            "label": f"Selected: {ex.get('id','(no-id)')}",
            "react": int(ex.get("res",0)),
            "ph": ex.get("ph",{})
        })
    return cells

def rule_out(in_p: dict, in_s: dict, extras: list):
    ruled_out = set()
    for c in get_cells(in_p, in_s, extras):
        if c["react"] == 0:
            ph = c["ph"]
            for ag in AGS:
                if ag in IGNORED_AGS:
                    continue
                if ph_has(ph, ag) and is_homozygous(ph, ag):
                    ruled_out.add(ag)
    return ruled_out

def all_reactive_pattern(in_p: dict, in_s: dict):
    all_panel = all(normalize_grade(in_p[i])==1 for i in range(1,12))
    all_screen = all(normalize_grade(in_s[k])==1 for k in ["I","II","III"])
    return all_panel and all_screen

def combo_valid_against_negatives(combo: tuple, cells: list):
    for c in cells:
        if c["react"] == 0:
            ph = c["ph"]
            for ag in combo:
                if ph_has(ph, ag) and is_homozygous(ph, ag):
                    return False
    return True

def combo_covers_all_positives(combo: tuple, cells: list):
    for c in cells:
        if c["react"] == 1:
            ph = c["ph"]
            if not any(ph_has(ph, ag) for ag in combo):
                return False
    return True

def find_best_combo(candidates: list, cells: list, max_size: int = 3):
    cand_sig = [c for c in candidates if c not in INSIGNIFICANT_AGS]
    cand_cold = [c for c in candidates if c in INSIGNIFICANT_AGS]
    ordered = cand_sig + cand_cold

    for r in range(1, max_size+1):
        for combo in combinations(ordered, r):
            if not combo_valid_against_negatives(combo, cells):
                continue
            if not combo_covers_all_positives(combo, cells):
                continue
            return combo
    return None

def separability_map(combo: tuple, cells: list):
    sep = {}
    for ag in combo:
        other = [x for x in combo if x != ag]
        found_unique_pos = False
        for c in cells:
            if c["react"] == 1:
                ph = c["ph"]
                if ph_has(ph, ag) and all(not ph_has(ph, o) for o in other):
                    found_unique_pos = True
                    break
        sep[ag] = found_unique_pos
    return sep

def check_rule_three_only_on_discriminating(ag: str, combo: tuple, cells: list):
    other = [x for x in combo if x != ag]
    p = 0
    n = 0
    for c in cells:
        ph = c["ph"]
        ag_pos = ph_has(ph, ag)

        if c["react"] == 1:
            if ag_pos and all(not ph_has(ph, o) for o in other):
                p += 1
        else:
            if not ag_pos:
                n += 1

    full = (p >= 3 and n >= 3)
    mod  = (p >= 2 and n >= 3)
    return full, mod, p, n

def suggest_selected_cells(target: str, combo: tuple):
    others = [x for x in combo if x != target]
    out = []

    def ok(ph):
        if not ph_has(ph, target):
            return False
        for o in others:
            if ph_has(ph, o):
                return False
        return True

    for i in range(11):
        ph = st.session_state.panel11_df.iloc[i]
        if ok(ph):
            note = "OK"
            if target in DOSAGE:
                note = "Homozygous preferred" if is_homozygous(ph, target) else "Heterozygous (dosage caution)"
            out.append((f"Panel #{i+1}", note))

    sc_lbls = ["I","II","III"]
    for i in range(3):
        ph = st.session_state.screen3_df.iloc[i]
        if ok(ph):
            note = "OK"
            if target in DOSAGE:
                note = "Homozygous preferred" if is_homozygous(ph, target) else "Heterozygous (dosage caution)"
            out.append((f"Screen {sc_lbls[i]}", note))

    return out

def enzyme_hint_if_needed(targets_needing_help: list):
    hits = [x for x in targets_needing_help if x in ENZYME_DESTROYED]
    if hits:
        return f"Enzyme option may help (destroys/weakens: {', '.join(hits)}). Use only per SOP and interpret carefully."
    return None

def patient_antigen_negative_reminder(ags: list) -> str:
    if not ags:
        return ""
    bullets = "".join([f"<li>Anti-{a} → confirm patient is <b>{a}-negative</b> (phenotype/genotype; pre-transfusion sample preferred).</li>" for a in ags])
    return f"""
    <div class='clinical-alert'>
      ✅ <b>Final confirmation step</b><br>
      Verify the patient is <b>ANTIGEN-NEGATIVE</b> for the corresponding antigen(s):
      <ul style="margin-top:6px;">{bullets}</ul>
    </div>
    """

def anti_g_alert() -> str:
    return """
    <div class='clinical-alert'>
      ⚠️ <b>Anti-G consideration (D + C pattern)</b><br>
      Anti-G may mimic <b>Anti-D + Anti-C</b>. If clinically important (especially pregnancy / RhIG decision),
      do not label as true Anti-D until Anti-G is excluded per SOP / reference lab.
    </div>
    """

def dat_guidance_html(igg: str, c3d: str, ctrl: str) -> str:
    if ctrl == "Positive":
        return """
        <div class='clinical-danger'>
        ⛔ <b>DAT CONTROL POSITIVE</b> → Invalid DAT run. Repeat DAT before interpretation.
        </div>
        """
    if igg == "Not done" and c3d == "Not done":
        return ""
    if igg == "Negative" and c3d == "Negative":
        return """
        <div class='clinical-info'>
        DAT (IgG/C3d) NEGATIVE → consider non-immune causes / low-level antibody; correlate clinically.
        </div>
        """
    if igg == "Positive" and c3d == "Negative":
        return """
        <div class='clinical-alert'>
        DAT IgG POSITIVE / C3d NEGATIVE → consistent with <b>warm autoantibody</b> (WAIHA) pattern. Consider eluate / adsorption per SOP.
        </div>
        """
    if igg == "Negative" and c3d == "Positive":
        return """
        <div class='clinical-alert'>
        DAT IgG NEGATIVE / C3d POSITIVE → complement-mediated pattern (cold antibody / drug / etc.). Correlate with RT/IS reactivity and clinical context.
        </div>
        """
    if igg == "Positive" and c3d == "Positive":
        return """
        <div class='clinical-alert'>
        DAT IgG POSITIVE / C3d POSITIVE → mixed immune pattern. Consider eluate + adsorption strategy per SOP and evaluate for underlying alloantibody.
        </div>
        """
    return ""

# --------------------------------------------------------------------------
# 6) SIDEBAR
# --------------------------------------------------------------------------
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Menu", ["Workstation", "Supervisor"], key="nav_menu")
    if st.button("RESET DATA", key="btn_reset"):
        st.session_state.ext = []
        st.rerun()

# --------------------------------------------------------------------------
# 7) SUPERVISOR
# --------------------------------------------------------------------------
if nav == "Supervisor":
    st.title("Config")

    if st.text_input("Password", type="password", key="sup_pass") == "admin123":

        st.subheader("1) Lot Setup")
        c1, c2 = st.columns(2)
        lp = c1.text_input("ID Panel Lot#", value=st.session_state.lot_p, key="lot_p_in")
        ls = c2.text_input("Screen Panel Lot#", value=st.session_state.lot_s, key="lot_s_in")

        if st.button("Save Lots (Local)", key="save_lots_local"):
            st.session_state.lot_p = lp
            st.session_state.lot_s = ls
            Path("data").mkdir(exist_ok=True)
            Path("data/lots.json").write_text(json.dumps({"lot_p": lp, "lot_s": ls}, ensure_ascii=False, indent=2), encoding="utf-8")
            st.success("Saved locally. Press **Save to GitHub** to publish.")

        st.write("---")

        st.subheader("2) Paste from Excel (Fast Monthly Update) — NO CSV / NO Upload")
        st.markdown("""
- افتح الـPDF في Excel → ظلّل الجدول كله (0/1 + ID لو موجود) → **Copy**
- ارجع هنا → **Paste** → اضغط **Update**
""")

        colA, colB = st.columns(2)

        with colA:
            st.markdown("### ID Panel (11 Cells) — Paste here")
            paste_p11 = st.text_area("Paste Panel 11 table", height=220, key="paste_p11")
            if st.button("✅ Update ID Panel from Paste", use_container_width=True, key="btn_up_p11"):
                try:
                    ids = [f"C{i+1}" for i in range(11)]
                    df = parse_paste_to_panel_df(paste_p11, expected_rows=11, default_ids=ids)
                    st.session_state.panel11_df = df
                    Path("data/p11.csv").write_text(df.to_csv(index=False), encoding="utf-8")
                    st.success("ID Panel updated successfully (Local).")
                except Exception as e:
                    st.error(f"Paste/Update failed: {e}")

        with colB:
            st.markdown("### Screening Cells (3 Cells) — Paste here")
            paste_p3 = st.text_area("Paste Screening 3 table", height=220, key="paste_p3")
            if st.button("✅ Update Screening Cells from Paste", use_container_width=True, key="btn_up_p3"):
                try:
                    ids = ["SI","SII","SIII"]
                    df = parse_paste_to_panel_df(paste_p3, expected_rows=3, default_ids=ids)
                    st.session_state.screen3_df = df
                    Path("data/p3.csv").write_text(df.to_csv(index=False), encoding="utf-8")
                    st.success("Screening Cells updated successfully (Local).")
                except Exception as e:
                    st.error(f"Paste/Update failed: {e}")

        st.write("---")
        st.subheader("3) Manual Edit (Optional)")
        st.info("لو حبيت تعدّل يدويًا بدل الـPaste، استخدم الجداول دي.")

        ed1 = st.data_editor(
            st.session_state.panel11_df,
            use_container_width=True,
            num_rows="fixed",
            key="ed_panel11"
        )
        ed2 = st.data_editor(
            st.session_state.screen3_df,
            use_container_width=True,
            num_rows="fixed",
            key="ed_screen3"
        )

        ed1 = _coerce_01_df(ed1)
        ed2 = _coerce_01_df(ed2)

        c3, c4 = st.columns(2)
        if c3.button("💾 Save Edited Tables (Local)", use_container_width=True):
            st.session_state.panel11_df = ed1
            st.session_state.screen3_df = ed2
            Path("data/p11.csv").write_text(ed1.to_csv(index=False), encoding="utf-8")
            Path("data/p3.csv").write_text(ed2.to_csv(index=False), encoding="utf-8")
            st.success("Saved edited tables locally.")

        st.subheader("4) Publish to ALL devices (Save to GitHub)")
        if c4.button("💾 Save to GitHub (Commit)", use_container_width=True):
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
# 8) WORKSTATION
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
    _ = top1.text_input("Name", key="pt_name")
    _ = top2.text_input("MRN", key="pt_mrn")
    _ = top3.text_input("Tech", key="tech_nm")
    _ = top4.date_input("Date", value=date.today(), key="run_dt")

    with st.form("main_form", clear_on_submit=False):
        st.write("### Reaction Entry")
        L, R = st.columns([1, 2.5])

        with L:
            st.write("Controls")
            ac_res = st.radio("Auto Control (AC)", ["Negative", "Positive"], key="rx_ac")

            recent_tx = st.checkbox("Recent transfusion (≤ 4 weeks)?", value=False, key="recent_tx")
            if recent_tx:
                st.markdown("""
                <div class='clinical-danger'>
                🩸 <b>RECENT TRANSFUSION FLAGGED</b><br>
                ⚠️ Consider <b>DHTR</b> / anamnestic alloantibody response if clinically compatible.
                </div>
                """, unsafe_allow_html=True)

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
            in_p = {1:p1,2:p2,3:p3,4:p4,5:p5,6:p6,7:p7,8:p8,9:p9,10:p10,11:p11}
            in_s = {"I": s_I, "II": s_II, "III": s_III}

            ac_negative = (ac_res == "Negative")
            all_rx = all_reactive_pattern(in_p, in_s)

            # ------------------------------------------------------------------
            # PAN-REACTIVE PATHWAYS (as requested)
            # ------------------------------------------------------------------
            if all_rx and ac_negative:
                st.markdown("""
                <div class='clinical-danger'>
                ⚠️ <b>PAN-REACTIVE (ALL CELLS POSITIVE) with NEGATIVE AUTOCONTROL</b><br>
                Most consistent with <b>Antibody to High-Incidence (High-Frequency) Antigen</b> (± multiple alloantibodies – rare).<br><br>
                <b>Action:</b>
                <ol>
                  <li><b>STOP</b> routine rule-out / single-specificity interpretation.</li>
                  <li><b>Refer to Blood Bank Physician</b> / Reference Laboratory.</li>
                  <li>Consider patient phenotype/genotype; compatible unit search.</li>
                  <li>If urgent: investigate rare compatible donors (including <b>first-degree relatives</b>) per policy/regulations.</li>
                </ol>
                </div>
                """, unsafe_allow_html=True)

            elif all_rx and (not ac_negative):
                st.markdown("""
                <div class='clinical-danger'>
                ⚠️ <b>PAN-REACTIVE (ALL CELLS POSITIVE) with POSITIVE AUTOCONTROL</b><br>
                Suggests <b>autoantibody / WAIHA</b> until proven otherwise. Perform <b>Monospecific DAT</b> first.
                </div>
                """, unsafe_allow_html=True)

                st.markdown("### Monospecific DAT (Enter results)")
                d1, d2, d3 = st.columns(3)
                st.session_state.dat_igg = d1.selectbox("DAT IgG", DAT_OPT, key="dat_igg_key")
                st.session_state.dat_c3d = d2.selectbox("DAT C3d", DAT_OPT, key="dat_c3d_key")
                st.session_state.dat_ctrl = d3.selectbox("DAT Control", DAT_OPT, key="dat_ctrl_key")
                st.markdown(dat_guidance_html(st.session_state.dat_igg, st.session_state.dat_c3d, st.session_state.dat_ctrl),
                            unsafe_allow_html=True)

                st.markdown("""
                <div class='clinical-info'>
                🔎 <b>Note:</b> Routine specificity engine is <b>paused</b> in pan-reactive cases. Complete DAT/eluate/adsorption workflow per SOP.
                </div>
                """, unsafe_allow_html=True)

            # If pan-reactive → stop normal algorithm
            if all_rx:
                pass
            else:
                # ------------------------------
                # Normal algorithm
                # ------------------------------
                cells = get_cells(in_p, in_s, st.session_state.ext)
                ruled = rule_out(in_p, in_s, st.session_state.ext)
                candidates = [a for a in AGS if a not in ruled and a not in IGNORED_AGS]
                best = find_best_combo(candidates, cells, max_size=3)

                st.subheader("Conclusion (Step 1: Rule-out / Rule-in)")

                if not best:
                    st.error("No resolved specificity from current data. Proceed with Selected Cells / Enhancement.")
                    poss_sig = [a for a in candidates if a not in INSIGNIFICANT_AGS][:12]
                    poss_cold = [a for a in candidates if a in INSIGNIFICANT_AGS][:6]
                    if poss_sig or poss_cold:
                        st.markdown("### ⚠️ Not excluded yet (Needs more work — DO NOT confirm now):")
                        if poss_sig:
                            st.write("**Clinically significant possibilities:** " + ", ".join([f"Anti-{x}" for x in poss_sig]))
                        if poss_cold:
                            st.info("Cold/Insignificant possibilities: " + ", ".join([f"Anti-{x}" for x in poss_cold]))
                else:
                    sep_map = separability_map(best, cells)
                    resolved = [a for a in best if sep_map.get(a, False)]
                    needs_work = [a for a in best if not sep_map.get(a, False)]

                    if resolved:
                        st.success("Resolved (pattern explained & separable): " + ", ".join([f"Anti-{a}" for a in resolved]))
                    if needs_work:
                        st.warning("Pattern suggests these, but NOT separable yet (DO NOT confirm): " +
                                   ", ".join([f"Anti-{a}" for a in needs_work]))

                    remaining_other = [a for a in candidates if a not in best]
                    other_sig = [a for a in remaining_other if a not in INSIGNIFICANT_AGS][:10]
                    other_cold = [a for a in remaining_other if a in INSIGNIFICANT_AGS][:6]
                    if other_sig or other_cold:
                        st.markdown("### ⚠️ Not excluded yet (background possibilities):")
                        if other_sig:
                            st.write("**Clinically significant:** " + ", ".join([f"Anti-{x}" for x in other_sig]))
                        if other_cold:
                            st.info("Cold/Insignificant: " + ", ".join([f"Anti-{x}" for x in other_cold]))

                    # Rule of three
                    st.write("---")
                    st.subheader("Confirmation (Rule of Three) — Resolved & Separable only")

                    confirmed = []
                    if not resolved:
                        st.info("No antibody is separable yet → DO NOT apply Rule of Three. Add discriminating selected cells.")
                    else:
                        for a in resolved:
                            full, mod, p_cnt, n_cnt = check_rule_three_only_on_discriminating(a, best, cells)
                            if full:
                                st.write(f"✅ **Anti-{a} CONFIRMED**: Full Rule (3+3) met on discriminating cells (P:{p_cnt} / N:{n_cnt})")
                                confirmed.append(a)
                            elif mod:
                                st.write(f"✅ **Anti-{a} CONFIRMED**: Modified Rule (2+3) met on discriminating cells (P:{p_cnt} / N:{n_cnt})")
                                confirmed.append(a)
                            else:
                                st.write(f"⚠️ **Anti-{a} NOT confirmed yet**: need more discriminating cells (P:{p_cnt} / N:{n_cnt})")

                    # Patient antigen-negative reminder (for confirmed only)
                    if confirmed:
                        st.markdown(patient_antigen_negative_reminder(confirmed), unsafe_allow_html=True)

                    # Anti-G alert if D + C pattern is present (D resolved/confirmed + C not excluded or present)
                    if ("D" in resolved or "D" in confirmed) and ("C" in candidates or "C" in remaining_other or "C" in best):
                        st.markdown(anti_g_alert(), unsafe_allow_html=True)

                    # Selected cells suggestions (ONLY if needed)
                    st.write("---")
                    targets_needing_selected = needs_work[:]  # interference only
                    if targets_needing_selected:
                        st.markdown("### 🧪 Selected Cells (Only if needed to resolve interference / confirm)")
                        for a in targets_needing_selected:
                            st.warning(f"Anti-{a}: need {a}+ cells that are NEGATIVE for other antibodies in the combo.")
                            sugg = suggest_selected_cells(a, best)
                            if sugg:
                                for lab, note in sugg[:12]:
                                    st.write(f"- {lab}  <span class='cell-hint'>{note}</span>", unsafe_allow_html=True)
                            else:
                                st.write(f"- No suitable discriminating cell in current inventory → use another lot / external selected cells.")
                        enz = enzyme_hint_if_needed(targets_needing_selected)
                        if enz:
                            st.info("💡 " + enz)
                    else:
                        st.success("No Selected Cells needed based on current data.")

    # Selected cells library input
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
