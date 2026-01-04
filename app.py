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
# 0) GitHub Save/Read Engine (uses Streamlit Secrets)
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

def github_read_file(path_in_repo: str) -> str | None:
    """
    Reads a file from GitHub. Returns text or None if not found.
    Works for small/medium files via contents API; falls back to download_url if provided.
    """
    token, repo, branch = _gh_get_cfg()
    if not token or not repo:
        return None

    api = f"https://api.github.com/repos/{repo}/contents/{path_in_repo}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}

    r = requests.get(api, headers=headers, params={"ref": branch}, timeout=30)
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise RuntimeError(f"GitHub READ error {r.status_code}: {r.text}")

    js = r.json()
    if isinstance(js, dict) and js.get("type") == "file":
        # Prefer base64 content if available
        if "content" in js and js.get("encoding") == "base64":
            raw = base64.b64decode(js["content"]).decode("utf-8", errors="replace")
            return raw
        # Fallback to download_url
        dl = js.get("download_url")
        if dl:
            rr = requests.get(dl, headers=headers, timeout=30)
            if rr.status_code == 200:
                return rr.text
            raise RuntimeError(f"GitHub download_url error {rr.status_code}: {rr.text}")
    return None

def github_list_dir(path_in_repo: str) -> list[str]:
    """
    Lists files in a GitHub directory. Returns list of paths.
    """
    token, repo, branch = _gh_get_cfg()
    if not token or not repo:
        return []

    api = f"https://api.github.com/repos/{repo}/contents/{path_in_repo}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}

    r = requests.get(api, headers=headers, params={"ref": branch}, timeout=30)
    if r.status_code == 404:
        return []
    if r.status_code != 200:
        raise RuntimeError(f"GitHub LIST error {r.status_code}: {r.text}")

    js = r.json()
    if isinstance(js, list):
        return [x.get("path") for x in js if isinstance(x, dict) and x.get("type") == "file"]
    return []

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
# 0.1) HISTORY ENGINE (GitHub-backed, large capacity via monthly partition)
# --------------------------------------------------------------------------
HISTORY_DIR_GH = "data/history"     # monthly files stored here on GitHub
HISTORY_LOCAL_CACHE = "data/cases_cache.csv"  # optional local cache (safe fallback)
HISTORY_MAX_MONTH_FILES_TO_SEARCH = 48        # search across last up to 48 files (4 years)

DUPLICATE_WINDOW_MINUTES = 10

HISTORY_COLUMNS = [
    "case_id", "saved_at",
    "mrn", "name", "sex", "age_y", "age_m", "age_d",
    "tech", "run_dt",
    "lot_p", "lot_s",
    "ac_res", "recent_tx",
    "all_rx",
    "dat_igg", "dat_c3d", "dat_ctl",
    "conclusion_short",
    "fingerprint",
    "summary_json"
]

def _safe_str(x):
    return "" if x is None else str(x).strip()

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

def _current_month_tag(d: date | None = None) -> str:
    d = d or date.today()
    return f"{d.year:04d}-{d.month:02d}"

def _gh_month_file(tag: str) -> str:
    return f"{HISTORY_DIR_GH}/{tag}.csv"

def _df_ensure_cols(df: pd.DataFrame) -> pd.DataFrame:
    for col in HISTORY_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[HISTORY_COLUMNS]

def load_month_df_from_github(tag: str) -> pd.DataFrame:
    default = pd.DataFrame(columns=HISTORY_COLUMNS)
    path = _gh_month_file(tag)
    txt = github_read_file(path)
    if not txt:
        return default
    try:
        from io import StringIO
        df = pd.read_csv(StringIO(txt))
        return _df_ensure_cols(df)
    except Exception:
        return default

def save_month_df_to_github(tag: str, df: pd.DataFrame):
    df = _df_ensure_cols(df)
    path = _gh_month_file(tag)
    github_upsert_file(path, df.to_csv(index=False), f"Append history ({tag})")

def load_all_history_df() -> pd.DataFrame:
    """
    Loads history from GitHub monthly files (most recent first).
    Falls back to local cache if GitHub is not configured.
    """
    # If GitHub config missing, fallback to local
    token, repo, _ = _gh_get_cfg()
    if not token or not repo:
        default = pd.DataFrame(columns=HISTORY_COLUMNS)
        df = load_csv_if_exists(HISTORY_LOCAL_CACHE, default)
        return _df_ensure_cols(df)

    try:
        files = github_list_dir(HISTORY_DIR_GH)
        # Extract tags from filenames like data/history/YYYY-MM.csv
        tags = []
        for p in files:
            name = p.split("/")[-1]
            if name.endswith(".csv") and len(name) >= 11:
                tag = name.replace(".csv", "")
                # crude validation YYYY-MM
                if len(tag) == 7 and tag[4] == "-":
                    tags.append(tag)
        tags = sorted(tags, reverse=True)[:HISTORY_MAX_MONTH_FILES_TO_SEARCH]

        all_dfs = []
        for tag in tags:
            dfm = load_month_df_from_github(tag)
            if len(dfm) > 0:
                all_dfs.append(dfm)

        if not all_dfs:
            return pd.DataFrame(columns=HISTORY_COLUMNS)

        df = pd.concat(all_dfs, ignore_index=True)
        df = _df_ensure_cols(df)

        # Update local cache (best-effort)
        try:
            Path("data").mkdir(exist_ok=True)
            df.to_csv(HISTORY_LOCAL_CACHE, index=False)
        except Exception:
            pass

        return df
    except Exception:
        # fallback to local cache
        default = pd.DataFrame(columns=HISTORY_COLUMNS)
        df = load_csv_if_exists(HISTORY_LOCAL_CACHE, default)
        return _df_ensure_cols(df)

def append_case_record(rec: dict):
    """
    Appends a case record into the current month GitHub file.
    Duplicate suppression only if identical fingerprint saved within last N minutes.
    """
    # If GitHub not configured, fallback to local cache only
    token, repo, _ = _gh_get_cfg()
    use_github = bool(token and repo)

    tag = _current_month_tag(date.today())
    df_month = load_month_df_from_github(tag) if use_github else pd.DataFrame(columns=HISTORY_COLUMNS)
    df_month = _df_ensure_cols(df_month)

    fp = _safe_str(rec.get("fingerprint", ""))

    if fp and len(df_month) > 0:
        same = df_month[df_month["fingerprint"].astype(str) == fp]
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

    df2 = pd.concat([df_month, pd.DataFrame([rec])], ignore_index=True)
    df2 = _df_ensure_cols(df2)

    # Sort month file by saved_at (desc) best-effort
    try:
        df2["saved_at"] = df2["saved_at"].astype(str)
        df2 = df2.sort_values("saved_at", ascending=False)
    except Exception:
        pass

    if use_github:
        save_month_df_to_github(tag, df2)

        # Update local cache too (best-effort)
        try:
            df_all = load_all_history_df()
            df_all = pd.concat([df_all, pd.DataFrame([rec])], ignore_index=True)
            df_all = _df_ensure_cols(df_all)
            df_all.to_csv(HISTORY_LOCAL_CACHE, index=False)
        except Exception:
            pass
    else:
        # local only
        Path("data").mkdir(exist_ok=True)
        df2.to_csv(HISTORY_LOCAL_CACHE, index=False)

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
    pt_sex: str,
    age_y: int,
    age_m: int,
    age_d: int,
    tech: str,
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
    conclusion_short: str = "",
    details: dict = None
) -> dict:
    saved_at = _now_ts()
    run_dt_str = str(run_dt)

    mrn = _safe_str(pt_mrn)
    name = _safe_str(pt_name)
    sex = _safe_str(pt_sex) if _safe_str(pt_sex) else ""
    tech = _safe_str(tech)

    try:
        age_y = int(age_y)
    except Exception:
        age_y = 0
    try:
        age_m = int(age_m)
    except Exception:
        age_m = 0
    try:
        age_d = int(age_d)
    except Exception:
        age_d = 0

    case_id = f"{mrn}_{saved_at}".replace(" ", "_").replace(":", "-")

    payload = {
        "patient": {"name": name, "mrn": mrn, "sex": sex, "age": {"y": age_y, "m": age_m, "d": age_d}},
        "tech": tech,
        "run_dt": run_dt_str,
        "saved_at": saved_at,
        "lots": {"panel": lot_p, "screen": lot_s},
        "inputs": {"panel_reactions": in_p, "screen_reactions": in_s, "AC": ac_res, "recent_tx": bool(recent_tx)},
        "all_rx": bool(all_rx),
        "dat": {"igg": dat_igg, "c3d": dat_c3d, "control": dat_ctl},
        "selected_cells": ext,
        "interpretation": details or {}
    }

    fp_obj = {
        "mrn": mrn,
        "sex": sex,
        "age": {"y": age_y, "m": age_m, "d": age_d},
        "run_dt": run_dt_str,
        "lots": {"panel": lot_p, "screen": lot_s},
        "inputs": {"panel_reactions": in_p, "screen_reactions": in_s, "AC": ac_res, "recent_tx": bool(recent_tx)},
        "all_rx": bool(all_rx),
        "dat": {"igg": dat_igg, "c3d": dat_c3d, "control": dat_ctl},
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
        "sex": sex,
        "age_y": age_y,
        "age_m": age_m,
        "age_d": age_d,
        "tech": tech,
        "run_dt": run_dt_str,
        "lot_p": lot_p,
        "lot_s": lot_s,
        "ac_res": ac_res,
        "recent_tx": bool(recent_tx),
        "all_rx": bool(all_rx),
        "dat_igg": dat_igg,
        "dat_c3d": dat_c3d,
        "dat_ctl": dat_ctl,
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

# --------------------------------------------------------------------------
# 3) STATE
# --------------------------------------------------------------------------
default_panel11_df = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
default_screen3_df = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])

Path("data").mkdir(exist_ok=True)

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

# patient header defaults (ensures RESET always works)
for k, v in {
    "pt_name": "",
    "pt_mrn": "",
    "pt_sex": "M",
    "age_y": 0,
    "age_m": 0,
    "age_d": 0,
    "tech_nm": "",
    "run_dt": date.today(),
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# --------------------------------------------------------------------------
# 4) HELPERS / ENGINE
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

# --------------------------------------------------------------------------
# 4.6) HISTORY REPORT RENDERER (Professional view instead of JSON)
# --------------------------------------------------------------------------
def _as_list(x):
    return x if isinstance(x, list) else []

def _fmt_antibody_list(lst):
    lst = [a for a in _as_list(lst) if a]
    if not lst:
        return "—"
    return ", ".join([f"Anti-{a}" for a in lst])

def render_history_report(payload: dict):
    patient = payload.get("patient", {}) or {}
    lots = payload.get("lots", {}) or {}
    inputs = payload.get("inputs", {}) or {}
    dat = payload.get("dat", {}) or {}
    interp = payload.get("interpretation", {}) or {}
    selected = payload.get("selected_cells", []) or []

    name = _safe_str(patient.get("name",""))
    mrn  = _safe_str(patient.get("mrn",""))
    sex  = _safe_str(patient.get("sex",""))
    age  = patient.get("age", {}) or {}
    age_y = _safe_str(age.get("y",""))
    age_m = _safe_str(age.get("m",""))
    age_d = _safe_str(age.get("d",""))

    tech = _safe_str(payload.get("tech",""))
    run_dt = _safe_str(payload.get("run_dt",""))
    saved_at = _safe_str(payload.get("saved_at",""))

    ac = _safe_str(inputs.get("AC",""))
    recent_tx = bool(inputs.get("recent_tx", False))
    all_rx = bool(payload.get("all_rx", False))

    lot_p = _safe_str(lots.get("panel",""))
    lot_s = _safe_str(lots.get("screen",""))

    # Chips (flags)
    chips = []
    chips.append(f"<span class='chip chip-ok'>AC: {ac or '—'}</span>")
    chips.append(f"<span class='chip {'chip-danger' if all_rx else 'chip-ok'}'>Pattern: {'PAN-reactive' if all_rx else 'Non-pan'}</span>")
    if recent_tx:
        chips.append("<span class='chip chip-danger'>Recent transfusion ≤ 4 weeks</span>")
    else:
        chips.append("<span class='chip chip-ok'>No recent transfusion flag</span>")

    # DAT chips
    dat_igg = _safe_str(dat.get("igg",""))
    dat_c3d = _safe_str(dat.get("c3d",""))
    dat_ctl = _safe_str(dat.get("control",""))
    if dat_igg or dat_c3d or dat_ctl:
        chips.append(f"<span class='chip chip-warn'>DAT IgG: {dat_igg or '—'}</span>")
        chips.append(f"<span class='chip chip-warn'>DAT C3d: {dat_c3d or '—'}</span>")
        chips.append(f"<span class='chip chip-warn'>DAT Control: {dat_ctl or '—'}</span>")

    st.markdown(f"""
    <div class="report-card">
        <div class="report-title">Antibody Identification — History Report</div>
        <div class="report-sub">Saved at: <b>{saved_at or '—'}</b> &nbsp;|&nbsp; Run Date: <b>{run_dt or '—'}</b></div>
        <div>{''.join(chips)}</div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"<div class='kv'><b>Patient Name</b><br>{name or '—'}</div>", unsafe_allow_html=True)
    with c2:
        st.markdown(f"<div class='kv'><b>MRN</b><br>{mrn or '—'}</div>", unsafe_allow_html=True)
    with c3:
        st.markdown(f"<div class='kv'><b>Sex</b><br>{sex or '—'}</div>", unsafe_allow_html=True)
    with c4:
        st.markdown(f"<div class='kv'><b>Age (Y/M/D)</b><br>{age_y or '0'} / {age_m or '0'} / {age_d or '0'}</div>", unsafe_allow_html=True)

    st.write("")
    a1, a2, a3 = st.columns(3)
    with a1:
        st.markdown(f"<div class='kv'><b>Tech / Operator</b><br>{tech or '—'}</div>", unsafe_allow_html=True)
    with a2:
        st.markdown(f"<div class='kv'><b>ID Panel Lot</b><br>{lot_p or '—'}</div>", unsafe_allow_html=True)
    with a3:
        st.markdown(f"<div class='kv'><b>Screen Lot</b><br>{lot_s or '—'}</div>", unsafe_allow_html=True)

    # Reactions
    st.write("")
    st.subheader("Reactions Summary")

    screen_rx = inputs.get("screen_reactions", {}) or {}
    panel_rx  = inputs.get("panel_reactions", {}) or {}

    sr_df = pd.DataFrame([{
        "Screen I": screen_rx.get("I",""),
        "Screen II": screen_rx.get("II",""),
        "Screen III": screen_rx.get("III",""),
    }])
    st.markdown("**Screening Cells**")
    st.dataframe(sr_df, use_container_width=True)

    pr_rows = []
    for i in range(1, 12):
        pr_rows.append({"Cell": f"Panel #{i}", "Reaction": panel_rx.get(str(i), panel_rx.get(i, ""))})
    pr_df = pd.DataFrame(pr_rows)
    st.markdown("**Panel Cells (1–11)**")
    st.dataframe(pr_df, use_container_width=True)

    # Interpretation
    st.write("")
    st.subheader("Interpretation / Results")

    pattern = _safe_str(interp.get("pattern",""))
    if pattern:
        st.info(f"Pattern pathway: {pattern}")

    best_combo = interp.get("best_combo", None)
    if best_combo is not None:
        st.markdown("**Primary Suggested Combination (best fit)**")
        st.write(_fmt_antibody_list(best_combo))

    confirmed = interp.get("confirmed", [])
    resolved  = interp.get("resolved", [])
    needs_work = interp.get("needs_work", [])
    supported_bg = interp.get("supported_bg", [])
    not_ex_sig = interp.get("not_excluded_sig", [])
    not_ex_cold = interp.get("not_excluded_cold", [])
    no_disc = interp.get("no_discriminating", [])

    b1, b2, b3 = st.columns(3)
    with b1:
        st.markdown(f"<div class='kv'><b>Confirmed</b><br>{_fmt_antibody_list(confirmed)}</div>", unsafe_allow_html=True)
    with b2:
        st.markdown(f"<div class='kv'><b>Resolved (not fully confirmed)</b><br>{_fmt_antibody_list(resolved)}</div>", unsafe_allow_html=True)
    with b3:
        st.markdown(f"<div class='kv'><b>Needs work / Interference</b><br>{_fmt_antibody_list(needs_work)}</div>", unsafe_allow_html=True)

    if supported_bg:
        st.warning("Background suspected (not confirmed): " + _fmt_antibody_list(supported_bg))
    if not_ex_sig:
        st.warning("Clinically significant NOT excluded: " + _fmt_antibody_list(not_ex_sig))
    if not_ex_cold:
        st.info("Cold/insignificant NOT excluded: " + _fmt_antibody_list(not_ex_cold))
    if no_disc:
        st.warning("No discriminating cells available for: " + _fmt_antibody_list(no_disc))

    # Selected cells
    st.write("")
    st.subheader("Selected Cells Added (if any)")
    if selected:
        try:
            sc_df = pd.DataFrame(selected)
            cols = [c for c in ["id", "res"] if c in sc_df.columns]
            if cols:
                st.dataframe(sc_df[cols], use_container_width=True)
            else:
                st.dataframe(sc_df, use_container_width=True)
        except Exception:
            st.write(selected)
    else:
        st.write("— None —")

# --------------------------------------------------------------------------
# 4.5) SUPERVISOR: Copy/Paste Parser (Option A: 26 columns in AGS order)
# --------------------------------------------------------------------------
def _token_to_01(tok: str) -> int:
    s = str(tok).strip().lower()
    if s in ("", "0", "neg", "negative", "nt", "n/t", "na", "n/a", "-", "—"):
        return 0
    if "+" in s:
        return 1
    if s in ("1", "1+", "2", "2+", "3", "3+", "4", "4+", "pos", "positive", "w", "wk", "weak", "w+", "wf"):
        return 1
    for ch in s:
        if ch.isdigit() and ch != "0":
            return 1
    return 0

def parse_paste_table(txt: str, expected_rows: int, id_prefix: str, id_list=None):
    rows = [r for r in str(txt).strip().splitlines() if r.strip()]
    data = []

    if id_list is None:
        id_list = [f"{id_prefix}{i+1}" for i in range(expected_rows)]

    for i in range(min(expected_rows, len(rows))):
        parts = rows[i].split("\t")
        vals = [_token_to_01(p) for p in parts]

        if len(vals) > len(AGS):
            vals = vals[-len(AGS):]
        while len(vals) < len(AGS):
            vals.append(0)

        d = {"ID": id_list[i]}
        for j, ag in enumerate(AGS):
            d[ag] = int(vals[j])
        data.append(d)

    df = pd.DataFrame(data)
    if len(df) < expected_rows:
        for k in range(len(df), expected_rows):
            d = {"ID": id_list[k], **{ag: 0 for ag in AGS}}
            df = pd.concat([df, pd.DataFrame([d])], ignore_index=True)

    return df, f"Parsed {min(expected_rows, len(rows))} row(s). Expecting {expected_rows}."

def _checkbox_column_config():
    return {
        ag: st.column_config.CheckboxColumn(
            ag,
            help="Tick = Antigen Present (1). Untick = Absent (0).",
            default=False
        )
        for ag in AGS
    }

# --------------------------------------------------------------------------
# 5) SIDEBAR
# --------------------------------------------------------------------------
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Menu", ["Workstation", "Supervisor"], key="nav_menu")

    # ✅ FULL RESET: clears patient + age + sex + reactions + analysis + selected cells
    if st.button("RESET DATA", key="btn_reset"):
        # Patient header
        for k, v in {
            "pt_name": "",
            "pt_mrn": "",
            "pt_sex": "M",
            "age_y": 0,
            "age_m": 0,
            "age_d": 0,
            "tech_nm": "",
            "run_dt": date.today(),
        }.items():
            st.session_state[k] = v

        # Reaction inputs
        for k, v in {
            "rx_ac": "Negative",
            "recent_tx": False,
            "rx_sI": "0",
            "rx_sII": "0",
            "rx_sIII": "0",
            "rx_p1": "0", "rx_p2": "0", "rx_p3": "0", "rx_p4": "0", "rx_p5": "0", "rx_p6": "0",
            "rx_p7": "0", "rx_p8": "0", "rx_p9": "0", "rx_p10": "0", "rx_p11": "0",
            "dat_igg": "Not Done",
            "dat_c3d": "Not Done",
            "dat_ctl": "Not Done",
            "ex_id": "",
            "ex_res": "0",
        }.items():
            st.session_state[k] = v

        # Analysis state
        st.session_state.ext = []
        st.session_state.analysis_ready = False
        st.session_state.analysis_payload = None
        st.session_state.show_dat = False
        st.rerun()

# --------------------------------------------------------------------------
# 6) SUPERVISOR
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
            st.success("Saved locally. Press **Save to GitHub** to publish.")

        st.write("---")
        st.subheader("2) Monthly Grid Update (Copy/Paste + Safe Manual Edit)")
        st.info("Option A active: Paste **26 columns** exactly in **AGS order**. "
                "Rows should be tab-separated. If your paste includes extra leading columns, the app will take the **last 26**.")

        tab_paste, tab_edit = st.tabs(["📋 Copy/Paste Update", "✍️ Manual Edit (Safe)"])

        with tab_paste:
            cA, cB = st.columns(2)

            with cA:
                st.markdown("### Panel 11 (Paste)")
                p_txt = st.text_area("Paste 11 rows (tab-separated; 26 columns in AGS order)", height=170, key="p11_paste")
                if st.button("✅ Update Panel 11 from Paste", key="upd_p11_paste"):
                    df_new, msg = parse_paste_table(p_txt, expected_rows=11, id_prefix="C")
                    df_new["ID"] = [f"C{i+1}" for i in range(11)]
                    st.session_state.panel11_df = df_new.copy()
                    st.success(msg + " Panel 11 updated locally.")

                st.caption("Preview (Panel 11)")
                st.dataframe(st.session_state.panel11_df.iloc[:, :15], use_container_width=True)

            with cB:
                st.markdown("### Screen 3 (Paste)")
                s_txt = st.text_area("Paste 3 rows (tab-separated; 26 columns in AGS order)", height=170, key="p3_paste")
                if st.button("✅ Update Screen 3 from Paste", key="upd_p3_paste"):
                    df_new, msg = parse_paste_table(s_txt, expected_rows=3, id_prefix="S", id_list=["SI", "SII", "SIII"])
                    df_new["ID"] = ["SI", "SII", "SIII"]
                    st.session_state.screen3_df = df_new.copy()
                    st.success(msg + " Screen 3 updated locally.")

                st.caption("Preview (Screen 3)")
                st.dataframe(st.session_state.screen3_df.iloc[:, :15], use_container_width=True)

            st.markdown("""
            <div class='clinical-alert'>
            ⚠️ Tip: If your PDF/table paste includes extra leading columns (labels), the app automatically takes the <b>LAST 26 columns</b> and ignores the rest.
            </div>
            """, unsafe_allow_html=True)

        with tab_edit:
            st.markdown("### Manual Edit (Supervisor only) — Safe mode")
            st.markdown("""
            <div class='clinical-info'>
            ✅ Safe rules applied: <b>ID locked</b> + <b>No add/remove rows</b> + <b>Only 0/1 via checkboxes</b>.<br>
            Use this only for small corrections after copy/paste.
            </div>
            """, unsafe_allow_html=True)

            t1, t2 = st.tabs(["Panel 11 (Edit)", "Screen 3 (Edit)"])

            with t1:
                edited_p11 = st.data_editor(
                    st.session_state.panel11_df,
                    use_container_width=True,
                    num_rows="fixed",
                    disabled=["ID"],
                    column_config=_checkbox_column_config(),
                    key="editor_panel11"
                )
                colx1, colx2 = st.columns([1, 2])
                with colx1:
                    if st.button("⚠️ Apply Manual Changes (Panel 11)", type="primary", key="apply_p11"):
                        st.session_state.panel11_df = edited_p11.copy()
                        st.success("Panel 11 updated safely (local).")
                with colx2:
                    st.caption("Applies only when you click Apply (prevents accidental changes).")

            with t2:
                edited_p3 = st.data_editor(
                    st.session_state.screen3_df,
                    use_container_width=True,
                    num_rows="fixed",
                    disabled=["ID"],
                    column_config=_checkbox_column_config(),
                    key="editor_screen3"
                )
                coly1, coly2 = st.columns([1, 2])
                with coly1:
                    if st.button("⚠️ Apply Manual Changes (Screen 3)", type="primary", key="apply_p3"):
                        st.session_state.screen3_df = edited_p3.copy()
                        st.success("Screen 3 updated safely (local).")
                with coly2:
                    st.caption("Applies only when you click Apply (prevents accidental changes).")

        st.write("---")
        st.subheader("3) Publish to ALL devices (Save to GitHub)")
        st.warning("Before publishing: confirm Lot numbers + Panel/Screen tables are correct.")

        confirm_pub = st.checkbox("I confirm Panel/Screen data were reviewed and are correct", key="confirm_publish")

        if st.button("💾 Save to GitHub (Commit)", key="save_gh"):
            if not confirm_pub:
                st.error("Confirmation required before publishing.")
            else:
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

    # ✅ ONE-LINE HEADER (Age stays on same line with Sex/Tech)
    col_name, col_mrn, col_sex, col_age, col_tech, col_date = st.columns([2.2, 1.4, 1.0, 2.3, 1.4, 1.4])

    col_name.text_input("Name", key="pt_name")
    col_mrn.text_input("MRN", key="pt_mrn")
    col_sex.selectbox("Sex", ["M", "F"], key="pt_sex")

    with col_age:
        st.markdown("<div style='font-weight:600; margin-bottom:0.25rem;'>Age (Y / M / D)</div>", unsafe_allow_html=True)
        ay, am, ad = st.columns([1, 1, 1])
        ay.number_input("Y", min_value=0, max_value=120, step=1, key="age_y", label_visibility="collapsed")
        am.number_input("M", min_value=0, max_value=11, step=1, key="age_m", label_visibility="collapsed")
        ad.number_input("D", min_value=0, max_value=31, step=1, key="age_d", label_visibility="collapsed")

    col_tech.text_input("Tech", key="tech_nm")
    col_date.date_input("Date", value=st.session_state.get("run_dt", date.today()), key="run_dt")

    # ---------------------------
    # HISTORY LOOKUP (GitHub-backed)
    # ---------------------------
    cases_df = load_all_history_df()
    hist = find_case_history(cases_df, mrn=st.session_state.get("pt_mrn",""), name=st.session_state.get("pt_name",""))

    if len(hist) > 0:
        st.markdown(f"""
        <div class='clinical-alert'>
        🧾 <b>History Found</b> — This patient has <b>{len(hist)}</b> previous record(s).  
        Please review before interpretation.
        </div>
        """, unsafe_allow_html=True)

        with st.expander("📚 Open Patient History"):
            show_cols = ["saved_at","run_dt","tech","sex","age_y","age_m","age_d","conclusion_short","ac_res","recent_tx","all_rx"]
            show_cols = [c for c in show_cols if c in hist.columns]
            st.dataframe(hist[show_cols], use_container_width=True)

            idx_list = list(range(len(hist)))
            pick = st.selectbox(
                "Select a previous run",
                idx_list,
                format_func=lambda i: f"{hist.iloc[i]['saved_at']} | {hist.iloc[i]['conclusion_short']}"
            )

            bA, bB = st.columns([1,1])
            with bA:
                view_report = st.button("Open selected run (Report)", key="btn_open_hist_report")
            with bB:
                view_json = st.button("View Raw JSON (Debug)", key="btn_open_hist_json")

            if view_report or view_json:
                try:
                    payload = json.loads(hist.iloc[pick]["summary_json"])
                    if view_report:
                        render_history_report(payload)
                    if view_json:
                        st.json(payload)
                except Exception:
                    st.error("Could not open this record (corrupted JSON).")

    # ----------------------------------------------------------------------
    # MAIN FORM
    # ----------------------------------------------------------------------
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
                ⚠️ Consider <b>Delayed Hemolytic Transfusion Reaction (DHTR)</b> / anamnestic alloantibody response if compatible with clinical picture.<br>
                <ul>
                  <li>Review Hb trend, hemolysis markers (bilirubin/LDH/haptoglobin), DAT as indicated.</li>
                  <li>Compare pre- vs post-transfusion samples if available.</li>
                  <li>Escalate early if new alloantibody suspected.</li>
                </ul>
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
            st.session_state.analysis_ready = False
            st.session_state.analysis_payload = None
            st.session_state.show_dat = False
        else:
            in_p = {1:p1,2:p2,3:p3,4:p4,5:p5,6:p6,7:p7,8:p8,9:p9,10:p10,11:p11}
            in_s = {"I": s_I, "II": s_II, "III": s_III}
            st.session_state.analysis_payload = {
                "in_p": in_p,
                "in_s": in_s,
                "ac_res": ac_res,
                "recent_tx": recent_tx,
            }
            st.session_state.analysis_ready = True

            ac_negative = (ac_res == "Negative")
            all_rx = all_reactive_pattern(in_p, in_s)
            st.session_state.show_dat = bool(all_rx and (not ac_negative))

    if st.session_state.analysis_ready and st.session_state.analysis_payload:
        in_p = st.session_state.analysis_payload["in_p"]
        in_s = st.session_state.analysis_payload["in_s"]
        ac_res = st.session_state.analysis_payload["ac_res"]
        recent_tx = st.session_state.analysis_payload["recent_tx"]

        ac_negative = (ac_res == "Negative")
        all_rx = all_reactive_pattern(in_p, in_s)

        # --------------------------------------------------------------
        # PAN-REACTIVE LOGIC
        # --------------------------------------------------------------
        if all_rx and ac_negative:
            tx_note = ""
            if recent_tx:
                tx_note = """
                <li style="color:#7a0000;"><b>Recent transfusion ≤ 4 weeks</b>: strongly consider <b>DHTR</b> / anamnestic alloantibody response if clinically compatible; compare pre/post samples and review hemolysis markers.</li>
                """

            st.markdown(f"""
            <div class='clinical-danger'>
            ⚠️ <b>Pan-reactive pattern with NEGATIVE autocontrol</b><br>
            <b>Most consistent with:</b>
            <ul>
              <li><b>Alloantibody to a High-Incidence (High-Frequency) Antigen</b></li>
              <li><b>OR multiple alloantibodies</b> not separable with the current cells</li>
            </ul>
            <b>Action / Workflow (priority):</b>
            <ol>
              <li><b>STOP</b> routine single-specificity interpretation (rule-out/rule-in is not valid here).</li>
              <li>Immediate referral to <b>Blood Bank Physician / Reference Lab</b>.</li>
              <li>Request <b>patient extended phenotype / genotype</b> (pre-transfusion if available).</li>
              <li>Start <b>rare compatible unit search</b> (regional/national resources).</li>
              <li><b>First-degree relatives donors</b>: consider typing/testing as potential compatible donors when clinically appropriate.</li>
              <li>Use <b>additional panels / different lots</b> + <b>selected cells</b> to separate multiple alloantibodies if suspected.</li>
              {tx_note}
            </ol>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("""
            <div class='clinical-info'>
            🔎 <b>Note:</b> Routine specificity engine is intentionally paused for this pattern.
            </div>
            """, unsafe_allow_html=True)

            if st.button("💾 Save Case to History", key="save_case_pan_acneg"):
                rec = build_case_record(
                    pt_name=st.session_state.get("pt_name",""),
                    pt_mrn=st.session_state.get("pt_mrn",""),
                    pt_sex=st.session_state.get("pt_sex",""),
                    age_y=st.session_state.get("age_y",0),
                    age_m=st.session_state.get("age_m",0),
                    age_d=st.session_state.get("age_d",0),
                    tech=st.session_state.get("tech_nm",""),
                    run_dt=st.session_state.get("run_dt", date.today()),
                    lot_p=st.session_state.lot_p,
                    lot_s=st.session_state.lot_s,
                    ac_res=ac_res,
                    recent_tx=recent_tx,
                    in_p=in_p,
                    in_s=in_s,
                    ext=st.session_state.ext,
                    all_rx=all_rx,
                    dat_igg="",
                    dat_c3d="",
                    dat_ctl="",
                    conclusion_short="Pan-reactive + AC Negative (High-incidence / multiple allo suspected)",
                    details={"pattern": "pan_reactive_ac_negative"}
                )
                ok, msg = append_case_record(rec)
                if ok:
                    st.success("Saved ✅ (History updated on GitHub)")
                else:
                    st.warning("⚠️ " + msg)

        elif all_rx and (not ac_negative):
            st.markdown("""
            <div class='clinical-danger'>
            ⚠️ <b>Pan-reactive pattern with POSITIVE autocontrol</b><br>
            Requires <b>Monospecific DAT</b> pathway (IgG / C3d / Control) before any alloantibody claims.
            </div>
            """, unsafe_allow_html=True)

            st.subheader("Monospecific DAT Entry (Required)")
            c1, c2, c3 = st.columns(3)
            dat_igg = c1.selectbox("DAT IgG", YN3, key="dat_igg")
            dat_c3d = c2.selectbox("DAT C3d", YN3, key="dat_c3d")
            dat_ctl = c3.selectbox("DAT Control", YN3, key="dat_ctl")

            if dat_ctl == "Positive":
                st.markdown("""
                <div class='clinical-danger'>
                ⛔ <b>DAT Control is POSITIVE</b> → invalid run / control failure.<br>
                Repeat DAT before interpretation.
                </div>
                """, unsafe_allow_html=True)
            elif dat_igg == "Not Done" or dat_c3d == "Not Done":
                st.markdown("""
                <div class='clinical-alert'>
                ⚠️ Please perform <b>Monospecific DAT (IgG & C3d)</b> to proceed.
                </div>
                """, unsafe_allow_html=True)
            else:
                if dat_igg == "Positive":
                    ads = "Auto-adsorption (ONLY if NOT recently transfused)" if not recent_tx else "Allo-adsorption (recent transfusion → avoid auto-adsorption)"
                    st.markdown(f"""
                    <div class='clinical-info'>
                    ✅ <b>DAT IgG POSITIVE</b> (C3d: {dat_c3d}) → consistent with <b>Warm Autoantibody / WAIHA</b>.<br><br>
                    <b>Recommended Workflow:</b>
                    <ol>
                      <li>Consider <b>eluate</b> when indicated.</li>
                      <li>Perform <b>adsorption</b>: <b>{ads}</b> to unmask alloantibodies.</li>
                      <li>Patient <b>phenotype/genotype</b> (pre-transfusion preferred).</li>
                      <li>Transfuse per policy (antigen-matched / least-incompatible as appropriate).</li>
                    </ol>
                    </div>
                    """, unsafe_allow_html=True)

                elif dat_igg == "Negative" and dat_c3d == "Positive":
                    st.markdown("""
                    <div class='clinical-info'>
                    ✅ <b>DAT IgG NEGATIVE + C3d POSITIVE</b> → complement-mediated process (e.g., cold autoantibody).<br><br>
                    <b>Recommended Workflow:</b>
                    <ol>
                      <li>Evaluate cold interference (pre-warm / thermal amplitude) per SOP.</li>
                      <li>Repeat as needed at 37°C.</li>
                      <li>Refer if clinically significant transfusion requirement.</li>
                    </ol>
                    </div>
                    """, unsafe_allow_html=True)

                else:
                    st.markdown("""
                    <div class='clinical-alert'>
                    ⚠️ <b>AC POSITIVE but DAT IgG & C3d NEGATIVE</b> → consider in-vitro interference/technique issue (rouleaux, cold at RT, reagent effects).<br><br>
                    <b>Recommended Actions:</b>
                    <ol>
                      <li>Repeat with proper technique; saline replacement if rouleaux suspected.</li>
                      <li>Pre-warm/37°C repeat if cold suspected.</li>
                      <li>If unresolved → refer.</li>
                    </ol>
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown("""
            <div class='clinical-info'>
            🔎 <b>Note:</b> Routine specificity engine remains paused in pan-reactive cases until DAT pathway is addressed.
            </div>
            """, unsafe_allow_html=True)

            if st.button("💾 Save Case to History", key="save_case_pan_acpos"):
                rec = build_case_record(
                    pt_name=st.session_state.get("pt_name",""),
                    pt_mrn=st.session_state.get("pt_mrn",""),
                    pt_sex=st.session_state.get("pt_sex",""),
                    age_y=st.session_state.get("age_y",0),
                    age_m=st.session_state.get("age_m",0),
                    age_d=st.session_state.get("age_d",0),
                    tech=st.session_state.get("tech_nm",""),
                    run_dt=st.session_state.get("run_dt", date.today()),
                    lot_p=st.session_state.lot_p,
                    lot_s=st.session_state.lot_s,
                    ac_res=ac_res,
                    recent_tx=recent_tx,
                    in_p=in_p,
                    in_s=in_s,
                    ext=st.session_state.ext,
                    all_rx=all_rx,
                    dat_igg=st.session_state.get("dat_igg",""),
                    dat_c3d=st.session_state.get("dat_c3d",""),
                    dat_ctl=st.session_state.get("dat_ctl",""),
                    conclusion_short="Pan-reactive + AC Positive (DAT pathway)",
                    details={"pattern": "pan_reactive_ac_positive"}
                )
                ok, msg = append_case_record(rec)
                if ok:
                    st.success("Saved ✅ (History updated on GitHub)")
                else:
                    st.warning("⚠️ " + msg)

        if all_rx:
            pass
        else:
            cells = get_cells(in_p, in_s, st.session_state.ext)
            ruled = rule_out(in_p, in_s, st.session_state.ext)
            candidates = [a for a in AGS if a not in ruled and a not in IGNORED_AGS]
            best = find_best_combo(candidates, cells, max_size=3)

            st.subheader("Conclusion (Step 1: Rule-out / Rule-in)")

            conclusion_short = ""
            details = {}

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

                conclusion_short = "No resolved specificity (needs selected cells / more work)"
                details = {"best_combo": None, "candidates_not_excluded": candidates}

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
                other_sig = [a for a in remaining_other if a not in INSIGNIFICANT_AGS]
                other_cold = [a for a in remaining_other if a in INSIGNIFICANT_AGS]

                active_not_excluded = set(resolved + needs_work + other_sig + other_cold)

                auto_ruled_out, supported_bg, inconclusive_bg, no_disc_bg = background_auto_resolution(
                    background_list=other_sig + other_cold,
                    active_not_excluded=active_not_excluded,
                    cells=cells
                )

                other_sig_final = [a for a in other_sig if a not in auto_ruled_out]
                other_cold_final = [a for a in other_cold if a not in auto_ruled_out]

                if auto_ruled_out:
                    st.markdown("### ✅ Auto Rule-out (from available discriminating cells):")
                    for ag, labs in auto_ruled_out.items():
                        st.write(f"- **Anti-{ag} ruled out** (discriminating cell(s) NEGATIVE): " + ", ".join(labs))

                if supported_bg:
                    st.markdown("### ⚠️ Background antibodies suggested by discriminating cells (NOT confirmed yet):")
                    for ag, labs in supported_bg.items():
                        st.write(f"- **Anti-{ag} suspected** (discriminating cell(s) POSITIVE): " + ", ".join(labs))

                if inconclusive_bg:
                    st.markdown("### ⚠️ Inconclusive background (mixed discriminating results):")
                    for ag, labs in inconclusive_bg.items():
                        st.write(f"- **Anti-{ag} inconclusive** (mixed results): " + ", ".join(labs))

                if other_sig_final or other_cold_final or no_disc_bg:
                    st.markdown("### ⚠️ Not excluded yet (background possibilities):")
                    if other_sig_final:
                        st.write("**Clinically significant:** " + ", ".join([f"Anti-{x}" for x in other_sig_final]))
                    if other_cold_final:
                        st.info("Cold/Insignificant: " + ", ".join([f"Anti-{x}" for x in other_cold_final]))
                    if no_disc_bg:
                        st.warning("No discriminating cells available in current panel/screen for: " +
                                   ", ".join([f"Anti-{x}" for x in no_disc_bg]))

                st.write("---")
                st.subheader("Confirmation (Rule of Three) — Resolved & Separable only")

                confirmation = {}
                confirmed = set()
                needs_more_for_confirmation = set()

                if not resolved:
                    st.info("No antibody is separable yet → DO NOT apply Rule of Three. Add discriminating selected cells.")
                else:
                    for a in resolved:
                        full, mod, p_cnt, n_cnt = check_rule_three_only_on_discriminating(a, best, cells)
                        confirmation[a] = (full, mod, p_cnt, n_cnt)
                        if full or mod:
                            confirmed.add(a)
                        else:
                            needs_more_for_confirmation.add(a)

                    for a in resolved:
                        full, mod, p_cnt, n_cnt = confirmation[a]
                        if full:
                            st.write(f"✅ **Anti-{a} CONFIRMED**: Full Rule (3+3) met on discriminating cells (P:{p_cnt} / N:{n_cnt})")
                        elif mod:
                            st.write(f"✅ **Anti-{a} CONFIRMED**: Modified Rule (2+3) met on discriminating cells (P:{p_cnt} / N:{n_cnt})")
                        else:
                            st.write(f"⚠️ **Anti-{a} NOT confirmed yet**: need more discriminating cells (P:{p_cnt} / N:{n_cnt})")

                if confirmed:
                    st.markdown(patient_antigen_negative_reminder(sorted(list(confirmed)), strong=True), unsafe_allow_html=True)
                elif resolved:
                    st.markdown(patient_antigen_negative_reminder(sorted(list(resolved)), strong=False), unsafe_allow_html=True)

                d_present = ("D" in confirmed) or ("D" in resolved) or ("D" in needs_work)
                c_present = ("C" in confirmed) or ("C" in resolved) or ("C" in needs_work) or ("C" in supported_bg) or ("C" in other_sig_final)
                if d_present and c_present:
                    strong = ("D" in confirmed and "C" in confirmed)
                    st.markdown(anti_g_alert_html(strong=strong), unsafe_allow_html=True)

                st.write("---")

                targets_needing_selected = list(dict.fromkeys(
                    needs_work +
                    list(needs_more_for_confirmation) +
                    list(supported_bg.keys()) +
                    other_sig_final
                ))

                if targets_needing_selected:
                    st.markdown("### 🧪 Selected Cells (Only if needed to resolve interference / exclude / confirm)")

                    for a in targets_needing_selected:
                        active_set_now = set(resolved + needs_work + other_sig_final + list(supported_bg.keys()))

                        if a in needs_work:
                            st.warning(f"Anti-{a}: **Interference / not separable** → need {a}+ cells NEGATIVE for other active suspects.")
                        elif a in other_sig_final:
                            st.warning(f"Anti-{a}: **Clinically significant background NOT excluded** → need discriminating cells to exclude/confirm.")
                        elif a in supported_bg:
                            st.info(f"Anti-{a}: **Suggested by discriminating POSITIVE cell(s)** → requires confirmation (rule-of-three / additional discriminating cells).")
                        else:
                            st.info(f"Anti-{a}: **Not confirmed yet** → need more discriminating cells.")

                        sugg = suggest_selected_cells(a, list(active_set_now))
                        if sugg:
                            for lab, note in sugg[:12]:
                                st.write(f"- {lab}  <span class='cell-hint'>{note}</span>", unsafe_allow_html=True)
                        else:
                            st.write("- No suitable discriminating cell in current inventory → use another lot / external selected cells.")

                    enz = enzyme_hint_if_needed(targets_needing_selected)
                    if enz:
                        st.info("💡 " + enz)

                else:
                    st.success("No Selected Cells needed: all resolved antibodies are confirmed AND no clinically significant background remains unexcluded.")

                confirmed_list = sorted(list(confirmed)) if isinstance(confirmed, set) else []
                resolved_list = resolved if isinstance(resolved, list) else []
                needs_work_list = needs_work if isinstance(needs_work, list) else []
                supported_list = sorted(list(supported_bg.keys())) if isinstance(supported_bg, dict) else []

                if confirmed_list:
                    conclusion_short = "Confirmed: " + ", ".join([f"Anti-{x}" for x in confirmed_list])
                elif resolved_list:
                    conclusion_short = "Resolved (not fully confirmed): " + ", ".join([f"Anti-{x}" for x in resolved_list])
                else:
                    conclusion_short = "Unresolved / Needs more work"

                details = {
                    "best_combo": list(best),
                    "resolved": resolved_list,
                    "needs_work": needs_work_list,
                    "confirmed": confirmed_list,
                    "supported_bg": supported_list,
                    "not_excluded_sig": other_sig_final if isinstance(other_sig_final, list) else [],
                    "not_excluded_cold": other_cold_final if isinstance(other_cold_final, list) else [],
                    "no_discriminating": no_disc_bg if isinstance(no_disc_bg, list) else []
                }

            if st.button("💾 Save Case to History", key="save_case_nonpan"):
                rec = build_case_record(
                    pt_name=st.session_state.get("pt_name",""),
                    pt_mrn=st.session_state.get("pt_mrn",""),
                    pt_sex=st.session_state.get("pt_sex",""),
                    age_y=st.session_state.get("age_y",0),
                    age_m=st.session_state.get("age_m",0),
                    age_d=st.session_state.get("age_d",0),
                    tech=st.session_state.get("tech_nm",""),
                    run_dt=st.session_state.get("run_dt", date.today()),
                    lot_p=st.session_state.lot_p,
                    lot_s=st.session_state.lot_s,
                    ac_res=ac_res,
                    recent_tx=recent_tx,
                    in_p=in_p,
                    in_s=in_s,
                    ext=st.session_state.ext,
                    all_rx=all_rx,
                    dat_igg=st.session_state.get("dat_igg",""),
                    dat_c3d=st.session_state.get("dat_c3d",""),
                    dat_ctl=st.session_state.get("dat_ctl",""),
                    conclusion_short=conclusion_short,
                    details=details
                )
                ok, msg = append_case_record(rec)
                if ok:
                    st.success("Saved ✅ (History updated on GitHub)")
                else:
                    st.warning("⚠️ " + msg)

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
