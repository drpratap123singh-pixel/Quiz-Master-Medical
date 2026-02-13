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

# --- DYNAMIC FONT & THEME ENGINE ---
if 'font_size' not in st.session_state: st.session_state.font_size = 20

def apply_custom_styles(theme):
    f_size = st.session_state.font_size
    
    themes = {
        "Light": {"bg": "#ffffff", "text": "#1a1a1a", "card": "#f8f9fa", "sub": "#495057"},
        "Dark": {"bg": "#0e1117", "text": "#ffffff", "card": "#262730", "sub": "#bfbfbf"},
        "Sepia (Tinted)": {"bg": "#f4ecd8", "text": "#433422", "card": "#e4dcc8", "sub": "#5f4b32"}
    }
    colors = themes.get(theme, themes["Light"])

    st.markdown(f"""
        <style>
        .stApp {{ background-color: {colors['bg']}; color: {colors['text']}; }}
        
        /* Force high contrast visibility at all times (NO FADING) */
        p, div, label, span, h1, h2, h3, h4, .stMarkdown, .stRadio label {{
            font-size: {f_size}px !important;
            color: {colors['text']} !important;
            opacity: 1 !important;
            filter: none !important;
        }}
        
        .stCaption {{ font-size: {f_size - 4}px !important; color: {colors['sub']} !important; }}
        
        /* Make expanders and cards bright and clear */
        .streamlit-expanderHeader, .stExpander {{
            background-color: {colors['card']} !important;
            border: 1px solid {colors['sub']} !important;
        }}
        
        /* Better button visibility */
        .stButton>button {{
            border: 2px solid {colors['sub']} !important;
            font-weight: bold !important;
        }}
        </style>
    """, unsafe_allow_html=True)

# --- 1. AUTO-DETECT WORKING MODELS ---
@st.cache_data
def get_working_models():
    try:
        valid_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                valid_models.append(m.name)
        valid_models.sort(key=lambda x: "flash" not in x)
        return valid_models
    except:
        return ["models/gemini-1.5-flash", "models/gemini-pro"]

# --- DATA MANAGER ---
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f: return json.load(f)
        except: return []
    return []

def save_quiz_to_history(topic, score, total, questions, user_answers):
    history = load_history()
    entry = {"date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "topic": topic, "score": f"{score}/{total}", "data": questions, "user_answers": user_answers}
    history.insert(0, entry) 
    try:
        with open(HISTORY_FILE, "w") as f: json.dump(history, f)
    except: pass
    return history

def create_text_report(topic, score, total, questions, user_answers):
    report = f"🎓 QUIZ MASTER REPORT\nTopic: {topic}\nScore: {score}/{total}\n" + "="*50 + "\n\n"
    for i, q in enumerate(questions):
        ans = user_answers.get(i) or user_answers.get(str(i))
        correct = q['correct_option']
        report += f"Q{i+1}: {q['question']}\nSTATUS: {'✅ CORRECT' if ans == correct else f'❌ WRONG (Chose {ans})'}\n"
        report += f"OPTIONS:\n" + "\n".join([f" {'->' if k==correct else '  '} {k}: {v}" for k,v in q['options'].items()])
        report += f"\n\nEXPLANATION: {q.get('explanation', 'N/A')}\nEXTRA EDGE: {q.get('extra_edge', 'N/A')}\n"
        report += "\n" + "="*50 + "\n\n" 
    return report

def generate_quiz(model_name, topic, num, difficulty, input_type, context_data=None, previous_questions=[]):
    model = genai.GenerativeModel(model_name)
    prompt = f"Act as a Medical Consultant. Create a {difficulty} quiz with {num} questions on {topic}. Output VALID JSON ONLY. Short explanations."
    if previous_questions: prompt += f"\nAvoid these: {previous_questions[-20:]}"
    content = [prompt]
    if input_type == "Text/PDF" and context_data:
        prompt += f"\nContext: {context_data[:10000]}..."
        content = [prompt]
    elif input_type == "Image" and context_data:
        prompt += "\nAnalyze image."; content = [prompt, context_data]
    prompt += "\nFormat: [{\"question\":\"...\", \"options\":{\"A\":\"..\",\"B\":\"..\",\"C\":\"..\",\"D\":\"..\"}, \"correct_option\":\"A\", \"explanation\":\"...\", \"extra_edge\":\"...\"}]"
    if input_type != "Image": content = [prompt]
    else: content[0] = prompt

    max_retries, timer_placeholder = 3, st.empty()
    for attempt in range(max_retries):
        try:
            response = model.generate_content(content)
            timer_placeholder.empty()
            txt = response.text
            start, end = txt.find('['), txt.rfind(']') + 1
            return json.loads(txt[start:end])
        except ResourceExhausted:
            for t in range(20, 0, -1):
                timer_placeholder.warning(f"⚠️ Cooling down... {t}s"); time.sleep(1)
            timer_placeholder.empty(); continue
        except: return []
    return []

# --- SHARED UI: FONT CONTROLS ---
def render_font_controls():
    c1, c2, c3 = st.columns([8, 1, 1])
    with c2:
        if st.button("➖"): 
            st.session_state.font_size = max(12, st.session_state.font_size - 2)
            st.rerun()
    with c3:
        if st.button("➕"): 
            st.session_state.font_size = min(40, st.session_state.font_size + 2)
            st.rerun()

# --- APP UI ---
if 'page' not in st.session_state: st.session_state.page = "home"
if 'quiz_data' not in st.session_state: st.session_state.quiz_data = []
if 'user_answers' not in st.session_state: st.session_state.user_answers = {}
if 'current_index' not in st.session_state: st.session_state.current_index = 0
if 'history' not in st.session_state: st.session_state.history = load_history()

with st.sidebar:
    st.title("🩺 QUIZ MASTER")
    theme_choice = st.selectbox("Theme", ["Light", "Dark", "Sepia (Tinted)"])
    models = get_working_models()
    model_choice = st.selectbox("AI Model", models) if models else "models/gemini-1.5-flash"
    st.divider()
    if st.button("🏠 New Quiz"):
        st.session_state.page = "home"; st.rerun()
    st.subheader("📜 Recent History")
    for i, item in enumerate(st.session_state.history):
        if st.button(f"{item['topic']} ({item['score']})", key=f"hist_{i}"):
            st.session_state.quiz_data = item['data']; st.session_state.user_answers = item.get('user_answers', {}); st.session_state.current_index = 0; st.session_state.page = "scorecard"; st.rerun()

apply_custom_styles(theme_choice)
render_font_controls()

if st.session_state.page == "home":
    st.title("🚀 Generate Quiz")
    method = st.radio("Source", ["Gemini Knowledge", "Paste Text", "Upload PDF", "Upload Image"], horizontal=True)
    ctx, img = None, None
    if method == "Gemini Knowledge": topic = st.text_input("Topic")
    elif method == "Paste Text": topic = st.text_input("Topic Name"); ctx = st.text_area("Content")
    elif method == "Upload PDF":
        topic = st.text_input("Topic Name"); f = st.file_uploader("PDF", type='pdf')
        if f: 
            reader = PyPDF2.PdfReader(f)
            ctx = "".join([p.extract_text() for p in reader.pages])
    elif method == "Upload Image":
        topic = st.text_input("Topic Name"); f = st.file_uploader("Image", type=['png','jpg','jpeg'])
        if f: img = Image.open(f); st.image(img, width=200)

    c1, c2 = st.columns(2)
    diff = c1.select_slider("Difficulty", ["Easy", "Medium", "Hard"])
    num = c2.slider("Questions", 5, 20, 10)

    if st.button("Start Quiz", type="primary"):
        with st.spinner("Generating..."):
            st.session_state.current_topic, st.session_state.current_model, st.session_state.current_input_type = topic, model_choice, ("Image" if img else "Text/PDF" if ctx else "Topic")
            st.session_state.current_context, st.session_state.current_difficulty = (img if img else ctx), diff
            data = generate_quiz(model_choice, topic, num, diff, st.session_state.current_input_type, st.session_state.current_context)
            if data: st.session_state.quiz_data = data; st.session_state.user_answers = {}; st.session_state.current_index = 0; st.session_state.page = "quiz"; st.rerun()

elif st.session_state.page == "quiz":
    q = st.session_state.quiz_data[st.session_state.current_index]
    st.progress((st.session_state.current_index + 1) / len(st.session_state.quiz_data))
    st.subheader(f"Q: {q['question']}")
    opts = list(q['options'].keys())
    prev = st.session_state.user_answers.get(st.session_state.current_index)
    sel = st.radio("Choose:", opts, format_func=lambda x: f"{x}: {q['options'][x]}", key=f"r_{st.session_state.current_index}", index=opts.index(prev) if prev in opts else None)
    if sel: st.session_state.user_answers[st.session_state.current_index] = sel
    c1, c2 = st.columns(2)
    if c1.button("Prev") and st.session_state.current_index > 0: st.session_state.current_index -= 1; st.rerun()
    if st.session_state.current_index < len(st.session_state.quiz_data) - 1:
        if c2.button("Next"): st.session_state.current_index += 1; st.rerun()
    elif c2.button("Finish"): st.session_state.page = "scorecard"; st.rerun()

elif st.session_state.page == "scorecard":
    st.balloons()
    score = sum([1 for i,q in enumerate(st.session_state.quiz_data) if st.session_state.user_answers.get(i)==q['correct_option']])
    st.title(f"Score: {score}/{len(st.session_state.quiz_data)}")
    if 'saved' not in st.session_state:
        st.session_state.history = save_quiz_to_history(st.session_state.current_topic, score, len(st.session_state.quiz_data), st.session_state.quiz_data, st.session_state.user_answers)
        st.session_state.saved = True; st.rerun()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🏠 Start Fresh"): st.session_state.page = "home"; del st.session_state['saved']; st.rerun()
    with col2:
        report = create_text_report(st.session_state.current_topic, score, len(st.session_state.quiz_data), st.session_state.quiz_data, st.session_state.user_answers)
        st.download_button("📥 Download Result", report, f"Quiz_{st.session_state.current_topic}.txt")
    with col3:
        if st.button("🔄 Add 10 More"):
            with st.spinner("Adding..."):
                exist = [q['question'] for q in st.session_state.quiz_data]
                new_data = generate_quiz(st.session_state.current_model, st.session_state.current_topic, 10, st.session_state.current_difficulty, st.session_state.current_input_type, st.session_state.current_context, exist)
                if new_data: st.session_state.quiz_data.extend(new_data); del st.session_state['saved']; st.session_state.page = "quiz"; st.session_state.current_index = len(exist); st.rerun()

    wrongs = [str(i+1) for i,q in enumerate(st.session_state.quiz_data) if st.session_state.user_answers.get(i)!=q['correct_option']]
    if wrongs: st.error(f"❌ Mistakes: {', '.join(wrongs)}")
    
    for i, q in enumerate(st.session_state.quiz_data):
        ans = st.session_state.user_answers.get(i)
        color = "green" if ans == q['correct_option'] else "red"
        with st.expander(f"Q{i+1} [{color.upper()}]: {q['question']}"):
            st.write(f"**Your Answer:** {ans} | **Correct:** {q['correct_option']}")
            for opt, txt in q['options'].items():
                if opt == q['correct_option']: st.success(f"{opt}: {txt}")
                elif opt == ans: st.error(f"{opt}: {txt}")
                else: st.write(f"{opt}: {txt}")
            st.info(f"**Explanation:** {q['explanation']}"); st.warning(f"**Extra Edge:** {q['extra_edge']}")
