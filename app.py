import streamlit as st
import pandas as pd
import io
from datetime import date

# ==========================================
# 1. SETUP & STYLING
# ==========================================
st.set_page_config(page_title="MCH Tabuk Serology", layout="wide", page_icon="🏥")

st.markdown("""
<style>
    @media print {
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; }
        .block-container { padding: 0 !important; }
        .print-only { display: block !important; }
        .results-box { border: 2px solid #333; padding: 15px; margin-top: 10px; font-family: 'Times New Roman'; }
        .footer-print { position: fixed; bottom: 0; width: 100%; text-align: center; font-size: 10px; border-top: 1px solid #ccc; }
    }
    
    .hospital-header { 
        text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 15px; margin-bottom: 20px; 
        font-family: 'Arial'; color: #003366; 
    }
    
    .status-pass { background-color: #d1e7dd; padding: 8px; border-radius: 5px; color: #0f5132; border-left: 5px solid #198754; margin-bottom:5px; }
    .status-fail { background-color: #f8d7da; padding: 8px; border-radius: 5px; color: #842029; border-left: 5px solid #dc3545; margin-bottom:5px; }
    
    .dr-signature {
        position: fixed; bottom: 10px; right: 15px;
        font-family: 'Georgia', serif; font-size: 12px; color: #8B0000;
        background: rgba(255,255,255,0.95); padding: 5px 10px; border: 1px solid #eecaca; z-index: 99;
    }
    
    /* Grid Fixes */
    div[data-testid="stDataEditor"] table { width: 100% !important; }
</style>
""", unsafe_a
