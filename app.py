import streamlit as st
import pandas as pd
import io
from datetime import date

# 1. SETUP
st.set_page_config(page_title="MCH Tabuk - Serology", layout="wide", page_icon="🏥")

st.markdown("""
<style>
    @media print {
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; }
        .block-container { padding: 0 !important; }
        .print-only { display: block !important; }
        .results-box { border: 2px solid #333; padding: 15px; font-family: 'Times New Roman'; font-size:14px;}
        .consultant-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; }
    }
    .hospital-header { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: 'Arial'; color: #003366; }
    .signature-badge { position: fixed; bottom: 10px; right: 15px; font-family: 'Georgia', serif; font-size: 12px; color: #8B0000; background: rgba(255,255,255,0.95); padding: 5px 10px; border: 1px solid #eecaca; border-radius: 5px; z-index:99; } 
    div[data-testid="stDataEditor"] table { width: 100% !important; } 
    .status-pass { background-color: #d1e7dd; padding: 10px; border-radius: 5px; color: #0f5132; margin-bottom:5px; } 
    .status-fail { background-color: #f8d7da; padding: 10px; border-radius: 5px; color: #842029; margin-bottom:5px; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='signature-badge no-print'><b>Dr. Haitham Ismail</b><br>Clinical Hematology/Transfusion Consultant</div>", unsafe_allow_html=True)

antigens_order = ["D", "C", "E", "c", "e", "Cw", "K", "k", "Kpa", "Kpb", "Jsa", "Jsb", "Fya", "Fyb", "Jka", "Jkb", "Lea", "Leb", "P1", "M", "N", "S", "s", "Lua", "Lub", "Xga"]
allele_pairs = {'C':'c', 'c':'C', 'E':'e', 'e':'E', 'K':'k', 'k':'K', 'Kpa':'Kpb', 'Kpb':'Kpa', 'Fya':'Fyb', 'Fyb':'Fya', 'Jka':'Jkb', 'Jkb':'Jka', 'M':'N', 'N':'M', 'S':'s', 's':'S', 'Lea':'Leb', 'Leb':'Lea'}
STRICT_DOSAGE = ["C", "c", "E", "e", "Fya", "Fyb", "Jka", "Jkb", "M", "N", "S", "s"]

# STATE
if 'panel_11' not in st.session_state:
    st.session_state.panel_11 = pd.DataFrame([{"ID": f"Cell {i+1}", **{ag: 0 for ag in antigens_order}} for i in range(11)])
if 'panel_3' not in st.session_state:
    st.session_state.panel_3 = pd.DataFrame([{"ID": f"Scn {i}", **{ag: 0 for ag in antigens_order}} for i in ["I", "II", "III"]])
if 'inputs' not in st.session_state: st.session_state.inputs = {f"c{i}": "Neg" for i in range(1, 12)}
if 'inputs_s' not in st.session_state: st.session_state.inputs_s = {f"s{i}": "Neg" for i in ["I", "II", "III"]}
if 'extra_cells' not in st.session_state: st.session_state.extra_cells = []
if 'admin_mode' not in st.session_state: st.session_state.admin_mode = False

# 2. STRICT CASE-SENSITIVE PARSER (V31 FIX)
def clean_header_raw(val):
    # لا نستخدم .upper() هنا للحفاظ على c vs C
    return str(val).strip().replace("\n","").replace(" ","").replace("(","").replace(")","")

def normalize_val(val):
    # تنظيف قيم الداتا (+ و 0)
    s = str(val).lower().strip()
    if any(x in s for x in ['+', '1', 'pos', 'yes', 'w']): return 1
    return 0

def strict_scan(file_bytes):
    xls = pd.ExcelFile(file_bytes)
    
    # البحث في كل الصفحات
    for sheet in xls.sheet_names:
        df = pd.read_excel(file_bytes, sheet_name=sheet, header=None)
        
        best_row_idx = -1
        best_row_matches = 0
        best_col_map = {}
        
        # Scan first 20 rows
        for r in range(min(20, len(df))):
            row_map = {}
            match_count = 0
            
            for c in range(len(df.columns)):
                # القيمة الخام بدون تكبير حروف
                cell_val = clean_header_raw(df.iloc[r, c])
                
                real_name = None
                
                # 1. المطابقة الدقيقة الحساسة للحالة (C vs c)
                if cell_val in antigens_order:
                    real_name = cell_val
                
                # 2. حالات خاصة للملفات الصعبة
                elif cell_val == "D" or cell_val == "RhD": real_name = "D"
                # C vs c logic
                elif cell_val == "C": real_name = "C"
                elif cell_val == "c": real_name = "c"
                # E vs e logic
                elif cell_val == "E": real_name = "E"
                elif cell_val == "e": real_name = "e"
                # S vs s logic
                elif cell_val == "S": real_name = "S"
                elif cell_val == "s": real_name = "s"
                # K v
