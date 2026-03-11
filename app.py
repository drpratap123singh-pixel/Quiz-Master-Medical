import streamlit as st
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
import json
import os
import datetime
import time
from PIL import Image
import PyPDF2

# --- CONFIGURATION ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
except:
    api_key = "PASTE_YOUR_KEY_HERE_ONLY_FOR_LOCAL"

genai.configure(api_key=api_key)
HISTORY_FILE = "quiz_history.json"

st.set_page_config(page_title="QUIZ MASTER PRO", layout="wide", page_icon="🩺")

# --- UI ENGINE: BULLETPROOF WHITE THEME ---
if 'font_size' not in st.session_state: st.session_state.font_size = 20

def apply_quiz_ui():
    f_size = st.session_state.font_size
    st.markdown(f"""
        <style>
        .stApp {{ background-color: #ffffff !important; color: #000000 !important; }}
        p, div, label, span, h1, h2, h3, h4, .stMarkdown, .stRadio label, li, td, th {{
            font-size: {f_size}px !important; color: #000000 !important; opacity: 1.0 !important;
        }}
        .stTextInput input, .stTextArea textarea {{
            background-color: #ffffff !important; color: #000000 !important; border: 1px solid #000000 !important;
        }}
        div[data-baseweb="select"] > div {{
            background-color: #ffffff !important; color: #000000 !important; border: 1px solid #000000 !important;
        }}
        ul[data-baseweb="menu"] {{ background-color: #ffffff !important; }}
        li[data-baseweb="option"] {{ color: #000000 !important; }}
        [data-testid="stSidebar"] {{
            background-color: #f8f9fa !important; border-right: 1px solid #cccccc !important;
        }}
        .streamlit-expanderHeader {{
            background-color: #f0f2f6 !important; color: #000000 !important; border: 1px solid #000000 !important;
        }}
        .stExpander {{ background-color: #ffffff !important; border: 1px solid #000000 !important; }}
        .stButton>button, div[data-testid="stDownloadButton"]>button {{
            background-color: #ffffff !important; color: #000000 !important; border: 1px solid #000000 !important; font-weight: bold !important;
        }}
        [data-testid="stSidebar"] button {{ text-align: left !important; border: none !important; background: transparent !important; }}
        
        /* Table Styling for Match the Following */
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 15px; }}
        th, td {{ border: 1px solid #000000 !important; padding: 8px; text-align: left; }}
        th {{ background-color: #f0f2f6 !important; }}
        </style>
    """, unsafe_allow_html=True)

# --- TOP BAR CONTROLS ---
def render_controls():
    c1, c2, c3 = st.columns([8, 1, 1])
    with c2:
        if st.button("➖"): st.session_state.font_size = max(12, st.session_state.font_size - 2); st.rerun()
    with c3:
        if st.button("➕"): st.session_state.font_size = min(46, st.session_state.font_size + 2); st.rerun()

# --- AI CORE ---
@st.cache_data
def get_working_models():
    try:
        valid = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        valid.sort(key=lambda x: "flash" not in x)
        return valid
    except: return ["models/gemini-1.5-flash", "models/gemini-pro"]

def generate_quiz(model_name, topic, num, difficulty, input_type, context_data=None, previous_questions=[]):
    model = genai.GenerativeModel(model_
