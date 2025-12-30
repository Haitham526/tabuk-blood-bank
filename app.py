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
# 4. LOGIC ENGINE (FIXED: stepwise + high-incidence + no premature confirmation)
# --------------------------------------------------------------------------
def normalize_grade(val):
    s = str(val).lower().strip()
    if s in ["0", "neg", "negative"]:
        return 0
    # Hemolysis treated as +4 for grading logic, but still "positive"
    return 1

def grade_to_level(val):
    s = str(val).strip().lower()
    if s in ["0", "neg", "negative"]:
        return 0
    if "hemol" in s:
        return 4
    # "+1" "+2" "+3" "+4"
    for k in ["+1","+2","+3","+4"]:
        if k in s:
            return int(k.replace("+",""))
    # fallback: any positive = 1
    return 1

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

def get_cell_ph(source, idx):
    # source: "panel" 1..11 OR "screen" 0..2
    if source == "panel":
        return st.session_state.p11.iloc[idx-1]
    return st.session_state.p3.iloc[idx]

def is_homozygous_for_ag(ph_row, ag):
    # homozygous defined ONLY for DOSAGE antigens using pairs
    if ag not in DOSAGE:
        return True
    pair = PAIRS.get(ag)
    if not pair:
        return True
    # If ag is present and pair absent => homozygous
    # If ag present and pair present => hetero
    # If ag absent => not applicable
    return (ph_row.get(ag,0)==1 and ph_row.get(pair,0)==0)

def can_rule_out_from_negative_cell(ph_row, ag):
    # policy: rule out if negative reaction AND antigen present homozygous on that nonreactive cell
    if ph_row.get(ag,0)!=1:
        return False
    return is_homozygous_for_ag(ph_row, ag)

def evaluate_fit_for_ag(ag, in_p, in_s, extras):
    """
    Return a fit score + counts.
    We want an antigen that explains positives and negatives:
    - positives should be mostly antigen-positive
    - negatives should be mostly antigen-negative
    But do NOT "confirm" here; this is Step-1 scoring only.
    """
    pos_ag_pos = 0
    pos_total  = 0
    neg_ag_neg = 0
    neg_total  = 0

    # Panel
    for i in range(1,12):
        r = normalize_grade(in_p[i])
        ph = get_cell_ph("panel", i)
        if r==1:
            pos_total += 1
            if ph.get(ag,0)==1:
                pos_ag_pos += 1
        else:
            neg_total += 1
            if ph.get(ag,0)==0:
                neg_ag_neg += 1

    # Screen
    smap={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        r = normalize_grade(in_s[k])
        ph = get_cell_ph("screen", smap[k])
        if r==1:
            pos_total += 1
            if ph.get(ag,0)==1:
                pos_ag_pos += 1
        else:
            neg_total += 1
            if ph.get(ag,0)==0:
                neg_ag_neg += 1

    # Extras
    for ex in extras:
        r = normalize_grade(ex['res'])
        ph = ex['ph']
        if r==1:
            pos_total += 1
            if ph.get(ag,0)==1:
                pos_ag_pos += 1
        else:
            neg_total += 1
            if ph.get(ag,0)==0:
                neg_ag_neg += 1

    # Fit percent: weighted
    fit_pos = (pos_ag_pos/pos_total)*100 if pos_total else 0
    fit_neg = (neg_ag_neg/neg_total)*100 if neg_total else 0
    fit = round((fit_pos*0.65 + fit_neg*0.35),1)

    return fit, pos_ag_pos, pos_total, neg_ag_neg, neg_total

def analyze_step1_ruleout_rulein(in_p, in_s, extra_cells):
    ruled_out = set()

    # 1) Panel Exclusion using nonreactive cells (one cell at a time)
    for i in range(1, 12):
        if normalize_grade(in_p[i]) == 0:
            ph = get_cell_ph("panel", i)
            for ag in AGS:
                if ag in ruled_out:
                    continue
                if can_rule_out_from_negative_cell(ph, ag):
                    ruled_out.add(ag)

    # 2) Screen Exclusion
    smap={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        if normalize_grade(in_s[k]) == 0:
            ph = get_cell_ph("screen", smap[k])
            for ag in AGS:
                if ag in ruled_out:
                    continue
                if can_rule_out_from_negative_cell(ph, ag):
                    ruled_out.add(ag)

    # 3) Extra Exclusion
    for ex in extra_cells:
        if normalize_grade(ex['res']) == 0:
            ph = ex['ph']
            for ag in AGS:
                if ag in ruled_out:
                    continue
                # for extras: if ag is dosage and pair present -> treat as hetero => not safe to rule out
                if ag in DOSAGE and ph.get(PAIRS.get(ag,""),0)==1:
                    continue
                if ph.get(ag,0)==1:
                    ruled_out.add(ag)

    # Candidates = not ruled out (but still may be unresolved)
    candidates = [x for x in AGS if x not in ruled_out]
    candidates = [x for x in candidates if x not in IGNORED_AGS]

    # Score candidates by fit
    scored = []
    for ag in candidates:
        fit, a, b, c, d = evaluate_fit_for_ag(ag, in_p, in_s, extra_cells)
        scored.append((ag, fit, a, b, c, d))
    scored.sort(key=lambda x: x[1], reverse=True)

    # Determine "resolved" vs "not excluded":
    # Resolved requires: decent fit AND at least one positive cell that is antigen-positive AND at least one negative cell that is antigen-negative
    resolved = []
    not_excluded = []
    for ag, fit, pos_ag_pos, pos_total, neg_ag_neg, neg_total in scored:
        has_support_pos = (pos_ag_pos >= 1)
        has_support_neg = (neg_ag_neg >= 1) if neg_total else True  # if no negatives at all, can't resolve
        if has_support_pos and has_support_neg and fit >= 75:
            resolved.append((ag, fit, pos_ag_pos, pos_total, neg_ag_neg, neg_total))
        else:
            not_excluded.append((ag, fit, pos_ag_pos, pos_total, neg_ag_neg, neg_total))

    # Limit lists for clean UI
    resolved = resolved[:6]
    not_excluded = not_excluded[:10]

    notes = []
    # anti-G pattern flag (kept as advisory only; do NOT force add C/E wrongly)
    g_indices = [1,2,3,4,8]
    is_G_pattern = all(normalize_grade(in_p[i])==1 for i in g_indices)
    if is_G_pattern:
        notes.append("anti_G_suspect")

    return ruled_out, resolved, not_excluded, notes

def check_rule_3(cand, in_p, in_s, extras):
    p, n = 0, 0
    for i in range(1, 12):
        s=normalize_grade(in_p[i]); h=get_cell_ph("panel", i).get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    si={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        s=normalize_grade(in_s[k]); h=get_cell_ph("screen", si[k]).get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    for c in extras:
        s=normalize_grade(c['res']); h=c['ph'].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    ok_full = (p>=3 and n>=3)
    ok_mod  = (p>=2 and n>=3)
    return ok_full, ok_mod, p, n

def find_matching_cells_in_inventory(target_ab, conflicts):
    found_list = []
    # Panel
    for i in range(1,12):
        cell = get_cell_ph("panel", i)
        if cell.get(target_ab,0)==1:
            clean = True
            for bad in conflicts:
                if cell.get(bad,0)==1:
                    clean=False; break
            if clean:
                found_list.append(f"Panel #{i}")
    # Screen
    sc_lbls = ["I","II","III"]
    for i in range(3):
        cell = get_cell_ph("screen", i)
        if cell.get(target_ab,0)==1:
            clean=True
            for bad in conflicts:
                if cell.get(bad,0)==1:
                    clean=False; break
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
                p1=st.selectbox("1",GRADES,key="1"); p2=st.selectbox("2",GRADES,key="2"); p3=st.selectbox("3",GRADES,key="3"); p4=st.selectbox("4",GRADES,key="4"); p5=st.selectbox("5",GRADES,key="5"); p6=st.selectbox("6",GRADES,key="6")
            with g2:
                p7=st.selectbox("7",GRADES,key="7"); p8=st.selectbox("8",GRADES,key="8"); p9=st.selectbox("9",GRADES,key="9"); p10=st.selectbox("10",GRADES,key="10"); p11=st.selectbox("11",GRADES,key="11")

        run = st.form_submit_button("🚀 Run Analysis")

    if run:
        if not st.session_state.lot_p or not st.session_state.lot_s:
            st.error("⛔ Action Blocked: Lots not configured by Supervisor.")
        else:
            # DAT mode
            if ac_res == "Positive":
                st.session_state.dat_mode = True
            else:
                st.session_state.dat_mode = False

                i_p = {1:p1,2:p2,3:p3,4:p4,5:p5,6:p6,7:p7,8:p8,9:p9,10:p10,11:p11}
                i_s = {"I":s1,"II":s2,"III":s3}

                # ------------------------------------------------------------------
                # FIX #1: High-incidence ONLY when (panel 11/11 + screen 3/3) positive
                # ------------------------------------------------------------------
                panel_pos  = sum(normalize_grade(i_p[i]) for i in range(1,12))
                screen_pos = sum(normalize_grade(i_s[k]) for k in ["I","II","III"])

                if (panel_pos == 11) and (screen_pos == 3):
                    st.markdown("""<div class='clinical-alert'>⚠️ <b>Antibody against High-Incidence Antigen suspected.</b><br>
                    Pan-reactivity with Negative Auto Control.<br>
                    Action: Search compatible donor from first-degree relatives / Reference Lab.</div>""",
                                unsafe_allow_html=True)
                else:
                    ruled_out, resolved, not_excluded, notes = analyze_step1_ruleout_rulein(i_p, i_s, st.session_state.ext)

                    st.subheader("Conclusion (Step 1: Rule-out / Rule-in)")

                    if not resolved:
                        st.error("No resolved specificity from current data. Proceed with Selected Cells / Enhancement as needed.")
                    else:
                        sig_res = [x for x in resolved if x[0] not in INSIGNIFICANT_AGS]
                        cold_res = [x for x in resolved if x[0] in INSIGNIFICANT_AGS]

                        if "anti_G_suspect" in notes:
                            st.warning("⚠️ **Anti-G consideration**: Pattern may suggest Anti-G vs Anti-D+C. Differentiate by adsorption/elution if clinically indicated (do not auto-confirm here).")

                        if sig_res:
                            st.success("✅ **Resolved / Likely (Proceed to Confirmation later):** " +
                                       ", ".join([f"Anti-{x[0]} (Fit {x[1]}%)" for x in sig_res]))
                        if cold_res:
                            st.info("ℹ️ **Resolved cold/insignificant:** " +
                                    ", ".join([f"Anti-{x[0]} (Fit {x[1]}%)" for x in cold_res]))

                        # Multiple resolved → show separation strategy
                        sig_names = [x[0] for x in sig_res]
                        if len(sig_names) > 1:
                            st.write("---")
                            st.markdown("**🧪 Separation Strategy (Using Inventory):**")
                            for t in sig_names:
                                conf = [x for x in sig_names if x!=t]
                                found = find_matching_cells_in_inventory(t, conf)
                                s_txt = f"<span class='cell-hint'>{', '.join(found)}</span>" if found else "<span style='color:red'>Search External</span>"
                                st.write(f"- For **{t}**: need ({t}+ / {' ,'.join(conf)} negative) → {s_txt}")

                    # Not excluded list (do NOT confirm)
                    if not_excluded:
                        st.write("---")
                        st.markdown("⚠️ **Not excluded yet (Needs more work — DO NOT confirm now):**")
                        sig_ne = [x for x in not_excluded if x[0] not in INSIGNIFICANT_AGS]
                        cold_ne = [x for x in not_excluded if x[0] in INSIGNIFICANT_AGS]

                        if sig_ne:
                            st.write("- Clinically significant possibilities: " + ", ".join([x[0] for x in sig_ne[:8]]))
                        if cold_ne:
                            st.write("- Cold/insignificant not excluded: " + ", ".join([x[0] for x in cold_ne[:8]]))

                    # ------------------------------------------------------------------
                    # FIX #2: Rule of three ONLY for RESOLVED antibodies
                    # ------------------------------------------------------------------
                    st.write("---")
                    st.subheader("Confirmation (Rule of Three) — Resolved only")

                    if not resolved:
                        st.info("No resolved antibody yet → do NOT apply Rule of Three. Add selected cells / repeat with different lot as needed.")
                    else:
                        # Confirm only resolved list
                        valid_all = True
                        for ag, fit, *_ in resolved:
                            ok_full, ok_mod, p, n = check_rule_3(ag, i_p, i_s, st.session_state.ext)
                            if ok_full:
                                st.write(f"✅ **Anti-{ag}** | Full Rule (3+3) | Fit: {fit}% | (P:{p} / N:{n})")
                            elif ok_mod:
                                st.write(f"✅ **Anti-{ag}** | Modified Rule (2+3) | Fit: {fit}% | (P:{p} / N:{n})")
                            else:
                                st.write(f"⚠️ **Anti-{ag}** | Unconfirmed | Fit: {fit}% | (P:{p} / N:{n})")
                                valid_all = False

                        if valid_all:
                            if st.button("Generate Official Report"):
                                # Only include RESOLVED significant in report
                                res_sig = [x[0] for x in resolved if x[0] not in INSIGNIFICANT_AGS]
                                res_cold = [x[0] for x in resolved if x[0] in INSIGNIFICANT_AGS]

                                rpt=f"""<div class='print-only'><center><h2>Maternity & Children Hospital - Tabuk</h2><h3>Serology Report</h3></center>
                                <div class='result-sheet'>
                                <b>Pt:</b> {nm} ({mr})<br><b>Tech:</b> {tc} | <b>Lot:</b> {st.session_state.lot_p}<hr>
                                <b>Resolved:</b> Anti-{', '.join(res_sig) if res_sig else 'N/A'}<br>
                                <b>Other:</b> {('Anti-' + ', '.join(res_cold)) if res_cold else 'N/A'}<br>
                                <b>Validation:</b> Confirmed where applicable (p≤0.05).<br>
                                <b>Note:</b> Antibodies listed under “Not excluded” are NOT confirmed and require additional selected cells.<br><br>
                                <b>Consultant Verified:</b> _____________</div>
                                <div class='print-footer'>Dr. Haitham Ismail | Consultant</div></div>
                                <script>window.print()</script>"""
                                st.markdown(rpt, unsafe_allow_html=True)
                        else:
                            st.warning("⚠️ Some resolved specificities still need confirmation. Add selected cells as needed.")

    # DAT Workup
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
                st.warning("👉 **Mostly WAIHA** (Warm Autoimmune Hemolytic Anemia).")
                st.write("- Refer to Blood Bank Physician.")
                st.write("- Consider Elution / Adsorption as indicated.")
                st.markdown("<div class='clinical-waiha'><b>⚠️ Critical Note:</b> If recently transfused, consider <b>DHTR</b>. Elution should be considered.</div>", unsafe_allow_html=True)
            elif c3d=="Positive" and igg=="Negative":
                st.info("👉 **Suggestive of CAS** (Cold Agglutinin Syndrome).")
                st.write("- Apply Pre-warm Technique.")
            else:
                st.info("DAT monospecific is negative (IgG-/C3d-). Correlate clinically and review technique.")

    # Add Selected Cell
    if not st.session_state.dat_mode:
        with st.expander("➕ Add Selected Cell (From Library)"):
            id_x=st.text_input("ID")
            rs_x=st.selectbox("R",GRADES,key="exr")
            ag_col=st.columns(6)
            new_p={}
            for i,ag in enumerate(AGS):
                if ag_col[i%6].checkbox(ag):
                    new_p[ag]=1
                else:
                    new_p[ag]=0
            if st.button("Confirm Add"):
                st.session_state.ext.append({"res":normalize_grade(rs_x),"res_txt":rs_x,"ph":new_p})
                st.success("Added! Re-run Analysis.")

    if st.session_state.ext:
        st.table(pd.DataFrame(st.session_state.ext)[['res_txt']])
