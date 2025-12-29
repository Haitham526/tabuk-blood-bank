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

# --------------------------------------------------------------------------
# 3. STATE (load defaults from local repo files if present)
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
# 4. LOGIC ENGINE
# --------------------------------------------------------------------------
def normalize_grade(val):
    s = str(val).lower().strip()
    return 0 if s in ["0", "neg"] else 1

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

def find_matching_cells_in_inventory(target_ab, conflicts):
    found_list = []
    for i in range(11):
        cell = st.session_state.p11.iloc[i]
        if cell.get(target_ab,0)==1:
            clean = True
            for bad in conflicts:
                if cell.get(bad,0)==1: clean=False; break
            if clean: found_list.append(f"Panel #{i+1}")
    sc_lbls = ["I","II","III"]
    for i in range(3):
        cell = st.session_state.p3.iloc[i]
        if cell.get(target_ab,0)==1:
            clean = True
            for bad in conflicts:
                if cell.get(bad,0)==1: clean=False; break
            if clean: found_list.append(f"Screen {sc_lbls[i]}")
    return found_list

def _is_dosage_blocked(ag: str, ph_row: pd.Series) -> bool:
    """
    Dosage rule: Rh/Duffy/Kidd/MNS cannot be ruled out using heterozygous cells.
    If antigen is present AND paired antigen is also present => heterozygous => blocked.
    """
    if ag in DOSAGE:
        pair = PAIRS.get(ag)
        if pair and ph_row.get(pair,0)==1:
            return True
    return False

def analyze_alloantibodies(in_p, in_s, extra_cells):
    ruled_out = set()
    dosage_blocked = {ag: [] for ag in AGS}  # evidence where rule-out was blocked

    # 1) Panel Exclusion
    for i in range(1, 12):
        if normalize_grade(in_p[i]) == 0:
            ph = st.session_state.p11.iloc[i-1]
            for ag in AGS:
                if ph.get(ag,0)==1:
                    if _is_dosage_blocked(ag, ph):
                        dosage_blocked[ag].append(f"Panel #{i}")
                        continue
                    ruled_out.add(ag)

    # 2) Screen Exclusion
    smap={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        if normalize_grade(in_s[k]) == 0:
            ph = st.session_state.p3.iloc[smap[k]]
            for ag in AGS:
                if ag in ruled_out:
                    continue
                if ph.get(ag,0)==1:
                    if _is_dosage_blocked(ag, ph):
                        dosage_blocked[ag].append(f"Screen {k}")
                        continue
                    ruled_out.add(ag)

    # 3) Extra Exclusion
    for ex in extra_cells:
        if normalize_grade(ex['res']) == 0:
            ph = ex['ph']
            for ag in AGS:
                if ph.get(ag,0)==1:
                    # we cannot know heterozygosity from extra cells checkboxes reliably,
                    # so we treat extras as "selected cell" (user-defined). No dosage blocking here.
                    ruled_out.add(ag)

    candidates = [x for x in AGS if x not in ruled_out]
    display_cands = [x for x in candidates if x not in IGNORED_AGS]

    # Anti-G heuristic (as-is)
    g_indices = [1,2,3,4,8]
    is_G_pattern = True
    for idx in g_indices:
        if normalize_grade(in_p[idx]) == 0:
            is_G_pattern = False
            break

    is_D = "D" in display_cands
    final_list = []
    notes = []

    for c in display_cands:
        if is_D:
            if c in ["C", "E"]:
                if c=="C" and is_G_pattern:
                    notes.append("anti_G_suspect")
                    final_list.append(c)
                else:
                    continue
        final_list.append(c)

    if "c" in final_list:
        notes.append("anti-c_risk")

    # keep only meaningful evidence (non-empty)
    dosage_protected = {k:v for k,v in dosage_blocked.items() if v}

    return final_list, notes, dosage_protected

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
    ok = ok_full or ok_mod
    return ok, ok_full, ok_mod, p, n

def fit_score(cand, in_p, in_s, extras):
    """
    Score how well antigen distribution matches reactions.
    +2 for matching positive (reactive & antigen+)
    +2 for matching negative (nonreactive & antigen-)
    -3 for mismatch (reactive & antigen-) or (nonreactive & antigen+)
    """
    score = 0
    total = 0

    # panel
    for i in range(1, 12):
        r = normalize_grade(in_p[i])
        a = st.session_state.p11.iloc[i-1].get(cand,0)
        total += 1
        if r==1 and a==1: score += 2
        elif r==0 and a==0: score += 2
        else: score -= 3

    # screen
    si={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        r = normalize_grade(in_s[k])
        a = st.session_state.p3.iloc[si[k]].get(cand,0)
        total += 1
        if r==1 and a==1: score += 2
        elif r==0 and a==0: score += 2
        else: score -= 3

    # extras
    for c in extras:
        r = normalize_grade(c['res'])
        a = c['ph'].get(cand,0)
        total += 1
        if r==1 and a==1: score += 2
        elif r==0 and a==0: score += 2
        else: score -= 3

    # normalize to a 0..100-ish range for display
    # max per cell = +2, min ~ -3
    # We clamp.
    norm = max(0, min(100, int((score + (3*total)) * 100 / (5*total))))
    return norm

# --------------------------------------------------------------------------
# 5. UI
# --------------------------------------------------------------------------
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Menu", ["Workstation", "Supervisor"])
    if st.button("RESET DATA"):
        st.session_state.ext=[]; st.session_state.dat_mode=False
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
    nm=c1.text_input("Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")

    with st.form("main"):
        st.write("### Reaction Entry")
        L, R = st.columns([1, 2.5])
        with L:
            st.write("Controls")
            ac_res = st.radio("Auto Control (AC)", ["Negative", "Positive"])
            st.write("Screening")
            s1=st.selectbox("Scn I", GRADES)
            s2=st.selectbox("Scn II", GRADES)
            s3=st.selectbox("Scn III", GRADES)
        with R:
            st.write("Panel Reactions")
            g1,g2=st.columns(2)
            with g1:
                c1=st.selectbox("1",GRADES,key="1"); c2=st.selectbox("2",GRADES,key="2"); c3=st.selectbox("3",GRADES,key="3"); c4=st.selectbox("4",GRADES,key="4"); c5=st.selectbox("5",GRADES,key="5"); c6=st.selectbox("6",GRADES,key="6")
            with g2:
                c7=st.selectbox("7",GRADES,key="7"); c8=st.selectbox("8",GRADES,key="8"); c9=st.selectbox("9",GRADES,key="9"); c10=st.selectbox("10",GRADES,key="10"); c11=st.selectbox("11",GRADES,key="11")

        run = st.form_submit_button("🚀 Run Analysis")

    if run:
        if not st.session_state.lot_p or not st.session_state.lot_s:
            st.error("⛔ Action Blocked: Lots not configured by Supervisor.")
        else:
            if ac_res == "Positive":
                st.session_state.dat_mode = True
            else:
                st.session_state.dat_mode = False
                i_p = {1:c1,2:c2,3:c3,4:c4,5:c5,6:c6,7:c7,8:c8,9:c9,10:c10,11:c11}
                i_s = {"I":s1,"II":s2,"III":s3}
                cnt = sum([normalize_grade(x) for x in i_p.values()])

                if cnt >= 11:
                    st.markdown("""<div class='clinical-alert'>⚠️ <b>High Incidence Antigen suspected.</b><br>Pan-reactivity with Neg AC.<br>Action: Check siblings / Reference Lab.</div>""", unsafe_allow_html=True)
                else:
                    final, notes, dosage_protected = analyze_alloantibodies(i_p, i_s, st.session_state.ext)

                    # Score + Rule-of-3 for display decisions
                    items = []
                    for ab in final:
                        ok, ok_full, ok_mod, p, n = check_rule_3(ab, i_p, i_s, st.session_state.ext)
                        sc = fit_score(ab, i_p, i_s, st.session_state.ext)
                        items.append({
                            "ab": ab, "score": sc, "ok": ok, "ok_full": ok_full, "ok_mod": ok_mod,
                            "p": p, "n": n,
                            "dosage_protected": ab in dosage_protected
                        })

                    # Separate clinically significant vs insignificant
                    sig_items = [x for x in items if x["ab"] not in INSIGNIFICANT_AGS]
                    insig_items = [x for x in items if x["ab"] in INSIGNIFICANT_AGS]

                    # Sort: confirmed first by score, then unconfirmed by score
                    sig_items.sort(key=lambda x: (x["ok"], x["score"]), reverse=True)
                    insig_items.sort(key=lambda x: (x["ok"], x["score"]), reverse=True)

                    st.subheader("Conclusion")

                    # Anti-G / anti-c notes remain
                    if "anti_G_suspect" in notes:
                        st.warning("⚠️ **Anti-G or Anti-D+C**: Pattern (Cells 1,2,3,4,8 Pos) suggests Anti-G. Perform Adsorption/Elution to differentiate.")
                    if "anti-c_risk" in notes:
                        st.markdown("""<div class='clinical-alert'>🛑 <b>Anti-c Detected:</b> Patient requires R1R1 (E- c-) units to prevent Anti-E formation.</div>""", unsafe_allow_html=True)

                    confirmed = [x for x in sig_items if x["ok"]]
                    pending   = [x for x in sig_items if not x["ok"]]
                    confirmed_insig = [x for x in insig_items if x["ok"]]
                    pending_insig   = [x for x in insig_items if not x["ok"]]

                    if not confirmed and not pending and not confirmed_insig and not pending_insig:
                        st.error("No Match Found / Inconclusive.")
                    else:
                        # 1) Confirmed (clinically significant)
                        if confirmed:
                            lab = ", ".join([f"Anti-{x['ab']}" for x in confirmed])
                            st.success(f"✅ **Confirmed (Rule of Three met):** {lab}")
                            for x in confirmed:
                                tag = "Full Rule (3+3)" if x["ok_full"] else "Modified Rule (2+3)"
                                st.write(f"- **Anti-{x['ab']}** | {tag} | Fit: {x['score']}% | (P:{x['p']} / N:{x['n']})")

                        # 2) Not excluded yet (clinically significant)
                        if pending:
                            st.warning("⚠️ **Not excluded yet (Needs confirmation / Selected cells):**")
                            for x in pending:
                                dp = ""
                                if x["dosage_protected"]:
                                    cells = ", ".join(dosage_protected.get(x["ab"], []))
                                    dp = f" **(Dosage-protected: {cells})**"
                                st.write(f"- **Anti-{x['ab']}** | Fit: {x['score']}% | (P:{x['p']} / N:{x['n']}){dp}")

                        # 3) Clinically insignificant (optional)
                        if confirmed_insig:
                            lab = ", ".join([f"Anti-{x['ab']}" for x in confirmed_insig])
                            st.info(f"ℹ️ **Cold/Insignificant confirmed:** {lab}")
                        if pending_insig:
                            st.info("ℹ️ **Cold/Insignificant not excluded yet:** " + ", ".join([f"Anti-{x['ab']}" for x in pending_insig]))

                        # Separation Strategy only when there are multiple clinically significant candidates
                        sig_names = [x["ab"] for x in sig_items]
                        if len(sig_names) > 1:
                            st.write("---")
                            st.markdown("**🧪 Separation Strategy (Using Inventory):**")
                            for t in sig_names:
                                conf = [x for x in sig_names if x!=t]
                                found = find_matching_cells_in_inventory(t, conf)
                                s_txt = f"<span class='cell-hint'>{', '.join(found)}</span>" if found else "<span style='color:red'>Search External</span>"
                                st.write(f"- Confirm **{t}**: Needs ({t}+ / {' '.join(conf)} neg) {s_txt}")

                        # Report only when at least one clinically significant is confirmed AND no pending significant
                        if confirmed and not pending:
                            if st.button("Generate Official Report"):
                                sig_report = ", ".join([x["ab"] for x in confirmed])
                                rpt=f"""<div class='print-only'><center><h2>Maternity & Children Hospital - Tabuk</h2><h3>Serology Report</h3></center><div class='result-sheet'><b>Pt:</b> {nm} ({mr})<br><b>Tech:</b> {tc} | <b>Lot:</b> {st.session_state.lot_p}<hr><b>Result (Confirmed):</b> Anti-{sig_report}<br><b>Validation:</b> Confirmed (p<=0.05).<br><b>Clinical:</b> Phenotype Negative. Transfuse compatible.<br><br><b>Consultant Verified:</b> _____________</div><div class='print-footer'>Dr. Haitham Ismail | Consultant</div></div><script>window.print()</script>"""
                                st.markdown(rpt, unsafe_allow_html=True)
                        else:
                            if pending:
                                st.warning("⚠️ Add Selected Cells / Additional evidence before issuing final report.")

    if st.session_state.dat_mode:
        st.write("---")
        st.subheader("🧪 Monospecific DAT Workup")

        c_d1, c_d2, c_d3 = st.columns(3)
        igg = c_d1.selectbox("IgG", ["Negative","Positive"], key="dig")
        c3d = c_d2.selectbox("C3d", ["Negative","Positive"], key="dc3")
        ctl = c_d3.selectbox("Control", ["Negative","Positive"], key="dct")

        st.markdown("**Interpretation:**")
        if ctl == "Positive":
            st.error("Invalid. Control Positive.")
        else:
            if igg=="Positive":
                st.warning("👉 **WAIHA** (Warm Autoimmune Hemolytic Anemia).")
                st.write("- Perform Elution/Adsorption.")
                st.markdown("<div class='clinical-waiha'><b>⚠️ Critical Note:</b> If recently transfused, rule out <b>Delayed Hemolytic Transfusion Reaction (DHTR)</b>. Elution is Mandatory.</div>", unsafe_allow_html=True)
            elif c3d=="Positive" and igg=="Negative":
                st.info("👉 **CAS** (Cold Agglutinin Syndrome).")
                st.write("- Use Pre-warm Technique.")

    if not st.session_state.dat_mode:
        with st.expander("➕ Add Selected Cell (From Library)"):
            id_x=st.text_input("ID")
            rs_x=st.selectbox("R",GRADES,key="exr")
            ag_col=st.columns(6)
            new_p={}
            for i,ag in enumerate(AGS):
                if ag_col[i%6].checkbox(ag): new_p[ag]=1
                else: new_p[ag]=0
            if st.button("Confirm Add"):
                st.session_state.ext.append({"res":normalize_grade(rs_x),"res_txt":rs_x,"ph":new_p})
                st.success("Added! Re-run Analysis.")

    if st.session_state.ext:
        st.table(pd.DataFrame(st.session_state.ext)[['res_txt']])
