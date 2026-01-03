import os
import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta, timezone
import json
import base64
import requests
from pathlib import Path
from itertools import combinations
import secrets

from supabase import create_client

# =============================================================================
# 0) SUPABASE AUTH (Login/Signup via Invite + staff_id)
# =============================================================================
APP_TZ = timezone(timedelta(hours=3))  # +0300
EMAIL_DOMAIN = "bb.local"             # internal email format: staff_id@bb.local

SUPABASE_URL = st.secrets.get("SUPABASE_URL", "").strip()
SUPABASE_ANON_KEY = st.secrets.get("SUPABASE_ANON_KEY", "").strip()
SUPABASE_SERVICE_ROLE_KEY = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

if not SUPABASE_URL or not SUPABASE_ANON_KEY or not SUPABASE_SERVICE_ROLE_KEY:
    st.error("Missing Supabase secrets: SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY")
    st.stop()

sb_public = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)              # user login
sb_admin  = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)      # server privileged

def staff_to_email(staff_id: str) -> str:
    staff_id = str(staff_id).strip()
    return f"{staff_id}@{EMAIL_DOMAIN}"

def now_ts() -> str:
    return datetime.now(APP_TZ).isoformat()

def load_profile(user_id: str):
    res = sb_admin.table("users_profile").select("*").eq("user_id", user_id).limit(1).execute()
    data = res.data or []
    return data[0] if data else None

def ensure_auth_state():
    if "session" not in st.session_state:
        st.session_state.session = None
    if "user" not in st.session_state:
        st.session_state.user = None
    if "profile" not in st.session_state:
        st.session_state.profile = None

ensure_auth_state()

def do_login(staff_id: str, password: str):
    email = staff_to_email(staff_id)
    auth_resp = sb_public.auth.sign_in_with_password({"email": email, "password": password})
    st.session_state.session = auth_resp.session
    st.session_state.user = auth_resp.user
    st.session_state.profile = load_profile(auth_resp.user.id)

def do_logout():
    try:
        sb_public.auth.sign_out()
    except Exception:
        pass
    st.session_state.session = None
    st.session_state.user = None
    st.session_state.profile = None

def gen_invite_code(length_bytes: int = 6) -> str:
    return secrets.token_urlsafe(length_bytes).replace("-", "").replace("_", "").upper()[:10]

def create_invite(created_by_user_id: str, hospital_code: str, role: str, staff_id: str | None, expires_days: int = 14):
    code = gen_invite_code()
    expires_at = (datetime.now(APP_TZ) + timedelta(days=expires_days)).isoformat()
    payload = {
        "code": code,
        "hospital_code": hospital_code,
        "role": role,
        "created_by": created_by_user_id,
        "created_at": now_ts(),
        "is_active": True,
        "expires_at": expires_at,
    }
    if staff_id:
        payload["staff_id"] = staff_id.strip()
    sb_admin.table("invites").insert(payload).execute()
    return code, expires_at

def redeem_invite(invite_code: str, staff_id: str, password: str):
    invite_code = invite_code.strip().upper()
    staff_id = staff_id.strip()

    inv = sb_admin.table("invites").select("*").eq("code", invite_code).limit(1).execute().data
    if not inv:
        return False, "Invite code غير صحيح."
    inv = inv[0]

    if not inv.get("is_active", False):
        return False, "Invite غير نشط."
    if inv.get("used_at") is not None or inv.get("used_by") is not None:
        return False, "Invite تم استخدامه بالفعل."

    # expiry
    expires_at = inv.get("expires_at")
    if expires_at:
        try:
            exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > exp_dt.astimezone(timezone.utc):
                return False, "Invite منتهي الصلاحية."
        except Exception:
            pass

    # bound staff id
    bound_staff = inv.get("staff_id")
    if bound_staff and bound_staff.strip() != staff_id:
        return False, "هذا الـ Invite مخصص لرقم وظيفي مختلف."

    # staff_id uniqueness in profile
    exists = sb_admin.table("users_profile").select("id").eq("staff_id", staff_id).limit(1).execute().data
    if exists:
        return False, "هذا الـ staff_id مسجل بالفعل."

    email = staff_to_email(staff_id)

    try:
        created = sb_admin.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True
        })
        user_id = created.user.id
    except Exception as e:
        return False, f"Failed to create auth user: {e}"

    try:
        sb_admin.table("users_profile").insert({
            "user_id": user_id,
            "staff_id": staff_id,
            "hospital_code": inv["hospital_code"],
            "role": inv["role"],
            "created_at": now_ts(),
        }).execute()
    except Exception as e:
        try:
            sb_admin.auth.admin.delete_user(user_id)
        except Exception:
            pass
        return False, f"Profile create failed: {e}"

    sb_admin.table("invites").update({
        "used_at": now_ts(),
        "used_by": user_id,
        "is_active": False
    }).eq("id", inv["id"]).execute()

    return True, "تم إنشاء الحساب بنجاح. تقدر تعمل Login الآن."

def require_login():
    if not st.session_state.user:
        st.info("Login من الشمال أو اعمل Signup باستخدام Invite code.")
        st.stop()

def role_is(*roles):
    prof = st.session_state.profile or {}
    return prof.get("role") in roles

# =============================================================================
# 0.1) GitHub Save Engine (uses Streamlit Secrets)
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
# 1) PAGE SETUP & CSS
# =============================================================================
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
    div[data-testid="stDataEditor"] table { width: 100% !important; }
</style>
""", unsafe_allow_html=True)

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

GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]
YN3 = ["Not Done", "Negative", "Positive"]

# =============================================================================
# 3) STATE
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
if "show_dat" not in st.session_state:
    st.session_state.show_dat = False

if "confirmed_lock" not in st.session_state:
    st.session_state.confirmed_lock = set()

# =============================================================================
# 4) HELPERS / ENGINE (كما هو)
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

# =============================================================================
# 4.5) SUPERVISOR: Copy/Paste Parser
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
# 5) SIDEBAR (Auth + Menu)
# =============================================================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    st.markdown("### Account")

    if st.session_state.user:
        prof = st.session_state.profile or {}
        st.success(f"Logged in: {prof.get('staff_id','?')}")
        st.write(f"Role: **{prof.get('role','?')}**")
        st.write(f"Hospital: **{prof.get('hospital_code','?')}**")
        if st.button("Logout"):
            do_logout()
            st.rerun()
    else:
        st.caption("Login with staff_id + password")
        staff_id_in = st.text_input("staff_id", key="login_staff")
        password_in = st.text_input("Password", type="password", key="login_pass")
        if st.button("Login"):
            try:
                do_login(staff_id_in, password_in)
                st.success("Login successful")
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")

        st.divider()
        st.caption("Signup with Invite")
        invite_code = st.text_input("Invite code", key="signup_code")
        staff_id_new = st.text_input("staff_id (رقم وظيفي)", key="signup_staff")
        pass_new = st.text_input("New password", type="password", key="signup_pass")
        pass_new2 = st.text_input("Confirm password", type="password", key="signup_pass2")
        if st.button("Create account"):
            if pass_new != pass_new2:
                st.error("Passwords do not match.")
            elif len(pass_new) < 8:
                st.error("Password must be at least 8 characters.")
            else:
                ok, msg = redeem_invite(invite_code, staff_id_new, pass_new)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

    st.divider()
    nav = st.radio("Menu", ["Workstation", "Supervisor"], key="nav_menu")

    if st.button("RESET DATA", key="btn_reset"):
        st.session_state.ext = []
        st.session_state.analysis_ready = False
        st.session_state.analysis_payload = None
        st.session_state.show_dat = False
        st.session_state.confirmed_lock = set()
        st.rerun()

# Require login for app usage
require_login()

# Refresh profile if missing
if not st.session_state.profile:
    st.session_state.profile = load_profile(st.session_state.user.id)

profile = st.session_state.profile or {}
if not profile:
    st.error("No profile row found for this user in users_profile.")
    st.stop()

# =============================================================================
# 6) SUPERVISOR (Role-based, no password)
# =============================================================================
if nav == "Supervisor":
    if not role_is("admin", "supervisor"):
        st.error("⛔ Access denied. Supervisor page is for Admin/Supervisor only.")
        st.stop()

    st.title("Config")

    # -------- Invites section (NEW) --------
    st.subheader("0) User Invitations (Supabase)")
    st.markdown("<div class='clinical-info'>Admin can invite supervisors/staff. Supervisor can invite staff only (same hospital).</div>", unsafe_allow_html=True)

    with st.expander("Create Invite", expanded=True):
        my_role = profile.get("role")
        my_hosp = profile.get("hospital_code")

        if my_role == "admin":
            hospital_code = st.text_input("hospital_code", value=my_hosp or "MCHTABUK")
            role = st.selectbox("role", ["supervisor", "staff"])
        else:
            hospital_code = my_hosp
            role = "staff"
            st.write(f"Hospital locked: **{hospital_code}**")
            st.write("Role locked: **staff**")

        bind_staff = st.checkbox("Bind invite to a specific staff_id (optional)")
        bind_val = None
        if bind_staff:
            bind_val = st.text_input("Bind staff_id")

        expires_days = st.number_input("Expires in (days)", min_value=1, max_value=90, value=14)

        if st.button("Generate Invite Code"):
            try:
                code, exp = create_invite(
                    created_by_user_id=st.session_state.user.id,
                    hospital_code=hospital_code.strip(),
                    role=role,
                    staff_id=bind_val,
                    expires_days=int(expires_days)
                )
                st.success(f"Invite created: **{code}** (expires: {exp})")
            except Exception as e:
                st.error(f"Invite create failed: {e}")

    with st.expander("My Invites (audit)", expanded=False):
        try:
            inv_rows = sb_admin.table("invites") \
                .select("code,hospital_code,role,staff_id,is_active,created_at,expires_at,used_at,used_by") \
                .eq("created_by", st.session_state.user.id) \
                .order("created_at", desc=True) \
                .limit(100).execute().data
            if inv_rows:
                st.dataframe(inv_rows, use_container_width=True)
            else:
                st.info("No invites created yet.")
        except Exception as e:
            st.error(f"Failed to load invites: {e}")

    st.write("---")

    # -------- Existing Supervisor features (your original) --------
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
        ⚠️ Tip: لو الـPDF فيه Labels قبل الداتا، paste غالبًا هيبقى فيه أعمدة زيادة في البداية.
        البرنامج تلقائيًا بياخد <b>آخر 26 عمود</b> ويهمل أي حاجة قبلهم.
        </div>
        """, unsafe_allow_html=True)

    with tab_edit:
        st.markdown("### Manual Edit (Supervisor only) — Safe mode")
        st.markdown("""
        <div class='clinical-info'>
        ✅ Safe rules applied: <b>ID locked</b> + <b>No add/remove rows</b> + <b>Only 0/1 via checkboxes</b>.<br>
        استخدم ده فقط للتصحيح اليدوي بعد الـCopy/Paste.
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
    st.warning("قبل النشر: راجع اللوت + راجع الجداول بسرعة (Panel/Screen).")

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
# 7) WORKSTATION (unchanged)
# =============================================================================
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

    # -------------------- The rest of your workstation logic stays the same --------------------
    # IMPORTANT: I am keeping your existing logic; below is unchanged from your code.
    if st.session_state.analysis_ready and st.session_state.analysis_payload:
        in_p = st.session_state.analysis_payload["in_p"]
        in_s = st.session_state.analysis_payload["in_s"]
        ac_res = st.session_state.analysis_payload["ac_res"]
        recent_tx = st.session_state.analysis_payload["recent_tx"]

        ac_negative = (ac_res == "Negative")
        all_rx = all_reactive_pattern(in_p, in_s)

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

        if all_rx:
            pass
        else:
            cells = get_cells(in_p, in_s, st.session_state.ext)
            ruled = rule_out(in_p, in_s, st.session_state.ext)
            candidates = [a for a in AGS if a not in ruled and a not in IGNORED_AGS]

            st.subheader("Conclusion (Step 1: Rule-out / Rule-in)")

            if st.session_state.confirmed_lock:
                confirmed_locked = sorted(list(st.session_state.confirmed_lock))
                st.success("Resolved (LOCKED confirmed): " + ", ".join([f"Anti-{a}" for a in confirmed_locked]))

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
                st.subheader("Confirmation (Rule of Three) — Confirmed singles")

                st.markdown(patient_antigen_negative_reminder(confirmed_locked, strong=True), unsafe_allow_html=True)

                d_present = ("D" in st.session_state.confirmed_lock)
                c_present = ("C" in st.session_state.confirmed_lock)
                if d_present and c_present:
                    st.markdown(anti_g_alert_html(strong=True), unsafe_allow_html=True)

                conflicts = confirmed_conflict_map(st.session_state.confirmed_lock, cells)
                if conflicts:
                    st.markdown("""
                    <div class='clinical-alert'>
                    ⚠️ <b>Data conflict alert</b><br>
                    A confirmed antibody has reactive cells that are antigen-negative.
                    <b>Do NOT delete the confirmed antibody automatically</b>; investigate multiple antibodies and/or phenotype entry error.
                    </div>
                    """, unsafe_allow_html=True)
                    for ab, labs in conflicts.items():
                        st.write(f"- **Anti-{ab} confirmed**, but these reactive cell(s) are **{ab}-negative**: " + ", ".join(labs))

                st.write("---")
                targets_needing_selected = list(dict.fromkeys(
                    list(supported_bg.keys()) + other_sig_final
                ))

                if targets_needing_selected:
                    st.markdown("### 🧪 Selected Cells (Only if needed to resolve interference / exclude / confirm)")
                    for a in targets_needing_selected:
                        active_set_now = set(list(st.session_state.confirmed_lock) + other_sig_final + list(supported_bg.keys()))
                        st.warning(f"Anti-{a}: need discriminating cells to exclude/confirm (especially after locking confirmed antibodies).")

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
                    st.success("No Selected Cells needed: confirmed antibody is locked AND no clinically significant background remains unexcluded.")

            else:
                best = find_best_combo(candidates, cells, max_size=3)

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
                    resolved_raw = [a for a in best if sep_map.get(a, False)]
                    needs_work = [a for a in best if not sep_map.get(a, False)]

                    resolved_sig = [a for a in resolved_raw if a not in INSIGNIFICANT_AGS]
                    resolved_cold = [a for a in resolved_raw if a in INSIGNIFICANT_AGS]

                    if resolved_sig:
                        st.success("Resolved (pattern explained & separable): " + ", ".join([f"Anti-{a}" for a in resolved_sig]))
                    if needs_work:
                        st.warning("Pattern suggests these, but NOT separable yet (DO NOT confirm): " +
                                   ", ".join([f"Anti-{a}" for a in needs_work]))
                    if resolved_cold and not resolved_sig:
                        st.info("Cold/Insignificant (separable, but do NOT auto-confirm): " + ", ".join([f"Anti-{a}" for a in resolved_cold]))

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
                    st.subheader("Confirmation (Rule of Three) — Confirmed singles")

                    confirmed = set()
                    if not resolved_sig:
                        st.info("No clinically significant antibody is separable yet → DO NOT apply Rule of Three. Add discriminating selected cells.")
                    else:
                        for a in resolved_sig:
                            full, mod, p_cnt, n_cnt = check_rule_three_only_on_discriminating(a, best, cells)
                            if full:
                                st.write(f"✅ **Anti-{a} CONFIRMED**: Full Rule (3+3) met on discriminating cells (P:{p_cnt} / N:{n_cnt})")
                                confirmed.add(a)
                            elif mod:
                                st.write(f"✅ **Anti-{a} CONFIRMED**: Modified Rule (2+3) met on discriminating cells (P:{p_cnt} / N:{n_cnt})")
                                confirmed.add(a)
                            else:
                                st.write(f"⚠️ **Anti-{a} NOT confirmed yet**: need more discriminating cells (P:{p_cnt} / N:{n_cnt})")

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

                    st.write("---")

                    targets_needing_selected = list(dict.fromkeys(
                        needs_work +
                        list(supported_bg.keys()) +
                        other_sig_final
                    ))

                    if targets_needing_selected:
                        st.markdown("### 🧪 Selected Cells (Only if needed to resolve interference / exclude / confirm)")
                        for a in targets_needing_selected:
                            active_set_now = set(resolved_sig + needs_work + other_sig_final + list(supported_bg.keys()))
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
