import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta, timezone
import json
import base64
import requests
from pathlib import Path
from itertools import combinations
import secrets
import re

# ============================================================
# 0) CONFIG: Supabase + GitHub (Streamlit Secrets)
# ============================================================

def _cfg():
    # Supabase
    sb_url = st.secrets.get("SUPABASE_URL", "").strip()
    sb_anon = st.secrets.get("SUPABASE_ANON_KEY", "").strip()
    sb_service = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()  # used ONLY for privileged ops (create user / invites admin)
    # GitHub
    gh_token = st.secrets.get("GITHUB_TOKEN", None)
    gh_repo = st.secrets.get("GITHUB_REPO", None)   # e.g. "Haitham526/tabuk-blood-bank"
    gh_branch = st.secrets.get("GITHUB_BRANCH", "main")

    return {
        "SUPABASE_URL": sb_url,
        "SUPABASE_ANON_KEY": sb_anon,
        "SUPABASE_SERVICE_ROLE_KEY": sb_service,
        "GITHUB_TOKEN": gh_token,
        "GITHUB_REPO": gh_repo,
        "GITHUB_BRANCH": gh_branch,
    }

CFG = _cfg()

# ============================================================
# 1) HTTP helpers (no extra packages)
# ============================================================

def _sb_headers(anon_jwt: str | None = None, service: bool = False):
    headers = {
        "Content-Type": "application/json",
        "apikey": CFG["SUPABASE_ANON_KEY"],
        "Authorization": f"Bearer {CFG['SUPABASE_ANON_KEY']}",
    }
    if anon_jwt:
        headers["Authorization"] = f"Bearer {anon_jwt}"
    if service:
        # Service role bypasses RLS. Use carefully.
        headers["apikey"] = CFG["SUPABASE_SERVICE_ROLE_KEY"]
        headers["Authorization"] = f"Bearer {CFG['SUPABASE_SERVICE_ROLE_KEY']}"
    return headers

def _sb_rest(path: str):
    return f"{CFG['SUPABASE_URL'].rstrip('/')}/rest/v1/{path.lstrip('/')}"

def _sb_auth(path: str):
    return f"{CFG['SUPABASE_URL'].rstrip('/')}/auth/v1/{path.lstrip('/')}"

def sb_rest_get(table: str, params: dict, jwt: str | None = None, service: bool = False):
    url = _sb_rest(table)
    r = requests.get(url, headers=_sb_headers(jwt, service=service), params=params, timeout=30)
    return r

def sb_rest_post(table: str, payload: dict | list, jwt: str | None = None, service: bool = False):
    url = _sb_rest(table)
    r = requests.post(url, headers=_sb_headers(jwt, service=service), json=payload, timeout=30)
    return r

def sb_rest_patch(table: str, params: dict, payload: dict, jwt: str | None = None, service: bool = False):
    url = _sb_rest(table)
    r = requests.patch(url, headers=_sb_headers(jwt, service=service), params=params, json=payload, timeout=30)
    return r

def sb_auth_sign_in(email: str, password: str):
    url = _sb_auth("token?grant_type=password")
    payload = {"email": email, "password": password}
    r = requests.post(url, headers=_sb_headers(None, service=False), json=payload, timeout=30)
    return r

def sb_auth_sign_up(email: str, password: str):
    # requires Service Role for admin-created users OR allow signups in Supabase settings
    # We will use SERVICE ROLE for controlled registration via invite codes.
    url = _sb_auth("admin/users")
    payload = {"email": email, "password": password, "email_confirm": True}
    r = requests.post(url, headers=_sb_headers(None, service=True), json=payload, timeout=30)
    return r

def sb_auth_get_user(jwt: str):
    url = _sb_auth("user")
    r = requests.get(url, headers=_sb_headers(jwt, service=False), timeout=30)
    return r

# ============================================================
# 2) GitHub Save Engine (for Panel/Screen/Lots shared to all devices)
# ============================================================

def github_upsert_file(path_in_repo: str, content_text: str, commit_message: str):
    token, repo, branch = CFG["GITHUB_TOKEN"], CFG["GITHUB_REPO"], CFG["GITHUB_BRANCH"]
    if not token or not repo:
        raise RuntimeError("Missing GitHub Secrets: GITHUB_TOKEN / GITHUB_REPO")

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

# ============================================================
# 3) PAGE SETUP + UI THEME (Deep Blue, clean)
# ============================================================

st.set_page_config(page_title="H-AXIS", layout="wide", page_icon="🩸")

st.markdown("""
<style>
/* --- global --- */
:root{
  --hx-deep:#0B1F3A;
  --hx-deep2:#0A2A4F;
  --hx-mid:#0E3A6A;
  --hx-soft:#EAF2FF;
  --hx-line:#CFE0FF;
  --hx-text:#0B1220;
  --hx-muted:#5B6B82;
  --hx-card:#FFFFFF;
}

html, body, [class*="css"]  { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; }
div.block-container { padding-top: 1.2rem; padding-bottom: 3.8rem; }

/* --- header card --- */
.hx-hero {
  background: linear-gradient(120deg, #EAF2FF 0%, #D9ECFF 45%, #CFE7FF 100%);
  border: 1px solid var(--hx-line);
  border-radius: 16px;
  padding: 18px 22px;
  box-shadow: 0 10px 22px rgba(11,31,58,0.10);
  margin-bottom: 16px;
}
.hx-title { font-size: 30px; font-weight: 800; letter-spacing: 0.2px; color: var(--hx-deep); }
.hx-sub { margin-top: 2px; font-size: 14px; color: var(--hx-muted); font-weight: 600; }
.hx-mini { margin-top: 8px; font-size: 12px; color: var(--hx-muted); }

/* --- pills --- */
.hx-pill{
  display:inline-block; padding: 6px 10px; border-radius: 999px;
  border: 1px solid var(--hx-line);
  background: rgba(255,255,255,0.65);
  font-size: 12px; font-weight: 700; color: var(--hx-deep2);
}

/* --- cards --- */
.hx-card{
  background: var(--hx-card);
  border: 1px solid var(--hx-line);
  border-radius: 14px;
  padding: 14px 14px;
  box-shadow: 0 8px 16px rgba(11,31,58,0.06);
}

/* --- alerts (professional, not ugly) --- */
.hx-alert{
  border-radius: 12px; padding: 12px 14px; border:1px solid var(--hx-line);
  background: #F6FAFF; color: var(--hx-text);
}
.hx-warn{
  border-radius: 12px; padding: 12px 14px; border:1px solid #FFD7A8;
  background: #FFF8EF; color: #3A2A10;
}
.hx-danger{
  border-radius: 12px; padding: 12px 14px; border:1px solid #FFC1C7;
  background: #FFF3F5; color: #3A0B13;
}
.hx-ok{
  border-radius: 12px; padding: 12px 14px; border:1px solid #BFE8D1;
  background: #F2FFF7; color: #073018;
}

/* --- signature --- */
.hx-sign {
  position: fixed; right: 16px; bottom: 10px; z-index: 9999;
  background: rgba(11,31,58,0.92);
  border: 1px solid rgba(255,255,255,0.16);
  padding: 10px 14px; border-radius: 14px;
  box-shadow: 0 10px 24px rgba(0,0,0,0.18);
  max-width: 320px;
}
.hx-sign .n { color:#FFFFFF; font-weight: 800; font-size: 13px; letter-spacing: 0.2px; }
.hx-sign .t { color:#D6E6FF; font-weight: 600; font-size: 11px; margin-top: 2px; line-height: 1.25; }

/* make dataframe wider */
div[data-testid="stDataEditor"] table { width: 100% !important; }

/* buttons slightly nicer */
.stButton button, .stDownloadButton button {
  border-radius: 12px !important;
  padding: 10px 14px !important;
}
</style>
""", unsafe_allow_html=True)

def hero(user_role: str | None = None, hospital_code: str | None = None):
    role_txt = f"{user_role.upper()}" if user_role else "SECURE ACCESS"
    hc = hospital_code if hospital_code else "—"
    st.markdown(f"""
    <div class="hx-hero">
      <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px;">
        <div>
          <div class="hx-title">H-AXIS</div>
          <div class="hx-sub">Antibody Identification & Serology Decision Support</div>
          <div class="hx-mini"><span class="hx-pill">Role: {role_txt}</span>&nbsp;&nbsp;<span class="hx-pill">Hospital: {hc}</span></div>
        </div>
        <div style="text-align:right;">
          <div class="hx-mini" style="font-weight:700; color:var(--hx-deep2);">Secure access: Staff ID + Password</div>
          <div class="hx-mini">First-time registration uses an Invite Code</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("""
<div class="hx-sign">
  <div class="n">Dr. Haitham Ismail</div>
  <div class="t">Clinical Hematology/Oncology &<br>BM Transplantation & Transfusion Medicine Consultant</div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# 4) DATABASE MODEL (expects these tables)
# ============================================================
# public.hospitals:    code(text PK), name(text), is_active(bool)
# public.users_profile: id(bigint), user_id(uuid), hospital_code(text), role(text), staff_id(text), created_at(timestamptz)
# public.invites:      id(uuid), code(text), hospital_code(text), role(text), created_by(uuid),
#                      created_at(timestamptz), expires_at(timestamptz), used_at(timestamptz),
#                      used_by(uuid), is_active(bool), staff_id(text nullable)

def _staff_email(staff_id: str) -> str:
    # internal mapping; user never sees email
    staff_id = staff_id.strip()
    return f"{staff_id}@bb.local"

def _valid_staff_id(s: str) -> bool:
    s = (s or "").strip()
    # allow digits + optional hyphen; adjust if you want strict digits only
    return bool(re.fullmatch(r"[0-9]{4,20}", s))

def _now_utc():
    return datetime.now(timezone.utc)

def _invite_code():
    # readable, non-ambiguous
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))

# ============================================================
# 5) AUTH STATE
# ============================================================

def auth_clear():
    for k in ["jwt", "user", "profile", "role", "hospital_code", "staff_id"]:
        if k in st.session_state:
            del st.session_state[k]
    st.rerun()

def auth_set(jwt: str, user_obj: dict, profile: dict):
    st.session_state.jwt = jwt
    st.session_state.user = user_obj
    st.session_state.profile = profile
    st.session_state.role = profile.get("role", "staff")
    st.session_state.hospital_code = profile.get("hospital_code", "")
    st.session_state.staff_id = profile.get("staff_id", "")
    st.rerun()

def is_logged_in() -> bool:
    return "jwt" in st.session_state and "user" in st.session_state and "profile" in st.session_state

def require_supabase_ready():
    missing = []
    if not CFG["SUPABASE_URL"]:
        missing.append("SUPABASE_URL")
    if not CFG["SUPABASE_ANON_KEY"]:
        missing.append("SUPABASE_ANON_KEY")
    if not CFG["SUPABASE_SERVICE_ROLE_KEY"]:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if missing:
        st.error("Supabase secrets missing: " + ", ".join(missing))
        st.stop()

require_supabase_ready()

# ============================================================
# 6) LOAD PROFILE BY user_id
# ============================================================

def fetch_profile_by_user_id(user_id: str, jwt: str | None = None, service: bool = False) -> dict | None:
    # Prefer service role to avoid RLS pain during app development.
    # If you later want strict RLS, switch service=False and ensure policies.
    params = {"select": "*", "user_id": f"eq.{user_id}", "limit": "1"}
    r = sb_rest_get("users_profile", params=params, jwt=jwt, service=service)
    if r.status_code != 200:
        return None
    rows = r.json()
    if not rows:
        return None
    return rows[0]

def fetch_hospital_name(code: str) -> str:
    if not code:
        return ""
    params = {"select": "name", "code": f"eq.{code}", "limit": "1"}
    r = sb_rest_get("hospitals", params=params, jwt=None, service=True)
    if r.status_code == 200 and r.json():
        return r.json()[0].get("name", "")
    return ""

# ============================================================
# 7) INVITES
# ============================================================

def create_invite(hospital_code: str, role: str, created_by_user_id: str, expires_hours: int = 168, staff_id: str | None = None):
    code = _invite_code()
    now = _now_utc()
    exp = now + timedelta(hours=int(expires_hours))
    payload = {
        "id": str(secrets.token_hex(16)),
        "code": code,
        "hospital_code": hospital_code,
        "role": role,
        "created_by": created_by_user_id,
        "created_at": now.isoformat(),
        "expires_at": exp.isoformat(),
        "used_at": None,
        "used_by": None,
        "is_active": True,
        "staff_id": staff_id if staff_id else None,
    }
    r = sb_rest_post("invites", payload, jwt=None, service=True)
    if r.status_code not in (201, 200):
        raise RuntimeError(f"Invite create failed: {r.status_code} {r.text}")
    return code

def validate_invite(code: str):
    code = (code or "").strip().upper()
    params = {"select": "*", "code": f"eq.{code}", "limit": "1"}
    r = sb_rest_get("invites", params=params, jwt=None, service=True)
    if r.status_code != 200 or not r.json():
        return None, "Invite code not found."
    inv = r.json()[0]
    if not inv.get("is_active", False):
        return None, "Invite is not active."
    if inv.get("used_at") is not None:
        return None, "Invite already used."
    exp = inv.get("expires_at")
    if exp:
        try:
            exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            if _now_utc() > exp_dt:
                return None, "Invite expired."
        except Exception:
            pass
    return inv, None

def consume_invite(invite_id: str, used_by: str):
    now = _now_utc().isoformat()
    params = {"id": f"eq.{invite_id}"}
    payload = {"used_at": now, "used_by": used_by, "is_active": False}
    r = sb_rest_patch("invites", params=params, payload=payload, jwt=None, service=True)
    if r.status_code not in (200, 204):
        raise RuntimeError(f"Invite consume failed: {r.status_code} {r.text}")

# ============================================================
# 8) USER CREATION (First-time registration via Invite)
# ============================================================

def register_with_invite(inv_code: str, staff_id: str, password: str):
    inv, err = validate_invite(inv_code)
    if err:
        return None, err

    staff_id = staff_id.strip()
    if inv.get("staff_id"):
        # optional binding: invite can be locked to a specific staff_id
        if inv["staff_id"] != staff_id:
            return None, "This invite is locked to a different Staff ID."

    email = _staff_email(staff_id)

    # 1) Create auth user (service role)
    r = sb_auth_sign_up(email=email, password=password)
    if r.status_code not in (200, 201):
        # If user already exists, show clean message
        if "already registered" in r.text.lower() or "duplicate" in r.text.lower():
            return None, "This Staff ID is already registered. Use Sign in."
        return None, f"Registration failed: {r.status_code}"

    user_obj = r.json()
    user_id = user_obj.get("id") or user_obj.get("user", {}).get("id")
    if not user_id:
        # some responses wrap differently
        return None, "Registration failed (no user id returned)."

    # 2) Insert users_profile
    payload = {
        "user_id": user_id,
        "hospital_code": inv["hospital_code"],
        "role": inv["role"],
        "staff_id": staff_id,
        "created_at": _now_utc().isoformat(),
    }
    rr = sb_rest_post("users_profile", payload, jwt=None, service=True)
    if rr.status_code not in (201, 200):
        return None, f"Profile creation failed: {rr.status_code}"

    # 3) Consume invite
    try:
        consume_invite(invite_id=inv["id"], used_by=user_id)
    except Exception:
        pass

    return {"user_id": user_id, "hospital_code": inv["hospital_code"], "role": inv["role"], "staff_id": staff_id}, None

# ============================================================
# 9) SIGN IN
# ============================================================

def sign_in_staff(staff_id: str, password: str):
    staff_id = staff_id.strip()
    email = _staff_email(staff_id)
    r = sb_auth_sign_in(email=email, password=password)
    if r.status_code != 200:
        return None, "Invalid Staff ID or password."

    token = r.json().get("access_token")
    if not token:
        return None, "Login failed (no token)."

    # get user
    u = sb_auth_get_user(token)
    if u.status_code != 200:
        return None, "Login failed (user fetch)."
    user_obj = u.json()
    user_id = user_obj.get("id")

    # fetch profile (service role to be robust)
    prof = fetch_profile_by_user_id(user_id, jwt=None, service=True)
    if not prof:
        return None, "Profile not found. Contact admin."

    return {"jwt": token, "user": user_obj, "profile": prof}, None

# ============================================================
# 10) SER0LOGY ENGINE CONSTANTS (your original logic preserved)
# ============================================================

AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

IGNORED_AGS = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"]
INSIGNIFICANT_AGS = ["Lea", "Lua", "Leb", "P1"]
ENZYME_DESTROYED = ["Fya","Fyb","M","N","S","s"]

GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]
YN3 = ["Not Done", "Negative", "Positive"]

# ============================================================
# 11) LOCAL STATE (Panel/Screen/Lots)
# ============================================================

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

# ============================================================
# 12) ENGINE HELPERS (your original logic preserved)
# ============================================================

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
    box_class = "hx-danger" if strong else "hx-warn"
    intro = ("Confirm the patient is ANTIGEN-NEGATIVE for the corresponding antigen(s) to support the antibody identification."
             if strong else
             "Before you finalize/report, confirm the patient is ANTIGEN-NEGATIVE for the corresponding antigen(s).")

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
    box = "hx-danger" if strong else "hx-warn"
    return f"""
    <div class='{box}'>
      <b>Consider Anti-G (D + C pattern)</b><br>
      Anti-G may mimic <b>Anti-D + Anti-C</b>. If clinically relevant (especially pregnancy / RhIG decision), do not label as true Anti-D until Anti-G is excluded.<br>
      <b>Suggested next steps (per SOP/reference lab):</b>
      <ol style="margin-top:6px;">
        <li>Assess if this impacts management (e.g., RhIG eligibility).</li>
        <li>Perform differential workup using appropriate adsorption/elution strategy if available, or refer to reference lab.</li>
        <li>Use pre-transfusion sample when possible.</li>
      </ol>
    </div>
    """

def confirmed_conflict_map(confirmed_set: set, cells: list):
    conflicts = {}
    for ab in confirmed_set:
        bad_labels = []
        for c in cells:
            if c["react"] == 1:
                if not ph_has(c["ph"], ab):
                    bad_labels.append(c["label"])
        if bad_labels:
            conflicts[ab] = bad_labels
    return conflicts

# ============================================================
# 13) SUPERVISOR PASTE/EDIT helpers (your original preserved)
# ============================================================

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
            ag, help="Tick = Antigen Present (1). Untick = Absent (0).", default=False
        )
        for ag in AGS
    }

# ============================================================
# 14) AUTH UI (Login / Register)
# ============================================================

def ui_auth():
    hero(None, None)

    st.markdown('<div class="hx-card">', unsafe_allow_html=True)
    tabs = st.tabs(["Sign in", "First-time registration (Invite Code)"])

    with tabs[0]:
        c1, c2 = st.columns([1, 1])
        staff_id = c1.text_input("Staff ID", placeholder="e.g., 51599657", key="login_staff")
        password = c2.text_input("Password", type="password", key="login_pwd")

        if st.button("Sign in", type="primary", use_container_width=True):
            if not _valid_staff_id(staff_id):
                st.error("Invalid Staff ID format.")
            elif not password or len(password) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                res, err = sign_in_staff(staff_id, password)
                if err:
                    st.error(err)
                else:
                    auth_set(res["jwt"], res["user"], res["profile"])

    with tabs[1]:
        c1, c2 = st.columns([1, 1])
        inv = c1.text_input("Invite Code", placeholder="8 characters", key="reg_inv").strip().upper()
        staff_id = c2.text_input("Staff ID", placeholder="Your staff ID", key="reg_staff")

        p1, p2 = st.columns([1, 1])
        pwd = p1.text_input("Create Password", type="password", key="reg_pwd1")
        pwd2 = p2.text_input("Confirm Password", type="password", key="reg_pwd2")

        if st.button("Register", type="primary", use_container_width=True):
            if not inv or len(inv) < 6:
                st.error("Enter a valid Invite Code.")
            elif not _valid_staff_id(staff_id):
                st.error("Invalid Staff ID format.")
            elif not pwd or len(pwd) < 6:
                st.error("Password must be at least 6 characters.")
            elif pwd != pwd2:
                st.error("Passwords do not match.")
            else:
                out, err = register_with_invite(inv, staff_id, pwd)
                if err:
                    st.error(err)
                else:
                    st.success("Registered successfully. Please sign in now.")
    st.markdown("</div>", unsafe_allow_html=True)

# ============================================================
# 15) ADMIN / SUPERVISOR UI (Invite generator + Hospitals + Users)
# ============================================================

def ui_admin_supervisor_panel():
    role = st.session_state.role
    hospital_code = st.session_state.hospital_code
    hero(role, hospital_code)

    # top actions
    top = st.columns([1.2, 1, 1, 1])
    top[0].markdown(f"<div class='hx-alert'><b>Signed in</b><br>Staff ID: <b>{st.session_state.staff_id}</b><br>Role: <b>{role.upper()}</b></div>", unsafe_allow_html=True)
    if top[3].button("Logout", use_container_width=True):
        auth_clear()

    # Admin can manage hospitals + supervisors
    if role == "admin":
        st.markdown("<div class='hx-card'>", unsafe_allow_html=True)
        st.subheader("Admin Console")

        t1, t2, t3 = st.tabs(["Hospitals", "Create Supervisor Invite", "Create Staff Invite (Any Hospital)"])

        with t1:
            st.caption("Add or review hospitals. (Table: public.hospitals)")
            c1, c2 = st.columns([1, 1])
            new_code = c1.text_input("Hospital Code", placeholder="e.g., MCHTABUK")
            new_name = c2.text_input("Hospital Name", placeholder="Maternity & Children Hospital - Tabuk")
            if st.button("Add hospital", type="primary"):
                if not new_code or not re.fullmatch(r"[A-Z0-9_]{3,32}", new_code.strip().upper()):
                    st.error("Hospital code must be A-Z, 0-9, underscore (3-32 chars).")
                else:
                    payload = {"code": new_code.strip().upper(), "name": new_name.strip(), "is_active": True}
                    r = sb_rest_post("hospitals", payload, jwt=None, service=True)
                    if r.status_code in (200, 201):
                        st.success("Hospital added.")
                    else:
                        st.error(f"Failed: {r.status_code}")

            # list
            rr = sb_rest_get("hospitals", params={"select": "code,name,is_active", "order": "code.asc"}, jwt=None, service=True)
            if rr.status_code == 200:
                st.dataframe(pd.DataFrame(rr.json()), use_container_width=True, hide_index=True)

        with t2:
            st.caption("Generate an Invite Code for a Supervisor (first-time registration).")
            hospitals = sb_rest_get("hospitals", params={"select":"code,name", "order":"code.asc"}, jwt=None, service=True)
            options = []
            if hospitals.status_code == 200:
                for h in hospitals.json():
                    options.append(f"{h['code']} — {h.get('name','')}")
            pick = st.selectbox("Target hospital", options=options if options else ["(no hospitals)"])
            exp_h = st.selectbox("Expires in", [24, 72, 168, 336], index=2, format_func=lambda x: f"{x} hours")
            if st.button("Generate Supervisor Invite", type="primary"):
                if "(no hospitals)" in pick:
                    st.error("Add a hospital first.")
                else:
                    hcode = pick.split("—")[0].strip()
                    try:
                        code = create_invite(hospital_code=hcode, role="supervisor",
                                             created_by_user_id=st.session_state.user["id"],
                                             expires_hours=int(exp_h))
                        st.success(f"Invite Code: {code}")
                        st.info("Send this code to the Supervisor to register (Invite Code + Staff ID + Password).")
                    except Exception as e:
                        st.error(str(e))

        with t3:
            st.caption("Generate Staff invite for any hospital (Admin override).")
            hospitals = sb_rest_get("hospitals", params={"select":"code,name", "order":"code.asc"}, jwt=None, service=True)
            options = []
            if hospitals.status_code == 200:
                for h in hospitals.json():
                    options.append(f"{h['code']} — {h.get('name','')}")
            pick2 = st.selectbox("Hospital", options=options if options else ["(no hospitals)"], key="adm_staff_inv_h")
            lock_staff = st.text_input("Lock to specific Staff ID (optional)", placeholder="leave empty to allow any", key="adm_lock_staff")
            exp_h2 = st.selectbox("Expires in ", [24, 72, 168, 336], index=2, format_func=lambda x: f"{x} hours", key="adm_staff_exp")
            if st.button("Generate Staff Invite", type="primary"):
                if "(no hospitals)" in pick2:
                    st.error("Add a hospital first.")
                else:
                    hcode = pick2.split("—")[0].strip()
                    try:
                        code = create_invite(hospital_code=hcode, role="staff",
                                             created_by_user_id=st.session_state.user["id"],
                                             expires_hours=int(exp_h2),
                                             staff_id=(lock_staff.strip() if lock_staff.strip() else None))
                        st.success(f"Invite Code: {code}")
                    except Exception as e:
                        st.error(str(e))

        st.markdown("</div>", unsafe_allow_html=True)

    # Supervisor can create staff invites for their hospital
    if role in ("admin", "supervisor"):
        st.markdown("<div class='hx-card'>", unsafe_allow_html=True)
        st.subheader("Invite Generator")

        st.caption("Generate Invite Codes for first-time registration.")

        c1, c2, c3 = st.columns([1, 1, 1])
        inv_role = "staff" if role == "supervisor" else c1.selectbox("Role", ["staff", "supervisor"], index=0)
        exp = c2.selectbox("Expires in", [24, 72, 168, 336], index=2, format_func=lambda x: f"{x} hours")
        lock_staff = c3.text_input("Lock to Staff ID (optional)", placeholder="optional")

        target_hospital = hospital_code
        if role == "admin":
            hospitals = sb_rest_get("hospitals", params={"select":"code,name","order":"code.asc"}, jwt=None, service=True)
            options = []
            if hospitals.status_code == 200:
                for h in hospitals.json():
                    options.append(f"{h['code']} — {h.get('name','')}")
            pick = st.selectbox("Target hospital", options=options if options else ["(no hospitals)"])
            if "(no hospitals)" not in pick:
                target_hospital = pick.split("—")[0].strip()

        if st.button("Generate Invite Code", type="primary"):
            try:
                code = create_invite(hospital_code=target_hospital, role=inv_role,
                                     created_by_user_id=st.session_state.user["id"],
                                     expires_hours=int(exp),
                                     staff_id=(lock_staff.strip() if lock_staff.strip() else None))
                st.success(f"Invite Code: {code}")
            except Exception as e:
                st.error(str(e))

        # Show active invites for this hospital (admin can see all by filtering with hospital)
        st.write("---")
        st.caption("Active invites (latest 50)")
        params = {"select":"code,role,hospital_code,created_at,expires_at,is_active,used_at,staff_id", "order":"created_at.desc", "limit":"50"}
        if role != "admin":
            params["hospital_code"] = f"eq.{hospital_code}"
        r = sb_rest_get("invites", params=params, jwt=None, service=True)
        if r.status_code == 200:
            df = pd.DataFrame(r.json())
            st.dataframe(df, use_container_width=True, hide_index=True)

        st.markdown("</div>", unsafe_allow_html=True)

# ============================================================
# 16) APP SIDEBAR NAV (Role-based)
# ============================================================

def sidebar_nav():
    role = st.session_state.role
    items = ["Workstation"]
    if role in ("admin", "supervisor"):
        items += ["Supervisor Panel Setup"]
    if role in ("admin", "supervisor"):
        items += ["Admin/Supervisor Console"]
    return st.sidebar.radio("Navigation", items)

# ============================================================
# 17) SUPERVISOR PANEL (your existing GitHub publish logic)
# ============================================================

def ui_supervisor_panel():
    role = st.session_state.role
    hospital_code = st.session_state.hospital_code
    hero(role, hospital_code)

    st.markdown("<div class='hx-card'>", unsafe_allow_html=True)
    st.subheader("Panel Configuration (Supervisor)")

    c1, c2, c3 = st.columns([1.2, 1.2, 1])
    c1.write(f"**Hospital:** {hospital_code}  \n**Role:** {role.upper()}")
    if c3.button("Logout", use_container_width=True):
        auth_clear()

    st.write("---")
    st.markdown("<div class='hx-alert'><b>Lot Setup</b><br>Update lots locally then publish to GitHub to sync all devices.</div>", unsafe_allow_html=True)

    cA, cB = st.columns(2)
    lp = cA.text_input("ID Panel Lot#", value=st.session_state.lot_p, key="lot_p_in")
    ls = cB.text_input("Screen Panel Lot#", value=st.session_state.lot_s, key="lot_s_in")

    if st.button("Save Lots (Local)"):
        st.session_state.lot_p = lp
        st.session_state.lot_s = ls
        st.success("Saved locally. Publish to GitHub to sync all devices.")

    st.write("---")
    st.subheader("Monthly Grid Update")
    st.caption("Paste 26 columns in AGS order. If there are extra columns, the app takes the LAST 26.")

    tab_paste, tab_edit = st.tabs(["Copy/Paste Update", "Manual Edit (Safe)"])

    with tab_paste:
        cA, cB = st.columns(2)

        with cA:
            st.markdown("**Panel 11 (Paste)**")
            p_txt = st.text_area("Paste 11 rows (tab-separated)", height=170, key="p11_paste")
            if st.button("Update Panel 11 from Paste", type="primary"):
                df_new, msg = parse_paste_table(p_txt, expected_rows=11, id_prefix="C")
                df_new["ID"] = [f"C{i+1}" for i in range(11)]
                st.session_state.panel11_df = df_new.copy()
                st.success(msg + " Panel 11 updated locally.")
            st.dataframe(st.session_state.panel11_df.iloc[:, :15], use_container_width=True)

        with cB:
            st.markdown("**Screen 3 (Paste)**")
            s_txt = st.text_area("Paste 3 rows (tab-separated)", height=170, key="p3_paste")
            if st.button("Update Screen 3 from Paste", type="primary"):
                df_new, msg = parse_paste_table(s_txt, expected_rows=3, id_prefix="S", id_list=["SI","SII","SIII"])
                df_new["ID"] = ["SI","SII","SIII"]
                st.session_state.screen3_df = df_new.copy()
                st.success(msg + " Screen 3 updated locally.")
            st.dataframe(st.session_state.screen3_df.iloc[:, :15], use_container_width=True)

    with tab_edit:
        st.markdown("<div class='hx-alert'><b>Safe rules:</b> ID locked • Fixed rows • 0/1 only via checkboxes.</div>", unsafe_allow_html=True)

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
            if st.button("Apply Manual Changes (Panel 11)", type="primary"):
                st.session_state.panel11_df = edited_p11.copy()
                st.success("Panel 11 updated safely (local).")

        with t2:
            edited_p3 = st.data_editor(
                st.session_state.screen3_df,
                use_container_width=True,
                num_rows="fixed",
                disabled=["ID"],
                column_config=_checkbox_column_config(),
                key="editor_screen3"
            )
            if st.button("Apply Manual Changes (Screen 3)", type="primary"):
                st.session_state.screen3_df = edited_p3.copy()
                st.success("Screen 3 updated safely (local).")

    st.write("---")
    st.subheader("Publish to ALL devices (Save to GitHub)")
    confirm_pub = st.checkbox("I confirm Panel/Screen data were reviewed and are correct", key="confirm_publish")

    if st.button("Save to GitHub (Commit)", type="primary"):
        if not confirm_pub:
            st.error("Confirmation required before publishing.")
        else:
            try:
                lots_json = json.dumps({"lot_p": st.session_state.lot_p, "lot_s": st.session_state.lot_s}, ensure_ascii=False, indent=2)
                github_upsert_file("data/p11.csv", st.session_state.panel11_df.to_csv(index=False), "Update monthly p11 panel")
                github_upsert_file("data/p3.csv",  st.session_state.screen3_df.to_csv(index=False), "Update monthly p3 screen")
                github_upsert_file("data/lots.json", lots_json, "Update monthly lots")
                st.success("Published to GitHub successfully.")
            except Exception as e:
                st.error(f"Save failed: {e}")

    st.markdown("</div>", unsafe_allow_html=True)

# ============================================================
# 18) WORKSTATION UI (your original, with small visual cleanup)
# ============================================================

def ui_workstation():
    role = st.session_state.role
    hospital_code = st.session_state.hospital_code
    hero(role, hospital_code)

    top = st.columns([1.2, 1, 1, 1])
    top[0].markdown(f"<div class='hx-alert'><b>User</b><br>Staff ID: <b>{st.session_state.staff_id}</b><br>Role: <b>{role.upper()}</b></div>", unsafe_allow_html=True)
    if top[3].button("Logout", use_container_width=True):
        auth_clear()

    lp_txt = st.session_state.lot_p if st.session_state.lot_p else "REQUIRED"
    ls_txt = st.session_state.lot_s if st.session_state.lot_s else "REQUIRED"
    st.markdown(f"<div class='hx-card'><span class='hx-pill'>ID Panel Lot: {lp_txt}</span> &nbsp; <span class='hx-pill'>Screen Lot: {ls_txt}</span></div>", unsafe_allow_html=True)

    st.write("")
    st.markdown("<div class='hx-card'>", unsafe_allow_html=True)

    top1, top2, top3, top4 = st.columns(4)
    _ = top1.text_input("Patient Name", key="pt_name")
    _ = top2.text_input("MRN", key="pt_mrn")
    _ = top3.text_input("Technologist", key="tech_nm")
    _ = top4.date_input("Run Date", value=date.today(), key="run_dt")

    with st.form("main_form", clear_on_submit=False):
        st.write("### Reaction Entry")
        L, R = st.columns([1, 2.5])

        with L:
            st.write("Controls")
            ac_res = st.radio("Auto Control (AC)", ["Negative", "Positive"], key="rx_ac")

            recent_tx = st.checkbox("Recent transfusion (≤ 4 weeks)?", value=False, key="recent_tx")
            if recent_tx:
                st.markdown("""
                <div class='hx-danger'>
                <b>RECENT TRANSFUSION FLAGGED</b><br>
                Consider <b>DHTR</b> / anamnestic alloantibody response if clinically compatible.
                </div>
                """, unsafe_allow_html=True)

            st.write("Screening")
            s_I   = st.selectbox("Screen I", GRADES, key="rx_sI")
            s_II  = st.selectbox("Screen II", GRADES, key="rx_sII")
            s_III = st.selectbox("Screen III", GRADES, key="rx_sIII")

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

        run_btn = st.form_submit_button("Run Analysis", use_container_width=True)

    if run_btn:
        if not st.session_state.lot_p or not st.session_state.lot_s:
            st.error("Lots are not configured by Supervisor.")
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

        # PAN-REACTIVE LOGIC
        if all_rx and ac_negative:
            tx_note = ""
            if recent_tx:
                tx_note = "<li><b>Recent transfusion ≤ 4 weeks</b>: consider DHTR/anamnestic response; compare pre/post samples and review hemolysis markers.</li>"

            st.markdown(f"""
            <div class='hx-danger'>
            <b>Pan-reactive pattern with NEGATIVE autocontrol</b><br>
            Most consistent with:
            <ul>
              <li><b>Alloantibody to a High-Incidence Antigen</b></li>
              <li><b>OR multiple alloantibodies</b> not separable with current cells</li>
            </ul>
            Action / Workflow:
            <ol>
              <li><b>Stop</b> routine single-specificity interpretation.</li>
              <li>Immediate referral to <b>Physician / Reference Lab</b>.</li>
              <li>Request <b>extended phenotype / genotype</b>.</li>
              <li>Initiate <b>rare compatible unit search</b>.</li>
              <li>Use additional panels/different lots + selected cells if separation needed.</li>
              {tx_note}
            </ol>
            </div>
            """, unsafe_allow_html=True)

        elif all_rx and (not ac_negative):
            st.markdown("""
            <div class='hx-danger'>
            <b>Pan-reactive pattern with POSITIVE autocontrol</b><br>
            Requires <b>Monospecific DAT</b> pathway before any alloantibody claims.
            </div>
            """, unsafe_allow_html=True)

            st.subheader("Monospecific DAT Entry (Required)")
            c1, c2, c3 = st.columns(3)
            dat_igg = c1.selectbox("DAT IgG", YN3, key="dat_igg")
            dat_c3d = c2.selectbox("DAT C3d", YN3, key="dat_c3d")
            dat_ctl = c3.selectbox("DAT Control", YN3, key="dat_ctl")

            if dat_ctl == "Positive":
                st.markdown("<div class='hx-danger'><b>DAT Control is POSITIVE</b> → invalid run / control failure. Repeat DAT.</div>", unsafe_allow_html=True)
            elif dat_igg == "Not Done" or dat_c3d == "Not Done":
                st.markdown("<div class='hx-warn'>Please perform <b>Monospecific DAT (IgG & C3d)</b> to proceed.</div>", unsafe_allow_html=True)
            else:
                if dat_igg == "Positive":
                    ads = "Auto-adsorption (ONLY if NOT recently transfused)" if not recent_tx else "Allo-adsorption (recent transfusion → avoid auto-adsorption)"
                    st.markdown(f"""
                    <div class='hx-alert'>
                    <b>DAT IgG POSITIVE</b> (C3d: {dat_c3d}) → consistent with <b>Warm Autoantibody / WAIHA</b>.<br><br>
                    Workflow:
                    <ol>
                      <li>Consider eluate when indicated.</li>
                      <li>Perform adsorption: <b>{ads}</b>.</li>
                      <li>Patient phenotype/genotype (pre-transfusion preferred).</li>
                      <li>Transfuse per policy (antigen-matched / least-incompatible as appropriate).</li>
                    </ol>
                    </div>
                    """, unsafe_allow_html=True)
                elif dat_igg == "Negative" and dat_c3d == "Positive":
                    st.markdown("""
                    <div class='hx-alert'>
                    <b>DAT IgG NEGATIVE + C3d POSITIVE</b> → complement-mediated process (e.g., cold autoantibody).<br><br>
                    Actions:
                    <ol>
                      <li>Evaluate cold interference per SOP.</li>
                      <li>Repeat as needed at 37°C.</li>
                      <li>Refer if clinically significant transfusion requirement.</li>
                    </ol>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                    <div class='hx-warn'>
                    <b>AC POSITIVE but DAT IgG & C3d NEGATIVE</b> → consider interference/technique issue (rouleaux/cold/reagent effects).<br><br>
                    Actions:
                    <ol>
                      <li>Repeat with proper technique; saline replacement if rouleaux suspected.</li>
                      <li>Pre-warm/37°C repeat if cold suspected.</li>
                      <li>If unresolved → refer.</li>
                    </ol>
                    </div>
                    """, unsafe_allow_html=True)

        if not all_rx:
            cells = get_cells(in_p, in_s, st.session_state.ext)
            ruled = rule_out(in_p, in_s, st.session_state.ext)
            candidates = [a for a in AGS if a not in ruled and a not in IGNORED_AGS]

            st.write("---")
            st.subheader("Conclusion")

            if st.session_state.confirmed_lock:
                confirmed_locked = sorted(list(st.session_state.confirmed_lock))
                st.markdown(f"<div class='hx-ok'><b>Resolved (LOCKED confirmed):</b> {', '.join([f'Anti-{a}' for a in confirmed_locked])}</div>", unsafe_allow_html=True)

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
                    st.markdown("### Auto Rule-out")
                    for ag, labs in auto_ruled_out.items():
                        st.write(f"- **Anti-{ag} ruled out**: " + ", ".join(labs))

                if supported_bg:
                    st.markdown("### Background antibodies suggested (not confirmed)")
                    for ag, labs in supported_bg.items():
                        st.write(f"- **Anti-{ag} suspected**: " + ", ".join(labs))

                if inconclusive_bg:
                    st.markdown("### Inconclusive background")
                    for ag, labs in inconclusive_bg.items():
                        st.write(f"- **Anti-{ag} inconclusive**: " + ", ".join(labs))

                if other_sig_final or other_cold_final or no_disc_bg:
                    st.markdown("### Not excluded yet")
                    if other_sig_final:
                        st.write("**Clinically significant:** " + ", ".join([f"Anti-{x}" for x in other_sig_final]))
                    if other_cold_final:
                        st.write("**Cold/Insignificant:** " + ", ".join([f"Anti-{x}" for x in other_cold_final]))
                    if no_disc_bg:
                        st.warning("No discriminating cells available for: " + ", ".join([f"Anti-{x}" for x in no_disc_bg]))

                st.markdown(patient_antigen_negative_reminder(confirmed_locked, strong=True), unsafe_allow_html=True)

                d_present = ("D" in st.session_state.confirmed_lock)
                c_present = ("C" in st.session_state.confirmed_lock)
                if d_present and c_present:
                    st.markdown(anti_g_alert_html(strong=True), unsafe_allow_html=True)

                conflicts = confirmed_conflict_map(st.session_state.confirmed_lock, cells)
                if conflicts:
                    st.markdown("<div class='hx-warn'><b>Data conflict alert</b><br>A confirmed antibody has reactive cells that are antigen-negative. Investigate multiple antibodies and/or phenotype entry error.</div>", unsafe_allow_html=True)
                    for ab, labs in conflicts.items():
                        st.write(f"- **Anti-{ab} confirmed**, but reactive cells are **{ab}-negative**: " + ", ".join(labs))

                targets_needing_selected = list(dict.fromkeys(list(supported_bg.keys()) + other_sig_final))
                if targets_needing_selected:
                    st.write("---")
                    st.subheader("Selected Cells (if needed)")
                    for a in targets_needing_selected:
                        active_set_now = set(list(st.session_state.confirmed_lock) + other_sig_final + list(supported_bg.keys()))
                        sugg = suggest_selected_cells(a, list(active_set_now))
                        if sugg:
                            st.write(f"**Anti-{a}** — suggested cells:")
                            for lab, note in sugg[:12]:
                                st.write(f"- {lab} ({note})")
                        else:
                            st.write(f"**Anti-{a}** — no suitable discriminating cell in current inventory.")
                    enz = enzyme_hint_if_needed(targets_needing_selected)
                    if enz:
                        st.info(enz)

            else:
                best = find_best_combo(candidates, cells, max_size=3)
                if not best:
                    st.markdown("<div class='hx-warn'><b>No resolved specificity from current data.</b> Use selected cells / another lot.</div>", unsafe_allow_html=True)
                else:
                    sep_map = separability_map(best, cells)
                    resolved_raw = [a for a in best if sep_map.get(a, False)]
                    needs_work = [a for a in best if not sep_map.get(a, False)]

                    resolved_sig = [a for a in resolved_raw if a not in INSIGNIFICANT_AGS]
                    resolved_cold = [a for a in resolved_raw if a in INSIGNIFICANT_AGS]

                    if resolved_sig:
                        st.markdown("<div class='hx-ok'><b>Resolved (separable):</b> " + ", ".join([f"Anti-{a}" for a in resolved_sig]) + "</div>", unsafe_allow_html=True)
                    if needs_work:
                        st.markdown("<div class='hx-warn'><b>Suggested but NOT separable yet:</b> " + ", ".join([f"Anti-{a}" for a in needs_work]) + "</div>", unsafe_allow_html=True)
                    if resolved_cold and not resolved_sig:
                        st.markdown("<div class='hx-alert'><b>Cold/Insignificant:</b> " + ", ".join([f"Anti-{a}" for a in resolved_cold]) + "</div>", unsafe_allow_html=True)

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

                    st.write("---")
                    st.subheader("Confirmation (Rule of Three)")

                    confirmed = set()
                    if not resolved_sig:
                        st.info("No clinically significant antibody is separable yet → do not apply rule-of-three. Add discriminating selected cells.")
                    else:
                        for a in resolved_sig:
                            full, mod, p_cnt, n_cnt = check_rule_three_only_on_discriminating(a, best, cells)
                            if full:
                                st.write(f"✅ Anti-{a} CONFIRMED (3+3) on discriminating cells (P:{p_cnt} / N:{n_cnt})")
                                confirmed.add(a)
                            elif mod:
                                st.write(f"✅ Anti-{a} CONFIRMED (2+3) on discriminating cells (P:{p_cnt} / N:{n_cnt})")
                                confirmed.add(a)
                            else:
                                st.write(f"⚠️ Anti-{a} NOT confirmed yet (P:{p_cnt} / N:{n_cnt})")

                    if confirmed:
                        st.session_state.confirmed_lock = set(confirmed)
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
                        st.write("---")
                        st.subheader("Selected Cells (if needed)")
                        for a in targets_needing_selected:
                            active_set_now = set(resolved_sig + needs_work + other_sig_final + list(supported_bg.keys()))
                            sugg = suggest_selected_cells(a, list(active_set_now))
                            if sugg:
                                st.write(f"**Anti-{a}** — suggested cells:")
                                for lab, note in sugg[:12]:
                                    st.write(f"- {lab} ({note})")
                            else:
                                st.write(f"**Anti-{a}** — no suitable discriminating cell in current inventory.")
                        enz = enzyme_hint_if_needed(targets_needing_selected)
                        if enz:
                            st.info(enz)

    st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("Add Selected Cell (From Library)"):
        ex_id = st.text_input("ID", key="ex_id")
        ex_res = st.selectbox("Reaction", GRADES, key="ex_res")
        ag_cols = st.columns(6)
        new_ph = {}
        for i, ag in enumerate(AGS):
            new_ph[ag] = 1 if ag_cols[i%6].checkbox(ag, key=f"ex_{ag}") else 0

        if st.button("Confirm Add"):
            st.session_state.ext.append({"id": ex_id.strip() if ex_id else "", "res": normalize_grade(ex_res), "ph": new_ph})
            st.success("Added. Re-run analysis.")

    if st.session_state.ext:
        st.dataframe(pd.DataFrame(st.session_state.ext)[["id","res"]], use_container_width=True, hide_index=True)

# ============================================================
# 19) MAIN ROUTER
# ============================================================

with st.sidebar:
    st.markdown("### H-AXIS")
    st.caption("Secure • Role-based • Multi-hospital")
    if is_logged_in():
        st.write(f"**Role:** {st.session_state.role.upper()}")
        st.write(f"**Hospital:** {st.session_state.hospital_code}")
    st.write("---")

if not is_logged_in():
    ui_auth()
else:
    nav = sidebar_nav()

    if nav == "Admin/Supervisor Console":
        ui_admin_supervisor_panel()
    elif nav == "Supervisor Panel Setup":
        ui_supervisor_panel()
    else:
        ui_workstation()
