import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import json
import base64
import requests
from pathlib import Path
from itertools import combinations
import hashlib

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
# 0.1) LOCAL HISTORY ENGINE (Simple internal storage: data/cases.csv)
# --------------------------------------------------------------------------
CASES_PATH = "data/cases.csv"
HISTORY_MAX_ROWS = 200000
DUPLICATE_WINDOW_MINUTES = 10

HISTORY_COLUMNS = [
    "case_id", "saved_at",
    "mrn", "name", "tech",
    "sex", "age_y", "age_m", "age_d",
    "run_dt",
    "lot_p", "lot_s",
    "ac_res", "recent_tx",
    "all_rx",
    "dat_igg", "dat_c3d", "dat_ctl",
    "abo_card", "abo_json",
    "phenotype_json",
    "conclusion_short",
    "fingerprint",
    "summary_json"
]

def _safe_str(x):
    return "" if x is None else str(x).strip()

def _ensure_data_folder():
    Path("data").mkdir(exist_ok=True)

def _now_ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _parse_dt(s: str):
    try:
        return datetime.strptime(str(s), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None

def _make_fingerprint(obj: dict) -> str:
    txt = json.dumps(obj, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(txt.encode("utf-8")).hexdigest()

def load_cases_df() -> pd.DataFrame:
    _ensure_data_folder()
    default = pd.DataFrame(columns=HISTORY_COLUMNS)
    df = load_csv_if_exists(CASES_PATH, default)
    for col in HISTORY_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[HISTORY_COLUMNS]

def save_cases_df(df: pd.DataFrame):
    _ensure_data_folder()
    df.to_csv(CASES_PATH, index=False)

def append_case_record(rec: dict):
    df = load_cases_df()
    fp = _safe_str(rec.get("fingerprint", ""))

    if fp:
        same = df[df["fingerprint"].astype(str) == fp]
        if len(same) > 0:
            try:
                same2 = same.copy()
                same2["__dt"] = same2["saved_at"].apply(_parse_dt)
                same2 = same2.dropna(subset=["__dt"]).sort_values("__dt", ascending=False)
                if len(same2) > 0:
                    last_dt = same2.iloc[0]["__dt"]
                    if last_dt and datetime.now() - last_dt <= timedelta(minutes=DUPLICATE_WINDOW_MINUTES):
                        return (False, f"Duplicate detected: identical record already saved within last {DUPLICATE_WINDOW_MINUTES} minutes.")
            except Exception:
                pass

    df2 = pd.concat([df, pd.DataFrame([rec])], ignore_index=True)

    try:
        df2["saved_at"] = df2["saved_at"].astype(str)
        df2 = df2.sort_values("saved_at", ascending=False).head(HISTORY_MAX_ROWS)
    except Exception:
        pass

    save_cases_df(df2)
    return (True, "Saved")

def find_case_history(df: pd.DataFrame, mrn: str = "", name: str = "") -> pd.DataFrame:
    mrn = _safe_str(mrn)
    name = _safe_str(name).lower()

    out = df.iloc[0:0]
    if mrn:
        out = df[df["mrn"].astype(str) == mrn]
    elif name:
        out = df[df["name"].astype(str).str.lower().str.contains(name, na=False)]

    try:
        out = out.sort_values("saved_at", ascending=False)
    except Exception:
        pass
    return out

def build_case_record(
    pt_name: str,
    pt_mrn: str,
    tech: str,
    sex: str,
    age_y: int,
    age_m: int,
    age_d: int,
    run_dt: date,
    lot_p: str,
    lot_s: str,
    ac_res: str,
    recent_tx: bool,
    in_p: dict,
    in_s: dict,
    ext: list,
    all_rx: bool,
    dat_igg: str = "",
    dat_c3d: str = "",
    dat_ctl: str = "",
    abo_card: str = "",
    abo_obj: dict = None,
    phenotype_obj: dict = None,
    conclusion_short: str = "",
    details: dict = None
) -> dict:
    saved_at = _now_ts()
    run_dt_str = str(run_dt)

    mrn = _safe_str(pt_mrn)
    name = _safe_str(pt_name)
    tech = _safe_str(tech)
    sex = _safe_str(sex)

    case_id = f"{mrn}_{saved_at}".replace(" ", "_").replace(":", "-")

    payload = {
        "patient": {
            "name": name,
            "mrn": mrn,
            "sex": sex,
            "age": {"years": int(age_y or 0), "months": int(age_m or 0), "days": int(age_d or 0)}
        },
        "tech": tech,
        "run_dt": run_dt_str,
        "saved_at": saved_at,
        "lots": {"panel": lot_p, "screen": lot_s},
        "inputs": {"panel_reactions": in_p, "screen_reactions": in_s, "AC": ac_res, "recent_tx": bool(recent_tx)},
        "all_rx": bool(all_rx),
        "dat": {"igg": dat_igg, "c3d": dat_c3d, "control": dat_ctl},
        "abo": {"card": _safe_str(abo_card), "results": (abo_obj or {})},
        "phenotype": (phenotype_obj or {}),
        "selected_cells": ext,
        "interpretation": details or {}
    }

    fp_obj = {
        "mrn": mrn,
        "run_dt": run_dt_str,
        "lots": {"panel": lot_p, "screen": lot_s},
        "inputs": {"panel_reactions": in_p, "screen_reactions": in_s, "AC": ac_res, "recent_tx": bool(recent_tx)},
        "all_rx": bool(all_rx),
        "dat": {"igg": dat_igg, "c3d": dat_c3d, "control": dat_ctl},
        "abo": {"card": _safe_str(abo_card), "results": (abo_obj or {})},
        "phenotype": (phenotype_obj or {}),
        "selected_cells": ext,
        "interpretation": details or {},
        "conclusion_short": _safe_str(conclusion_short)
    }
    fingerprint = _make_fingerprint(fp_obj)

    return {
        "case_id": case_id,
        "saved_at": saved_at,
        "mrn": mrn,
        "name": name,
        "tech": tech,
        "sex": sex,
        "age_y": int(age_y or 0),
        "age_m": int(age_m or 0),
        "age_d": int(age_d or 0),
        "run_dt": run_dt_str,
        "lot_p": lot_p,
        "lot_s": lot_s,
        "ac_res": ac_res,
        "recent_tx": bool(recent_tx),
        "all_rx": bool(all_rx),
        "dat_igg": dat_igg,
        "dat_c3d": dat_c3d,
        "dat_ctl": dat_ctl,
        "abo_card": _safe_str(abo_card),
        "abo_json": json.dumps(abo_obj or {}, ensure_ascii=False),
        "phenotype_json": json.dumps(phenotype_obj or {}, ensure_ascii=False),
        "conclusion_short": _safe_str(conclusion_short),
        "fingerprint": fingerprint,
        "summary_json": json.dumps(payload, ensure_ascii=False)
    }

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

    .report-card {
        border: 2px solid #8B0000;
        border-radius: 12px;
        padding: 14px 16px;
        background: #fff;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        margin-top: 10px;
        margin-bottom: 12px;
    }
    .report-title {
        font-size: 20px;
        font-weight: 800;
        color: #8B0000;
        margin-bottom: 2px;
    }
    .report-sub {
        color: #555;
        font-size: 12px;
        margin-bottom: 10px;
    }
    .kv {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 10px;
        padding: 10px 12px;
        height: 100%;
    }
    .kv b { color: #111; }
    .chip {
        display:inline-block;
        padding: 3px 8px;
        border-radius: 999px;
        font-weight: 700;
        font-size: 12px;
        margin-right: 6px;
        margin-bottom: 6px;
        border: 1px solid #ddd;
        background:#fafafa;
    }
    .chip-danger{ border-color:#dc3545; color:#a40012; background:#fff0f2;}
    .chip-ok{ border-color:#198754; color:#0f5132; background:#ecf7f0;}
    .chip-warn{ border-color:#ffca2c; color:#7a5a00; background:#fff9e6;}

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
# 2) CONSTANTS
# --------------------------------------------------------------------------
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

IGNORED_AGS = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"]
INSIGNIFICANT_AGS = ["Lea", "Lua", "Leb", "P1"]
ENZYME_DESTROYED = ["Fya","Fyb","M","N","S","s"]

GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]
YN3 = ["Not Done", "Negative", "Positive"]

# ABO / Grouping grades (include MF + Not Done)
ABO_GRADES = ["Not Done", "0", "+1", "+2", "+3", "+4", "Mixed Field", "Hemolysis"]
SEX_OPTS = ["", "M", "F"]
DETECT3 = ["Not Done", "Detected", "Not Detected"]

# Phenotype structure
RH_MAIN = ["C", "c", "E", "e", "K", "Control"]
EXT_1 = ["P1", "Lea", "Leb", "Lua", "Lub", "Control"]
EXT_2 = ["k", "Kpa", "Kpb", "Jka", "Jkb", "Control"]
EXT_3 = ["M", "N", "S", "s", "Fya", "Fyb"]

# --------------------------------------------------------------------------
# 3) STATE
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

if "ext" not in st.session_state:
    st.session_state.ext = []

if "analysis_ready" not in st.session_state:
    st.session_state.analysis_ready = False
if "analysis_payload" not in st.session_state:
    st.session_state.analysis_payload = None
if "show_dat" not in st.session_state:
    st.session_state.show_dat = False

# New patient profile defaults
if "pt_sex" not in st.session_state:
    st.session_state.pt_sex = ""
if "age_y" not in st.session_state:
    st.session_state.age_y = 0
if "age_m" not in st.session_state:
    st.session_state.age_m = 0
if "age_d" not in st.session_state:
    st.session_state.age_d = 0

# --------------------------------------------------------------------------
# 4) HELPERS / ENGINE
# --------------------------------------------------------------------------
def normalize_grade(val) -> int:
    s = str(val).lower().strip()
    if s in ["0", "neg", "negative", "none", "not done", "nd", "n/d"]:
        return 0
    if "mixed" in s:
        return 1
    if "hemo" in s:
        return 1
    return 1

def is_homozygous(ph, ag: str) -> bool:
    if ag not in DOSAGE:
        return True
    pair = PAIRS.get(ag)
    if not pair:
        return True
    return (ph.get(ag,0)==1 and ph.get(pair,0)==0)

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
        found_unique = False
        for c in cells:
            if c["react"] == 1:
                ph = c["ph"]
                if ph_has(ph, ag) and all(not ph_has(ph, o) for o in other):
                    found_unique = True
                    break
        sep[ag] = found_unique
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

def suggest_selected_cells(target: str, other_set: list):
    others = [x for x in other_set if x != target]
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

def discriminating_cells_for(target: str, active_not_excluded: set, cells: list):
    others = [x for x in active_not_excluded if x != target]
    disc = []
    for c in cells:
        ph = c["ph"]
        if not ph_has(ph, target):
            continue
        if any(ph_has(ph, o) for o in others):
            continue
        disc.append(c)
    return disc

def background_auto_resolution(background_list: list, active_not_excluded: set, cells: list):
    auto_ruled_out = {}
    supported = {}
    inconclusive = {}
    no_disc = []

    for ag in background_list:
        disc = discriminating_cells_for(ag, active_not_excluded, cells)
        if not disc:
            no_disc.append(ag)
            continue

        pos = [c for c in disc if c["react"] == 1]
        neg = [c for c in disc if c["react"] == 0]

        if pos and neg:
            inconclusive[ag] = [c["label"] for c in disc]
        elif pos:
            supported[ag] = [c["label"] for c in pos]
        else:
            auto_ruled_out[ag] = [c["label"] for c in neg]

    return auto_ruled_out, supported, inconclusive, no_disc

def patient_antigen_negative_reminder(antibodies: list, strong: bool = True) -> str:
    if not antibodies:
        return ""

    uniq = []
    for a in antibodies:
        if a and a not in uniq:
            uniq.append(a)

    uniq = [a for a in uniq if a not in IGNORED_AGS]
    if not uniq:
        return ""

    title = "✅ Final confirmation step (Patient antigen check)" if strong else "⚠️ Before final reporting (Patient antigen check)"
    box_class = "clinical-danger" if strong else "clinical-alert"
    intro = ("Confirm the patient is <b>ANTIGEN-NEGATIVE</b> for the corresponding antigen(s) to support the antibody identification."
             if strong else
             "Before you finalize/report, confirm the patient is <b>ANTIGEN-NEGATIVE</b> for the corresponding antigen(s).")

    bullets = "".join([f"<li>Anti-{ag} → verify patient is <b>{ag}-negative</b> (phenotype/genotype; pre-transfusion sample preferred).</li>" for ag in uniq])

    return f"""
    <div class='{box_class}'>
      <b>{title}</b><br>
      {intro}
      <ul style="margin-top:6px;">
        {bullets}
      </ul>
    </div>
    """

def anti_g_alert_html(strong: bool = False) -> str:
    box = "clinical-danger" if strong else "clinical-alert"
    return f"""
    <div class='{box}'>
      ⚠️ <b>Consider Anti-G (D + C pattern)</b><br>
      Anti-G may mimic <b>Anti-D + Anti-C</b>. If clinically relevant (especially pregnancy / RhIG decision), do not label as true Anti-D until Anti-G is excluded.<br>
      <b>Suggested next steps (per SOP/reference lab):</b>
      <ol style="margin-top:6px;">
        <li>Assess if this impacts management (e.g., RhIG eligibility).</li>
        <li>Perform differential workup using appropriate adsorption/elution strategy (D+ C− and D− C+ cells) if available, or refer to reference lab.</li>
        <li>Use pre-transfusion sample when possible.</li>
      </ol>
    </div>
    """

def _age_days(y: int, m: int, d: int) -> int:
    try:
        y = int(y or 0); m = int(m or 0); d = int(d or 0)
        return y*365 + m*30 + d
    except Exception:
        return 0

def _phenotype_conflict_alert(antibodies: list, ph_obj: dict):
    # If antibody Anti-X exists but phenotype says X Detected, flag.
    if not antibodies or not isinstance(ph
