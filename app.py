import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import json
import base64
import requests
from pathlib import Path
from itertools import combinations
import hashlib
import re
from typing import Dict, Any, List, Tuple, Optional

# =============================================================================
# 0) GitHub Engine (uses Streamlit Secrets)
# =============================================================================
def _gh_get_cfg():
    token = st.secrets.get("GITHUB_TOKEN", None)
    repo  = st.secrets.get("GITHUB_REPO", None)   # e.g. "Haitham526/tabuk-blood-bank"
    branch = st.secrets.get("GITHUB_BRANCH", "main")
    return token, repo, branch

def _gh_headers(token: str):
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    }

def github_get_file(path_in_repo: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (content_text, sha) or (None, None) if not found.
    """
    token, repo, branch = _gh_get_cfg()
    if not token or not repo:
        raise RuntimeError("Missing Streamlit Secrets: GITHUB_TOKEN / GITHUB_REPO")

    api = f"https://api.github.com/repos/{repo}/contents/{path_in_repo}"
    r = requests.get(api, headers=_gh_headers(token), params={"ref": branch}, timeout=30)
    if r.status_code == 404:
        return None, None
    if r.status_code != 200:
        raise RuntimeError(f"GitHub GET error {r.status_code}: {r.text}")

    j = r.json()
    sha = j.get("sha")
    enc = j.get("content", "")
    if not enc:
        return "", sha
    txt = base64.b64decode(enc).decode("utf-8", errors="replace")
    return txt, sha

def github_list_dir(path_in_repo: str) -> List[Dict[str, Any]]:
    token, repo, branch = _gh_get_cfg()
    if not token or not repo:
        raise RuntimeError("Missing Streamlit Secrets: GITHUB_TOKEN / GITHUB_REPO")

    api = f"https://api.github.com/repos/{repo}/contents/{path_in_repo}"
    r = requests.get(api, headers=_gh_headers(token), params={"ref": branch}, timeout=30)
    if r.status_code == 404:
        return []
    if r.status_code != 200:
        raise RuntimeError(f"GitHub LIST error {r.status_code}: {r.text}")

    j = r.json()
    if isinstance(j, dict) and j.get("type") == "file":
        return [j]
    if isinstance(j, list):
        return j
    return []

def github_upsert_file(path_in_repo: str, content_text: str, commit_message: str):
    token, repo, branch = _gh_get_cfg()
    if not token or not repo:
        raise RuntimeError("Missing Streamlit Secrets: GITHUB_TOKEN / GITHUB_REPO")

    api = f"https://api.github.com/repos/{repo}/contents/{path_in_repo}"
    headers = _gh_headers(token)

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

# =============================================================================
# 0.1) Local config files (panel/screen/lots) - still local + publish to GitHub
# =============================================================================
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

# =============================================================================
# 0.2) HISTORY ENGINE (GitHub, scalable per-patient directory)
# =============================================================================
HISTORY_ROOT = "data/history"     # repo path
HISTORY_DUP_WINDOW_MIN = 10       # ignore exact duplicates within this window
HISTORY_MAX_PER_PATIENT_INDEX = 5000  # safety cap (per MRN index file)

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

def _mrn_dir(mrn: str) -> str:
    mrn = _safe_str(mrn) or "NO_MRN"
    return f"{HISTORY_ROOT}/{mrn}"

def _index_path(mrn: str) -> str:
    return f"{_mrn_dir(mrn)}/index.jsonl"

def _case_path(mrn: str, case_id: str) -> str:
    return f"{_mrn_dir(mrn)}/{case_id}.json"

def _read_patient_index(mrn: str) -> List[dict]:
    txt, _ = github_get_file(_index_path(mrn))
    if not txt:
        return []
    rows = []
    for line in txt.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    # sort newest first if saved_at exists
    rows2 = []
    for r in rows:
        dt = _parse_dt(r.get("saved_at", ""))
        r["_dt"] = dt
        rows2.append(r)
    rows2.sort(key=lambda r: (r["_dt"] is None, r["_dt"]), reverse=True)
    for r in rows2:
        r.pop("_dt", None)
    return rows2

def _write_patient_index(mrn: str, rows: List[dict]):
    # keep only most recent N
    rows2 = []
    for r in rows:
        dt = _parse_dt(r.get("saved_at", ""))
        r2 = dict(r)
        r2["_dt"] = dt
        rows2.append(r2)
    rows2.sort(key=lambda r: (r["_dt"] is None, r["_dt"]), reverse=True)
    rows2 = rows2[:HISTORY_MAX_PER_PATIENT_INDEX]
    for r in rows2:
        r.pop("_dt", None)

    content = "\\n".join([json.dumps(r, ensure_ascii=False) for r in rows2]) + ("\\n" if rows2 else "")
    github_upsert_file(_index_path(mrn), content, f"Update history index for {mrn}")

def save_case_to_github(record: dict) -> Tuple[bool, str]:
    """
    record: full record dict with keys:
      - mrn, case_id, saved_at, fingerprint, summary_json, etc
    Saves:
      - case JSON file under data/history/<mrn>/<case_id>.json
      - updates per-patient index.jsonl
    """
    mrn = _safe_str(record.get("mrn", "")) or "NO_MRN"
    case_id = _safe_str(record.get("case_id", "")) or f"{mrn}_{_now_ts()}".replace(" ", "_").replace(":", "-")

    # Duplicate check: load patient index, compare fingerprint within time window
    try:
        idx = _read_patient_index(mrn)
    except Exception as e:
        return (False, f"History read failed: {e}")

    fp = _safe_str(record.get("fingerprint", ""))
    if fp and idx:
        # find any matching fp; if found within window, do not save
        for r in idx[:30]:  # recent check only
            if _safe_str(r.get("fingerprint","")) == fp:
                last_dt = _parse_dt(r.get("saved_at",""))
                if last_dt and (datetime.now() - last_dt) <= timedelta(minutes=HISTORY_DUP_WINDOW_MIN):
                    return (False, f"Duplicate detected: identical record already saved within last {HISTORY_DUP_WINDOW_MIN} minutes.")

    # Save full case file
    payload = None
    try:
        payload = json.loads(record.get("summary_json","{}"))
    except Exception:
        payload = {"_corrupt_summary_json": True}

    try:
        github_upsert_file(
            _case_path(mrn, case_id),
            json.dumps(payload, ensure_ascii=False, indent=2),
            f"Add case {case_id} for {mrn}"
        )
    except Exception as e:
        return (False, f"Case save failed: {e}")

    # Update index row (small)
    index_row = {
        "case_id": case_id,
        "saved_at": _safe_str(record.get("saved_at","")),
        "run_dt": _safe_str(record.get("run_dt","")),
        "mrn": mrn,
        "name": _safe_str(record.get("name","")),
        "tech": _safe_str(record.get("tech","")),
        "sex": _safe_str(record.get("sex","")),
        "age_y": _safe_str(record.get("age_y","")),
        "age_m": _safe_str(record.get("age_m","")),
        "age_d": _safe_str(record.get("age_d","")),
        "conclusion_short": _safe_str(record.get("conclusion_short","")),
        "abo_final": _safe_str(record.get("abo_final","")),
        "rhd_final": _safe_str(record.get("rhd_final","")),
        "abo_discrepancy": bool(record.get("abo_discrepancy", False)),
        "ac_res": _safe_str(record.get("ac_res","")),
        "recent_tx": bool(record.get("recent_tx", False)),
        "all_rx": bool(record.get("all_rx", False)),
        "fingerprint": _safe_str(record.get("fingerprint","")),
    }
    idx.insert(0, index_row)

    try:
        _write_patient_index(mrn, idx)
    except Exception as e:
        return (False, f"Index update failed (case saved): {e}")

    return (True, "Saved")

def load_history_index_as_df(mrn: str) -> pd.DataFrame:
    rows = _read_patient_index(mrn)
    if not rows:
        return pd.DataFrame(columns=[
            "saved_at","run_dt","tech","sex","age_y","age_m","age_d",
            "conclusion_short","abo_final","rhd_final","abo_discrepancy",
            "ac_res","recent_tx","all_rx","case_id"
        ])
    df = pd.DataFrame(rows)
    # guarantee columns
    wanted = [
        "saved_at","run_dt","tech","sex","age_y","age_m","age_d",
        "conclusion_short","abo_final","rhd_final","abo_discrepancy",
        "ac_res","recent_tx","all_rx","case_id"
    ]
    for c in wanted:
        if c not in df.columns:
            df[c] = ""
    df = df[wanted]
    try:
        df = df.sort_values("saved_at", ascending=False)
    except Exception:
        pass
    return df

def load_case_payload(mrn: str, case_id: str) -> Optional[dict]:
    txt, _ = github_get_file(_case_path(mrn, case_id))
    if not txt:
        return None
    try:
        return json.loads(txt)
    except Exception:
        return None

# =============================================================================
# 1) PAGE SETUP & CSS
# =============================================================================
st.set_page_config(page_title="MCH Tabuk - Serology Expert", layout="wide", page_icon="🩸")

# ------------------------------
# UI Theme (expander headers)
# ------------------------------
if "ui_theme" not in st.session_state:
    # Default theme (recommended)
    st.session_state.ui_theme = "Burgundy / White"

def _get_theme_vars(name: str) -> dict:
    name = (name or "").strip().lower()

    # Navy / Deep Blue
    if name.startswith("navy"):
        return {
            # Section (expander) header colors
            "sec_bg": "#0B1B3A",
            "sec_bg_hover": "#112A57",
            "sec_fg": "#B9F5FF",
            "sec_border": "rgba(11, 27, 58, 0.35)",
            "sec_shadow": "0 6px 16px rgba(11, 27, 58, 0.10)",
            # App header colors
            "hdr_bg": "#08162F",
            "hdr_title": "#B9F5FF",
            "hdr_sub": "#FFFFFF",
            "hdr_tag": "#D7F9FF",
            "hdr_border": "rgba(185, 245, 255, 0.35)",
        }

    # Burgundy / Wine (default)
    return {
        "sec_bg": "#5A0F1A",
        "sec_bg_hover": "#721425",
        "sec_fg": "#FFFFFF",
        "sec_border": "rgba(90, 15, 26, 0.30)",
        "sec_shadow": "0 6px 16px rgba(90, 15, 26, 0.10)",
        "hdr_bg": "#4A0B14",
        "hdr_title": "#FFFFFF",
        "hdr_sub": "#F6F1F2",
        "hdr_tag": "#FFF3D6",
        "hdr_border": "rgba(255, 243, 214, 0.35)",
    }


THEME_VARS = _get_theme_vars(st.session_state.ui_theme)


st.markdown("""
<style>
    .hospital-logo { color: #8B0000; text-align: center; border-bottom: 5px solid #8B0000; padding-bottom: 5px; font-family: 'Arial'; }
    .lot-bar {
        display: flex; justify-content: space-around; background-color: #f1f8e9;
        border: 1px solid #81c784; padding: 8px; border-radius: 5px; margin-bottom: 18px; font-weight: bold; color: #1b5e20;
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
    .report-title { font-size: 20px; font-weight: 800; color: #8B0000; margin-bottom: 2px; }
    .report-sub { color: #555; font-size: 12px; margin-bottom: 10px; }
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

    /* Status chips (to show where the issue is: ABO vs RhD) */
    .status-row { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 8px; }
    .status-chip {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 6px 10px; border-radius: 999px;
        font-weight: 800; font-size: 0.95rem;
        border: 1px solid rgba(0,0,0,0.12);
    }
    .chip-ok { background: #d1e7dd; }
    .chip-warn { background: #f8d7da; }
    .chip-neutral { background: #e2e3e5; }
    .chip-label { opacity: 0.75; font-weight: 900; letter-spacing: 0.2px; }

</style>
""", unsafe_allow_html=True)

UI_THEME_CSS = """
<style>
:root {
    --sec-bg: __SEC_BG__;
    --sec-bg-hover: __SEC_BG_HOVER__;
    --sec-fg: __SEC_FG__;
    --sec-border: __SEC_BORDER__;
    --sec-shadow: __SEC_SHADOW__;
    --hdr-bg: __HDR_BG__;
    --hdr-title: __HDR_TITLE__;
    --hdr-sub: __HDR_SUB__;
    --hdr-tag: __HDR_TAG__;
    --hdr-border: __HDR_BORDER__;
}

    /* Elegant expander headers (robust to Streamlit DOM changes) */
div[data-testid="stExpander"] details {
    border: 1px solid var(--sec-border) !important;
    border-radius: 16px !important;
    overflow: hidden !important;
    box-shadow: var(--sec-shadow) !important;
    background: #FFFFFF !important;
}
div[data-testid="stExpander"] details > summary {
    background: var(--sec-bg) !important;
    padding: 12px 16px !important;
}
div[data-testid="stExpander"] details > summary:hover {
    background: var(--sec-bg-hover) !important;
}
/* Color EVERYTHING inside the expander header (text + icons), regardless of tag structure */
div[data-testid="stExpander"] details > summary,
div[data-testid="stExpander"] details > summary * {
    color: var(--sec-fg) !important;
    font-weight: 800 !important;
    letter-spacing: 0.2px;
}
div[data-testid="stExpander"] details > summary svg,
div[data-testid="stExpander"] details > summary svg * {
    fill: var(--sec-fg) !important;
    color: var(--sec-fg) !important;
}

/* Slightly tighter spacing inside expanders */
div[data-testid="stExpander"] .stMarkdown,
div[data-testid="stExpander"] .stText {
    margin-top: 0.25rem;
}

/* App header (Doctor Decision) */
        .site-title{
            width:100%;
            text-align:center;
            font-weight:900;
            letter-spacing:.3px;
            font-size:38px;
            line-height:1.05;
            margin:10px 0 14px 0;
            color: var(--hdr-bg);
            text-shadow: 0 1px 0 rgba(255,255,255,.6);
        }
        @media (max-width: 900px){
            .site-title{ font-size:30px; }
        }


    .app-header {
        background: var(--hdr-bg);
        border: 1px solid var(--hdr-border);
        border-radius: 14px;
        padding: 14px 18px;
        margin: 6px 0 14px 0;
        text-align: center;
        box-shadow: var(--sec-shadow);
    }
    .app-header .app-title {
        font-size: 34px;
        font-weight: 900;
        letter-spacing: 0.6px;
        color: var(--hdr-title);
        line-height: 1.05;
        margin-bottom: 4px;
    }
    .app-header .app-subtitle {
        font-size: 18px;
        font-weight: 700;
        color: var(--hdr-sub);
        letter-spacing: 0.2px;
        margin-bottom: 4px;
    }
    .app-header .app-tagline {
        font-size: 13px;
        font-weight: 700;
        color: var(--hdr-tag);
        opacity: 0.95;
        letter-spacing: 0.4px;
    }

    /* ABO card colored labels */
    .abo-label {
        width: 100%;
        height: 34px;
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 900;
        letter-spacing: 0.3px;
        margin: 2px 0 6px 0;
        border: 1px solid rgba(0,0,0,0.08);
        position: relative;
        user-select: none;
    }
    .abo-a { background: #4F9BD9; color: #FFFFFF; }  /* Anti-A (blue) */
    .abo-b { background: #F3D35C; color: #111111; }  /* Anti-B (yellow) */
    .abo-d { background: #D3DAE2; color: #111111; }  /* Anti-D (silver) */
    .abo-ctl { background: #FFFFFF; color: #111111; border: 1px solid #D0D0D0; } /* Control (white) */
    .abo-a1 { background: #F2B274; color: #111111; } /* A1 cells (light orange) */
    .abo-bcells { background: #F2B274; color: #111111; } /* B cells (light orange) */

    /* Neonate card specific */
    .neo-ab { background: #FFFFFF; color: #111111; border: 1px solid #D0D0D0; } /* Anti-AB (white) */
    .neo-dat { background: #BFE9D2; color: #0A3D0A; border: 1px solid rgba(10,61,10,0.18); } /* DAT (light green) */
    .ctl-icon {
        position: absolute;
        left: 10px;
        top: 50%;
        transform: translateY(-50%);
        font-size: 11px;
        font-weight: 900;
        padding: 2px 7px;
        border-radius: 999px;
        background: rgba(0,0,0,0.08);
        color: #111111;
        letter-spacing: 0.4px;
    }
</style>
"""
for _k, _v in THEME_VARS.items():
    UI_THEME_CSS = UI_THEME_CSS.replace(f"__{_k.upper()}__", str(_v))

st.markdown(UI_THEME_CSS, unsafe_allow_html=True)


st.markdown("""
<div class='dr-signature no-print'>
    <span class='dr-name'>Dr. Haitham Ismail</span>
    <span class='dr-title'>Clinical Hematology/Oncology &<br>BM Transplantation & Transfusion Medicine Consultant</span>
</div>
""", unsafe_allow_html=True)

# =============================================================================
# 2) CONSTANTS
# =============================================================================
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

IGNORED_AGS = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"]
INSIGNIFICANT_AGS = ["Lea", "Lua", "Leb", "P1"]
ENZYME_DESTROYED = ["Fya","Fyb","M","N","S","s"]

GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]  # antibody ID grades
YN3 = ["Not Done", "Negative", "Positive"]

ABO_GRADES = ["Not Done", "0", "+1", "+2", "+3", "+4", "Mixed-field", "Hemolysis"]


def _render_abo_label_html(text: str, cls: str, ctl_badge: bool = False) -> str:
    badge = "<span class='ctl-icon'>ctl</span>" if ctl_badge else ""
    safe = str(text)
    return f"<div class='abo-label {cls}'>{badge}{safe}</div>"

SEX_OPTS = ["", "M", "F"]

PHENO_OPTS = ["Not Done", "Not Detected", "Detected"]  # antigen absent/present

# =============================================================================
# 3) STATE (panel/screen/lots/selected-cells)
# =============================================================================
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

# =============================================================================
# 4) HELPERS / ENGINE
# =============================================================================
def normalize_grade(val) -> int:
    s = str(val).lower().strip()
    if s in ["0", "neg", "negative", "none", "not done", "nd", "n/d"]:
        return 0
    return 1

def _grade_num(g: str) -> int:
    g = _safe_str(g)
    if g in ("", "Not Done"):
        return -1
    if g == "0":
        return 0
    if g == "+1":
        return 1
    if g == "+2":
        return 2
    if g == "+3":
        return 3
    if g == "+4":
        return 4
    if g == "Mixed-field":
        return 2
    if g == "Hemolysis":
        return 5
    return -1

def _is_pos_any(g: str) -> bool:
    return _grade_num(g) >= 1  # includes weak +1

def _is_pos_strong_abo_forward(g: str) -> bool:
    # expected >=3+ in your policy for adults/children >4 months
    return g in ("+3", "+4", "Hemolysis")

def _is_pos_ok_reverse(g: str) -> bool:
    # expected >=2+ in adults/children >4 months
    return g in ("+2", "+3", "+4", "Hemolysis", "Mixed-field")

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
    """
    UI safety reminder shown after antibody interpretation.
    - Strong = confirmed/clinically significant.
    - Not-strong = resolved/likely insignificant but still requires final confirmation.
    NOTE: We keep this strictly as a reminder; local policy and clinical context prevail.
    """
    if not antibodies:
        return ""

    # Normalize: we receive antigen symbols (e.g., "K", "E", "Jka") not full names.
    uniq = []
    seen = set()
    for ag in antibodies:
        if not ag or ag in IGNORED_AGS:
            continue
        if ag not in seen:
            seen.add(ag)
            uniq.append(ag)

    if not uniq:
        return ""

    title = "✅ Final confirmation step (Patient antigen check + unit selection)" if strong else \
            "⚠️ Before final reporting (Patient antigen check + unit selection)"
    subtitle = "Confirmed clinically significant antibody(ies) identified" if strong else \
               "Resolved / lower-likelihood antibody signal — confirm before finalizing"

    action = "MUST" if strong else "Prefer to"
    bullets = []
    for ag in uniq:
        if ag.upper() == "M":
            bullets.append(
                "<li><b>Anti-M</b>: <b>Prefer M-negative</b> units. "
                "If the antibody is <b>cold-reactive only</b> and M-negative units are not readily available, "
                "<b>AHG-compatible / prewarmed crossmatch-compatible</b> units may be acceptable per local policy & clinical context. "
                "If reactive at 37°C/AHG, treat as clinically significant and provide <b>M-negative</b> units.</li>"
            )
        else:
            bullets.append(
                f"<li><b>Anti-{ag}</b>: {action} select <b>{ag}-negative</b> RBC units and "
                f"confirm the patient is <b>{ag}-negative</b> (or document justification per policy).</li>"
            )

    html = f"""
    <div class="ba-box ba-border-soft" style="background:rgba(245, 245, 245, 0.75);">
      <div style="font-weight:800; font-size:1.02rem; margin-bottom:.25rem;">{title}</div>
      <div style="font-size:.92rem; margin-bottom:.4rem; opacity:.95;">{subtitle}</div>
      <ul style="margin:0 0 0 1.1rem; padding:0;">
        {''.join(bullets)}
      </ul>
    </div>
    """
    return html


def not_excluded_antigen_negative_notice(antigens: list) -> str:
    """
    Shown when an antibody is NOT EXCLUDED (i.e., still possible).
    The note must disappear automatically once the antibody becomes excluded by additional cells.
    """
    if not antigens:
        return ""

    uniq = []
    seen = set()
    for ag in antigens:
        if not ag or ag in IGNORED_AGS:
            continue
        if ag not in seen:
            seen.add(ag)
            uniq.append(ag)

    if not uniq:
        return ""

    bullets = []
    for ag in uniq:
        if ag.upper() == "M":
            bullets.append(
                "<li><b>Anti-M (not excluded)</b>: <b>Prefer M-negative</b> units; "
                "if only cold-reactive and M-negative units are not readily available, "
                "<b>AHG-compatible / prewarmed crossmatch-compatible</b> units may be acceptable per local policy.</li>"
            )
        else:
            bullets.append(
                f"<li><b>Anti-{ag} (not excluded)</b>: until excluded, select <b>{ag}-negative</b> RBC units (or follow local policy).</li>"
            )

    html = f"""
    <div class="ba-box ba-border-warn" style="background:rgba(255, 250, 230, 0.92);">
      <div style="font-weight:850; font-size:1.0rem; margin-bottom:.25rem;">⚠️ Not excluded — treat as potentially significant</div>
      <div style="font-size:.92rem; margin-bottom:.4rem; opacity:.95;">
        These antibodies are <b>not excluded</b>. If transfusion is required <b>before exclusion</b>, consider antigen-negative selection as below.
      </div>
      <ul style="margin:0 0 0 1.1rem; padding:0;">
        {''.join(bullets)}
      </ul>
    </div>
    """
    return html



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

# =============================================================================
# 4.1) ABO/RhD/DAT logic + discrepancy guidance
# =============================================================================
def _age_is_neonate(age_y: int, age_m: int, age_d: int) -> bool:
    # Neonate definition for this tool: < 4 months
    total_days = max(0, int(age_y or 0))*365 + max(0, int(age_m or 0))*30 + max(0, int(age_d or 0))
    return total_days < (4*30)

def _abo_from_forward_only(a: str, b: str) -> str:
    a_pos = _is_pos_any(a)
    b_pos = _is_pos_any(b)
    if a_pos and not b_pos:
        return "A"
    if b_pos and not a_pos:
        return "B"
    if a_pos and b_pos:
        return "AB"
    if (not a_pos) and (not b_pos):
        return "O"
    return "Unknown"

def _abo_mapping_consistent(forward_abo: str, rev_a1: str, rev_b: str) -> bool:
    """
    Checks if reverse matches the expected pattern for the ABO.
    Uses 'any positive' in reverse to evaluate.
    """
    a1_pos = _is_pos_any(rev_a1)
    b_pos  = _is_pos_any(rev_b)
    if forward_abo == "A":
        return (not a1_pos) and b_pos
    if forward_abo == "B":
        return a1_pos and (not b_pos)
    if forward_abo == "AB":
        return (not a1_pos) and (not b_pos)
    if forward_abo == "O":
        return a1_pos and b_pos
    return False

def interpret_abo_rhd(
    is_neonate: bool,
    purpose: str,
    raw: Dict[str, str],
    screen_any_positive: bool
) -> Dict[str, Any]:
    """
    raw keys:
      Adult: antiA, antiB, antiD, ctl, a1cells, bcells
      Neonate: antiA, antiB, antiAB, antiD, ctl, dat
    Returns:
      {abo_final, rhd_final, discrepancy(bool), invalid(bool), notes(list[str])}
    """
    notes = []
    discrepancy = False
    invalid = False

    ctl = _safe_str(raw.get("ctl","Not Done"))
    if ctl in ("+1","+2","+3","+4","Mixed-field","Hemolysis"):
        invalid = True
        discrepancy = True
        notes.append("Control is POSITIVE → test is INVALID. Repeat ABO/Rh typing with proper technique.")

    # RhD
    antiD = _safe_str(raw.get("antiD","Not Done"))
    if antiD in ("Not Done", ""):
        rhd_final = "Unknown"
    elif antiD == "0":
        rhd_final = "RhD Negative"
    elif antiD == "+4":
        rhd_final = "RhD Positive"
    else:
        rhd_final = "RhD Inconclusive / Weak D suspected"
        discrepancy = True
        notes.append("Anti-D is weaker than expected or shows mixed-field/hemolysis → treat as RhD NEGATIVE for transfusion and RhIG eligibility per policy; consider molecular testing if available.")

    # ABO
    if is_neonate:
        antiA = _safe_str(raw.get("antiA","Not Done"))
        antiB = _safe_str(raw.get("antiB","Not Done"))
        abo_guess = _abo_from_forward_only(antiA, antiB)

        # Flag mixed-field forward as discrepancy but still provide most probable ABO
        if antiA == "Mixed-field" or antiB == "Mixed-field":
            discrepancy = True
            notes.append("Mixed-field forward reactions detected. Correlate with clinical history (e.g., transfusion, sample issues) and repeat testing per policy.")

        # Flag weak forward as discrepancy but still provide most probable ABO
        if antiA in ("+1","+2") or antiB in ("+1","+2"):
            discrepancy = True
            notes.append("Weak/mixed-field A/B reactions can occur in neonates; report as 'most probable' and plan confirmation at 6 months (or per local policy).")
        if antiA == "Not Done" or antiB == "Not Done":
            discrepancy = True
            notes.append("Forward ABO not fully performed (Not Done). Complete testing if required.")
        abo_final = f"Most probable: {abo_guess}" if abo_guess != "Unknown" else "Most probable: Unknown"

        # DAT note (neonate)
        dat = _safe_str(raw.get("dat","Not Done"))
        if dat in ("+1","+2","+3","+4","Mixed-field","Hemolysis"):
            notes.append("DAT is POSITIVE. In neonates, consider maternal IgG coating; interpret ABO cautiously and ensure proper specimen handling.")
        if dat in ("Not Done",""):
            # allowed
            pass

        if purpose == "RhIG":
            notes.append("Purpose: RhIG eligibility (DVI+ card per your policy).")
        else:
            notes.append("Purpose: Transfusion (DVI− card per your policy).")

    else:
        antiA = _safe_str(raw.get("antiA","Not Done"))
        antiB = _safe_str(raw.get("antiB","Not Done"))
        rev_a1 = _safe_str(raw.get("a1cells","Not Done"))
        rev_b  = _safe_str(raw.get("bcells","Not Done"))

        # Determine forward ABO (any positive)
        fwd_abo = _abo_from_forward_only(antiA, antiB)

        # Discrepancy thresholds
        # Forward expected >=3+ (policy). If positive but <3+, flag.
        if antiA in ("+1","+2") or antiB in ("+1","+2"):
            discrepancy = True
            notes.append("Forward grouping shows weak/mixed-field reactions (<3+). Initiate ABO discrepancy workup per policy.")
        # Reverse expected >=2+ if positive. If 0/+1 where expected pos, flag.
        # We first compute expected pattern, then check if reverse is weak.
        if fwd_abo in ("A","B","O") or fwd_abo == "AB":
            # If reverse results are not done, discrepancy
            if rev_a1 in ("Not Done","") or rev_b in ("Not Done",""):
                discrepancy = True
                notes.append("Reverse grouping not fully performed. For patients >4 months, reverse grouping is required per policy.")
            else:
                # If pattern mismatch
                if not _abo_mapping_consistent(fwd_abo, rev_a1, rev_b):
                    discrepancy = True
                    notes.append("Forward and reverse grouping are inconsistent → ABO DISCREPANCY.")
                else:
                    # Even if consistent, ensure reverse strength meets expectation (>=2+ when positive expected)
                    # Determine which reverse should be positive
                    a1_should_pos = (fwd_abo in ("B","O"))
                    b_should_pos  = (fwd_abo in ("A","O"))
                    if a1_should_pos and (rev_a1 in ("0","+1")):
                        discrepancy = True
                        notes.append("Reverse grouping is weaker than expected (<2+). Consider hypogammaglobulinemia, age-related low isoagglutinins, recent transfusion, or plasma abnormalities; follow policy.")
                    if b_should_pos and (rev_b in ("0","+1")):
                        discrepancy = True
                        notes.append("Reverse grouping is weaker than expected (<2+). Consider hypogammaglobulinemia, age-related low isoagglutinins, recent transfusion, or plasma abnormalities; follow policy.")

        # Link to antibody screen if reverse extra reactions and screen is positive
        if discrepancy and screen_any_positive:
            notes.append("Antibody screen is POSITIVE. If reverse grouping shows unexpected reactivity, consider alloantibody/cold interference; review antibody ID history and use appropriate antigen-negative reagent cells per SOP.")

        # Mixed-field -> transfusion / transplant
        if antiA == "Mixed-field" or antiB == "Mixed-field" or rev_a1 == "Mixed-field" or rev_b == "Mixed-field":
            discrepancy = True
            notes.append("Mixed-field pattern: consider recent transfusion, stem cell transplant/chimerism, or sample issue. For transfused patients, confirm ABO ≥3 months after last transfusion (or per policy).")

        abo_final = fwd_abo if fwd_abo else "Unknown"
        if discrepancy and not invalid:
            # still show best estimate to help paperwork, but label discrepancy
            abo_final = f"{abo_final} (Discrepancy)"

    # Rouleaux/cold auto suspicion in ABO: everything positive including control
    if not is_neonate:
        all_pos_keys = ["antiA","antiB","antiD","ctl","a1cells","bcells"]
    else:
        all_pos_keys = ["antiA","antiB","antiAB","antiD","ctl"]
    all_pos = True
    for k in all_pos_keys:
        if not _is_pos_any(_safe_str(raw.get(k,"0"))):
            all_pos = False
            break
    if all_pos and _is_pos_any(ctl):
        discrepancy = True
        notes.append("All wells including control are reactive → consider rouleaux or cold autoantibody interference. Repeat with saline replacement / prewarm as appropriate per SOP.")

    return {
        "abo_final": abo_final,
        "rhd_final": rhd_final,
        "discrepancy": bool(discrepancy),
        "invalid": bool(invalid),
        "notes": notes
    }

# =============================================================================
# 4.2) Phenotype helpers + conflict alert
# =============================================================================

# =============================================================================
# 4.2) ABO discrepancy engine (general + specific guidance)
# =============================================================================
def _grade_rank(g: str) -> int:
    g = _safe_str(g)
    if g in ("Not Done","",None):
        return -1
    if g == "0":
        return 0
    if g == "Hemolysis":
        return 99
    if g == "Mixed-field":
        return 50
    m = re.match(r"\+(\d)", g)
    if m:
        return int(m.group(1))
    return -1

def _is_expected_pos_weak(g: str) -> bool:
    # Reverse expected positives should be ≥2+
    return _safe_str(g) in ("0","+1","Not Done","")

def _all_entered(grades: list) -> bool:
    return all(_safe_str(x) not in ("Not Done","",None) for x in grades)

def build_abo_guidance(
    is_neonate: bool,
    purpose: str,
    raw: Dict[str, str],
    screen_grades: Dict[str, str],
    dat_inputs: Dict[str, str]
) -> Dict[str, Any]:
    """
    Returns:
      {
        general: [..],
        specific: [{title, bullets}]
      }
    All guidance text is English.
    """
    general = [
        "Clerical check: confirm patient identity, specimen labels/barcodes, request details, and historical ABO/RhD (if available).",
        "Technical check: verify reagent/lot/expiry/storage, QC/control results, specimen quality, and repeat testing (or recollect) as needed.",
        "Clinical history: review recent transfusion, hematopoietic stem cell/BM transplant, neonatal/cord sample details, and relevant diagnoses."
    ]
    specific = []

    def add(title: str, bullets: list):
        bullets = [b for b in bullets if _safe_str(b)]
        if bullets:
            specific.append({"title": title, "bullets": bullets})

    # Screen status
    sc_I   = _safe_str(screen_grades.get("I","Not Done"))
    sc_II  = _safe_str(screen_grades.get("II","Not Done"))
    sc_III = _safe_str(screen_grades.get("III","Not Done"))
    sc_list = [sc_I, sc_II, sc_III]
    screen_complete = _all_entered(sc_list)
    screen_any_pos  = any(_is_pos_any(g) for g in sc_list if _safe_str(g) not in ("Not Done",""))
    screen_all_pos  = screen_complete and all(_is_pos_any(g) for g in sc_list)

    # Determine forward ABO guess
    antiA = _safe_str(raw.get("antiA","Not Done"))
    antiB = _safe_str(raw.get("antiB","Not Done"))
    fwd_abo = _abo_from_forward_only(antiA, antiB)

    # Grab reverse (adult)
    rev_a1 = _safe_str(raw.get("a1cells","Not Done"))
    rev_b  = _safe_str(raw.get("bcells","Not Done"))
    ctl    = _safe_str(raw.get("ctl","Not Done"))

    # 0) Control / spontaneous agglutination / combined discrepancies
    if _is_pos_any(ctl):
        add(
            "Control is POSITIVE / spontaneous agglutination suspected",
            [
                "Do NOT interpret ABO until the cause is resolved.",
                "Consider cold autoantibody (Auto-anti-I) or specimen interference.",
                "Forward (resolution): wash patient RBCs multiple times with 37°C warm saline; if IgM-related agglutination persists and DTT is available, consider DTT treatment per SOP.",
                "Reverse (resolution): perform pre-warming technique (warm serum and reagent cells separately to 37°C before mixing). If strong/persistent, consider cold auto-adsorption using the patient's washed RBCs per SOP."
            ]
        )

    # 1) Forward weak/missing antigens
    if antiA in ("+1","+2") or antiB in ("+1","+2"):
        bullets = [
            "Incubate at room temperature (RT) for 15–30 minutes, then repeat forward grouping.",
            "If still weak, consider enzyme-treated cells (if available) per SOP.",
            "If needed, perform adsorption/elution or refer to a reference lab per SOP."
        ]
        add("Weak/Missing Antigens (Forward grouping is weak)", bullets)

    # 2) Mixed-field emphasis (history-driven)
    if "Mixed-field" in (antiA, antiB, rev_a1, rev_b):
        add(
            "Mixed-field pattern detected — correlate with history",
            [
                "Most common: recent Group O RBC transfusion to a non-O patient (A/B/AB).",
                "Early after hematopoietic stem cell / bone marrow transplant (e.g., O donor → A recipient).",
                "A3 subgroup.",
                "Chimerism (twin / dispermic).",
                "Document the suspected cause in the technologist comment and confirm manually once history is verified."
            ]
        )

    # 3) Reverse weak/missing antibodies (adult/child)
    if not is_neonate and fwd_abo in ("A","B","O") and _safe_str(rev_a1) not in ("Not Done","") and _safe_str(rev_b) not in ("Not Done",""):
        a1_should_pos = (fwd_abo in ("B","O"))
        b_should_pos  = (fwd_abo in ("A","O"))
        weak_hit = (a1_should_pos and _safe_str(rev_a1) in ("0","+1")) or (b_should_pos and _safe_str(rev_b) in ("0","+1"))
        if weak_hit:
            need_cells = []
            if a1_should_pos and _safe_str(rev_a1) in ("0","+1"):
                need_cells.append("A1 cells")
            if b_should_pos and _safe_str(rev_b) in ("0","+1"):
                need_cells.append("B cells")
            add(
                "Weak/Missing Antibodies (Reverse grouping is weak/negative)",
                [
                    f"Forward suggests Group {fwd_abo}; reverse reactivity is weak/absent in expected cell(s): {', '.join(need_cells)}.",
                    "1) Incubate at RT for 15 minutes, then repeat reverse grouping.",
                    "2) If still negative/weak: use double-dose plasma, then repeat reverse grouping.",
                    "3) If still negative/weak: incubate at 4°C for 15 minutes and repeat reverse grouping. ⚠️ Must run Auto-Control."
                ]
            )

    # 4) Unexpected reverse reaction with A1 cells (Forward A or AB)
    if not is_neonate and fwd_abo in ("A","AB") and _is_pos_any(rev_a1):
        if not screen_complete:
            add(
                "Unexpected reverse reaction (A1 cells POSITIVE) — antibody screen needed",
                [
                    "Repeat reverse grouping to exclude technical/clerical error.",
                    "Run Auto-Control with reverse grouping.",
                    "Perform antibody screen and enter the result to refine the interpretation."
                ]
            )
        elif screen_any_pos:
            # Priority: address reverse interference when the antibody screen is positive.
            add(
                "Extra (Unexpected) — Screen POSITIVE (priority)",
                [
                    "Antibody screen is POSITIVE — an antibody may be responsible for the unexpected reverse reaction (e.g., cold-reactive allo/autoantibody) and/or rouleaux.",
                    "1) Rouleaux: perform saline replacement (reverse grouping).",
                    "2) Cold antibody (e.g., M, P1): perform pre-warming technique (37°C).",
                    "Proceed with antibody investigation/identification as indicated, then re-interpret ABO after interference is addressed.",
                ],
            )
            # Still consider Anti-A1 when the pattern fits (may coexist with other antibodies).
            add(
                "Also consider: Anti-A1 in an A subgroup (pattern-based)",
                [
                    "Because A1 cells are reactive with an A (or AB) forward type, Anti-A1 in an A2/A2B subgroup remains a possible contributor (may coexist with other antibodies).",
                    "👉 Test patient red cells with Anti-A1 lectin (Dolichos biflorus).",
                    "👉 Test patient serum with A2 reagent cells.",
                ],
            )

        else:
            add(
                "Extra (Unexpected) — Screen NEGATIVE",
                [
                    "Suspect Anti-A1 in an A2 subgroup (or A2B if AB forward).",
                    "Test patient RBCs with Anti-A1 lectin (Dolichos biflorus).",
                    "Test patient serum with A2 cells."
                ]
            )

    # 5) Bombay (Oh) suspicion
    if not is_neonate and fwd_abo == "O" and screen_all_pos:
        add(
            "All screening cells POSITIVE with Forward Group O — suspect Bombay (Oh)",
            [
                "Pan-reactivity on group O reagent cells suggests anti-H.",
                "Test patient RBCs with Anti-H lectin.",
                "Negative reaction with Anti-H lectin supports Bombay (Oh)."
            ]
        )

    # 6) Extra unexpected antigens: Acquired B
    if not is_neonate:
        # Pattern: forward looks AB but reverse looks A (strong anti-B present)
        if _is_pos_any(antiA) and _is_pos_any(antiB) and (not _is_pos_any(rev_a1)) and (_grade_rank(rev_b) >= 2):
            add(
                "Extra Unexpected Antigen — Acquired B phenotype (suspected)",
                [
                    "Clinical context: typically Group A patient with lower GI disease (e.g., colon cancer/bowel obstruction) or Gram-negative sepsis (e.g., E. coli).",
                    "Pattern: forward appears AB, while reverse appears A (strong anti-B in serum).",
                    "Investigations:",
                    "• Reagent verification: check Anti-B product insert; some monoclonal clones react with Acquired B. Retest using a different Anti-B clone if available.",
                    "• Auto-control: test patient serum against autologous RBCs.",
                    "• Acidified Anti-B test: test patient RBCs using human Anti-B serum acidified to pH 6.0 (if available).",
                    "Interpretation:",
                    "• If the Anti-B reaction disappears with a different monoclonal clone → consistent with Acquired B (patient is Group A).",
                    "• Auto-control is typically NEGATIVE in Acquired B.",
                    "• Acidified Anti-B: true B reacts strongly at pH 6.0; Acquired B does NOT react at pH 6.0."
                ]
            )

        # B(A) / A(B) phenotype (trace antigen with highly sensitive monoclonals)
        if fwd_abo in ("A","B"):
            # A(B): A forward with weak anti-B; B(A): B forward with weak anti-A
            weak_extra = False
            if fwd_abo == "A" and _safe_str(antiB) in ("+1","+2"):
                weak_extra = True
            if fwd_abo == "B" and _safe_str(antiA) in ("+1","+2"):
                weak_extra = True
            if weak_extra:
                add(
                    "Extra Unexpected Antigen — B(A) or A(B) phenotype (consider)",
                    [
                        "An autosomal dominant phenotype with trace antigen expression detected by highly sensitive monoclonal reagents (e.g., certain clones).",
                        "Resolution: retest using a different manufacturer’s reagent or polyclonal antisera (if available)."
                    ]
                )

    # 7) Wharton’s jelly (cord blood)
    cord_flag = bool(raw.get("cord_sample", False))
    if is_neonate and cord_flag:
        add(
            "Neonate cord sample — Wharton’s jelly contamination (consider)",
            [
                "Cord blood contaminated with hyaluronic acid-rich Wharton’s jelly may cause spontaneous agglutination.",
                "Resolution: wash cord RBCs 4–6 times with warm saline, then repeat forward grouping."
            ]
        )

    # 8) Strong DAT C3 (cold agglutinin supporting)
    dat_c3 = _safe_str(dat_inputs.get("c3d","Not Done"))
    if dat_c3 in ("+3","+4"):
        add(
            "DAT (C3) strongly POSITIVE — cold agglutinin interference (supporting)",
            [
                "Resolution: wash RBCs several times with warm saline and retest washed cells at 37°C."
            ]
        )

    return {"general": general, "specific": specific}



def build_how_to_report(
    is_neonate: bool,
    abo_interp: Dict[str, Any],
    raw: Dict[str, str],
    screen_any_positive: bool,
    mixed_field_history: Dict[str, bool] | None = None
) -> str:
    """Return an English copy/paste comment for the HIS/EMR based on the current pattern."""
    lines: list[str] = []
    mixed_field_history = mixed_field_history or {}
    recent_tx = bool(mixed_field_history.get("recent_tx"))
    hsct_bm = bool(mixed_field_history.get("hsct_bm"))

    # RhD inconclusive / weak D suspected
    rhd_final = _safe_str(abo_interp.get("rhd_final",""))
    if rhd_final.startswith("RhD Inconclusive"):
        lines.append("RhD typing is INCONCLUSIVE / weak D suspected.")
        lines.append("Interpretation note: a partial D phenotype cannot be excluded. Definitive classification requires RHD genotyping, which is not available at our facility.")
        lines.append("Transfusion safety: manage as RhD NEGATIVE (issue D− RBCs) until confirmed.")
        lines.append("RhIG note: when RhIG eligibility is clinically relevant (pregnancy, postpartum, newborn), manage as RhD NEGATIVE per local policy unless confirmatory testing is available.")
        lines.append("")

    # Weak forward antigens (any age): provide a reporting comment. In neonates, include an
    # administrative "most probable" statement with strict transfusion safety guidance.
    antiA_wf = _safe_str(raw.get("antiA","Not Done"))
    antiB_wf = _safe_str(raw.get("antiB","Not Done"))
    antiAB_wf = _safe_str(raw.get("antiAB","Not Done"))
    weak_forward = (antiA_wf in ("+1","+2")) or (antiB_wf in ("+1","+2")) or (antiAB_wf in ("+1","+2"))

    if weak_forward:
        abo_guess = _safe_str(abo_interp.get("abo_final",""))
        # Normalize strings like: "Most probable: A", "ABO: A", "A (Discrepancy)"
        abo_guess_clean = re.sub(r"\(.*?\)", "", abo_guess).strip()
        abo_guess_clean = re.sub(r"^(ABO\s*:\s*)", "", abo_guess_clean, flags=re.IGNORECASE).strip()
        abo_guess_clean = re.sub(r"^(Most\s+probable\s*:\s*)", "", abo_guess_clean, flags=re.IGNORECASE).strip()
        abo_guess_clean = abo_guess_clean or "Unknown"

        if is_neonate:
            lines.append("Forward grouping shows a WEAK reaction in a neonate (≤3–4 months) / cord sample pattern.")
            lines.append(f"ABO group: MOST PROBABLE {abo_guess_clean} based on current testing (administrative only).")
            lines.append("Action: repeat testing / recollect if indicated and CONFIRM ABO at ≥6 months of age (or per local policy).")
            lines.append("Transfusion until confirmed: issue Group O RBCs and AB plasma/platelets (or per local policy).")
            lines.append("")
        else:
            lines.append(
                f"ABO grouping is inconclusive due to weak forward antigen reactions. Forward typing suggests {abo_guess_clean}, "
                "however the ABO group cannot be confirmed at this stage. Repeat testing and resolve per SOP. "
                "Until confirmed, manage as ABO unknown for transfusion purposes (issue Group O RBCs and Group AB plasma/platelets per policy)."
            )

    # Mixed-field reporting (adult/child or neonate)
    antiA = _safe_str(raw.get("antiA","Not Done"))
    antiB = _safe_str(raw.get("antiB","Not Done"))
    rev_a1 = _safe_str(raw.get("a1cells","Not Done"))
    rev_b  = _safe_str(raw.get("bcells","Not Done"))
    mixed_field_present = "Mixed-field" in (antiA, antiB, _safe_str(raw.get("antiAB","")), rev_a1, rev_b, _safe_str(raw.get("ctl","")))

    if mixed_field_present:
        if recent_tx:
            lines.append(
                "Mixed-field pattern detected on ABO grouping. This is most consistent with recent transfusion, "
                "particularly Group O RBC transfusion to a non-O patient, resulting in mixed red cell populations. "
                "Correlate with transfusion history and prior documented blood group. Do not finalize ABO as confirmed based on the current specimen alone; "
                "repeat grouping on a new specimen as clinically appropriate and follow facility policy for interim transfusion management."
            )
        elif hsct_bm:
            lines.append(
                "Mixed-field pattern detected on ABO grouping. In the context of hematopoietic stem cell / bone marrow transplantation, "
                "this may represent post-transplant chimerism (donor/recipient mixed populations). "
                "Correlate with transplant timeline and historical ABO records (pre- and post-transplant). "
                "Do not finalize ABO as confirmed based on this specimen alone; manage per transplant transfusion policy and specialist guidance."
            )
        else:
            lines.append(
                "Mixed-field pattern detected on ABO grouping. Correlate with clinical history (recent transfusion, hematopoietic stem cell/BM transplant, "
                "A3 subgroup, or chimerism) and prior records. Do not finalize ABO as confirmed based on this specimen alone; repeat testing per policy."
            )

    # Reverse weak/missing antibodies (adult/child)
    if (not is_neonate) and "ABO DISCREPANCY" in " ".join([_safe_str(x) for x in abo_interp.get("notes", [])]):
        # Only add if not already covered by mixed-field / RhD comment
        if any("Reverse grouping is weaker" in _safe_str(n) for n in abo_interp.get("notes", [])):
            lines.append(
                "ABO discrepancy (reverse grouping): weak/missing expected antibodies. Forward grouping suggests the listed ABO type, "
                "however reverse reactions are weaker than expected/absent and the ABO group cannot be confirmed at this stage. "
                "Perform discrepancy resolution per protocol and do not finalize ABO as confirmed until resolved."
            )

    # Unexpected reverse with A1 cells + screen linkage
    if (not is_neonate) and any("Anti-A1" in _safe_str(n) or "unexpected reverse" in _safe_str(n).lower() for n in abo_interp.get("notes", [])):
        if screen_any_positive:
            lines.append(
                "Unexpected reverse reaction noted (A1 cells reactive). Antibody screen is POSITIVE, which may account for the unexpected reverse reactivity "
                "(e.g., cold-reactive allo/autoantibody and/or rouleaux). Proceed with interference resolution per SOP (e.g., saline replacement and/or pre-warming technique), "
                "and proceed with antibody investigation/identification as indicated. Because the pattern includes A1-cell reactivity, Anti-A1 in an A subgroup (A2/A2B) "
                "should still be considered as a possible contributor; confirm with Anti-A1 lectin and serum testing with A2 cells per SOP. Interpret/finalize ABO only after resolution/confirmation."
            )
        else:
            lines.append(
                "Unexpected reverse reaction noted (A1 cells reactive) with NEGATIVE antibody screen. This pattern may suggest Anti-A1 in an A subgroup (e.g., A2/A2B). "
                "Recommend confirmatory testing (Anti-A1 lectin and serum testing with A2 cells) per SOP."
            )

    return "\n\n".join([l for l in lines if l]).strip()
def _phenotype_get_antigen_state(ph: Dict[str, str], ag: str) -> str:
    return _safe_str(ph.get(ag, "Not Done"))

def _phenotype_is_detected(ph: Dict[str, str], ag: str) -> bool:
    return _phenotype_get_antigen_state(ph, ag) == "Detected"

def phenotype_conflict_notes(suspected_antibodies: List[str], phenotype: Dict[str, str]) -> List[str]:
    notes = []
    for ag in suspected_antibodies:
        if ag in IGNORED_AGS:
            continue
        if _phenotype_is_detected(phenotype, ag):
            notes.append(f"Conflict: Anti-{ag} suggested/confirmed but patient phenotype shows {ag} = Detected. Verify phenotype was done on PRE-transfusion sample and review antibody identification.")
    return notes

# =============================================================================
# 4.3) HISTORY REPORT (Professional view)
# =============================================================================
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

    demo = payload.get("demographics", {}) or {}
    abo = payload.get("abo", {}) or {}
    pheno = payload.get("phenotype", {}) or {}

    name = _safe_str(patient.get("name",""))
    mrn  = _safe_str(patient.get("mrn",""))
    tech = _safe_str(payload.get("tech",""))
    run_dt = _safe_str(payload.get("run_dt",""))
    saved_at = _safe_str(payload.get("saved_at",""))

    sex = _safe_str(demo.get("sex",""))
    age_y = _safe_str(demo.get("age_y",""))
    age_m = _safe_str(demo.get("age_m",""))
    age_d = _safe_str(demo.get("age_d",""))

    ac = _safe_str(inputs.get("AC",""))
    recent_tx = bool(inputs.get("recent_tx", False))
    all_rx = bool(payload.get("all_rx", False))

    lot_p = _safe_str(lots.get("panel",""))
    lot_s = _safe_str(lots.get("screen",""))

    abo_final = _safe_str(abo.get("abo_final",""))
    rhd_final = _safe_str(abo.get("rhd_final",""))
    abo_disc = bool(abo.get("discrepancy", False))

    chips = []
    if abo_final:
        chips.append(f"<span class='chip {'chip-warn' if abo_disc else 'chip-ok'}'>ABO: {abo_final}</span>")
    if rhd_final:
        chips.append(f"<span class='chip {'chip-warn' if 'Inconclusive' in rhd_final else 'chip-ok'}'>RhD: {rhd_final}</span>")
    chips.append(f"<span class='chip chip-ok'>AC: {ac or '—'}</span>")
    chips.append(f"<span class='chip {'chip-danger' if all_rx else 'chip-ok'}'>Pattern: {'PAN-reactive' if all_rx else 'Non-pan'}</span>")
    if recent_tx:
        chips.append("<span class='chip chip-danger'>Recent transfusion ≤ 4 weeks</span>")
    else:
        chips.append("<span class='chip chip-ok'>No recent transfusion flag</span>")

    dat_igg = _safe_str(dat.get("igg",""))
    dat_c3d = _safe_str(dat.get("c3d",""))
    dat_ctl = _safe_str(dat.get("control",""))
    if dat_igg or dat_c3d or dat_ctl:
        chips.append(f"<span class='chip chip-warn'>DAT IgG: {dat_igg or '—'}</span>")
        chips.append(f"<span class='chip chip-warn'>DAT C3d: {dat_c3d or '—'}</span>")
        chips.append(f"<span class='chip chip-warn'>DAT Control: {dat_ctl or '—'}</span>")

    st.markdown(f"""
    <div class="report-card">
        <div class="report-title">Case History Report</div>
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
        st.markdown(f"<div class='kv'><b>Age (Y/M/D)</b><br>{age_y or '—'} / {age_m or '—'} / {age_d or '—'}</div>", unsafe_allow_html=True)

    st.write("")
    a1, a2, a3 = st.columns(3)
    with a1:
        st.markdown(f"<div class='kv'><b>Tech / Operator</b><br>{tech or '—'}</div>", unsafe_allow_html=True)
    with a2:
        st.markdown(f"<div class='kv'><b>ID Panel Lot</b><br>{lot_p or '—'}</div>", unsafe_allow_html=True)
    with a3:
        st.markdown(f"<div class='kv'><b>Screen Lot</b><br>{lot_s or '—'}</div>", unsafe_allow_html=True)

    # ABO raw
    st.write("")
    st.subheader("ABO / RhD / DAT")
    abo_raw = abo.get("raw", {}) or {}
    if abo_raw:
        st.json(abo_raw, expanded=False)

    notes = abo.get("notes", []) or []
    if notes:
        st.markdown(
            "<div class='clinical-alert'><b>ABO Discrepancy Notes</b><ul style='margin-top:6px;'>" +
            "".join([f"<li>{_safe_str(n)}</li>" for n in notes]) +
            "</ul></div>",
            unsafe_allow_html=True
        )

    # Phenotype
    st.write("")
    st.subheader("Patient Phenotype (if available)")
    if pheno:
        ph_dict = pheno.get("results", {}) or {}
        if ph_dict:
            # render in a compact table
            rows = [{"Antigen": k, "Result": v} for k,v in ph_dict.items()]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.write("—")
    else:
        st.write("—")

    # Reactions
    st.write("")
    st.subheader("Antibody ID — Reactions Summary")
    screen_rx = inputs.get("screen_reactions", {}) or {}
    panel_rx  = inputs.get("panel_reactions", {}) or {}

    sr_df = pd.DataFrame([{
        "Screen I": screen_rx.get("I",""),
        "Screen II": screen_rx.get("II",""),
        "Screen III": screen_rx.get("III",""),
    }])
    st.markdown("**Screening Cells**")
    st.dataframe(sr_df, use_container_width=True, hide_index=True)

    pr_rows = []
    for i in range(1, 12):
        pr_rows.append({"Cell": f"Panel #{i}", "Reaction": panel_rx.get(str(i), panel_rx.get(i, ""))})
    pr_df = pd.DataFrame(pr_rows)
    st.markdown("**Panel Cells (1–11)**")
    st.dataframe(pr_df, use_container_width=True, hide_index=True)

    # Interpretation
    st.write("")
    st.subheader("Antibody ID — Interpretation / Results")
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
                st.dataframe(sc_df[cols], use_container_width=True, hide_index=True)
            else:
                st.dataframe(sc_df, use_container_width=True, hide_index=True)
        except Exception:
            st.write(selected)
    else:
        st.write("— None —")

# =============================================================================
# 4.4) SUPERVISOR: Copy/Paste Parser (Option A: 26 columns in AGS order)
# =============================================================================
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

# =============================================================================
# 5) SIDEBAR (Menu + Reset)
# =============================================================================
RESET_KEYS = [
    # demographics
    "pt_name","pt_mrn","pt_sex","age_y","age_m","age_d","tech_nm","run_dt",
    # ABO
    "abo_purpose",
    "abo_adult_antiA","abo_adult_antiB","abo_adult_antiD","abo_adult_ctl","abo_adult_a1","abo_adult_b",
    "abo_neonate_antiA","abo_neonate_antiB","abo_neonate_antiAB","abo_neonate_antiD","abo_neonate_ctl","abo_neonate_dat",
    # phenotype
    "ph_rh_C","ph_rh_c","ph_rh_E","ph_rh_e","ph_rh_K","ph_rh_ctl",
    "ph_ex_P1","ph_ex_Lea","ph_ex_Leb","ph_ex_Lua","ph_ex_Lub","ph_ex_ctl1",
    "ph_ex_k","ph_ex_Kpa","ph_ex_Kpb","ph_ex_Jka","ph_ex_Jkb","ph_ex_ctl2",
    "ph_ex_M","ph_ex_N","ph_ex_S","ph_ex_s","ph_ex_Fya","ph_ex_Fyb",
    # antibody reactions
    "rx_ac","recent_tx","rx_sI","rx_sII","rx_sIII",
    "rx_p1","rx_p2","rx_p3","rx_p4","rx_p5","rx_p6","rx_p7","rx_p8","rx_p9","rx_p10","rx_p11",
    # dat
    "dat_igg","dat_c3d","dat_ctl",
    # analysis flags
    "analysis_ready","analysis_payload",
]

with st.sidebar:
    # Use your custom icon file if you want later; for now keep a stable URL
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Menu", ["Workstation", "Supervisor"], key="nav_menu")
    st.markdown("---")
    st.radio("Theme", ["Burgundy / White", "Navy / Cyan"], key="ui_theme")
    THEME_VARS = _get_theme_vars(st.session_state.ui_theme)  # refresh after selection

    if st.button("RESET DATA", key="btn_reset"):
        st.session_state.ext = []
        for k in RESET_KEYS:
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()

# =============================================================================
# 6) SUPERVISOR PAGE
# =============================================================================
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
        st.info("Option A active: Paste **26 columns** exactly in **AGS order**. Rows should be tab-separated. "
                "If your paste includes extra leading columns, the app will take the **last 26**.")

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
                st.dataframe(st.session_state.panel11_df.iloc[:, :15], use_container_width=True, hide_index=True)

            with cB:
                st.markdown("### Screen 3 (Paste)")
                s_txt = st.text_area("Paste 3 rows (tab-separated; 26 columns in AGS order)", height=170, key="p3_paste")
                if st.button("✅ Update Screen 3 from Paste", key="upd_p3_paste"):
                    df_new, msg = parse_paste_table(s_txt, expected_rows=3, id_prefix="S", id_list=["SI", "SII", "SIII"])
                    df_new["ID"] = ["SI", "SII", "SIII"]
                    st.session_state.screen3_df = df_new.copy()
                    st.success(msg + " Screen 3 updated locally.")

                st.caption("Preview (Screen 3)")
                st.dataframe(st.session_state.screen3_df.iloc[:, :15], use_container_width=True, hide_index=True)

            st.markdown("""
            <div class='clinical-alert'>
            ⚠️ Tip: If your PDF/table has label columns before the antigen columns, the paste will have extra leading columns.
            The app automatically takes the <b>last 26 columns</b> and ignores any columns before them.
            </div>
            """, unsafe_allow_html=True)

        with tab_edit:
            st.markdown("### Manual Edit (Supervisor only) — Safe mode")
            st.markdown("""
            <div class='clinical-info'>
            ✅ Safe rules applied: <b>ID locked</b> + <b>No add/remove rows</b> + <b>Only 0/1 via checkboxes</b>.<br>
            Use this only for manual corrections after Copy/Paste.
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
        st.warning("Before publishing: review lots and panel/screen grids quickly.")

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

# =============================================================================
# 7) WORKSTATION PAGE
# =============================================================================
else:
    st.markdown("""<div class='site-title'>Maternity &amp; Children Hospital – Tabuk</div>""", unsafe_allow_html=True)

    st.markdown("""
        <div class='app-header'>
        <div class='app-title'>Doctor Decision</div>
            <div class='app-tagline'>ABO • RhD • DAT • Phenotype • Antibody ID</div>
    </div>
    """, unsafe_allow_html=True)

    lp_txt = st.session_state.lot_p if st.session_state.lot_p else "⚠️ REQUIRED"
    ls_txt = st.session_state.lot_s if st.session_state.lot_s else "⚠️ REQUIRED"
    st.markdown(f"<div class='lot-bar'><span>ID Panel Lot: {lp_txt}</span> | <span>Screen Lot: {ls_txt}</span></div>",
                unsafe_allow_html=True)

    # ----------------------------------------------------------------------
    # Demographics row (same line: Sex + Age Y/M/D + Tech)
    # ----------------------------------------------------------------------
    colw = st.columns([2.0, 1.4, 1.0, 0.7, 0.7, 0.7, 1.2, 1.2])
    _ = colw[0].text_input("Name", key="pt_name")
    _ = colw[1].text_input("MRN", key="pt_mrn")
    _ = colw[2].selectbox("Sex", SEX_OPTS, key="pt_sex")
    _ = colw[3].number_input("Age Y", min_value=0, max_value=130, step=1, key="age_y")
    _ = colw[4].number_input("Age M", min_value=0, max_value=11, step=1, key="age_m")
    _ = colw[5].number_input("Age D", min_value=0, max_value=31, step=1, key="age_d")
    _ = colw[6].text_input("Tech", key="tech_nm")
    _ = colw[7].date_input("Date", value=date.today(), key="run_dt")

    age_y = int(st.session_state.get("age_y", 0) or 0)
    age_m = int(st.session_state.get("age_m", 0) or 0)
    age_d = int(st.session_state.get("age_d", 0) or 0)
    is_neonate = _age_is_neonate(age_y, age_m, age_d)

    # ----------------------------------------------------------------------
    # HISTORY LOOKUP (GitHub; MRN-based)
    # ----------------------------------------------------------------------
    mrn_now = _safe_str(st.session_state.get("pt_mrn",""))
    if mrn_now:
        try:
            hist_df = load_history_index_as_df(mrn_now)
        except Exception as e:
            hist_df = pd.DataFrame()
            st.error(f"History lookup failed: {e}")

        if len(hist_df) > 0:
            st.markdown(f"""
            <div class='clinical-alert'>
            🧾 <b>History Found</b> — This patient has <b>{len(hist_df)}</b> previous record(s).  
            Please review before interpretation.
            </div>
            """, unsafe_allow_html=True)

            with st.expander("📚 Open Patient History"):
                show_cols = ["saved_at","run_dt","tech","sex","age_y","age_m","age_d","abo_final","rhd_final","abo_discrepancy","conclusion_short","ac_res","recent_tx","all_rx","case_id"]
                st.dataframe(hist_df[show_cols], use_container_width=True, hide_index=True)

                idx_list = list(range(len(hist_df)))
                pick = st.selectbox(
                    "Select a previous run",
                    idx_list,
                    format_func=lambda i: f"{hist_df.iloc[i]['saved_at']} | {hist_df.iloc[i]['conclusion_short']}"
                )
                if st.button("Open selected run (Report)", key="btn_open_hist_report"):
                    case_id = _safe_str(hist_df.iloc[pick]["case_id"])
                    payload = load_case_payload(mrn_now, case_id)
                    if not payload:
                        st.error("Could not open this record (missing/corrupted).")
                    else:
                        render_history_report(payload)

    # ----------------------------------------------------------------------
    # ABO / RhD / DAT section (collapsed, opens when discrepancy)
    # ----------------------------------------------------------------------

    # ----------------------------------------------------------------------
    # ABO / RhD / DAT section (collapsible; interpretation only after confirmation)
    # ----------------------------------------------------------------------
    with st.expander("🧾 ABO / RhD / DAT (Enter by grade)", expanded=False):

        # Let user choose workflow card (do NOT assume neonate when age is not entered)
        age_entered = (age_y + age_m + age_d) > 0
        if "abo_card_mode" not in st.session_state:
            st.session_state.abo_card_mode = "Adult/Child (≥ 4 months)"
            if age_entered and is_neonate:
                st.session_state.abo_card_mode = "Newborn/Neonate (< 4 months)"

        card_mode = st.radio(
            "ABO workflow card",
            ["Adult/Child (≥ 4 months)", "Newborn/Neonate (< 4 months)"],
            horizontal=True,
            key="abo_card_mode"
        )
        abo_is_neonate = card_mode.startswith("Newborn")

        # Build ABO raw input (current)
        if abo_is_neonate:
            st.markdown("""
            <div class='clinical-info'>
            👶 <b>Newborn/Neonate mode</b>: reverse grouping is typically unreliable and may be omitted per policy.<br>
            </div>
            """, unsafe_allow_html=True)

            purpose = st.radio("Purpose", ["Transfusion", "RhIG"], horizontal=True, key="abo_purpose")
            cord_sample = st.checkbox("Cord blood sample?", value=False, key="abo_cord_sample")

            c1, c2, c3, c4, c5, c6 = st.columns(6)
            with c1:
                st.markdown(_render_abo_label_html('Anti-A', 'abo-a'), unsafe_allow_html=True)
                antiA = st.selectbox('Anti-A', ABO_GRADES, key='abo_neonate_antiA', label_visibility='collapsed')
            with c2:
                st.markdown(_render_abo_label_html('Anti-B', 'abo-b'), unsafe_allow_html=True)
                antiB = st.selectbox('Anti-B', ABO_GRADES, key='abo_neonate_antiB', label_visibility='collapsed')
            with c3:
                st.markdown(_render_abo_label_html('Anti-AB', 'neo-ab'), unsafe_allow_html=True)
                antiAB = st.selectbox('Anti-AB', ABO_GRADES, key='abo_neonate_antiAB', label_visibility='collapsed')
            with c4:
                st.markdown(_render_abo_label_html('Anti-D (DVI+)', 'neo-d'), unsafe_allow_html=True)
                antiD = st.selectbox('Anti-D', ABO_GRADES, key='abo_neonate_antiD', label_visibility='collapsed')
            with c5:
                st.markdown(_render_abo_label_html('Control', 'neo-ctl', ctl_badge=True), unsafe_allow_html=True)
                ctl = st.selectbox('Control', ABO_GRADES, key='abo_neonate_ctl', label_visibility='collapsed')
            with c6:
                st.markdown(_render_abo_label_html('DAT', 'neo-dat'), unsafe_allow_html=True)
                datg = st.selectbox('DAT (grade or Not Done)', ABO_GRADES, key='abo_neonate_dat', label_visibility='collapsed')

            abo_raw_current = {
                "mode": "neonate",
                "purpose": "RhIG" if purpose == "RhIG" else "Transfusion",
                "antiA": antiA,
                "antiB": antiB,
                "antiAB": antiAB,
                "antiD": antiD,
                "ctl": ctl,
                "dat": datg,
                "cord_sample": bool(cord_sample),
            }
        else:
            st.markdown("""
            <div class='clinical-info'>
            👤 <b>Adult/Child mode</b>: forward + reverse grouping are required (per policy).
            </div>
            """, unsafe_allow_html=True)

            c1, c2, c3, c4, c5, c6 = st.columns(6)
            with c1:
                st.markdown(_render_abo_label_html('Anti-A', 'abo-a'), unsafe_allow_html=True)
                antiA = st.selectbox('Anti-A', ABO_GRADES, key='abo_adult_antiA', label_visibility='collapsed')
            with c2:
                st.markdown(_render_abo_label_html('Anti-B', 'abo-b'), unsafe_allow_html=True)
                antiB = st.selectbox('Anti-B', ABO_GRADES, key='abo_adult_antiB', label_visibility='collapsed')
            with c3:
                st.markdown(_render_abo_label_html('Anti-D (DVI−)', 'abo-d'), unsafe_allow_html=True)
                antiD = st.selectbox('Anti-D', ABO_GRADES, key='abo_adult_antiD', label_visibility='collapsed')
            with c4:
                st.markdown(_render_abo_label_html('Control', 'abo-ctl'), unsafe_allow_html=True)
                ctl  = st.selectbox('Control', ABO_GRADES, key='abo_adult_ctl', label_visibility='collapsed')
            with c5:
                st.markdown(_render_abo_label_html('A1 cells', 'abo-a1'), unsafe_allow_html=True)
                a1cells = st.selectbox('A1 cells', ABO_GRADES, key='abo_adult_a1', label_visibility='collapsed')
            with c6:
                st.markdown(_render_abo_label_html('B cells', 'abo-bcells'), unsafe_allow_html=True)
                bcells  = st.selectbox('B cells', ABO_GRADES, key='abo_adult_b', label_visibility='collapsed')



            abo_raw_current = {
                "mode": "adult",
                "antiA": antiA,
                "antiB": antiB,
                "antiD": antiD,
                "ctl": ctl,
                "a1cells": a1cells,
                "bcells": bcells
            }

        # Confirmation gate (prevents early 'discrepancy' before entries are complete)
        colb1, colb2 = st.columns([1, 1])
        confirm_abo = colb1.button("✅ Confirm ABO entry", type="primary", use_container_width=True, key="abo_confirm_btn")
        reset_abo   = colb2.button("✏️ Edit / Reset confirmation", use_container_width=True, key="abo_reset_btn")

        if reset_abo:
            st.session_state.abo_confirmed = False
            st.session_state.abo_raw_confirmed = None
            st.session_state.abo_interp_confirmed = None
            st.session_state.abo_guidance_confirmed = None
            st.session_state.abo_screen_any_positive = False

        if confirm_abo:
            # Basic completeness checks
            missing = []
            if abo_is_neonate:
                for k, lbl in [("antiA","Anti-A"),("antiB","Anti-B"),("antiD","Anti-D"),("ctl","Control")]:
                    if _safe_str(abo_raw_current.get(k,"Not Done")) in ("Not Done",""):
                        missing.append(lbl)
            else:
                for k, lbl in [("antiA","Anti-A"),("antiB","Anti-B"),("antiD","Anti-D"),("ctl","Control"),("a1cells","A1 cells"),("bcells","B cells")]:
                    if _safe_str(abo_raw_current.get(k,"Not Done")) in ("Not Done",""):
                        missing.append(lbl)

            if missing:
                st.error("Please complete the following fields before confirmation: " + ", ".join(missing))
            else:
                # Link inputs (screen + DAT)
                screen_grades = {
                    "I": _safe_str(st.session_state.get("rx_sI","Not Done")),
                    "II": _safe_str(st.session_state.get("rx_sII","Not Done")),
                    "III": _safe_str(st.session_state.get("rx_sIII","Not Done")),
                }
                dat_inputs = {
                    "igg": _safe_str(st.session_state.get("dat_igg","Not Done")),
                    "c3d": _safe_str(st.session_state.get("dat_c3d","Not Done")),
                    "ctl": _safe_str(st.session_state.get("dat_ctl","Not Done")),
                }

                screen_any_pos = any(_is_pos_any(g) for g in screen_grades.values() if _safe_str(g) not in ("Not Done",""))
                st.session_state.abo_screen_any_positive = bool(screen_any_pos)

                # Interpret (ABO/RhD)
                abo_interp_tmp = interpret_abo_rhd(
                    is_neonate=abo_is_neonate,
                    purpose=("RhIG" if _safe_str(abo_raw_current.get("purpose","Transfusion")) == "RhIG" else "Transfusion"),
                    raw=abo_raw_current,
                    screen_any_positive=bool(screen_any_pos)
                )
                guidance_tmp = build_abo_guidance(
                    is_neonate=abo_is_neonate,
                    purpose=_safe_str(abo_raw_current.get("purpose","Transfusion")),
                    raw=abo_raw_current,
                    screen_grades=screen_grades,
                    dat_inputs=dat_inputs
                )

                st.session_state.abo_confirmed = True
                st.session_state.abo_raw_confirmed = abo_raw_current
                st.session_state.abo_interp_confirmed = abo_interp_tmp
                st.session_state.abo_guidance_confirmed = guidance_tmp

        # Display (only after confirmation)
        if st.session_state.get("abo_confirmed", False) and st.session_state.get("abo_interp_confirmed"):
            abo_interp = st.session_state.abo_interp_confirmed
            guid = st.session_state.get("abo_guidance_confirmed") or {"general": [], "specific": []}

            is_discrep = bool(abo_interp.get("discrepancy", False)) or bool(abo_interp.get("invalid", False))
            abo_final = abo_interp.get("abo_final", "Unknown")
            rhd_final = abo_interp.get("rhd_final", "Unknown")

            # Highlight exactly where the issue is (ABO vs RhD)
            notes_join = " ".join([str(x) for x in abo_interp.get("notes", [])])
            control_pos = "Control is POSITIVE" in notes_join
            abo_issue = control_pos or ("Discrepancy" in abo_final) or ("Most probable" in abo_final) or (abo_final.strip().lower() in ("unknown", "invalid", "inconclusive"))
            rhd_issue = control_pos or ("Inconclusive" in rhd_final) or (rhd_final.strip().lower() in ("unknown", "invalid"))

            abo_chip = "chip-warn" if abo_issue else "chip-ok"
            rhd_chip = "chip-warn" if rhd_issue else "chip-ok"
            if is_discrep:
                st.markdown(f"""
                <div class='clinical-danger'>
                  ⚠️ <b>ABO DISCREPANCY / SPECIAL SITUATION</b>
                  <div class='status-row'>
                    <span class='status-chip {abo_chip}'><span class='chip-label'>ABO</span> {abo_final}</span>
                    <span class='status-chip {rhd_chip}'><span class='chip-label'>RhD</span> {rhd_final}</span>
                  </div>
                </div>
                """, unsafe_allow_html=True)

                st.markdown("<div class='clinical-alert'><b>General rule (always start here):</b></div>", unsafe_allow_html=True)
                st.markdown(
                    "<div class='clinical-alert'><ul style='margin-top:6px;'>" +
                    "".join([f"<li>{_safe_str(x)}</li>" for x in guid.get('general',[])]) +
                    "</ul></div>",
                    unsafe_allow_html=True
                )

                # Specific guidance
                if guid.get("specific"):
                    st.markdown("<div class='clinical-alert'><b>Specific guidance (based on the pattern entered):</b></div>", unsafe_allow_html=True)
                    for sec in guid["specific"]:
                        st.markdown(
                            "<div class='clinical-info'><b>" + _safe_str(sec.get("title","")) + "</b>" +
                            "<ul style='margin-top:6px;'>" +
                            "".join([f"<li>{_safe_str(b)}</li>" for b in sec.get("bullets",[])]) +
                            "</ul></div>",
                            unsafe_allow_html=True
                        )
                else:
                    st.info("No specific rule was triggered by the current pattern. Continue with clerical/technical checks and clinical history.")
                # Mixed-field history prompts (used for smarter reporting)
                mf_present = False
                if abo_is_neonate:
                    mf_present = "Mixed-field" in (
                        _safe_str(st.session_state.get("abo_neonate_antiA","")),
                        _safe_str(st.session_state.get("abo_neonate_antiB","")),
                        _safe_str(st.session_state.get("abo_neonate_antiAB","")),
                        _safe_str(st.session_state.get("abo_neonate_ctl","")),
                    )
                else:
                    mf_present = "Mixed-field" in (
                        _safe_str(st.session_state.get("abo_adult_antiA","")),
                        _safe_str(st.session_state.get("abo_adult_antiB","")),
                        _safe_str(st.session_state.get("abo_adult_a1","")),
                        _safe_str(st.session_state.get("abo_adult_b","")),
                        _safe_str(st.session_state.get("abo_adult_ctl","")),
                    )
                colh1, colh2 = st.columns(2)
                with colh1:
                    st.checkbox("History: recent transfusion?", key="abo_recent_tx", value=bool(st.session_state.get("abo_recent_tx", False)), disabled=not mf_present)
                with colh2:
                    st.checkbox("History: HSCT / BM transplant?", key="abo_hsct_bm", value=bool(st.session_state.get("abo_hsct_bm", False)), disabled=not mf_present)

                # How to report (copy/paste into HIS/EMR)
                report_text = build_how_to_report(
                    is_neonate=abo_is_neonate,
                    abo_interp=abo_interp,
                    raw={
                        "antiA": st.session_state.get("abo_neonate_antiA" if abo_is_neonate else "abo_adult_antiA", "Not Done"),
                        "antiB": st.session_state.get("abo_neonate_antiB" if abo_is_neonate else "abo_adult_antiB", "Not Done"),
                        "antiAB": (st.session_state.get("abo_neonate_antiAB", "Not Done") if abo_is_neonate else "Not Done"),
                        "a1cells": (st.session_state.get("abo_adult_a1", "Not Done") if not abo_is_neonate else "Not Done"),
                        "bcells": (st.session_state.get("abo_adult_b", "Not Done") if not abo_is_neonate else "Not Done"),
                        "ctl": st.session_state.get("abo_neonate_ctl" if abo_is_neonate else "abo_adult_ctl", "Not Done"),
                    },
                    screen_any_positive=bool(st.session_state.get("abo_screen_any_positive", False)),
                    mixed_field_history={"recent_tx": bool(st.session_state.get("abo_recent_tx", False)), "hsct_bm": bool(st.session_state.get("abo_hsct_bm", False))}
                )
                st.markdown("<div class='clinical-alert'><b>How to report (copy/paste):</b></div>", unsafe_allow_html=True)
                if report_text.strip():
                    st.code(report_text, language="text")
                else:
                    st.code("No automated reporting template matched this pattern. Please enter a comment below (or follow local policy).", language="text")


                # Manual confirmation + comment (saved with the case)
                st.checkbox("Manual confirmation completed (documented)", value=bool(st.session_state.get("abo_manual_confirm", False)), key="abo_manual_confirm")
                st.text_area("Technologist comment (optional; saved with the case)", key="abo_comment", height=120)

            else:
                st.markdown(f"""
                <div class='clinical-info'>
                  ✅ <b>ABO/RhD result is consistent</b>
                  <div class='status-row'>
                    <span class='status-chip {abo_chip}'><span class='chip-label'>ABO</span> {abo_final}</span>
                    <span class='status-chip {rhd_chip}'><span class='chip-label'>RhD</span> {rhd_final}</span>
                  </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.caption("Enter grades above, then click **Confirm ABO entry** to generate the interpretation and (if needed) discrepancy guidance.")
    with st.expander("🧬 Patient Phenotype (optional)", expanded=False):
        st.caption("Use: Not Done / Not Detected / Detected. Control should be Not Detected.")
        tab1, tab2 = st.tabs(["Rh phenotype (C/c/E/e/K)", "Extended phenotype"])

        with tab1:
            p1, p2, p3, p4, p5, p6 = st.columns(6)
            ph_C  = p1.selectbox("C", PHENO_OPTS, key="ph_rh_C")
            ph_c  = p2.selectbox("c", PHENO_OPTS, key="ph_rh_c")
            ph_E  = p3.selectbox("E", PHENO_OPTS, key="ph_rh_E")
            ph_e  = p4.selectbox("e", PHENO_OPTS, key="ph_rh_e")
            ph_K  = p5.selectbox("K", PHENO_OPTS, key="ph_rh_K")
            ph_ctl = p6.selectbox("Control", PHENO_OPTS, key="ph_rh_ctl")

        with tab2:
            st.markdown("**Card 1** (P1, Lea, Leb, Lua, Lub, Control)")
            a1, a2, a3, a4, a5, a6 = st.columns(6)
            ex_P1  = a1.selectbox("P1", PHENO_OPTS, key="ph_ex_P1")
            ex_Lea = a2.selectbox("Lea", PHENO_OPTS, key="ph_ex_Lea")
            ex_Leb = a3.selectbox("Leb", PHENO_OPTS, key="ph_ex_Leb")
            ex_Lua = a4.selectbox("Lua", PHENO_OPTS, key="ph_ex_Lua")
            ex_Lub = a5.selectbox("Lub", PHENO_OPTS, key="ph_ex_Lub")
            ex_ctl1 = a6.selectbox("Control", PHENO_OPTS, key="ph_ex_ctl1")

            st.markdown("**Card 2** (k, Kpa, Kpb, Jka, Jkb, Control)")
            b1, b2, b3, b4, b5, b6 = st.columns(6)
            ex_k   = b1.selectbox("k", PHENO_OPTS, key="ph_ex_k")
            ex_Kpa = b2.selectbox("Kpa", PHENO_OPTS, key="ph_ex_Kpa")
            ex_Kpb = b3.selectbox("Kpb", PHENO_OPTS, key="ph_ex_Kpb")
            ex_Jka = b4.selectbox("Jka", PHENO_OPTS, key="ph_ex_Jka")
            ex_Jkb = b5.selectbox("Jkb", PHENO_OPTS, key="ph_ex_Jkb")
            ex_ctl2 = b6.selectbox("Control", PHENO_OPTS, key="ph_ex_ctl2")

            st.markdown("**Card 3** (M, N, S, s, Fya, Fyb)")
            c1, c2, c3, c4, c5, c6 = st.columns(6)
            ex_M   = c1.selectbox("M", PHENO_OPTS, key="ph_ex_M")
            ex_N   = c2.selectbox("N", PHENO_OPTS, key="ph_ex_N")
            ex_S   = c3.selectbox("S", PHENO_OPTS, key="ph_ex_S")
            ex_s   = c4.selectbox("s", PHENO_OPTS, key="ph_ex_s")
            ex_Fya = c5.selectbox("Fya", PHENO_OPTS, key="ph_ex_Fya")
            ex_Fyb = c6.selectbox("Fyb", PHENO_OPTS, key="ph_ex_Fyb")

    def collect_phenotype_results() -> Dict[str, str]:
        ph = {}
        # Rh set
        for ag,key in [("C","ph_rh_C"),("c","ph_rh_c"),("E","ph_rh_E"),("e","ph_rh_e"),("K","ph_rh_K"),("Rh_ctl","ph_rh_ctl")]:
            ph[ag] = _safe_str(st.session_state.get(key,"Not Done"))
        # Extended
        for ag,key in [
            ("P1","ph_ex_P1"),("Lea","ph_ex_Lea"),("Leb","ph_ex_Leb"),("Lua","ph_ex_Lua"),("Lub","ph_ex_Lub"),("EX_ctl1","ph_ex_ctl1"),
            ("k","ph_ex_k"),("Kpa","ph_ex_Kpa"),("Kpb","ph_ex_Kpb"),("Jka","ph_ex_Jka"),("Jkb","ph_ex_Jkb"),("EX_ctl2","ph_ex_ctl2"),
            ("M","ph_ex_M"),("N","ph_ex_N"),("S","ph_ex_S"),("s","ph_ex_s"),("Fya","ph_ex_Fya"),("Fyb","ph_ex_Fyb")
        ]:
            ph[ag] = _safe_str(st.session_state.get(key,"Not Done"))
        return ph

    # ----------------------------------------------------------------------
    # MAIN FORM: Antibody Identification
    # ----------------------------------------------------------------------
    with st.form("main_form", clear_on_submit=False):
        st.write("### Antibody Identification — Reaction Entry")
        L, R = st.columns([1, 2.5])
    
        with L:
            st.write("Controls")
            ac_res = st.radio("Auto Control (AC)", ["Negative", "Positive"], key="rx_ac")
    
            recent_tx = st.checkbox("Recent transfusion (≤ 4 weeks)?", value=False, key="recent_tx")
    
            if recent_tx:
                st.markdown("""
                <div class='clinical-danger'>
                🩸 <b>RECENT TRANSFUSION FLAGGED</b><br>
                ⚠️ Consider <b>DHTR</b> / anamnestic alloantibody response if compatible with clinical picture.<br>
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
    
    # ----------------------------------------------------------------------
    # Run Analysis
    # ----------------------------------------------------------------------
    if run_btn:
        if not st.session_state.lot_p or not st.session_state.lot_s:
            st.error("⛔ Lots not configured by Supervisor.")
            st.session_state.analysis_ready = False
            st.session_state.analysis_payload = None
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
    
    
    # ----------------------------------------------------------------------
    # ABO interpretation is shown inside the ABO expander after confirmation.
    # (No auto-interpretation here to avoid premature discrepancy flags.)
    # ----------------------------------------------------------------------
    # ----------------------------------------------------------------------
        # Antibody analysis output + Save (single Save button)
        # ----------------------------------------------------------------------
        conclusion_short = ""
        details = {}
        all_rx = False
        dat_igg = ""
        dat_c3d = ""
        dat_ctl = ""
    
        if st.session_state.analysis_ready and st.session_state.analysis_payload:
            in_p = st.session_state.analysis_payload["in_p"]
            in_s = st.session_state.analysis_payload["in_s"]
            ac_res = st.session_state.analysis_payload["ac_res"]
            recent_tx = st.session_state.analysis_payload["recent_tx"]
    
            ac_negative = (ac_res == "Negative")
            all_rx = all_reactive_pattern(in_p, in_s)
    
            # PAN-REACTIVE LOGIC
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
    
                conclusion_short = "Pan-reactive + AC Negative (High-incidence / multiple allo suspected)"
                details = {"pattern": "pan_reactive_ac_negative"}
    
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
    
                conclusion_short = "Pan-reactive + AC Positive (DAT pathway)"
                details = {"pattern": "pan_reactive_ac_positive"}
    
            else:
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
                    if other_sig_final or other_cold_final:
                        _ne = sorted(list(set(other_sig_final + other_cold_final)))
                        st.markdown(not_excluded_antigen_negative_notice(_ne), unsafe_allow_html=True)

    
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
    
        # ----------------------------------------------------------------------
        # Selected cells expander (unchanged)
        # ----------------------------------------------------------------------
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
    
        # ----------------------------------------------------------------------
    # SINGLE SAVE (saves everything: demographics + ABO + phenotype + antibody ID)
    # ----------------------------------------------------------------------
    st.write("---")
    if st.button("💾 Save Full Case (ABO + Phenotype + Antibody ID)", type="primary", use_container_width=True):
        if not st.session_state.lot_p or not st.session_state.lot_s:
            st.error("⛔ Lots not configured by Supervisor.")
        else:
            pt_name = _safe_str(st.session_state.get("pt_name",""))
            pt_mrn  = _safe_str(st.session_state.get("pt_mrn",""))
            tech_nm = _safe_str(st.session_state.get("tech_nm",""))
            sex = _safe_str(st.session_state.get("pt_sex",""))
            run_dt_val = st.session_state.get("run_dt", date.today())

            # Must have MRN for GitHub history folders (recommended)
            if not pt_mrn:
                st.error("Please enter MRN before saving (required for history).")
            else:
                # in_p/in_s may not exist if user didn't run analysis; handle gracefully
                in_p = {}
                in_s = {}
                ac_res_sv = _safe_str(st.session_state.get("rx_ac",""))
                recent_tx_sv = bool(st.session_state.get("recent_tx", False))
                if st.session_state.analysis_payload:
                    in_p = st.session_state.analysis_payload.get("in_p", {})
                    in_s = st.session_state.analysis_payload.get("in_s", {})
                    ac_res_sv = st.session_state.analysis_payload.get("ac_res", ac_res_sv)
                    recent_tx_sv = bool(st.session_state.analysis_payload.get("recent_tx", recent_tx_sv))

                # phenotype results
                ph = collect_phenotype_results()

                # conflict notes (if antibodies exist)
                suspected_abs = []
                if isinstance(details, dict):
                    suspected_abs = list(dict.fromkeys((_as_list(details.get("confirmed", [])) + _as_list(details.get("resolved", [])))))
                conflicts = phenotype_conflict_notes(suspected_abs, ph)
                if conflicts:
                    st.markdown(
                        "<div class='clinical-danger'><b>Phenotype vs Antibody conflict</b><ul style='margin-top:6px;'>" +
                        "".join([f"<li>{c}</li>" for c in conflicts]) +
                        "</ul></div>",
                        unsafe_allow_html=True
                    )


                # ABO confirmation is required (stored from the ABO expander)
                abo_raw_sv = st.session_state.get("abo_raw_confirmed")
                abo_interp_sv = st.session_state.get("abo_interp_confirmed")
                abo_guid_sv = st.session_state.get("abo_guidance_confirmed") or {}
                abo_comment_sv = _safe_str(st.session_state.get("abo_comment",""))
                abo_manual_sv = bool(st.session_state.get("abo_manual_confirm", False))

                if not bool(st.session_state.get("abo_confirmed", False)) or (not abo_raw_sv) or (not abo_interp_sv):
                    st.error("⛔ Please enter and CONFIRM ABO results before saving.")
                    st.stop()

                saved_at = _now_ts()
                case_id = f"{pt_mrn}_{saved_at}".replace(" ", "_").replace(":", "-")

                payload = {
                    "patient": {"name": pt_name, "mrn": pt_mrn},
                    "demographics": {"sex": sex, "age_y": age_y, "age_m": age_m, "age_d": age_d},
                    "tech": tech_nm,
                    "run_dt": str(run_dt_val),
                    "saved_at": saved_at,
                    "lots": {"panel": st.session_state.lot_p, "screen": st.session_state.lot_s},
                    "abo": {
                        "raw": abo_raw_sv,
                        "abo_final": abo_interp_sv.get("abo_final", ""),
                        "rhd_final": abo_interp_sv.get("rhd_final", ""),
                        "discrepancy": bool(abo_interp_sv.get("discrepancy", False)),
                        "invalid": bool(abo_interp_sv.get("invalid", False)),
                        "notes": abo_interp_sv.get("notes", []),
                        "guidance": abo_guid_sv,
                        "comment": abo_comment_sv,
                        "manual_confirmation": bool(abo_manual_sv),
                    },
                    "phenotype": {
                        "results": ph
                    },
                    "inputs": {
                        "panel_reactions": in_p,
                        "screen_reactions": in_s,
                        "AC": ac_res_sv,
                        "recent_tx": bool(recent_tx_sv),
                    },
                    "all_rx": bool(all_rx),
                    "dat": {"igg": _safe_str(dat_igg), "c3d": _safe_str(dat_c3d), "control": _safe_str(dat_ctl)},
                    "selected_cells": st.session_state.ext,
                    "interpretation": details or {},
                    "conclusion_short": conclusion_short
                }

                # fingerprint excludes saved_at/case_id (for duplicate detection)
                fp_obj = {
                    "mrn": pt_mrn,
                    "run_dt": str(run_dt_val),
                    "lots": {"panel": st.session_state.lot_p, "screen": st.session_state.lot_s},
                    "abo": payload["abo"],
                    "phenotype": payload["phenotype"],
                    "inputs": payload["inputs"],
                    "all_rx": payload["all_rx"],
                    "dat": payload["dat"],
                    "selected_cells": payload["selected_cells"],
                    "interpretation": payload["interpretation"],
                    "conclusion_short": _safe_str(conclusion_short),
                }
                fingerprint = _make_fingerprint(fp_obj)

                record = {
                    "case_id": case_id,
                    "saved_at": saved_at,
                    "mrn": pt_mrn,
                    "name": pt_name,
                    "tech": tech_nm,
                    "sex": sex,
                    "age_y": age_y,
                    "age_m": age_m,
                    "age_d": age_d,
                    "run_dt": str(run_dt_val),
                    "lot_p": st.session_state.lot_p,
                    "lot_s": st.session_state.lot_s,
                    "ac_res": ac_res_sv,
                    "recent_tx": bool(recent_tx_sv),
                    "all_rx": bool(all_rx),
                    "conclusion_short": conclusion_short,
                    "abo_final": abo_interp_sv.get("abo_final",""),
                    "rhd_final": abo_interp_sv.get("rhd_final",""),
                    "abo_discrepancy": bool(abo_interp_sv.get("discrepancy", False)),
                    "fingerprint": fingerprint,
                    "summary_json": json.dumps(payload, ensure_ascii=False)
                }

                ok, msg = save_case_to_github(record)
                if ok:
                    st.success("Saved ✅ (GitHub history updated)")
                else:
                    st.warning("⚠️ " + msg)
