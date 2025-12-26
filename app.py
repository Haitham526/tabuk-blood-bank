import streamlit as st
import pandas as pd
import io
from datetime import date

# ==========================================
# 1. إعدادات الصفحة والتصميم
# ==========================================
st.set_page_config(page_title="MCH Tabuk - Serology", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print {
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; }
        .block-container { padding: 0 !important; }
        .print-only { display: block !important; }
        .results-box { border: 2px solid #333; padding: 15px; margin-top: 10px; font-family: 'Times New Roman'; }
        .footer-print { position: fixed; bottom: 0; width: 100%; text-align: center; font-size: 10px; border-top: 1px solid #ccc; }
    }
    
    .hospital-header { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: 'Arial'; color: #003366; }
    
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    
    .status-pass { background-color: #d1e7dd; padding: 8px; border-radius: 5px; color: #0f5132; border: 1px solid #a3cfbb; }
    .status-fail { background-color: #f8d7da; padding: 8px; border-radius: 5px; color: #842029; border: 1px solid #f1aeb5; }
    
    .signature-badge {
        position: fixed; bottom: 10px; right: 15px;
        font-family: 'Georgia', serif; font-size: 12px; color: #8B0000;
        background: rgba(255,255,255,0.95); padding: 5px 10px; border: 1px solid #eecaca; z-index: 99;
    }
</style>
""", unsafe_allow_html=True)

# الفوتر والتوقيع
st.markdown("<div class='signature-badge no-print'><b>Dr. Haitham Ismail</b><br>Clinical Hematology/Transfusion Consultant</div>", unsafe_allow_html=True)

# التعريفات (تمت كتابتها بحرص لمنع الأخطاء)
antigens_order = [
    "D", "C", "E", "c", "e", "Cw", 
    "K", "k", "Kpa", "Kpb", "Jsa", "Jsb", 
    "Fya", "Fyb", "Jka", "Jkb", "Lea", "Leb", 
    "P1", "M", "N", "S", "s", "Lua", "Lub", "Xga"
]

allele_pairs = {'C':'c', 'c':'C', 'E':'e', 'e':'E', 'K':'k', 'k':'K', 'Fya':'Fyb', 'Fyb':'Fya', 'Jka':'Jkb', 'Jkb':'Jka', 'M':'N', 'N':'M', 'S':'s', 's':'S'}
STRICT_DOSAGE = ["C", "c", "E", "e", "Fya", "Fyb", "Jka", "Jkb", "M", "N", "S", "s"]

# ==========================================
# 2. تهيئة الذاكرة (SESSION STATE)
# ==========================================
if 'panel_11' not in st.session_state:
    st.session_state.panel_11 = pd.DataFrame([{"ID": f"Cell {i+1}", **{ag: 0 for ag in antigens_order}} for i in range(11)])

if 'panel_3' not in st.session_state:
    st.session_state.panel_3 = pd.DataFrame([{"ID": f"Scn {i}", **{ag: 0 for ag in antigens_order}} for i in ["I", "II", "III"]])

if 'inputs' not in st.session_state:
    st.session_state.inputs = {f"c{i}": "Neg" for i in range(1, 12)}

if 'inputs_s' not in st.session_state:
    st.session_state.inputs_s = {f"s{i}": "Neg" for i in ["I", "II", "III"]}

if 'extra_cells' not in st.session_state:
    st.session_state.extra_cells = []

# ==========================================
# 3. وظائف النظام (PARSERS & LOGIC)
# ==========================================
def normalize_val(val):
    s = str(val).lower().strip()
    # يدعم 1, +, +w, Pos, Yes
    return 1 if any(x in s for x in ['+', '1', 'pos', 'yes', 'w']) else 0

def smart_parser_all_sheets(file_bytes, row_limit):
    """
    يبحث في كل صفحات الإكسيل عن العناوين (D, C, E) ويسحب البيانات تحتها
    بغض النظر عن التنسيق.
    """
    xls = pd.ExcelFile(file_bytes)
    
    for sheet in xls.sheet_names:
        try:
            df = pd.read_excel(file_bytes, sheet_name=sheet, header=None)
            
            # 1. البحث عن سطر العناوين
            header_idx = -1
            col_map = {}
            
            # نمسح أول 20 سطر
            for r in range(min(20, len(df))):
                temp_map = {}
                matches = 0
                for c in range(len(df.columns)):
                    val = str(df.iloc[r, c]).strip().replace("\n","").replace(" ","")
                    
                    real_ag = None
                    # بحث دقيق
                    if val in antigens_order: real_ag = val
                    elif val.upper() in ["RHD","D"]: real_ag = "D"
                    elif val.upper() in ["RHC","C"]: real_ag = "C" # Case matters? usually headers are caps
                    elif val.upper() in ["RHE","E"]: real_ag = "E"
                    
                    # Fuzzy match for C vs c check later if needed
                    # هنا نفترض التطابق المباشر أو التحسينات
                    
                    if real_ag:
                        temp_map[real_ag] = c
                        matches += 1
                
                if matches >= 4: # لو لقينا 4 انتيجينات على الأقل في السطر
                    header_idx = r
                    col_map = temp_map
                    # توسيع البحث في نفس السطر لباقي الانتيجينات
                    for c2 in range(len(df.columns)):
                        v2 = str(df.iloc[r, c2]).strip().replace(" ","")
                        if v2 in antigens_order and v2 not in col_map:
                            col_map[v2] = c2
                    break
            
            # 2. استخراج البيانات
            if header_idx != -1:
                final_data = []
                curr_row = header_idx + 1
                extracted = 0
                
                while extracted < row_limit and curr_row < len(df):
                    # التحقق هل الصف يحتوي بيانات (بفحص عمود D أو C)
                    # نتخطى الصفوف الفارغة أو الخطوط
                    
                    check_cols = [col_map.get("D"), col_map.get("C")]
                    check_cols = [x for x in check_cols if x is not None]
                    
                    has_data = False
                    for cc in check_cols:
                        v_check = str(df.iloc[curr_row, cc]).lower()
                        if any(x in v_check for x in ['0', '1', '+', 'w']):
                            has_data = True
                            break
                    
                    if has_data:
                        r_data = {"ID": f"Cell {extracted+1}" if row_limit > 3 else f"Scn {['I','II','III'][extracted]}"}
                        for ag in antigens_order:
                            val = 0
                            if ag in col_map:
                                val = normalize_val(df.iloc[curr_row, col_map[ag]])
                            r_data[ag] = int(val)
                        final_data.append(r_data)
                        extracted += 1
                        
                    curr_row += 1
                
                if extracted >= row_limit:
                    return pd.DataFrame(final_data), f"تم استيراد {extracted} خلايا بنجاح من ورقة {sheet}"
                    
        except:
            continue

    return None, "لم يتم العثور على جدول مطابق في الملف."

def can_rule_out(ag, pheno):
    if pheno.get(ag, 0) == 0: return False
    if ag in STRICT_DOSAGE:
        partner = allele_pairs.get(ag)
        if partner and pheno.get(partner, 0) == 1: return False
    return True

def check_r3_stats(cand, rows_p, inputs_p, rows_s, inputs_s, extra):
    p_cnt, n_cnt = 0, 0
    # Panel (11)
    for i in range(1, 12):
        s = 1 if inputs_p[i] != "Neg" else 0
        h = rows_p[i-1].get(cand, 0)
        if h==1 and s==1: p_cnt += 1
        if h==0 and s==0: n_cnt += 1
    # Screen (3)
    for i, l in enumerate(["I","II","III"]):
        s = 1 if inputs_s[f"s{l}"] != "Neg" else 0
        h = rows_s[i].get(cand, 0)
        if h==1 and s==1: p_cnt += 1
        if h==0 and s==0: n_cnt += 1
    # Extra
    for c in extra:
        if c['s']==1 and c['p'].get(cand,0)==1: p_cnt += 1
        if c['s']==0 and c['p'].get(cand,0)==0: n_cnt += 1
    
    passed = (p_cnt >= 3 and n_cnt >= 3) or (p_cnt >= 2 and n_cnt >= 3)
    method = "Standard Rule" if (p_cnt >=3 and n_cnt>=3) else "Modified Rule"
    if not passed: method = "Not Met"
    
    return passed, p_cnt, n_cnt, method

def set_bulk(v):
    for i in range(1, 12): st.session_state.inputs[f"c{i}"] = v

# ==========================================
# 4. القائمة الجانبية
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("القائمة:", ["User Workstation", "Supervisor Config"])
    st.divider()
    if st.button("🗑️ Reset All Data"):
        st.session_state.extra_cells = []
        st.rerun()

# ==========================================
# 5. صفحة الأدمن (SUPERVISOR)
# ==========================================
if nav == "Supervisor Config":
    st.title("🛠️ Master Configuration")
    if st.text_input("Admin Password", type="password") == "admin123":
        
        tab1, tab2 = st.tabs(["Panel (11 Cells)", "Screening (3 Cells)"])
        
        # TAB 1: Panel Upload
        with tab1:
            st.info("Upload PDF-Converted Excel for the Main Panel")
            up1 = st.file_uploader("Upload Panel 11", type=["xlsx"], key="up1")
            
            if up1:
                df_new, msg = smart_parser_all_sheets(io.BytesIO(up1.getvalue()), 11)
                if df_new is not None:
                    st.success(f"✅ {msg}")
                    st.session_state.panel_11 = df_new
                    st.button("تحديث العرض")
                else:
                    st.error(f"❌ {msg}")
            
            st.write("#### Live Grid Editor:")
            edited_p11 = st.data_editor(st.session_state.panel_11.fillna(0), height=400, hide_index=True, use_container_width=True)
            if st.button("Save Panel Changes"):
                st.session_state.panel_11 = edited_p11
                st.success("Saved.")

        # TAB 2: Screen Upload
        with tab2:
            st.info("Upload Screening Cells File (If available)")
            up2 = st.file_uploader("Upload Screen 3", type=["xlsx"], key="up2")
            
            if up2:
                df_scr, msg_s = smart_parser_all_sheets(io.BytesIO(up2.getvalue()), 3)
                if df_scr is not None:
                    st.success(f"✅ {msg_s}")
                    st.session_state.panel_3 = df_scr
                    st.button("تحديث العرض 2")
                else:
                    st.error(f"❌ {msg_s}")
            
            st.write("#### Screening Grid:")
            edited_p3 = st.data_editor(st.session_state.panel_3.fillna(0), height=200, hide_index=True, use_container_width=True)
            if st.button("Save Screen Changes"):
                st.session_state.panel_3 = edited_p3
                st.success("Saved.")

# ==========================================
# 6. صفحة العمل (USER)
# ==========================================
else:
    st.markdown("""<div class='hospital-header'><h1>Maternity & Children Hospital - Tabuk</h1><h4>Serology Workstation</h4></div>""", unsafe_allow_html=True)
    
    # Patient
    c1,c2,c3,c4 = st.columns(4)
    p_name=c1.text_input("Patient Name"); p_mrn=c2.text_input("MRN"); p_tech=c3.text_input("Tech"); p_date=c4.date_input("Date")
    st.divider()
    
    # Entry
    colL, colR = st.columns([1, 2])
    
    with colL:
        st.subheader("1. Screen / Control")
        # Auto Control
        ac_v = st.radio("AC", ["Negative", "Positive"], horizontal=True)
        if ac_v == "Positive": st.error("🚨 STOP: AC Positive -> DAT Required"); st.stop()
        
        st.write("---")
        # Screen
        for l in ["I", "II", "III"]:
            k = f"s{l}"
            st.session_state.inputs_s[k] = st.selectbox(f"Scn {l}", ["Neg", "w+", "1+", "2+", "3+"], key=f"sel_{k}")
        
        st.write("---")
        if st.button("Set Neg"): set_bulk("Neg")
        if st.button("Set Pos"): set_bulk("2+")

    with colR:
        st.subheader("2. Panel Results")
        # Grid inputs
        grid_cols = st.columns(6)
        in_p_map = {}
        for i in range(1, 12):
            k = f"c{i}"
            v = grid_cols[(i-1)%6].selectbox(f"C{i}", ["Neg", "w+", "1+", "2+", "3+"], key=f"pan_{i}", index=["Neg", "w+", "1+", "2+", "3+"].index(st.session_state.inputs[k]))
            st.session_state.inputs[k] = v
            in_p_map[i] = 0 if v == "Neg" else 1

    # Analysis
    st.divider()
    if st.checkbox("🔍 Analyze"):
        # Safe read rows
        rp11 = [st.session_state.panel_11.iloc[i].to_dict() for i in range(11)]
        rp3  = [st.session_state.panel_3.iloc[i].to_dict() for i in range(3)]
        
        ruled_out = set()
        
        # 1. Exclude from Panel
        for ag in antigens_order:
            for i, score in in_p_map.items():
                if score == 0:
                    if can_rule_out(ag, rp11[i-1]):
                        ruled_out.add(ag); break
        
        # 2. Exclude from Screen
        scr_idx = {"I":0, "II":1, "III":2}
        for k, v in st.session_state.inputs_s.items(): # k="sI"
            if v == "Neg":
                s_pheno = rp3[scr_idx[k[1:]]]
                for ag in antigens_order:
                    if ag not in ruled_out and can_rule_out(ag, s_pheno):
                        ruled_out.add(ag)
                        
        candidates = [x for x in antigens_order if x not in ruled_out]
        
        # 3. Include (Match)
        matches = []
        for c in candidates:
            mismatch = False
            for i, score in in_p_map.items():
                if score > 0 and rp11[i-1].get(c, 0) == 0:
                    mismatch = True
            if not mismatch: matches.append(c)
            
        # Display
        if not matches:
            st.error("❌ Inconclusive.")
        else:
            allow_report = True
            for m in matches:
                ok, p, n, meth = check_r3_stats(m, rp11, st.session_state.inputs, rp3, st.session_state.inputs_s, st.session_state.extra_cells)
                st.markdown(f"<div class='status-{'pass' if ok else 'fail'}'><b>Anti-{m}:</b> {meth} ({p} Pos / {n} Neg)</div>", unsafe_allow_html=True)
                if not ok: allow_report = False
            
            if allow_report:
                if st.button("🖨️ Print Final Report"):
                    html = f"""<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='results-box'><b>Pt:</b> {p_name} ({p_mrn})<br><b>Tech:</b> {p_tech}<hr><b>Conclusion:</b> Anti-{', '.join(matches)} Detected.<br>Probability met (p≤0.05).<br>Screening cells included in validation.<br><br><b>Sign:</b> ______________</div><div class='footer-print'>Dr. Haitham Ismail | Consultant</div></div><script>window.print()</script>"""
                    st.markdown(html, unsafe_allow_html=True)
            else:
                st.info("⚠️ Rule not met. Add Selected Cell:")
                with st.expander("Add Cell"):
                    colx1, colx2 = st.columns(2)
                    nid = colx1.text_input("ID")
                    nres = colx2.selectbox("Result", ["Neg","Pos"])
                    pht = {}
                    cc = st.columns(len(matches))
                    for i,mm in enumerate(matches):
                        rr = cc[i].radio(mm, ["+","0"], key=f"ex_{mm}")
                        pht[mm] = 1 if rr == "+" else 0
                    if st.button("Add"):
                        st.session_state.extra_cells.append({"src":nid, "score":1 if nres=="Pos" else 0, "pheno":pht, "s":1 if nres=="Pos" else 0})
                        st.rerun()
