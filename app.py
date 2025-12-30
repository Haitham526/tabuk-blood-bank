import streamlit as st
import pandas as pd
from datetime import date, datetime
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

# --------------------------------------------------------------------------
# 0.1) Local IO Helpers
# --------------------------------------------------------------------------
def ensure_data_dir():
    Path("data").mkdir(parents=True, exist_ok=True)

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

def write_text(path: str, text: str):
    ensure_data_dir()
    Path(path).write_text(text, encoding="utf-8")

def read_text(path: str, default: str = "") -> str:
    p = Path(path)
    if p.exists():
        return p.read_text(encoding="utf-8")
    return default

def _coerce_01(df: pd.DataFrame, cols: list) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0).astype(int).clip(0, 1)
    return out

def _validate_panel_df(df: pd.DataFrame, expected_rows: int, ags: list) -> (bool, str):
    missing = [c for c in (["ID"] + ags) if c not in df.columns]
    if missing:
        return False, f"Missing columns: {', '.join(missing)}"
    if len(df) != expected_rows:
        return False, f"Expected {expected_rows} rows, got {len(df)}"
    return True, "OK"

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
YN3 = ["Not Done", "Negative", "Positive"]

# --------------------------------------------------------------------------
# 3) STATE + PANEL LIBRARY (Sheets)
# --------------------------------------------------------------------------
ensure_data_dir()

default_panel11_df = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
default_screen3_df = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])

# Panel library manifest
manifest_path = "data/panels_manifest.json"
default_manifest = {
    "active_key": "ACTIVE",
    "panels": {
        "ACTIVE": {
            "name": "Active Panel (Current)",
            "created": "",
            "p11_path": "data/p11.csv",
            "p3_path": "data/p3.csv",
            "lots_path": "data/lots.json"
        }
    }
}
manifest = load_json_if_exists(manifest_path, default_manifest)

# Ensure base files exist
if not Path("data/p11.csv").exists():
    write_text("data/p11.csv", default_panel11_df.to_csv(index=False))
if not Path("data/p3.csv").exists():
    write_text("data/p3.csv", default_screen3_df.to_csv(index=False))
if not Path("data/lots.json").exists():
    write_text("data/lots.json", json.dumps({"lot_p": "", "lot_s": ""}, ensure_ascii=False, indent=2))

# Load active
active_key = manifest.get("active_key", "ACTIVE")
active_meta = manifest["panels"].get(active_key, manifest["panels"]["ACTIVE"])
p11_path = active_meta.get("p11_path", "data/p11.csv")
p3_path  = active_meta.get("p3_path",  "data/p3.csv")
lots_path = active_meta.get("lots_path", "data/lots.json")

if "panel11_df" not in st.session_state:
    st.session_state.panel11_df = load_csv_if_exists(p11_path, default_panel11_df)
if "screen3_df" not in st.session_state:
    st.session_state.screen3_df = load_csv_if_exists(p3_path, default_screen3_df)

st.session_state.panel11_df = _coerce_01(st.session_state.panel11_df, AGS)
st.session_state.screen3_df = _coerce_01(st.session_state.screen3_df, AGS)

lots_obj = load_json_if_exists(lots_path, {"lot_p": "", "lot_s": ""})
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

# --------------------------------------------------------------------------
# 4) HELPERS / ENGINE (UNCHANGED)
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

def patient_antigen_negative_reminder(antibodies: list) -> str:
    uniq = []
    for a in antibodies:
        if a and a not in uniq and a not in IGNORED_AGS:
            uniq.append(a)
    if not uniq:
        return ""
    bullets = "".join([f"<li>Anti-{ag} → verify patient is <b>{ag}-negative</b> (phenotype/genotype; pre-transfusion sample preferred).</li>" for ag in uniq])
    return f"""
    <div class='clinical-alert'>
      ✅ <b>Final confirmation step (Patient antigen check)</b><br>
      Confirm the patient is <b>ANTIGEN-NEGATIVE</b> for the corresponding antigen(s) to support the antibody identification.
      <ul style="margin-top:6px;">{bullets}</ul>
    </div>
    """

def anti_g_alert_html() -> str:
    return """
    <div class='clinical-alert'>
      ⚠️ <b>Consider Anti-G (D + C pattern)</b><br>
      Anti-G may mimic <b>Anti-D + Anti-C</b>. If clinically relevant (especially pregnancy / RhIG decision),
      do not label as true Anti-D until Anti-G is excluded. Refer per SOP/reference lab.
    </div>
    """

# --------------------------------------------------------------------------
# 5) SIDEBAR
# --------------------------------------------------------------------------
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Menu", ["Workstation", "Supervisor"], key="nav_menu")
    if st.button("RESET DATA", key="btn_reset"):
        st.session_state.ext = []
        st.session_state.analysis_ready = False
        st.session_state.analysis_payload = None
        st.session_state.show_dat = False
        st.rerun()

# --------------------------------------------------------------------------
# 6) SUPERVISOR (with SHEET/Panel Library)
# --------------------------------------------------------------------------
if nav == "Supervisor":
    st.title("Config")

    if st.text_input("Password", type="password", key="sup_pass") == "admin123":

        # --- Panel Library / Sheet selector
        st.subheader("A) Panel Library (Sheets)")

        panel_keys = list(manifest.get("panels", {}).keys())
        labels = []
        for k in panel_keys:
            meta = manifest["panels"][k]
            nm = meta.get("name", k)
            created = meta.get("created", "")
            labels.append(f"{k} — {nm}" + (f" ({created})" if created else ""))

        chosen_label = st.selectbox("Select Panel Sheet", labels, index=panel_keys.index(active_key) if active_key in panel_keys else 0)
        chosen_key = panel_keys[labels.index(chosen_label)]

        cL1, cL2 = st.columns([1.2, 1.8])
        if cL1.button("✅ Set as ACTIVE (Workstations will use it)", use_container_width=True):
            manifest["active_key"] = chosen_key
            write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))
            st.success("Active sheet updated. Reloading…")
            st.session_state.clear()
            st.rerun()

        if cL2.button("🗑️ Delete Sheet (except ACTIVE)", use_container_width=True):
            if chosen_key == "ACTIVE":
                st.error("Cannot delete ACTIVE base sheet.")
            else:
                try:
                    meta = manifest["panels"][chosen_key]
                    for p in [meta.get("p11_path"), meta.get("p3_path"), meta.get("lots_path")]:
                        if p and Path(p).exists():
                            Path(p).unlink()
                    del manifest["panels"][chosen_key]
                    write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))
                    st.success("Sheet deleted.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Delete failed: {e}")

        st.write("---")

        # --- Create new sheet (IMPORT)
        st.subheader("B) Add NEW Sheet (New Monthly Panel)")

        st.info("Upload two CSV files: (1) p11 panel (11 rows) and (2) p3 screening (3 rows). Must include columns: ID + all antigens.")
        new_key = st.text_input("New Sheet Key (e.g., 2026-01 or LOT123)", value="", key="new_sheet_key")
        new_name = st.text_input("Sheet Name (e.g., Jan-2026 Ortho Panel)", value="", key="new_sheet_name")
        new_lot_p = st.text_input("ID Panel Lot#", value="", key="new_lot_p")
        new_lot_s = st.text_input("Screen Panel Lot#", value="", key="new_lot_s")

        up1 = st.file_uploader("Upload p11.csv (11-cell panel)", type=["csv"], key="up_p11")
        up2 = st.file_uploader("Upload p3.csv (3 screening cells)", type=["csv"], key="up_p3")

        if st.button("➕ Create Sheet from Upload", use_container_width=True):
            if not new_key.strip():
                st.error("Please enter New Sheet Key.")
            elif new_key.strip() in manifest["panels"]:
                st.error("This Sheet Key already exists. Choose another.")
            elif not up1 or not up2:
                st.error("Please upload both p11.csv and p3.csv.")
            else:
                try:
                    df_p11 = pd.read_csv(up1)
                    df_p3  = pd.read_csv(up2)
                    df_p11 = _coerce_01(df_p11, AGS)
                    df_p3  = _coerce_01(df_p3, AGS)

                    ok1, msg1 = _validate_panel_df(df_p11, 11, AGS)
                    ok2, msg2 = _validate_panel_df(df_p3, 3, AGS)
                    if not ok1:
                        st.error(f"p11.csv invalid: {msg1}")
                    elif not ok2:
                        st.error(f"p3.csv invalid: {msg2}")
                    else:
                        key = new_key.strip()
                        p11_new = f"data/p11_{key}.csv"
                        p3_new  = f"data/p3_{key}.csv"
                        lots_new = f"data/lots_{key}.json"

                        write_text(p11_new, df_p11.to_csv(index=False))
                        write_text(p3_new, df_p3.to_csv(index=False))
                        write_text(lots_new, json.dumps({"lot_p": new_lot_p.strip(), "lot_s": new_lot_s.strip()}, ensure_ascii=False, indent=2))

                        manifest["panels"][key] = {
                            "name": new_name.strip() if new_name.strip() else key,
                            "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "p11_path": p11_new,
                            "p3_path": p3_new,
                            "lots_path": lots_new
                        }
                        write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))
                        st.success("New sheet created. You can now set it ACTIVE above.")
                except Exception as e:
                    st.error(f"Create failed: {e}")

        st.write("---")

        # --- Edit CURRENT ACTIVE sheet
        st.subheader("C) Edit CURRENT ACTIVE Sheet (Tables)")

        # reload active paths (after set active)
        manifest_live = load_json_if_exists(manifest_path, default_manifest)
        active_key_live = manifest_live.get("active_key", "ACTIVE")
        meta_live = manifest_live["panels"].get(active_key_live, manifest_live["panels"]["ACTIVE"])

        p11_live = meta_live.get("p11_path", "data/p11.csv")
        p3_live  = meta_live.get("p3_path",  "data/p3.csv")
        lots_live = meta_live.get("lots_path", "data/lots.json")

        panel_df = load_csv_if_exists(p11_live, default_panel11_df)
        screen_df = load_csv_if_exists(p3_live, default_screen3_df)
        panel_df = _coerce_01(panel_df, AGS)
        screen_df = _coerce_01(screen_df, AGS)
        lots_live_obj = load_json_if_exists(lots_live, {"lot_p": "", "lot_s": ""})

        c1, c2 = st.columns(2)
        lp = c1.text_input("ID Panel Lot# (ACTIVE)", value=lots_live_obj.get("lot_p",""), key="lot_p_in")
        ls = c2.text_input("Screen Panel Lot# (ACTIVE)", value=lots_live_obj.get("lot_s",""), key="lot_s_in")

        st.markdown("**ID Panel (11 Cells)**")
        panel_editor = st.data_editor(
            panel_df,
            use_container_width=True,
            num_rows="fixed",
            key="panel_editor",
            column_config={
                "ID": st.column_config.TextColumn("ID"),
                **{ag: st.column_config.NumberColumn(ag, min_value=0, max_value=1, step=1) for ag in AGS}
            }
        )

        st.markdown("**Screening Cells (3 Cells)**")
        screen_editor = st.data_editor(
            screen_df,
            use_container_width=True,
            num_rows="fixed",
            key="screen_editor",
            column_config={
                "ID": st.column_config.TextColumn("ID"),
                **{ag: st.column_config.NumberColumn(ag, min_value=0, max_value=1, step=1) for ag in AGS}
            }
        )

        panel_editor = _coerce_01(panel_editor, AGS)
        screen_editor = _coerce_01(screen_editor, AGS)

        b1, b2 = st.columns([1.2, 1.8])

        if b1.button("💾 Save ACTIVE Locally", use_container_width=True):
            ok1, msg1 = _validate_panel_df(panel_editor, 11, AGS)
            ok2, msg2 = _validate_panel_df(screen_editor, 3, AGS)
            if not ok1:
                st.error(f"Panel invalid: {msg1}")
            elif not ok2:
                st.error(f"Screen invalid: {msg2}")
            else:
                write_text(p11_live, panel_editor.to_csv(index=False))
                write_text(p3_live, screen_editor.to_csv(index=False))
                write_text(lots_live, json.dumps({"lot_p": lp.strip(), "lot_s": ls.strip()}, ensure_ascii=False, indent=2))
                st.success("Saved ACTIVE locally.")

        if b2.button("💾 Publish ACTIVE to GitHub (Commit)", use_container_width=True):
            try:
                ok1, msg1 = _validate_panel_df(panel_editor, 11, AGS)
                ok2, msg2 = _validate_panel_df(screen_editor, 3, AGS)
                if not ok1:
                    st.error(f"Panel invalid: {msg1}")
                elif not ok2:
                    st.error(f"Screen invalid: {msg2}")
                else:
                    lots_json = json.dumps({"lot_p": lp.strip(), "lot_s": ls.strip()}, ensure_ascii=False, indent=2)

                    github_upsert_file(p11_live.replace("\\","/"), panel_editor.to_csv(index=False), f"Update panel sheet {active_key_live}")
                    github_upsert_file(p3_live.replace("\\","/"),  screen_editor.to_csv(index=False), f"Update screen sheet {active_key_live}")
                    github_upsert_file(lots_live.replace("\\","/"), lots_json, f"Update lots sheet {active_key_live}")
                    github_upsert_file(manifest_path.replace("\\","/"), json.dumps(manifest_live, ensure_ascii=False, indent=2), "Update panels manifest")
                    st.success("✅ Published ACTIVE + manifest to GitHub successfully.")
            except Exception as e:
                st.error(f"❌ Publish failed: {e}")

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

            if all_rx and ac_negative:
                st.markdown("""
                <div class='clinical-danger'>
                ⚠️ <b>Pan-reactive pattern with NEGATIVE autocontrol</b><br>
                Most consistent with <b>Antibody to High-Incidence Antigen</b> or multiple alloantibodies not separable here.<br>
                <b>STOP</b> routine interpretation → refer to Blood Bank Physician / Reference Lab.
                </div>
                """, unsafe_allow_html=True)

            elif all_rx and (not ac_negative):
                st.markdown("""
                <div class='clinical-danger'>
                ⚠️ <b>Pan-reactive pattern with POSITIVE autocontrol</b><br>
                Requires <b>Monospecific DAT</b> pathway (IgG / C3d / Control) before any alloantibody claims.
                </div>
                """, unsafe_allow_html=True)

            if all_rx:
                st.markdown("""
                <div class='clinical-info'>
                🔎 Routine specificity engine paused in pan-reactive cases.
                </div>
                """, unsafe_allow_html=True)

            else:
                cells = get_cells(in_p, in_s, st.session_state.ext)
                ruled = rule_out(in_p, in_s, st.session_state.ext)
                candidates = [a for a in AGS if a not in ruled and a not in IGNORED_AGS]
                best = find_best_combo(candidates, cells, max_size=3)

                st.subheader("Conclusion (Step 1: Rule-out / Rule-in)")
                if not best:
                    st.error("No resolved specificity from current data. Proceed with Selected Cells / Enhancement.")
                else:
                    sep_map = separability_map(best, cells)
                    resolved = [a for a in best if sep_map.get(a, False)]
                    needs_work = [a for a in best if not sep_map.get(a, False)]

                    if resolved:
                        st.success("Resolved (pattern explained & separable): " + ", ".join([f"Anti-{a}" for a in resolved]))
                    if needs_work:
                        st.warning("Pattern suggests these, but NOT separable yet (DO NOT confirm): " +
                                   ", ".join([f"Anti-{a}" for a in needs_work]))

                    st.write("---")
                    st.subheader("Confirmation (Rule of Three) — Resolved & Separable only")
                    confirmed = []
                    if resolved:
                        for a in resolved:
                            full, mod, p_cnt, n_cnt = check_rule_three_only_on_discriminating(a, best, cells)
                            if full or mod:
                                confirmed.append(a)
                                if full:
                                    st.write(f"✅ **Anti-{a} CONFIRMED**: Full Rule (3+3) met (P:{p_cnt} / N:{n_cnt})")
                                else:
                                    st.write(f"✅ **Anti-{a} CONFIRMED**: Modified Rule (2+3) met (P:{p_cnt} / N:{n_cnt})")
                            else:
                                st.write(f"⚠️ **Anti-{a} NOT confirmed yet**: need more discriminating cells (P:{p_cnt} / N:{n_cnt})")
                    else:
                        st.info("No separable antibody to confirm.")

                    if confirmed:
                        st.markdown(patient_antigen_negative_reminder(confirmed), unsafe_allow_html=True)

                    if ("D" in resolved or "D" in confirmed) and ("C" in resolved or "C" in confirmed):
                        st.markdown(anti_g_alert_html(), unsafe_allow_html=True)

                    st.write("---")
                    targets = list(dict.fromkeys(needs_work))
                    if targets:
                        st.markdown("### 🧪 Selected Cells (Only if needed)")
                        active_set_now = set(resolved + needs_work)
                        for a in targets:
                            st.warning(f"Anti-{a}: need {a}+ cells NEGATIVE for other active suspects.")
                            sugg = suggest_selected_cells(a, list(active_set_now))
                            if sugg:
                                for lab, note in sugg[:12]:
                                    st.write(f"- {lab}  <span class='cell-hint'>{note}</span>", unsafe_allow_html=True)
                            else:
                                st.write("- No suitable discriminating cell → use another lot / external selected cells.")
                        enz = enzyme_hint_if_needed(targets)
                        if enz:
                            st.info("💡 " + enz)
                    else:
                        st.success("No Selected Cells needed based on current data.")

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
