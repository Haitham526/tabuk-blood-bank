import streamlit as st
import pandas as pd
import io
from datetime import date

# ==========================================
# 1. إعدادات الصفحة
# ==========================================
st.set_page_config(page_title="MCH Tabuk - Serology", layout="wide", page_icon="🏥")

# تحسينات الشكل والطباعة
st.markdown("""
<style>
    @media print {
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; }
        .block-container { padding: 0 !important; }
        .print-only { display: block !important; }
        .results-box { border: 2px solid #333; padding: 15px; margin-top: 20px; font-family: 'Times New Roman'; font-size: 14px; }
        .consultant-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; }
    }
    
    .hospital-header { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: 'Arial'; color: #003366; }
    
    /* توسيع الجدول */
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    
    /* توقيع الدكتور هيثم */
    .signature-badge {
        position: fixed; bottom: 10px; ri
