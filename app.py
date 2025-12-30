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

IGNORED_AGS = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"]
INSIGNIFICANT_AGS = ["Lea", "Lua", "Leb", "P1"]
GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]

ENZYME_SENSITIVE = ["Fya","Fyb","M","N","S"]  # s removed as requested

# --------------------------------------------------------------------------
# 3. STATE (tables are p11/p3 — DO NOT TOUCH with widget keys)
# --------------------------------------------------------------------------
default_p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
default_p3  = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])

if 'p11' not in st.session_state or not isinstance(st.session_state.get("p11"), pd.DataFrame):
    st.session_state.p11 = load_csv_if_exists("data/p11.csv", default_p11)

if 'p3' not in st.session_state or not isinstance(st.session_state.get("p3"), pd.DataFrame):
    st.session_state.p3 = load_csv_if_exists("data/p3.csv", default_p3)

default_lots = {"lot_p": "", "lot_s": ""}
lots_obj = load_json_if_exists("data/lots.json", default_lots)

if 'lot_p' not in st.session_state:
    st.session_state.lot_p = lots_obj.get("lot_p", "")
if 'lot_s' not in st.session_state:
    st.session_state.lot_s = lots_obj.get("lot_s", "")

if 'dat_mode' not in st.session_state: st.session_state.dat_mode = False
if 'ext' not in st.session_state: st.session_state.ext = []
if 'last_run' not in st.session_state: st.session_state.last_run = None

# --------------------------------------------------------------------------
# 4. LOGIC ENGINE (Rule-out -> Resolve -> Confirm)
# --------------------------------------------------------------------------
def normalize_grade(val):
    s = str(val).lower().strip()
    return 0 if s in ["0", "neg", "negative"] else 1

def grade_to_int(val):
    s = str(val).strip().lower()
    if "hemo" in s:
        return 4
    if s.startswith("+"):
        try:
            return int(s.replace("+",""))
        except:
            return None
    if s in ["0", "neg", "negative"]:
        return 0
    return None

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
                v = 1 if any(x in str(p).lower() for x in ['+', '1', 'pos', 'w']) else 0
                vals.append(v)
            if len(vals) > 26: vals=vals[-26:]
            while len(vals) < 26: vals.append(0)
            d = {"ID": f"C{c+1}" if limit==11 else f"Scn"}
            for i, ag in enumerate(AGS): d[ag] = vals[i]
            data.append(d)
            c+=1
        return pd.DataFrame(data), f"Updated {c} rows."
    except Exception as e:
        return None, str(e)

def is_homozygous(cell_row, ag):
    if ag in DOSAGE:
        pair = PAIRS.get(ag, None)
        if pair is None:
            return True
        return (cell_row.get(ag,0)==1 and cell_row.get(pair,0)==0)
    else:
        return (cell_row.get(ag,0)==1)

def compute_ruled_out(in_p, in_s, extra_cells):
    ruled_out = set()

    # Panel negatives
    for i in range(1, 12):
        if normalize_grade(in_p[i]) == 0:
            ph = st.session_state.p11.iloc[i-1]
            for ag in AGS:
                if ph.get(ag,0)==1 and is_homozygous(ph, ag):
                    ruled_out.add(ag)

    # Screen negatives
    smap={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        if normalize_grade(in_s[k]) == 0:
            ph = st.session_state.p3.iloc[smap[k]]
            for ag in AGS:
                if ag not in ruled_out and ph.get(ag,0)==1 and is_homozygous(ph, ag):
                    ruled_out.add(ag)

    # Extra negatives
    for ex in extra_cells:
        if normalize_grade(ex['res']) == 0:
            for ag in AGS:
                if ex['ph'].get(ag,0)==1:
                    ruled_out.add(ag)

    return ruled_out

def build_cell_views(in_p, in_s, extra_cells):
    cells = []
    for i in range(1, 12):
        cells.append({"src":"P","idx":i,"rxn": normalize_grade(in_p[i]),"grade_txt": in_p[i],"row": st.session_state.p11.iloc[i-1]})
    si={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        cells.append({"src":"S","idx":k,"rxn": normalize_grade(in_s[k]),"grade_txt": in_s[k],"row": st.session_state.p3.iloc[si[k]]})
    for n, ex in enumerate(extra_cells, start=1):
        cells.append({"src":"X","idx":n,"rxn": normalize_grade(ex['res']),"grade_txt": ex.get("res_txt",""),"row": ex["ph"]})
    return cells

def fit_score_for_ag(ag, cells):
    mismatch_pos = 0
    mismatch_neg = 0
    support_pos = 0
    support_neg = 0

    for c in cells:
        rxn = c["rxn"]
        row = c["row"]
        has_ag = row.get(ag,0)==1

        if rxn == 1:
            if has_ag:
                support_pos += 1
            else:
                mismatch_pos += 1
        else:
            if not has_ag:
                support_neg += 1
            else:
                if is_homozygous(row if isinstance(row, dict) else row, ag):
                    mismatch_neg += 1

    return mismatch_pos, mismatch_neg, support_pos, support_neg

def resolve_candidates(in_p, in_s, extra_cells):
    ruled_out = compute_ruled_out(in_p, in_s, extra_cells)
    remaining = [x for x in AGS if x not in ruled_out and x not in IGNORED_AGS]

    cells = build_cell_views(in_p, in_s, extra_cells)
    reactive_count = sum([c["rxn"] for c in cells])

    scored = []
    for ag in remaining:
        mm_pos, mm_neg, sup_pos, sup_neg = fit_score_for_ag(ag, cells)
        scored.append({"ag": ag,"mm_pos": mm_pos,"mm_neg": mm_neg,"sup_pos": sup_pos,"sup_neg": sup_neg})

    # Conservative "Resolved" gate to prevent Xga/Lua noise
    resolved = []
    not_excluded = []
    for s in scored:
        if s["sup_pos"] >= 2 and s["mm_pos"] <= 1 and s["mm_neg"] <= 1:
            resolved.append(s)
        else:
            not_excluded.append(s)

    resolved = sorted(resolved, key=lambda x: (x["mm_pos"], x["mm_neg"], -x["sup_pos"]))
    not_excluded = sorted(not_excluded, key=lambda x: (x["mm_pos"], x["mm_neg"], -x["sup_pos"]))

    notes = []
    g_indices = [1,2,3,4,8]
    is_G_pattern = True
    for idx in g_indices:
        if normalize_grade(in_p[idx]) == 0:
            is_G_pattern = False
            break

    resolved_ags = [x["ag"] for x in resolved]
    if "D" in resolved_ags and is_G_pattern:
        notes.append("anti_G_suspect")
    if "c" in resolved_ags:
        notes.append("anti-c_risk")

    return resolved, not_excluded, notes, reactive_count

def check_rule_3(cand, in_p, in_s, extras):
    p, n = 0, 0
    for i in range(1, 12):
        s=normalize_grade(in_p[i]); h=st.session_state.p11.iloc[i-1].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    si={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        s=normalize_grade(in_s[k]); h=st.session_state.p3.iloc[si[k]].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    for c in extras:
        s=normalize_grade(c['res']); h=c['ph'].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    ok_full = (p>=3 and n>=3)
    ok_mod  = (p>=2 and n>=3)
    return ok_full, ok_mod, p, n

def strength_caution(panel_grades, screen_grades):
    vals = []
    for v in panel_grades.values():
        gi = grade_to_int(v)
        if gi is not None and gi>0:
            vals.append(gi)
    for v in screen_grades.values():
        gi = grade_to_int(v)
        if gi is not None and gi>0:
            vals.append(gi)
    if len(vals) < 2:
        return None
    if (max(vals) - min(vals)) >= 2:
        return "⚠️ Strength variation ≥2 grades. This may reflect dosage effect, mixed antibodies, or cell variability. Interpret cautiously."
    return None

def find_matching_cells_in_inventory(target_ag, conflicts):
    found_list = []
    for i in range(11):
        cell = st.session_state.p11.iloc[i]
        if cell.get(target_ag,0)==1:
            clean = True
            for bad in conflicts:
                if cell.get(bad,0)==1:
                    clean = False
                    break
            if clean:
                found_list.append(f"Panel #{i+1}")
    sc_lbls = ["I","II","III"]
    for i in range(3):
        cell = st.session_state.p3.iloc[i]
        if cell.get(target_ag,0)==1:
            clean = True
            for bad in conflicts:
                if cell.get(bad,0)==1:
                    clean = False
                    break
            if clean:
                found_list.append(f"Screen {sc_lbls[i]}")
    return found_list

# --------------------------------------------------------------------------
# 5. UI
# --------------------------------------------------------------------------
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Menu", ["Workstation", "Supervisor"])
    if st.button("RESET DATA"):
        st.session_state.ext=[]; st.session_state.dat_mode=False
        st.session_state.last_run=None
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
    nm=c1.text_input("Name")
    mr=c2.text_input("MRN")
    tc=c3.text_input("Tech")
    dt=c4.date_input("Date")

    with st.form("main"):
        st.write("### Reaction Entry")
        L, R = st.columns([1, 2.5])

        with L:
            st.write("Controls")
            ac_res = st.radio("Auto Control (AC)", ["Negative", "Positive"], key="rx_ac")
            st.write("Screening")
            s1=st.selectbox("Scn I", GRADES, key="rx_s1")
            s2=st.selectbox("Scn II", GRADES, key="rx_s2")
            s3=st.selectbox("Scn III", GRADES, key="rx_s3")

        with R:
            st.write("Panel Reactions")
            g1,g2=st.columns(2)
            with g1:
                p1=st.selectbox("1",GRADES,key="rx_p1")
                p2=st.selectbox("2",GRADES,key="rx_p2")
                p3=st.selectbox("3",GRADES,key="rx_p3")
                p4=st.selectbox("4",GRADES,key="rx_p4")
                p5=st.selectbox("5",GRADES,key="rx_p5")
                p6=st.selectbox("6",GRADES,key="rx_p6")
            with g2:
                p7=st.selectbox("7",GRADES,key="rx_p7")
                p8=st.selectbox("8",GRADES,key="rx_p8")
                p9=st.selectbox("9",GRADES,key="rx_p9")
                p10=st.selectbox("10",GRADES,key="rx_p10")
                p11=st.selectbox("11",GRADES,key="rx_p11")

        run = st.form_submit_button("🚀 Run Analysis")

    if run:
        if not st.session_state.lot_p or not st.session_state.lot_s:
            st.error("⛔ Action Blocked: Lots not configured by Supervisor.")
        else:
            if ac_res == "Positive":
                st.session_state.dat_mode = True
                st.session_state.last_run = None
            else:
                st.session_state.dat_mode = False
                i_p = {1:p1,2:p2,3:p3,4:p4,5:p5,6:p6,7:p7,8:p8,9:p9,10:p10,11:p11}
                i_s = {"I":s1,"II":s2,"III":s3}
                resolved, not_exc, notes, total_reactive = resolve_candidates(i_p, i_s, st.session_state.ext)
                st.session_state.last_run = {"i_p": i_p, "i_s": i_s, "resolved": resolved, "not_exc": not_exc, "notes": notes, "total_reactive": total_reactive}

    # DISPLAY RESULTS
    if st.session_state.last_run and not st.session_state.dat_mode:
        data = st.session_state.last_run
        i_p = data["i_p"]; i_s=data["i_s"]
        resolved = data["resolved"]; not_exc=data["not_exc"]; notes=data["notes"]; total_reactive=data["total_reactive"]

        caution = strength_caution(i_p, i_s)
        if caution:
            st.warning(caution)

        st.subheader("Conclusion (Step 1: Rule-out / Rule-in)")

        if total_reactive >= 11:
            st.markdown("""<div class='clinical-alert'>⚠️ <b>High Incidence Antigen suspected.</b><br>Pan-reactivity with Neg AC.<br>Action: Search compatible donor among first-degree relatives / Reference Lab.</div>""", unsafe_allow_html=True)

        resolved_ags = [x["ag"] for x in resolved]
        notexc_ags   = [x["ag"] for x in not_exc]

        if "anti_G_suspect" in notes:
            st.warning("⚠️ **Anti-G possibility**: Pattern suggests Anti-G (or Anti-D + Anti-C). Recommend adsorption/elution differentiation if clinically required.")

        if "anti-c_risk" in notes:
            st.markdown("""<div class='clinical-alert'>🛑 <b>Anti-c likely:</b> Consider providing R1R1 (E- / c-) units to reduce risk of future Anti-E.</div>""", unsafe_allow_html=True)

        if resolved_ags:
            sigs = [x for x in resolved_ags if x not in INSIGNIFICANT_AGS]
            others = [x for x in resolved_ags if x in INSIGNIFICANT_AGS]
            if sigs:
                st.success(f"✅ **Resolved (Likely Identified):** Anti-{', Anti-'.join(sigs)}")
            if others:
                st.info(f"ℹ️ **Resolved (Cold/Usually insignificant):** Anti-{', Anti-'.join(others)}")
        else:
            st.error("No resolved specificity from current data. Proceed with Selected Cells / Enhancement as needed.")

        if notexc_ags:
            st.markdown("**⚠️ Not excluded yet (Needs more work — DO NOT confirm now):**")
            show_list = [a for a in notexc_ags if a not in INSIGNIFICANT_AGS]
            show_list2 = [a for a in notexc_ags if a in INSIGNIFICANT_AGS]
            if show_list:
                st.write("- Clinically significant possibilities:", ", ".join(show_list))
            if show_list2:
                st.write("- Cold/insignificant possibilities:", ", ".join(show_list2))

        sig_resolved = [a for a in resolved_ags if a not in INSIGNIFICANT_AGS]
        if len(sig_resolved) > 1:
            st.write("---")
            st.markdown("### 🧪 Separation Strategy (Selected Cells — from inventory if possible)")
            for t in sig_resolved:
                conf = [x for x in sig_resolved if x!=t]
                found = find_matching_cells_in_inventory(t, conf)
                s_txt = f"<span class='cell-hint'>{', '.join(found)}</span>" if found else "<span style='color:red'>Search External / Different lot</span>"
                st.write(f"- To confirm **Anti-{t}**: Need cell **{t}+** and **{' / '.join([c+'−' for c in conf])}**  {s_txt}")
                if any(x in ENZYME_SENSITIVE for x in [t]+conf):
                    st.caption("Enzyme note: If interference involves **M/N/S/Fya/Fyb**, consider enzyme-treated cells when appropriate to help resolve masking.")

        st.write("---")
        st.subheader("Confirmation (Rule of Three) — Resolved only")

        if not resolved_ags:
            st.info("No resolved antibody yet → do NOT apply Rule of Three. Add selected cells / repeat with different lot as needed.")
        else:
            valid_all = True
            for ab in resolved_ags:
                ok_full, ok_mod, p, n = check_rule_3(ab, i_p, i_s, st.session_state.ext)
                if ok_full:
                    st.write(f"✅ **Anti-{ab}:** Full Rule met (3+ / 3−)  (P:{p} / N:{n})")
                elif ok_mod:
                    st.write(f"✅ **Anti-{ab}:** Modified Rule met (2+ / 3−)  (P:{p} / N:{n})")
                else:
                    st.write(f"⚠️ **Anti-{ab}:** Not confirmed yet  (P:{p} / N:{n})")
                    valid_all = False

            if valid_all:
                if st.button("Generate Official Report"):
                    sigs = [x for x in resolved_ags if x not in INSIGNIFICANT_AGS]
                    others = [x for x in resolved_ags if x in INSIGNIFICANT_AGS]
                    final_txt = ("Anti-" + ", Anti-".join(sigs)) if sigs else ("Anti-" + ", Anti-".join(others))
                    rpt=f"""<div class='print-only'><center><h2>Maternity & Children Hospital - Tabuk</h2><h3>Serology Report</h3></center><div class='result-sheet'><b>Pt:</b> {nm} ({mr})<br><b>Tech:</b> {tc} | <b>Lot:</b> {st.session_state.lot_p}<hr><b>Resolved Result:</b> {final_txt}<br><b>Validation:</b> Rule of Three satisfied (Full/Modified).<br><br><b>Consultant Verified:</b> _____________</div><div class='print-footer'>Dr. Haitham Ismail | Consultant</div></div><script>window.print()</script>"""
                    st.markdown(rpt, unsafe_allow_html=True)
            else:
                st.warning("⚠️ Resolved antibody exists but not fully confirmed yet. Add selected cells / additional evidence.")

    # DAT WORKUP
    if st.session_state.dat_mode:
        st.write("---")
        st.subheader("🧪 Monospecific DAT Workup")

        c_d1, c_d2, c_d3 = st.columns(3)
        igg = c_d1.selectbox("IgG", ["Negative","Positive"], key="rx_dat_igg")
        c3d = c_d2.selectbox("C3d", ["Negative","Positive"], key="rx_dat_c3d")
        ctl = c_d3.selectbox("Control", ["Negative","Positive"], key="rx_dat_ctl")

        st.markdown("**Interpretation:**")
        if ctl == "Positive":
            st.error("Invalid. Control Positive.")
        else:
            if igg=="Positive":
                st.warning("👉 **WAIHA** (Warm Autoimmune Hemolytic Anemia) likely (IgG ± C3d).")
                st.write("- Refer to Blood Bank Physician.")
                st.write("- Consider Elution / Adsorption as applicable.")
                st.markdown("<div class='clinical-waiha'><b>⚠️ Critical Note:</b> If recently transfused, consider <b>Delayed Hemolytic Transfusion Reaction (DHTR)</b>. Elution may be required.</div>", unsafe_allow_html=True)
            elif c3d=="Positive" and igg=="Negative":
                st.info("👉 **CAS** (Cold Agglutinin Syndrome) likely (C3d only).")
                st.write("- Use Pre-warm Technique.")
                st.write("- Consider cold workup / physician review.")

    # EXTRA SELECTED CELLS
    if not st.session_state.dat_mode:
        with st.expander("➕ Add Selected Cell (From Library)"):
            id_x=st.text_input("ID", key="rx_ex_id")
            rs_x=st.selectbox("R",GRADES,key="rx_ex_res")
            ag_col=st.columns(6)
            new_p={}
            for i,ag in enumerate(AGS):
                new_p[ag] = 1 if ag_col[i%6].checkbox(ag, key=f"rx_ex_{ag}") else 0
            if st.button("Confirm Add", key="rx_ex_add"):
                st.session_state.ext.append({"res":normalize_grade(rs_x),"res_txt":rs_x,"ph":new_p})
                st.success("Added! Re-run Analysis.")

    if st.session_state.ext:
        st.table(pd.DataFrame(st.session_state.ext)[['res_txt']])
