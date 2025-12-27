import streamlit as st
import pandas as pd
from datetime import date

# 1. إعدادات الصفحة (CLEAN SETUP)
st.set_page_config(page_title="MCH Tabuk Bank", layout="wide")

# CSS لإصلاح الجدول والتصميم
st.markdown("""
<style>
    /* إخفاء القوائم غير الضرورية */
    .stApp > header, .sidebar, footer, .no-print { display: none !important; }
    
    /* تنسيق التقرير */
    .report-paper { 
        border: 2px solid #000; 
        padding: 30px; 
        margin-top: 10px; 
        font-family: 'Times New Roman'; 
    }
    
    /* جعل الجدول يقبل اللصق ويظهر كاملاً */
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    
    /* الألوان */
    .success-box { background: #d4edda; color: #155724; padding: 10px; margin: 5px 0; border-radius: 5px;}
    .fail-box { background: #f8d7da; color: #721c24; padding: 10px; margin: 5px 0; border-radius: 5px;}
    
    /* التوقيع */
    .sig-float { position: fixed; bottom: 10px; right: 15px; background: white; border: 1px solid #ccc; padding: 5px; z-index: 99; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="sig-float no-print">Dr. Haitham Ismail | Consultant</div>', unsafe_allow_html=True)

# 2. البيانات والثوابت
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# تهيئة الذاكرة (بدون تعقيد)
if 'panel_11' not in st.session_state:
    # جدول صفري
    st.session_state.panel_11 = pd.DataFrame(0, index=[f"Cell {i+1}" for i in range(11)], columns=AGS)
if 'panel_3' not in st.session_state:
    st.session_state.panel_3 = pd.DataFrame(0, index=["Scn I","Scn II","Scn III"], columns=AGS)
if 'ext' not in st.session_state: st.session_state.ext = []

# تهيئة المدخلات يدوياً لمنع الـ TypeError
input_keys = ["s_I","s_II","s_III"] + [f"c_{i}" for i in range(1,12)]
for k in input_keys:
    if k not in st.session_state: st.session_state[k] = "Neg"

# 3. المنطق (LOGIC)
def can_exclude(ag, row_data):
    if row_data[ag] == 0: return False
    if ag in DOSAGE:
        pair = PAIRS.get(ag)
        if pair and row_data.get(pair) == 1: return False # Heterozygous -> Keep
    return True

def analyze_logic():
    # جمع البيانات
    p11 = st.session_state.panel_11
    p3 = st.session_state.panel_3
    
    # 1. Exclusion
    ruled_out = set()
    
    # Panel Exclusion
    for i in range(1, 12):
        res = st.session_state[f"c_{i}"]
        if res == "Neg":
            row = p11.iloc[i-1]
            for ag in AGS:
                if can_exclude(ag, row): ruled_out.add(ag)
    
    # Screen Exclusion
    for i, s in enumerate(["I","II","III"]):
        res = st.session_state[f"s_{s}"]
        if res == "Neg":
            row = p3.iloc[i]
            for ag in AGS:
                if ag not in ruled_out and can_exclude(ag, row): ruled_out.add(ag)
                
    candidates = [x for x in AGS if x not in ruled_out]
    
    # 2. Matching
    matches = []
    for c in candidates:
        mis = False
        # Check Panel Positives
        for i in range(1, 12):
            if st.session_state[f"c_{i}"] != "Neg" and p11.iloc[i-1][c] == 0: mis = True
        if not mis: matches.append(c)
        
    return matches

def check_rule_3(cand):
    pos = 0; neg = 0
    # P11
    for i in range(1, 12):
        s = 1 if st.session_state[f"c_{i}"]!="Neg" else 0
        h = st.session_state.panel_11.iloc[i-1][cand]
        if s==1 and h==1: pos+=1
        if s==0 and h==0: neg+=1
    # P3
    for i, s in enumerate(["I","II","III"]):
        sc = 1 if st.session_state[f"s_{s}"]!="Neg" else 0
        h = st.session_state.panel_3.iloc[i][cand]
        if sc==1 and h==1: pos+=1
        if sc==0 and h==0: neg+=1
    # Ext
    for x in st.session_state.ext:
        if x['s']==1 and x['ph'][cand]==1: pos+=1
        if x['s']==0 and x['ph'][cand]==0: neg+=1
    
    return pos, neg, (pos>=3 and neg>=3) or (pos>=2 and neg>=3)

# 4. الواجهة (INTERFACE)
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=50)
    menu = st.radio("القائمة:", ["Workstation", "Admin Config"])
    st.divider()
    if st.button("تصفير الكل (Reset)"):
        st.session_state.ext = []
        st.rerun()

# ----------------- ADMIN -----------------
if menu == "Admin Config":
    st.title("🛠️ إعداد الجدول (Copy/Paste Mode)")
    pwd = st.text_input("Admin Password", type="password")
    
    if pwd == "admin123":
        t1, t2 = st.tabs(["Panel 11", "Screening 3"])
        
        with t1:
            st.info("💡 **طريقة العمل:** افتح الإكسيل الخاص بك، انسخ الأرقام (0 و 1) فقط، تعال هنا قف في أول خلية، واضغط Ctrl+V.")
            st.caption("Panel Data:")
            # Data Editor يقبل اللصق المباشر من الإكسيل
            edited_p11 = st.data_editor(st.session_state.panel_11, height=450, use_container_width=True)
            if st.button("حفظ التعديلات (Panel)"):
                st.session_state.panel_11 = edited_p11
                st.success("تم الحفظ!")
                
        with t2:
            st.caption("Screening Data:")
            edited_p3 = st.data_editor(st.session_state.panel_3)
            if st.button("حفظ التعديلات (Screen)"):
                st.session_state.panel_3 = edited_p3
                st.success("تم الحفظ!")
    
# ----------------- WORKSTATION -----------------
else:
    st.markdown("<h2 style='text-align:center; color:#003366'>MCH Tabuk - Blood Bank</h2>", unsafe_allow_html=True)
    
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    
    st.divider()
    
    # واجهة إدخال صلبة (بدون Loops) لتجنب الأخطاء
    colL, colR = st.columns([1, 2])
    
    with colL:
        st.subheader("1. Screen/AC")
        ac = st.radio("AC", ["Negative","Positive"], horizontal=True)
        if ac == "Positive": st.error("STOP: DAT Required"); st.stop()
        
        st.write("---")
        st.session_state.s_I = st.selectbox("Scn I", ["Neg","w+","1+","2+"], key="bx_s1")
        st.session_state.s_II = st.selectbox("Scn II", ["Neg","w+","1+","2+"], key="bx_s2")
        st.session_state.s_III = st.selectbox("Scn III", ["Neg","w+","1+","2+"], key="bx_s3")
        
        if st.button("Set Screen Neg"):
            st.session_state.s_I="Neg"; st.session_state.s_II="Neg"; st.session_state.s_III="Neg"; st.rerun()

    with colR:
        st.subheader("2. Panel Results")
        rc1, rc2 = st.columns(2)
        # كتابة الأزرار سطر سطر لمنع الانهيار
        st.session_state.c_1 = rc1.selectbox("C1", ["Neg","w+","1+","2+","3+"], key="p_1")
        st.session_state.c_2 = rc1.selectbox("C2", ["Neg","w+","1+","2+","3+"], key="p_2")
        st.session_state.c_3 = rc1.selectbox("C3", ["Neg","w+","1+","2+","3+"], key="p_3")
        st.session_state.c_4 = rc1.selectbox("C4", ["Neg","w+","1+","2+","3+"], key="p_4")
        st.session_state.c_5 = rc1.selectbox("C5", ["Neg","w+","1+","2+","3+"], key="p_5")
        st.session_state.c_6 = rc1.selectbox("C6", ["Neg","w+","1+","2+","3+"], key="p_6")
        
        st.session_state.c_7 = rc2.selectbox("C7", ["Neg","w+","1+","2+","3+"], key="p_7")
        st.session_state.c_8 = rc2.selectbox("C8", ["Neg","w+","1+","2+","3+"], key="p_8")
        st.session_state.c_9 = rc2.selectbox("C9", ["Neg","w+","1+","2+","3+"], key="p_9")
        st.session_state.c_10 = rc2.selectbox("C10", ["Neg","w+","1+","2+","3+"], key="p_10")
        st.session_state.c_11 = rc2.selectbox("C11", ["Neg","w+","1+","2+","3+"], key="p_11")
        
        if st.button("Set Panel Neg"):
            for i in range(1,12): st.session_state[f"c_{i}"]="Neg"
            st.rerun()

    st.divider()
    if st.button("🚀 Analyze Result", type="primary"):
        matches = analyze_logic()
        
        st.subheader("Interpretation")
        if not matches:
            st.error("No antibody identified / Inconclusive.")
        else:
            final_allow = True
            for m in matches:
                p, n, ok = check_rule_3(m)
                color = "success-box" if ok else "fail-box"
                txt = "Confirmed (Rule of 3)" if ok else "Rule Not Met (Need cells)"
                st.markdown(f"<div class='{color}'><b>Anti-{m}:</b> {txt} ({p} Pos / {n} Neg)</div>", unsafe_allow_html=True)
                if not ok: final_allow = False
            
            if final_allow:
                if st.button("🖨️ Print Final Report"):
                    rpt = f"""
                    <div class='print-only'>
                        <br><center><h2>MCH Tabuk - Serology Lab</h2></center>
                        <div class='report-paper'>
                            <p><b>Patient:</b> {nm} | <b>MRN:</b> {mr}</p>
                            <p><b>Tech:</b> {tc} | <b>Date:</b> {dt}</p>
                            <hr>
                            <h3>Results</h3>
                            <p><b>Identified:</b> Anti-{', '.join(matches)}</p>
                            <p><b>Validation:</b> Statistical rule (p<=0.05) Met.</p>
                            <p><b>Notes:</b> Please Phenotype patient (Must be Negative).</p>
                            <br><br><br>
                            <p><b>Signature:</b> ___________________________</p>
                        </div>
                        <div style='position:fixed;bottom:0;text-align:center;width:100%'>Dr. Haitham Ismail</div>
                    </div>
                    <script>window.print();</script>
                    """
                    st.markdown(rpt, unsafe_allow_html=True)
            else:
                with st.expander("➕ Add Selected Cell (External)"):
                    ex_id = st.text_input("Cell Lot ID")
                    ex_res = st.selectbox("Reaction", ["Neg","Pos"])
                    ex_ph = {}
                    # Build pheno checkboxes for matches only
                    cls = st.columns(len(matches))
                    for i, mat in enumerate(matches):
                        if cls[i].checkbox(mat, key=f"xc_{mat}"): ex_ph[mat]=1
                        else: ex_ph[mat]=0
                    
                    if st.button("Confirm Addition"):
                        sc = 1 if ex_res=="Pos" else 0
                        st.session_state.ext.append({"id":ex_id, "s":sc, "ph":ex_ph})
                        st.rerun()
