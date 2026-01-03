import streamlit as st
import pandas as pd
from datetime import date, datetime, timezone
import json
import base64
import requests
from pathlib import Path
from itertools import combinations

# =============================================================================
# 0) CONFIG
# =============================================================================
APP_NAME = "H-AXIS"
TAGLINE = "Antibody Identification & Serology Decision Support"
APP_ICON = "🩸"

# =============================================================================
# 0.1) Supabase (Streamlit Secrets)
# =============================================================================
def _sb_cfg():
    url = st.secrets.get("SUPABASE_URL", None)
    anon = st.secrets.get("SUPABASE_ANON_KEY", None)
    return url, anon

def _ensure_sb():
    url, anon = _sb_cfg()
    if not url or not anon:
        raise RuntimeError("Missing Streamlit Secrets: SUPABASE_URL / SUPABASE_ANON_KEY")
    return url.rstrip("/"), anon

def sb_req(method: str, path: str, key: str, jwt: str | None = None, params=None, json_body=None, timeout=30):
    base, _ = _ensure_sb()
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
    }
    if jwt:
        headers["Authorization"] = f"Bearer {jwt}"
    url = f"{base}{path}"
    return requests.request(method, url, headers=headers, params=params, json=json_body, timeout=timeout)

def sb_rpc(fn_name: str, payload: dict, jwt: str):
    base, anon = _ensure_sb()
    r = sb_req("POST", f"/rest/v1/rpc/{fn_name}", key=anon, jwt=jwt, json_body=payload)
    if r.status_code not in (200, 201):
        raise RuntimeError(r.text)
    return r.json()

def staff_email(staff_id: str) -> str:
    # Internal mapping only; staff never sees this email in UI
    # Keep stable for password login.
    return f"{staff_id.strip()}@bb.local"

# =============================================================================
# 0.2) Supabase Auth helpers (password grant)
# =============================================================================
def sb_sign_in_password(staff_id: str, password: str) -> dict:
    base, anon = _ensure_sb()
    email = staff_email(staff_id)
    path = "/auth/v1/token"
    params = {"grant_type": "password"}
    r = sb_req("POST", path, key=anon, params=params, json_body={"email": email, "password": password})
    if r.status_code != 200:
        raise RuntimeError("Invalid Staff ID or Password.")
    return r.json()

def sb_sign_up(staff_id: str, password: str) -> dict:
    base, anon = _ensure_sb()
    email = staff_email(staff_id)
    path = "/auth/v1/signup"
    r = sb_req("POST", path, key=anon, json_body={"email": email, "password": password})
    if r.status_code not in (200, 201):
        # Most common: user exists already
        msg = "Signup failed. Staff ID may already be registered, or password is invalid."
        try:
            j = r.json()
            if isinstance(j, dict) and j.get("msg"):
                msg = j.get("msg")
        except Exception:
            pass
        raise RuntimeError(msg)
    return r.json()

def sb_get_profile(jwt: str) -> dict | None:
    base, anon = _ensure_sb()
    # Query users_profile for this user_id
    # We'll use the view of "me" via auth.uid() through RPC to avoid exposing SQL filtering issues.
    out = sb_rpc("get_my_profile", {}, jwt=jwt)
    if isinstance(out, list) and out:
        return out[0]
    if isinstance(out, dict) and out:
        return out
    return None

def sb_sign_out_local():
    # Supabase signout endpoint is optional; we just clear local session.
    for k in ["auth_token", "refresh_token", "user_id", "role", "hospital_code", "staff_id", "profile_loaded"]:
        if k in st.session_state:
            del st.session_state[k]

# =============================================================================
# 0.3) GitHub Save Engine (uses Streamlit Secrets)
# =============================================================================
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

# =============================================================================
# 1) PAGE SETUP & THEME (Deep Blue)
# =============================================================================
st.set_page_config(page_title=f"{APP_NAME} - {TAGLINE}", layout="wide", page_icon=APP_ICON)

DEEP_BLUE_CSS = """
<style>
:root{
  --bg:#07182d;
  --panel:#0c2342;
  --panel2:#0f2d55;
  --card:#0b2240;
  --accent:#2d8cff;
  --accent2:#00c2ff;
  --text:#eaf2ff;
  --muted:#b6c7e6;
  --good:#2ecc71;
  --warn:#f7c948;
  --bad:#ff4d6d;
  --line: rgba(255,255,255,0.10);
}

html, body, [class*="css"]{
  font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, "Helvetica Neue", Arial;
}

section.main{
  background: radial-gradient(1100px 500px at 20% 0%, rgba(45,140,255,0.18), transparent 55%),
              radial-gradient(900px 400px at 90% 10%, rgba(0,194,255,0.14), transparent 60%),
              linear-gradient(180deg, var(--bg) 0%, #050f1d 100%);
  color: var(--text);
}

div[data-testid="stSidebar"]{
  background: linear-gradient(180deg, var(--panel) 0%, #081b33 100%);
  border-right: 1px solid var(--line);
}

.haxis-header{
  background: linear-gradient(135deg, rgba(45,140,255,0.22), rgba(0,194,255,0.10));
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 18px 18px;
  margin-bottom: 14px;
  box-shadow: 0 8px 28px rgba(0,0,0,0.25);
}
.haxis-title{
  font-size: 28px;
  font-weight: 800;
  letter-spacing: 0.6px;
  margin: 0;
}
.haxis-tag{
  color: var(--muted);
  margin-top: 4px;
  font-weight: 500;
}

.topbar{
  display:flex;
  justify-content: space-between;
  align-items:center;
  gap: 12px;
  margin-top: 10px;
}
.pill{
  display:inline-flex;
  align-items:center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 999px;
  border:1px solid var(--line);
  background: rgba(255,255,255,0.06);
  color: var(--text);
  font-weight: 600;
}
.pill small{ color: var(--muted); font-weight: 600; }

.card{
  background: rgba(255,255,255,0.05);
  border:1px solid var(--line);
  border-radius: 16px;
  padding: 16px;
  box-shadow: 0 10px 26px rgba(0,0,0,0.22);
}

.hcard{
  background: rgba(255,255,255,0.045);
  border:1px solid var(--line);
  border-radius: 16px;
  padding: 14px 16px;
  margin-top: 10px;
}

.alert{
  border-radius: 14px;
  padding: 12px 14px;
  border: 1px solid var(--line);
  background: rgba(255,255,255,0.06);
  color: var(--text);
}
.alert.good{ border-color: rgba(46,204,113,0.35); background: rgba(46,204,113,0.12); }
.alert.warn{ border-color: rgba(247,201,72,0.40); background: rgba(247,201,72,0.12); }
.alert.bad{ border-color: rgba(255,77,109,0.40); background: rgba(255,77,109,0.14); }

.signature{
  position: fixed;
  bottom: 14px;
  right: 18px;
  background: rgba(11,34,64,0.82);
  border: 1px solid rgba(255,255,255,0.14);
  backdrop-filter: blur(8px);
  padding: 10px 14px;
  border-radius: 14px;
  z-index: 999;
  box-shadow: 0 10px 26px rgba(0,0,0,0.28);
  text-align: left;
  max-width: 320px;
}
.signature .name{
  font-weight: 800;
  color: #eaf2ff;
  font-size: 14px;
}
.signature .title{
  color: var(--muted);
  font-size: 11px;
  line-height: 1.25;
  margin-top: 2px;
}

div[data-testid="stDataEditor"] table { width: 100% !important; }

a { color: #9ad0ff; }
</style>
"""
st.markdown(DEEP_BLUE_CSS, unsafe_allow_html=True)

st.markdown("""
<div class="signature">
  <div class="name">Dr. Haitham Ismail</div>
  <div class="title">Clinical Hematology/Oncology &<br>BM Transplantation & Transfusion Medicine Consultant</div>
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

GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]
YN3 = ["Not Done", "Negative", "Positive"]

# =============================================================================
# 3) SESSION STATE
# =============================================================================
def _init_state():
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

    if "confirmed_lock" not in st.session_state:
        st.session_state.confirmed_lock = set()

    if "profile_loaded" not in st.session_state:
        st.session_state.profile_loaded = False

_init_state()

# =============================================================================
# 4) ENGINE HELPERS (unchanged core logic)
# =============================================================================
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

    title = "Final confirmation step (Patient antigen check)" if strong else "Before final reporting (Patient antigen check)"
    cls = "bad" if strong else "warn"
    intro = ("Confirm the patient is ANTIGEN-NEGATIVE for the corresponding antigen(s) to support the antibody identification."
             if strong else
             "Before you finalize/report, confirm the patient is ANTIGEN-NEGATIVE for the corresponding antigen(s).")

    bullets = "".join([f"<li>Anti-{ag} → verify patient is <b>{ag}-negative</b> (phenotype/genotype; pre-transfusion sample preferred).</li>" for ag in uniq])

    return f"""
    <div class='alert {cls}'>
      <b>{title}</b><br>
      <span style="color: var(--muted);">{intro}</span>
      <ul style="margin-top:6px;">
        {bullets}
      </ul>
    </div>
    """

def anti_g_alert_html(strong: bool = False) -> str:
    cls = "bad" if strong else "warn"
    return f"""
    <div class='alert {cls}'>
      <b>Consider Anti-G (D + C pattern)</b><br>
      <span style="color: var(--muted);">
      Anti-G may mimic Anti-D + Anti-C. If clinically relevant (especially pregnancy / RhIG decision), do not label as true Anti-D until Anti-G is excluded.
      </span>
      <ol style="margin-top:6px;">
        <li>Assess if this impacts management (e.g., RhIG eligibility).</li>
        <li>Perform differential workup using appropriate adsorption/elution strategy (D+ C− and D− C+ cells), or refer to reference lab.</li>
        <li>Use pre-transfusion sample when possible.</li>
      </ol>
    </div>
    """

def confirmed_conflict_map(confirmed_set: set, cells: list):
    conflicts = {}
    for ab in confirmed_set:
        bad_labels = []
        for c in cells:
            if c["react"] == 1 and not ph_has(c["ph"], ab):
                bad_labels.append(c["label"])
        if bad_labels:
            conflicts[ab] = bad_labels
    return conflicts

# =============================================================================
# 5) SUPERVISOR PASTE PARSER (kept)
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

    return df, f"Parsed {min(expected_rows, len(rows))} row(s). Expected {expected_rows}."

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
# 6) AUTH UI (Staff ID only)
# =============================================================================
def auth_gate():
    st.markdown(f"""
    <div class="haxis-header">
      <div class="haxis-title">{APP_NAME}</div>
      <div class="haxis-tag">{TAGLINE}</div>
      <div class="haxis-tag" style="margin-top:10px;">
        Secure access: <b>Staff ID</b> + Password (or Invite Code for first-time registration)
      </div>
    </div>
    """, unsafe_allow_html=True)

    tab_login, tab_register = st.tabs(["Sign in", "First-time registration (Invite Code)"])

    with tab_login:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        staff_id = st.text_input("Staff ID", key="login_staff_id")
        pwd = st.text_input("Password", type="password", key="login_pwd")
        col1, col2 = st.columns([1, 1])
        go = col1.button("Sign in", use_container_width=True)
        if go:
            try:
                token = sb_sign_in_password(staff_id, pwd)
                st.session_state.auth_token = token["access_token"]
                st.session_state.refresh_token = token.get("refresh_token")
                st.session_state.staff_id = staff_id.strip()
                st.session_state.profile_loaded = False
                st.success("Signed in successfully.")
                st.rerun()
            except Exception as e:
                st.error(str(e))
        st.markdown('</div>', unsafe_allow_html=True)

    with tab_register:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        staff_id = st.text_input("Staff ID", key="reg_staff_id")
        invite = st.text_input("Invite Code", key="reg_invite")
        pwd1 = st.text_input("Create password", type="password", key="reg_pwd1")
        pwd2 = st.text_input("Confirm password", type="password", key="reg_pwd2")

        go = st.button("Create account", use_container_width=True, key="btn_create_acc")
        if go:
            try:
                if not staff_id.strip():
                    raise RuntimeError("Staff ID is required.")
                if not invite.strip():
                    raise RuntimeError("Invite Code is required.")
                if not pwd1 or len(pwd1) < 8:
                    raise RuntimeError("Password must be at least 8 characters.")
                if pwd1 != pwd2:
                    raise RuntimeError("Password confirmation does not match.")

                # 1) Sign up
                su = sb_sign_up(staff_id.strip(), pwd1)

                # 2) Get token by signing in (ensures we have JWT)
                token = sb_sign_in_password(staff_id.strip(), pwd1)
                jwt = token["access_token"]

                # 3) Consume invite + create profile (RPC)
                out = sb_rpc("consume_invite_and_create_profile", {
                    "p_staff_id": staff_id.strip(),
                    "p_invite_code": invite.strip()
                }, jwt=jwt)

                # 4) Store session
                st.session_state.auth_token = jwt
                st.session_state.refresh_token = token.get("refresh_token")
                st.session_state.staff_id = staff_id.strip()
                st.session_state.profile_loaded = False

                st.success("Account created successfully.")
                st.rerun()

            except Exception as e:
                st.error(str(e))
        st.markdown('</div>', unsafe_allow_html=True)

# =============================================================================
# 7) Load profile after auth
# =============================================================================
def ensure_profile_loaded():
    if "auth_token" not in st.session_state:
        return False
    if st.session_state.get("profile_loaded"):
        return True
    try:
        prof = sb_get_profile(st.session_state.auth_token)
        if not prof:
            raise RuntimeError("Profile not found. Contact admin.")
        st.session_state.role = str(prof.get("role", "")).lower()
        st.session_state.hospital_code = prof.get("hospital_code", "")
        st.session_state.staff_id = prof.get("staff_id", st.session_state.get("staff_id",""))
        st.session_state.profile_loaded = True
        return True
    except Exception as e:
        st.error(str(e))
        return False

def is_admin():
    return str(st.session_state.get("role","")).lower() == "admin"

def is_supervisor():
    return str(st.session_state.get("role","")).lower() == "supervisor"

def can_config():
    return is_admin() or is_supervisor()

# =============================================================================
# 8) SIDEBAR NAV
# =============================================================================
def sidebar_nav():
    with st.sidebar:
        st.markdown(f"### {APP_NAME}")
        st.caption(TAGLINE)

        if "auth_token" in st.session_state and ensure_profile_loaded():
            st.markdown('<div class="pill">', unsafe_allow_html=True)
            st.markdown(f"Role: <b>{st.session_state.role.upper()}</b><br><small>Hospital: {st.session_state.hospital_code or '—'}</small>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

            if st.button("Sign out", use_container_width=True):
                sb_sign_out_local()
                st.rerun()

        st.write("---")

        menu = ["Workstation"]
        if can_config():
            menu.append("Admin Console")

        nav = st.radio("Navigation", menu, key="nav_menu")

        if st.button("Reset session (case)", use_container_width=True, key="btn_reset_case"):
            st.session_state.ext = []
            st.session_state.analysis_ready = False
            st.session_state.analysis_payload = None
            st.session_state.show_dat = False
            st.session_state.confirmed_lock = set()
            st.rerun()

    return nav

# =============================================================================
# 9) ADMIN CONSOLE (Panel/Screen/Lots + Invite Generator + GitHub publish)
# =============================================================================
def admin_console_page():
    st.markdown(f"""
    <div class="haxis-header">
      <div class="haxis-title">Admin Console</div>
      <div class="haxis-tag">Configuration & Publishing • Invite Management</div>
    </div>
    """, unsafe_allow_html=True)

    if not can_config():
        st.error("Access denied.")
        return

    # ------------------------------
    # 1) Lot setup
    # ------------------------------
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("### 1) Lot Setup")

    c1, c2 = st.columns(2)
    lp = c1.text_input("ID Panel Lot #", value=st.session_state.lot_p, key="lot_p_in")
    ls = c2.text_input("Screen Panel Lot #", value=st.session_state.lot_s, key="lot_s_in")

    colA, colB = st.columns([1, 2])
    if colA.button("Save (local)", use_container_width=True):
        st.session_state.lot_p = lp
        st.session_state.lot_s = ls
        st.success("Saved locally. You can publish later.")
    colB.caption("Local save affects this session; publish pushes to GitHub for all devices.")

    st.markdown("</div>", unsafe_allow_html=True)

    # ------------------------------
    # 2) Grid update
    # ------------------------------
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("### 2) Monthly Grid Update (Copy/Paste + Safe Manual Edit)")
    st.caption("Paste must include 26 antigen columns in AGS order. Extra leading columns are ignored automatically (last 26 columns are used).")

    tab_paste, tab_edit = st.tabs(["Copy/Paste Update", "Manual Edit (Safe)"])

    with tab_paste:
        cA, cB = st.columns(2)

        with cA:
            st.markdown("#### Panel 11 (Paste)")
            p_txt = st.text_area("Paste 11 rows (tab-separated; 26 columns in AGS order)", height=170, key="p11_paste")
            if st.button("Update Panel 11 from Paste", use_container_width=True, key="upd_p11_paste"):
                df_new, msg = parse_paste_table(p_txt, expected_rows=11, id_prefix="C")
                df_new["ID"] = [f"C{i+1}" for i in range(11)]
                st.session_state.panel11_df = df_new.copy()
                st.success(msg)

            st.caption("Preview (Panel 11)")
            st.dataframe(st.session_state.panel11_df, use_container_width=True, height=260)

        with cB:
            st.markdown("#### Screen 3 (Paste)")
            s_txt = st.text_area("Paste 3 rows (tab-separated; 26 columns in AGS order)", height=170, key="p3_paste")
            if st.button("Update Screen 3 from Paste", use_container_width=True, key="upd_p3_paste"):
                df_new, msg = parse_paste_table(s_txt, expected_rows=3, id_prefix="S", id_list=["SI", "SII", "SIII"])
                df_new["ID"] = ["SI", "SII", "SIII"]
                st.session_state.screen3_df = df_new.copy()
                st.success(msg)

            st.caption("Preview (Screen 3)")
            st.dataframe(st.session_state.screen3_df, use_container_width=True, height=260)

    with tab_edit:
        st.markdown("#### Manual Edit — Safe mode")
        st.caption("Rules: ID locked • fixed rows • checkboxes only (0/1)")

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
            if st.button("Apply Manual Changes (Panel 11)", type="primary", use_container_width=True, key="apply_p11"):
                st.session_state.panel11_df = edited_p11.copy()
                st.success("Panel 11 updated (local).")

        with t2:
            edited_p3 = st.data_editor(
                st.session_state.screen3_df,
                use_container_width=True,
                num_rows="fixed",
                disabled=["ID"],
                column_config=_checkbox_column_config(),
                key="editor_screen3"
            )
            if st.button("Apply Manual Changes (Screen 3)", type="primary", use_container_width=True, key="apply_p3"):
                st.session_state.screen3_df = edited_p3.copy()
                st.success("Screen 3 updated (local).")

    st.markdown("</div>", unsafe_allow_html=True)

    # ------------------------------
    # 3) Invite Generator (IN-APP)
    # ------------------------------
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("### 3) Invite Generator")

    my_role = str(st.session_state.get("role","")).lower()

    col1, col2, col3 = st.columns([1.2, 1.2, 1.6])
    inv_staff_id = col1.text_input("Target Staff ID", key="inv_staffid")

    # Admin: any role; Supervisor: staff only
    if my_role == "admin":
        inv_role = col2.selectbox("Role", ["staff", "supervisor", "admin"], key="inv_role")
    else:
        inv_role = "staff"
        col2.selectbox("Role", ["staff"], key="inv_role_locked", disabled=True)

    # Admin can target any hospital; Supervisor locked to own hospital
    if my_role == "admin":
        inv_hosp = col3.text_input("Hospital Code", value=st.session_state.get("hospital_code",""), key="inv_hosp")
    else:
        inv_hosp = st.session_state.get("hospital_code","")
        col3.text_input("Hospital Code", value=inv_hosp, key="inv_hosp_locked", disabled=True)

    # optional expiry
    exp_col1, exp_col2 = st.columns([1.2, 2.0])
    expires = exp_col1.date_input("Expiry (optional)", value=None, key="inv_exp")
    exp_col2.caption("If empty: invite does not expire (unless you deactivate it).")

    if st.button("Generate invite code", use_container_width=True, key="btn_inv_gen"):
        try:
            if not inv_staff_id.strip():
                raise RuntimeError("Target Staff ID is required.")
            payload = {
                "p_staff_id": inv_staff_id.strip(),
                "p_role": inv_role,
                "p_hospital_code": inv_hosp.strip(),
                "p_expires_at": (datetime.combine(expires, datetime.min.time()).replace(tzinfo=timezone.utc).isoformat()
                                if expires else None)
            }
            out = sb_rpc("create_invite_secure", payload, jwt=st.session_state.auth_token)
            row = out[0] if isinstance(out, list) and out else out
            code = row.get("code")
            st.markdown('<div class="alert good"><b>Invite created</b></div>', unsafe_allow_html=True)
            st.code(code, language="text")
            st.caption(f"Hospital: {row.get('hospital_code')}  |  Role: {row.get('role')}  |  Active: {row.get('is_active')}")
        except Exception as e:
            st.markdown(f'<div class="alert bad"><b>Invite generation failed:</b> {str(e)}</div>', unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # ------------------------------
    # 4) Publish to GitHub
    # ------------------------------
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("### 4) Publish to ALL devices (GitHub)")
    st.caption("This updates data/p11.csv, data/p3.csv, data/lots.json in your GitHub repo.")

    confirm_pub = st.checkbox("I confirm Panel/Screen data and lots were reviewed and are correct", key="confirm_publish")

    if st.button("Save to GitHub (Commit)", use_container_width=True, key="save_gh"):
        if not confirm_pub:
            st.error("Confirmation required before publishing.")
        else:
            try:
                lots_json = json.dumps({"lot_p": st.session_state.lot_p, "lot_s": st.session_state.lot_s},
                                       ensure_ascii=False, indent=2)
                github_upsert_file("data/p11.csv", st.session_state.panel11_df.to_csv(index=False), "Update monthly p11 panel")
                github_upsert_file("data/p3.csv",  st.session_state.screen3_df.to_csv(index=False), "Update monthly p3 screen")
                github_upsert_file("data/lots.json", lots_json, "Update monthly lots")
                st.success("Published to GitHub successfully.")
            except Exception as e:
                st.error(f"Save failed: {e}")

    st.markdown("</div>", unsafe_allow_html=True)

# =============================================================================
# 10) WORKSTATION PAGE
# =============================================================================
def workstation_page():
    st.markdown(f"""
    <div class="haxis-header">
      <div class="haxis-title">{APP_NAME}</div>
      <div class="haxis-tag">{TAGLINE}</div>
      <div class="topbar">
        <div class="pill">🧪 <span>Panel Lot:</span> <small>{st.session_state.lot_p or "REQUIRED"}</small></div>
        <div class="pill">🧫 <span>Screen Lot:</span> <small>{st.session_state.lot_s or "REQUIRED"}</small></div>
        <div class="pill">👤 <span>Staff ID:</span> <small>{st.session_state.get("staff_id","—")}</small></div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if not st.session_state.lot_p or not st.session_state.lot_s:
        st.markdown('<div class="alert warn"><b>Lots are not configured.</b> Ask supervisor/admin to set Panel/Screen lots in Admin Console.</div>', unsafe_allow_html=True)

    top1, top2, top3, top4 = st.columns(4)
    _ = top1.text_input("Patient Name", key="pt_name")
    _ = top2.text_input("MRN", key="pt_mrn")
    _ = top3.text_input("Operator", value=st.session_state.get("staff_id",""), key="tech_nm")
    _ = top4.date_input("Date", value=date.today(), key="run_dt")

    with st.form("main_form", clear_on_submit=False):
        st.markdown("### Reaction Entry")
        L, R = st.columns([1, 2.5])

        with L:
            st.markdown("#### Controls")
            ac_res = st.radio("Auto Control (AC)", ["Negative", "Positive"], key="rx_ac")

            recent_tx = st.checkbox("Recent transfusion (≤ 4 weeks)?", value=False, key="recent_tx")
            if recent_tx:
                st.markdown("""
                <div class="alert bad">
                  <b>RECENT TRANSFUSION FLAGGED</b><br>
                  Consider DHTR / anamnestic alloantibody response if clinically compatible.<br>
                  <ul style="margin-top:6px;">
                    <li>Review Hb trend and hemolysis markers (bilirubin/LDH/haptoglobin).</li>
                    <li>Compare pre- vs post-transfusion samples if available.</li>
                    <li>Escalate early if new alloantibody suspected.</li>
                  </ul>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("#### Screening")
            s_I   = st.selectbox("Screen I", GRADES, key="rx_sI")
            s_II  = st.selectbox("Screen II", GRADES, key="rx_sII")
            s_III = st.selectbox("Screen III", GRADES, key="rx_sIII")

        with R:
            st.markdown("#### Panel Reactions")
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

        run_btn = st.form_submit_button("Run Analysis", use_container_width=True)

    if run_btn:
        if not st.session_state.lot_p or not st.session_state.lot_s:
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

    # -------------------------------
    # Analysis output (your original logic preserved)
    # -------------------------------
    if st.session_state.analysis_ready and st.session_state.analysis_payload:
        in_p = st.session_state.analysis_payload["in_p"]
        in_s = st.session_state.analysis_payload["in_s"]
        ac_res = st.session_state.analysis_payload["ac_res"]
        recent_tx = st.session_state.analysis_payload["recent_tx"]

        ac_negative = (ac_res == "Negative")
        all_rx = all_reactive_pattern(in_p, in_s)

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("## Interpretation")

        # PAN-REACTIVE
        if all_rx and ac_negative:
            tx_note = ""
            if recent_tx:
                tx_note = "<li><b>Recent transfusion ≤ 4 weeks</b>: consider DHTR / anamnestic response if clinically compatible.</li>"

            st.markdown(f"""
            <div class="alert bad">
              <b>Pan-reactive pattern with NEGATIVE autocontrol</b><br>
              Most consistent with:
              <ul style="margin-top:6px;">
                <li>Alloantibody to a high-incidence antigen</li>
                <li>OR multiple alloantibodies not separable with current cells</li>
              </ul>
              <b>Recommended workflow:</b>
              <ol style="margin-top:6px;">
                <li>Stop routine single-specificity interpretation.</li>
                <li>Refer to BB physician / reference lab.</li>
                <li>Request extended phenotype/genotype (pre-transfusion if possible).</li>
                <li>Initiate rare compatible unit search as needed.</li>
                <li>Consider additional panels/different lots + selected cells.</li>
                {tx_note}
              </ol>
            </div>
            """, unsafe_allow_html=True)

        elif all_rx and (not ac_negative):
            st.markdown("""
            <div class="alert bad">
              <b>Pan-reactive pattern with POSITIVE autocontrol</b><br>
              Requires monospecific DAT pathway (IgG / C3d / Control) before alloantibody claims.
            </div>
            """, unsafe_allow_html=True)

            st.markdown("### Monospecific DAT Entry (Required)")
            c1, c2, c3 = st.columns(3)
            dat_igg = c1.selectbox("DAT IgG", YN3, key="dat_igg")
            dat_c3d = c2.selectbox("DAT C3d", YN3, key="dat_c3d")
            dat_ctl = c3.selectbox("DAT Control", YN3, key="dat_ctl")

            if dat_ctl == "Positive":
                st.markdown('<div class="alert bad"><b>DAT Control is POSITIVE</b> → invalid run. Repeat DAT.</div>', unsafe_allow_html=True)
            elif dat_igg == "Not Done" or dat_c3d == "Not Done":
                st.markdown('<div class="alert warn"><b>Please perform monospecific DAT (IgG & C3d)</b> to proceed.</div>', unsafe_allow_html=True)
            else:
                if dat_igg == "Positive":
                    ads = "Auto-adsorption (ONLY if NOT recently transfused)" if not recent_tx else "Allo-adsorption (recent transfusion → avoid auto-adsorption)"
                    st.markdown(f"""
                    <div class="alert good">
                      <b>DAT IgG POSITIVE</b> (C3d: {dat_c3d}) → consistent with warm autoantibody / WAIHA.<br><br>
                      <b>Workflow:</b>
                      <ol style="margin-top:6px;">
                        <li>Consider eluate when indicated.</li>
                        <li>Adsorption: <b>{ads}</b> to unmask alloantibodies.</li>
                        <li>Phenotype/genotype (pre-transfusion preferred).</li>
                        <li>Transfuse per policy (antigen-matched / least-incompatible as appropriate).</li>
                      </ol>
                    </div>
                    """, unsafe_allow_html=True)
                elif dat_igg == "Negative" and dat_c3d == "Positive":
                    st.markdown("""
                    <div class="alert good">
                      <b>DAT IgG NEGATIVE + C3d POSITIVE</b> → complement-mediated process (e.g., cold autoantibody).<br><br>
                      <b>Workflow:</b>
                      <ol style="margin-top:6px;">
                        <li>Evaluate cold interference (pre-warm / thermal amplitude) per SOP.</li>
                        <li>Repeat as needed at 37°C.</li>
                        <li>Refer if clinically significant transfusion requirement.</li>
                      </ol>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                    <div class="alert warn">
                      <b>AC POSITIVE but DAT IgG & C3d NEGATIVE</b> → consider in-vitro interference/technique issues (rouleaux, cold at RT, reagent effects).<br><br>
                      <b>Actions:</b>
                      <ol style="margin-top:6px;">
                        <li>Repeat with proper technique; saline replacement if rouleaux suspected.</li>
                        <li>Pre-warm/37°C repeat if cold suspected.</li>
                        <li>If unresolved → refer.</li>
                      </ol>
                    </div>
                    """, unsafe_allow_html=True)

        # NON-PAN: normal engine
        if not all_rx:
            cells = get_cells(in_p, in_s, st.session_state.ext)
            ruled = rule_out(in_p, in_s, st.session_state.ext)
            candidates = [a for a in AGS if a not in ruled and a not in IGNORED_AGS]

            st.markdown("### Step 1: Rule-out / Rule-in")

            if st.session_state.confirmed_lock:
                confirmed_locked = sorted(list(st.session_state.confirmed_lock))
                st.markdown(f'<div class="alert good"><b>Resolved (LOCKED confirmed):</b> {", ".join([f"Anti-{a}" for a in confirmed_locked])}</div>', unsafe_allow_html=True)

                remaining_other = [a for a in candidates if a not in st.session_state.confirmed_lock]
                other_sig = [a for a in remaining_other if a not in INSIGNIFICANT_AGS]
                other_cold = [a for a in remaining_other if a in INSIGNIFICANT_AGS]
                active_not_excluded = set(confirmed_locked + other_sig + other_cold)

                auto_ruled_out, supported_bg, inconclusive_bg, no_disc_bg = background_auto_resolution(
                    background_list=other_sig + other_cold,
                    active_not_excluded=active_not_excluded,
                    cells=cells
                )

                other_sig_final = [a for a in other_sig if a not in auto_ruled_out]
                other_cold_final = [a for a in other_cold if a not in auto_ruled_out]

                if auto_ruled_out:
                    st.markdown("#### Auto Rule-out (discriminating negative cells):")
                    for ag, labs in auto_ruled_out.items():
                        st.write(f"- Anti-{ag} ruled out: " + ", ".join(labs))

                if supported_bg:
                    st.markdown("#### Background antibodies suggested (NOT confirmed):")
                    for ag, labs in supported_bg.items():
                        st.write(f"- Anti-{ag} suspected: " + ", ".join(labs))

                if inconclusive_bg:
                    st.markdown("#### Inconclusive background:")
                    for ag, labs in inconclusive_bg.items():
                        st.write(f"- Anti-{ag} inconclusive: " + ", ".join(labs))

                st.markdown("### Confirmation (Rule of Three)")
                st.markdown(patient_antigen_negative_reminder(confirmed_locked, strong=True), unsafe_allow_html=True)

                d_present = ("D" in st.session_state.confirmed_lock)
                c_present = ("C" in st.session_state.confirmed_lock)
                if d_present and c_present:
                    st.markdown(anti_g_alert_html(strong=True), unsafe_allow_html=True)

                conflicts = confirmed_conflict_map(st.session_state.confirmed_lock, cells)
                if conflicts:
                    st.markdown('<div class="alert warn"><b>Data conflict alert:</b> A confirmed antibody has reactive cells that are antigen-negative. Investigate multiple antibodies and/or phenotype entry error.</div>', unsafe_allow_html=True)
                    for ab, labs in conflicts.items():
                        st.write(f"- Anti-{ab} confirmed, but reactive cell(s) are {ab}-negative: " + ", ".join(labs))

                targets_needing_selected = list(dict.fromkeys(list(supported_bg.keys()) + other_sig_final))
                if targets_needing_selected:
                    st.markdown("### Selected Cells (if needed)")
                    for a in targets_needing_selected:
                        active_set_now = set(list(st.session_state.confirmed_lock) + other_sig_final + list(supported_bg.keys()))
                        st.markdown(f'<div class="alert warn"><b>Anti-{a}:</b> discriminating cells needed.</div>', unsafe_allow_html=True)

                        sugg = suggest_selected_cells(a, list(active_set_now))
                        if sugg:
                            for lab, note in sugg[:12]:
                                st.write(f"- {lab} ({note})")
                        else:
                            st.write("- No suitable discriminating cell in current inventory → use another lot / external selected cells.")

                    enz = enzyme_hint_if_needed(targets_needing_selected)
                    if enz:
                        st.markdown(f'<div class="alert good"><b>Tip:</b> {enz}</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="alert good"><b>No Selected Cells needed:</b> confirmed antibody locked and no significant background remains.</div>', unsafe_allow_html=True)

            else:
                best = find_best_combo(candidates, cells, max_size=3)
                if not best:
                    st.markdown('<div class="alert warn"><b>No resolved specificity from current data.</b> Proceed with selected cells / additional panels.</div>', unsafe_allow_html=True)
                else:
                    sep_map = separability_map(best, cells)
                    resolved_raw = [a for a in best if sep_map.get(a, False)]
                    needs_work = [a for a in best if not sep_map.get(a, False)]

                    resolved_sig = [a for a in resolved_raw if a not in INSIGNIFICANT_AGS]
                    resolved_cold = [a for a in resolved_raw if a in INSIGNIFICANT_AGS]

                    if resolved_sig:
                        st.markdown(f'<div class="alert good"><b>Resolved:</b> {", ".join([f"Anti-{a}" for a in resolved_sig])}</div>', unsafe_allow_html=True)
                    if needs_work:
                        st.markdown(f'<div class="alert warn"><b>Suggested but not separable (do NOT confirm):</b> {", ".join([f"Anti-{a}" for a in needs_work])}</div>', unsafe_allow_html=True)
                    if resolved_cold and not resolved_sig:
                        st.markdown(f'<div class="alert warn"><b>Cold/insignificant (do not auto-confirm):</b> {", ".join([f"Anti-{a}" for a in resolved_cold])}</div>', unsafe_allow_html=True)

                    remaining_other = [a for a in candidates if a not in best]
                    other_sig = [a for a in remaining_other if a not in INSIGNIFICANT_AGS]
                    other_cold = [a for a in remaining_other if a in INSIGNIFICANT_AGS]

                    active_not_excluded = set(resolved_sig + needs_work + other_sig + other_cold + resolved_cold)
                    auto_ruled_out, supported_bg, inconclusive_bg, no_disc_bg = background_auto_resolution(
                        background_list=other_sig + other_cold + resolved_cold,
                        active_not_excluded=active_not_excluded,
                        cells=cells
                    )

                    other_sig_final = [a for a in other_sig if a not in auto_ruled_out]
                    other_cold_final = [a for a in other_cold if a not in auto_ruled_out]

                    st.markdown("### Confirmation (Rule of Three)")
                    confirmed = set()
                    if not resolved_sig:
                        st.markdown('<div class="alert warn"><b>No separable clinically significant antibody yet.</b> Add discriminating selected cells.</div>', unsafe_allow_html=True)
                    else:
                        for a in resolved_sig:
                            full, mod, p_cnt, n_cnt = check_rule_three_only_on_discriminating(a, best, cells)
                            if full or mod:
                                confirmed.add(a)

                    if confirmed:
                        st.session_state.confirmed_lock = set(confirmed)
                        st.markdown(f'<div class="alert good"><b>Confirmed:</b> {", ".join([f"Anti-{a}" for a in sorted(list(confirmed))])}</div>', unsafe_allow_html=True)
                        st.markdown(patient_antigen_negative_reminder(sorted(list(confirmed)), strong=True), unsafe_allow_html=True)
                    elif resolved_sig:
                        st.markdown(patient_antigen_negative_reminder(sorted(list(resolved_sig)), strong=False), unsafe_allow_html=True)

                    d_present = ("D" in confirmed) or ("D" in resolved_sig) or ("D" in needs_work)
                    c_present = ("C" in confirmed) or ("C" in resolved_sig) or ("C" in needs_work) or ("C" in supported_bg) or ("C" in other_sig_final)
                    if d_present and c_present:
                        strong = ("D" in confirmed and "C" in confirmed)
                        st.markdown(anti_g_alert_html(strong=strong), unsafe_allow_html=True)

                    targets_needing_selected = list(dict.fromkeys(needs_work + list(supported_bg.keys()) + other_sig_final))
                    if targets_needing_selected:
                        st.markdown("### Selected Cells (if needed)")
                        for a in targets_needing_selected:
                            active_set_now = set(resolved_sig + needs_work + other_sig_final + list(supported_bg.keys()))
                            st.markdown(f'<div class="alert warn"><b>Anti-{a}:</b> discriminating cells needed.</div>', unsafe_allow_html=True)

                            sugg = suggest_selected_cells(a, list(active_set_now))
                            if sugg:
                                for lab, note in sugg[:12]:
                                    st.write(f"- {lab} ({note})")
                            else:
                                st.write("- No suitable discriminating cell in current inventory → use another lot / external selected cells.")

                        enz = enzyme_hint_if_needed(targets_needing_selected)
                        if enz:
                            st.markdown(f'<div class="alert good"><b>Tip:</b> {enz}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown('<div class="alert good"><b>No Selected Cells needed:</b> all resolved antibodies confirmed and no significant background remains.</div>', unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    # Selected cells input
    st.markdown('<div class="card">', unsafe_allow_html=True)
    with st.expander("Add Selected Cell (From Library)", expanded=False):
        ex_id = st.text_input("Cell ID", key="ex_id")
        ex_res = st.selectbox("Reaction", GRADES, key="ex_res")
        ag_cols = st.columns(6)
        new_ph = {}
        for i, ag in enumerate(AGS):
            new_ph[ag] = 1 if ag_cols[i%6].checkbox(ag, key=f"ex_{ag}") else 0

        if st.button("Add selected cell", use_container_width=True, key="btn_add_ex"):
            st.session_state.ext.append({"id": ex_id.strip() if ex_id else "", "res": normalize_grade(ex_res), "ph": new_ph})
            st.success("Selected cell added. Re-run analysis.")

    if st.session_state.ext:
        st.caption("Selected cells:")
        st.table(pd.DataFrame(st.session_state.ext)[["id","res"]])
    st.markdown("</div>", unsafe_allow_html=True)

# =============================================================================
# 11) MAIN
# =============================================================================
if "auth_token" not in st.session_state:
    auth_gate()
else:
    ensure_profile_loaded()
    nav = sidebar_nav()
    if nav == "Admin Console":
        admin_console_page()
    else:
        workstation_page()
