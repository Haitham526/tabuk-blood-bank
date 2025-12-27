import streamlit as st
import pandas as pd
import io
from datetime import date

# 1. SETUP
st.set_page_config(page_title="MCH Serology", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { .stApp > header, .sidebar, footer, .no-print { display: none !important; } .print-only { display: block !important; } }
    .print-only { display: none; }
    .hospital-header { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: 'Arial'; color: #003366; }
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    .signature-badge { position: fixed; bottom: 10px; right: 15px; background: rgba(255,255,255,0.9); padding: 5px 10px; border: 1px solid #ccc; z-index:99; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='signature-badge no-print'><b>Dr. Haitham Ismail</b><br>Consultant</div>", unsafe_allow_html=True)

# DATA
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'res' not in st.session_state: st.session_state.res = {f"c{i}":"Neg" for i in range(1,12)}
if 'scr' not in st.session_state: st.session_state.scr = {f"s{i}":"Neg" for i in ["I","II","III"]}
if 'ext' not in st.session_state: st.session_state.ext = []

# ==========================================
# 2. LOGIC: PARSER V47 (The Table 3 Solver)
# ==========================================
def normalize(val):
    s = str(val).lower().strip()
    # أهم سطر: بيقبل + و 1 و +w
    return 1 if any(x in s for x in ['+', '1', 'pos', 'yes', 'w']) else 0

def exact_parser_v47(file_bytes, limit_rows=11):
    try:
        xls = pd.ExcelFile(file_bytes)
        
        # نلف على كل الشيتات
        for sheet in xls.sheet_names:
            # نقرأ بدون هيدر عشان نشوف الملف الخام
            df = pd.read_excel(file_bytes, sheet_name=sheet, header=None)
            
            # 1. تحديد مكان كل عمود بدقة
            col_map = {}
            header_row = -1
            
            # نمسح أول 30 سطر
            for r in range(min(30, len(df))):
                matches = 0
                temp_map = {}
                
                for c in range(len(df.columns)):
                    val = str(df.iloc[r, c]).strip().replace(" ","") # No Upper() to keep Case
                    
                    detected = None
                    
                    # Exact Case Match for tricky ones
                    if val in ["c","C","e","E","k","K","s","S"]: detected = val
                    elif val.upper() in ["D","RHD"]: detected = "D"
                    else:
                        # For others, use UPPER
                        if val.upper() in [x.upper() for x in AGS]:
                            for ag in AGS:
                                if ag.upper() == val.upper(): detected = ag; break
                    
                    if detected:
                        temp_map[detected] = c
                        matches += 1
                
                # لو لقينا اكتر من 4 انتيجينات في السطر، يبقى ده سطر العناوين
                if matches >= 4:
                    header_row = r
                    col_map = temp_map
                    # محاولة تكميلية للبحث عن الباقي في نفس السطر
                    break
            
            # 2. سحب البيانات تحت السطر ده
            if header_row != -1:
                start_data = header_row + 1
                final_data = []
                extracted = 0
                curr = start_data
                
                while extracted < limit_rows and curr < len(df):
                    
                    # التحقق من أن الصف يحتوي بيانات (بواسطة عمود D أو C)
                    # نتخطى السطور الفاضية
                    is_valid = False
                    check_list = []
                    if "D" in col_map: check_list.append(col_map["D"])
                    if "C" in col_map: check_list.append(col_map["C"])
                    if "K" in col_map: check_list.append(col_map["K"])
                    
                    for cx in check_list:
                        raw = str(df.iloc[curr, cx]).lower()
                        if any(x in raw for x in ['+', '0', '1', 'w']): 
                            is_valid = True
                            break
                    
                    if is_valid:
                        lbl = f"Cell {extracted+1}" if limit_rows==11 else f"Scn {['I','II','III'][extracted]}"
                        r_dic = {"ID": lbl}
                        
                        for ag in AGS:
                            val = 0
                            if ag in col_map:
                                col_idx = col_map[ag]
                                # نقرأ القيمة من الإكسيل ونحولها
                                val = normalize(df.iloc[curr, col_idx])
                            r_dic[ag] = int(val)
                        
                        final_data.append(r_dic)
                        extracted += 1
                        
                    curr += 1
                
                if extracted >= 1:
                    return pd.DataFrame(final_data), f"Done: Found {extracted} rows in '{sheet}'"

        return None, "Columns Not Found."
        
    except Exception as e: return None, str(e)

# Helpers
def can_out(ag, ph):
    if ph.get(ag,0)==0: return False
    if ag in DOSAGE:
        pr=PAIRS.get(ag)
        if pr and ph.get(pr,0)==1: return False
    return True

def rule_calc(c, r11, i11, r3, i3, ex):
    p, n = 0, 0
    # P11
    for i in range(1,12):
        s = 1 if i11[f"c{i}"]!="Neg" else 0
        h = r11.iloc[i-1].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # P3
    for i,l in enumerate(["I","II","III"]):
        s = 1 if i3[f"s{l}"]!="Neg" else 0
        h = r3.iloc[i].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # EX
    for x in ex:
        if x['s']==1 and x['p'].get(c,0)==1: p+=1
        if x['s']==0 and x['p'].get(c,0)==0: n+=1
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    t = "Std" if (p>=3 and n>=3) else "Mod"
    return ok, p, n, t

def bulk(v): 
    for i in range(1,12): st.session_state.res[f"c{i}"]=v

# UI
with st.sidebar:
    st.header("Config")
    nav = st.radio("Mode", ["Workstation", "Supervisor"])
    if st.button("Reset"): st.session_state.ext=[]; st.rerun()

# ADMIN
if nav == "Supervisor":
    st.title("🛠️ Admin Config")
    if st.text_input("Pwd",type="password")=="admin123":
        t1,t2=st.tabs(["Panel 11","Screen"])
        
        with t1:
            st.info("Upload File (Auto-Detect +w)")
            up=st.file_uploader("P11", type=["xlsx"])
            if up:
                df, m = exact_parser_v47(io.BytesIO(up.getvalue()), 11)
                if df is not None:
                    st.success(m); st.session_state.p11=df; st.rerun()
                else: st.error(m)
            e1 = st.data_editor(st.session_state.p11, hide_index=True)
            if st.button("Save P11"): st.session_state.p11=e1; st.success("OK")
            
        with t2:
            st.info("Upload Screen")
            u2=st.file_uploader("Scr", type=["xlsx"])
            if u2:
                df2, m2 = exact_parser_v47(io.BytesIO(u2.getvalue()), 3)
                if df2 is not None:
                    st.success(m2); st.session_state.p3=df2; st.rerun()
            e2 = st.data_editor(st.session_state.p3, hide_index=True)
            if st.button("Save Scr"): st.session_state.p3=e2; st.success("OK")

# USER
else:
    st.markdown("<h2 class='hospital-header'>MCH Tabuk Serology</h2>", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    L,R=st.columns([1,2])
    with L:
        ac=st.radio("AC", ["Negative","Positive"]); 
        if ac=="Positive": st.error("DAT REQ"); st.stop()
        for x in ["I","II","III"]: st.session_state.scr[f"s{x}"]=st.selectbox(x,["Neg","w+","1+","2+"],key=f"u{x}")
    with R:
        g=st.columns(6); im={}
        for i in range(1,12):
            st.session_state.res[f"c{i}"] = g[(i-1)%6].selectbox(f"{i}",["Neg","w+","1+","2+"],key=f"p{i}")
            im[i]=0 if st.session_state.res[f"c{i}"]=="Neg" else 1
            
    if st.checkbox("Analyze"):
        r11=[st.session_state.p11.iloc[i].to_dict() for i in range(11)]
        r3=[st.session_state.p3.iloc[i].to_dict() for i in range(3)]
        ruled=set()
        
        # Exclude
        for ag in AGS:
            for i,s in im.items():
                if s==0 and can_out(ag, r11[i-1]): ruled.add(ag); break
        scmap={"I":0,"II":1,"III":2}
        for k,v in st.session_state.scr.items():
            if v=="Neg":
                for ag in AGS:
                    if ag not in ruled and can_out(ag, r3[scmap[k.replace("s","")]]): ruled.add(ag)
        
        matches=[]
        for c in [x for x in AGS if x not in ruled]:
            mis=False
            for i,s in im.items():
                if s>0 and r11[i-1].get(c,0)==0: mis=True
            if not mis: matches.append(c)
            
        if not matches: st.error("Inconclusive")
        else:
            allow=True
            for m in matches:
                ok,p,n,msg = rule_calc(m, st.session_state.p11, st.session_state.res, st.session_state.p3, st.session_state.scr, st.session_state.ext)
                st.markdown(f"<div class='status-{'pass' if ok else 'fail'}'><b>Anti-{m}:</b> {msg} ({p}/{n})</div>", unsafe_allow_html=True)
                if not ok: allow=False
            
            if allow:
                if st.button("Print"):
                    h=f"<div class='print-only'><center><h2>MCH Tabuk</h2></center><br>Pt:{nm} | {mr}<hr>Res: Anti-{', '.join(matches)}<br>Valid Rule of 3.<br><br>Sig:________</div><script>window.print()</script>"
                    st.markdown(h, unsafe_allow_html=True)
            else:
                w
