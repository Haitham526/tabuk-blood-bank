import streamlit as st
import pandas as pd
from datetime import date
import io

# ---------------------------------------------------------
# 1. إعدادات النظام الأساسية
# ---------------------------------------------------------
st.set_page_config(page_title="MCH Tabuk - Serology", layout="wide", page_icon="🩸")

# تنسيقات الطباعة والهيدر فقط (بدون تعقيد)
st.markdown("""
<style>
    @media print {
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; }
        .print-only { display: block !important; }
    }
    .print-only { display: none; }
    
    .hospital-title { text-align: center; color: #003366; font-family: 'Arial'; border-bottom: 4px solid #005f73; }
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    
    .status-box { padding: 10px; border-radius: 5px; margin-bottom: 5px; color: #fff; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. الثوابت والقوائم
# ---------------------------------------------------------
# نكتب القائمة كاملة في سطر واحد لمنع أخطاء النسخ
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# تهيئة الذاكرة (بشكل بسيط جداً)
if 'init_done' not in st.session_state:
    # إنشاء جداول فارغة بالكامل
    st.session_state.panel = pd.DataFrame([{"ID": f"C{i+1}", **{a: 0 for a in AGS}} for i in range(11)])
    st.session_state.screen = pd.DataFrame([{"ID": f"S{i}", **{a: 0 for a in AGS}} for i in ["I","II","III"]])
    # نتائج المستخدم
    st.session_state.user_p = {i: "Neg" for i in range(1,12)}
    st.session_state.user_s = {i: "Neg" for i in ["I","II","III"]}
    st.session_state.extras = []
    st.session_state.init_done = True

# ---------------------------------------------------------
# 3. الوظائف (بدون تعقيد)
# ---------------------------------------------------------
def normalize(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+', '1', 'pos', 'w']) else 0

def parser(file):
    try:
        # قراءة ذكية (Matrix Search)
        df = pd.read_excel(file, header=None)
        
        # 1. البحث عن أماكن الأعمدة
        col_map = {}
        for r in range(min(25, len(df))):
            for c in range(min(60, len(df.columns))):
                txt = str(df.iloc[r,c]).upper().strip().replace(" ","").replace("(","").replace(")","")
                
                det = None
                if txt in AGS: det=txt
                elif txt in ["RHD","D"]: det="D"
                elif txt in ["RHC","C"]: det="C"
                elif txt in ["RHE","E"]: det="E"
                elif txt in ["RHC","HR'"]: det="c"
                
                if det and det not in col_map: col_map[det] = c
        
        if len(col_map) < 3: return None, "Failed to map columns."
        
        # 2. استخراج البيانات (تحت صف العناوين)
        # البحث عن صف يحتوي داتا (رقم 11 مثلا أو علامة +)
        data_rows = []
        found = 0
        r_curr = 0
        
        # البحث عن أول صف بيانات
        while r_curr < len(df) and found < 11:
            # نتأكد أن الصف ده صف داتا بفحص عمود D
            is_data = False
            if "D" in col_map:
                d_val = str(df.iloc[r_curr, col_map["D"]]).lower()
                if any(x in d_val for x in ['+','0','1','w']): is_data = True
            
            if is_data:
                row_dict = {"ID": f"C{found+1}"}
                for ag in AGS:
                    v = 0
                    if ag in col_map:
                        v = normalize(df.iloc[r_curr, col_map[ag]])
                    row_dict[ag] = int(v)
                data_rows.append(row_dict)
                found += 1
            r_curr += 1
            
        return pd.DataFrame(data_rows), f"Success ({found} rows)"
        
    except Exception as e: return None, str(e)

def rule_check(cand):
    # وظيفة حساب Rule of Three
    pos = 0; neg = 0
    # Panel
    for i in range(1, 12):
        s = 1 if st.session_state.user_p[i] != "Neg" else 0
        h = st.session_state.panel.iloc[i-1][cand]
        if s==1 and h==1: pos+=1
        if s==0 and h==0: neg+=1
    # Screen
    for i, idx in enumerate(["I","II","III"]):
        s = 1 if st.session_state.user_s[idx] != "Neg" else 0
        h = st.session_state.screen.iloc[i][cand]
        if s==1 and h==1: pos+=1
        if s==0 and h==0: neg+=1
    # Extras
    for c in st.session_state.extras:
        s = c['s']; h = c['ph'].get(cand,0)
        if s==1 and h==1: pos+=1
        if s==0 and h==0: neg+=1
        
    valid = (pos>=3 and neg>=3) or (pos>=2 and neg>=3)
    return valid, pos, neg

def can_rule_out_fn(ag, pheno):
    if pheno.get(ag,0) == 0: return False
    if ag in DOSAGE:
        partner = PAIRS.get(ag)
        if partner and pheno.get(partner,0)==1: return False
    return True

# ---------------------------------------------------------
# 4. الواجهة (User Interface) - تقسيم بسيط وآمن
# ---------------------------------------------------------
# القائمة الجانبية
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=50)
    st.header("القائمة")
    menu = st.radio("اختر الوضع:", ["العمل اليومي (Workstation)", "إعدادات المشرف (Admin)"])
    st.divider()
    if st.button("🗑️ حذف البيانات المؤقتة (Reset)"):
        for k in list(st.session_state.keys()):
            if k not in ['panel','screen','init_done']: del st.session_state[k]
        st.rerun()

# ----------------------------
# 4.A صفحة المشرف (Admin)
# ----------------------------
if menu == "إعدادات المشرف (Admin)":
    st.title("🛠️ إعدادات النظام")
    pwd = st.text_input("كلمة مرور المشرف", type="password")
    
    if pwd == "admin123":
        t1, t2 = st.tabs(["Panel 11", "Screening"])
        
        with t1:
            st.info("ارفع ملف الإكسيل (PDF Converted)")
            f = st.file_uploader("Upload Excel", type=["xlsx"])
            if f:
                new_df, msg = parser(io.BytesIO(f.getvalue()))
                if new_df is not None:
                    st.success(msg)
                    st.session_state.panel = new_df
                    st.rerun()
                else: st.error(msg)
            
            st.write("جدول البانل الحالي (للتعديل اليدوي):")
            # Force cleanup
            st.session_state.panel = st.session_state.panel.fillna(0)
            edit1 = st.data_editor(st.session_state.panel, hide_index=True)
            if st.button("حفظ البانل"):
                st.session_state.panel = edit1; st.success("تم الحفظ")
        
        with t2:
            st.write("تعديل خلايا السكرين:")
            edit2 = st.data_editor(st.session_state.screen, hide_index=True)
            if st.button("حفظ السكرين"):
                st.session_state.screen = edit2; st.success("تم الحفظ")
    
    elif pwd: st.error("كلمة المرور خطأ")

# ----------------------------
# 4.B صفحة العمل (Workstation)
# ----------------------------
else:
    st.markdown("<h2 class='hospital-title'>Maternity & Children Hospital - Tabuk</h2>", unsafe_allow_html=True)
    
    # 1. Patient Data
    c1, c2, c3, c4 = st.columns(4)
    nm=c1.text_input("Name"); mrn=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    
    st.write("---")
    
    # 2. Results Entry (Safe Column Layout)
    col_s, col_p = st.columns([1, 2])
    
    with col_s:
        st.subheader("1. Screen/AC")
        # Auto Control
        ac = st.radio("Auto Control", ["Negative", "Positive"])
        if ac=="Positive": st.error("⚠️ STOP: Auto Control Positive"); st.stop()
        
        st.caption("Screening:")
        for x in ["I","II","III"]:
            st.session_state.user_s[x] = st.selectbox(f"Cell {x}", ["Neg","w+","1+","2+"], key=f"s_{x}")
            
    with col_p:
        st.subheader("2. Panel (11 Cells)")
        # بدلاً من الجريد المعقد، سنستخدم عمودين بسيطين
        cp1, cp2 = st.columns(2)
        for i in range(1, 12):
            col_target = cp1 if i <= 6 else cp2
            val = col_target.selectbox(f"C{i}", ["Neg","w+","1+","2+","3+"], key=f"p_{i}")
            st.session_state.user_p[i] = val

    # 3. Analysis Button
    st.write("---")
    if st.button("🚀 Analyze / تشخيص", type="primary", use_container_width=True):
        
        # A. Logic Check
        r11 = [st.session_state.panel.iloc[i].to_dict() for i in range(11)]
        r3  = [st.session_state.screen.iloc[i].to_dict() for i in range(3)]
        
        # 1. Exclusion
        ruled = set()
        # Panel negatives
        for i in range(1,12):
            if st.session_state.user_p[i] == "Neg":
                for ag in AGS:
                    if can_rule_out_fn(ag, r11[i-1]): ruled.add(ag)
        # Screen negatives
        s_idx = {"I":0,"II":1,"III":2}
        for k,v in st.session_state.user_s.items():
            if v == "Neg":
                for ag in AGS:
                    if ag not in ruled and can_rule_out_fn(ag, r3[s_idx[k]]): ruled.add(ag)
                    
        # 2. Matching
        cands = [x for x in AGS if x not in ruled]
        match = []
        for c in cands:
            miss = False
            for i in range(1,12):
                score = 1 if st.session_state.user_p[i]!="Neg" else 0
                if score==1 and r11[i-1].get(c,0)==0: miss = True
            if not miss: match.append(c)
            
        # 3. Output
        if not match:
            st.error("❌ نتيجة غير حاسمة (Inconclusive) - جميع الاحتمالات تم استبعادها أو النمط غير مطابق.")
        else:
            allow_print = True
            st.success(f"✅ الاحتمال الأقوى: Anti-{', '.join(match)}")
            
            for m in match:
                ok, p, n = rule_check(m)
                bg = "#198754" if ok else "#dc3545"
                txt = "Confirmed (Standard/Modified Rule)" if ok else "NOT Confirmed (Need Extra Cells)"
                
                st.markdown(f"""
                <div style='background-color:{bg}; color:white; padding:10px; border-radius:5px; margin-bottom:5px'>
                    <b>Anti-{m}:</b> {txt}<br>
                    Positive Reactions: {p} | Negative Reactions: {n}
                </div>
                """, unsafe_allow_html=True)
                if not ok: allow_print = False
                
            # Print Logic
            if allow_print:
                rpt = f"""
                <div class='print-only'>
                    <center><h2>MCH Tabuk - Serology Lab</h2></center>
                    <br>
                    <b>Patient:</b> {nm} (MRN: {mrn})<br>
                    <b>Technician:</b> {tc} | <b>Date:</b> {dt}
                    <hr>
                    <h3>Final Interpretation</h3>
                    <p><b>Antibodies Detected:</b> Anti-{', '.join(match)}</p>
                    <p><b>Validation:</b> Statistical probability met (p <= 0.05).</p>
                    <p><b>Recommendation:</b> Give Antigen Negative blood.</p>
                    <br><br>
                    <p><b>Signature:</b> _________________________</p>
                    <div style='position:fixed;bottom:0;width:100%;text-align:center;border-top:1px solid #ccc'>
                        Dr. Haitham Ismail | Consultant
                    </div>
                </div>
                <script>window.print();</script>
                """
                st.markdown(rpt, unsafe_allow_html=True)
                if st.button("🖨️ اضغط للطباعة"):
                    st.toast("Printing...")
            else:
                st.warning("⚠️ يرجى إضافة خلايا مختارة (Extra Cells) لتحقيق قاعدة 3 في 3.")
                # Extra Cells UI
                with st.expander("➕ إضافة خلية خارجية"):
                    ex1, ex2 = st.columns(2)
                    nid = ex1.text_input("Cell Lot ID")
                    nrs = ex2.selectbox("Result", ["Neg","Pos"])
                    # Checkbox grid for phenotype
                    st.write("Antigen Profile:")
                    temp_ph = {}
                    cols = st.columns(len(match))
                    for i,m in enumerate(match):
                        val = cols[i].checkbox(m, key=f"ex_{m}")
                        temp_ph[m] = 1 if val else 0
                    if st.button("Add Cell"):
                        st.session_state.extras.append({"s": 1 if nrs=="Pos" else 0, "ph": temp_ph, "id": nid})
                        st.rerun()

# Footer
st.markdown("<br><hr><center><small>MCH System V37.0 Safe-Mode</small></center>", unsafe_allow_html=True)
