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
#
