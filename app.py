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

# --- PERMANENT DARK MODE & FONT ENGINE ---
if 'font_size' not in st.session_state: st.session_state.font_size = 20

def apply_dark_theme():
    f_size = st.session_state.font_size
    st.markdown(f"""
        <style>
        /* Force Dark Background */
        .stApp {{ background-color: #0e1117 !important; color: #ffffff !important; }}
        
        /* Force Solid White Text - No Fading */
        p, div, label, span, h1, h2, h3, h4, .stMarkdown, .stRadio label, .stButton p, .stExpander p {{
            font-size: {f_size}px !important;
            color: #ffffff !important;
            opacity: 1.0 !important;
            filter: none !important;
        }}
        
        /* Sidebar Styling */
        div[data-testid="stSidebar"] {{ background-color: #1e1e1e !important; }}

        /* Buttons & Widgets Visibility */
        .stButton>button, div[data-testid="stDownloadButton"]>button {{
            background-color: #262730 !important;
            color: #ffffff !important;
            border: 1px solid #ffffff !important;
            opacity: 1.0 !important;
        }}

        /* Expander Headers */
        .streamlit-expanderHeader {{
            background-color: #262730 !important;
            color: #ffffff !important;
            border-bottom: 1px solid #ffffff !important;
            opacity: 1.0 !important;
        }}

        /* Selectboxes (AI Model) */
        .stSelectbox div[data-baseweb="select"] > div {{
            background-color: #262730 !important;
            color: #ffffff !important;
            border: 1px solid #ffffff !important;
        }}
        </style>
    """, unsafe_allow_html=True)

# --- TOP BAR FONT CONTROLS ---
def render_controls():
    c1, c2, c3 = st.columns([8, 1, 1])
    with c2:
        if st.button("➖"): 
            st.session_state.font_size = max(12, st.session_state.font_size - 2); st.rerun()
    with c3:
        if st.button("➕"): 
            st.session_state.font_size = min(46, st.session_state.font_size + 2); st.rerun()

# --- AI & DATA CORES ---
@st.cache_data
def get_working_models():
    try:
        valid = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        valid.sort(key=lambda x: "flash" not in x); return valid
    except: return ["models/gemini-1.5-flash", "models/gemini-pro"]

def generate_quiz(model_name, topic, num, difficulty, input_type, context_data=None, previous_questions=[]):
    model = genai.GenerativeModel(model_name)
    prompt = f"Medical Quiz. Topic: {topic}. Difficulty: {difficulty}. Num: {num}. JSON ONLY."
    if previous_questions: prompt += f"\nNo repeats: {previous_questions[-20:]}"
    content = [prompt]
    if input_type == "Text/PDF" and context_data: prompt += f"\nContext: {context_data[:10000]}..."; content = [prompt]
    elif input_type == "Image" and context_data: prompt += "\nAnalyze image."; content = [prompt, context_data]
    prompt += "\nFormat: [{\"question\":\"...\", \"options\":{\"A\":\"..\",\"B\":\"..\",\"C\":\"..\",\"D\":\"..\"}, \"correct_option\":\"A\", \"explanation\":\"...\", \"extra_edge\":\"...\"}]"
    
    max_retries, timer = 3, st.empty()
    for attempt in range(max_retries):
        try:
            response = model.generate_content(content if input_type=="Image" else [prompt])
            timer.empty(); txt = response.text
            start, end = txt.find('['), txt.rfind(']') + 1
            return json.loads(txt[start:end])
        except:
            for t in range(20, 0, -1):
                timer.warning(f"⚠️ Cooling down... {t}s"); time.sleep(1)
            timer.empty(); continue
    return []

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f: return json.load(f)
        except: return []
    return []

def save_quiz(topic, score, total, questions, answers):
    history = load_history()
    entry = {"date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "topic": topic, "score": f"{score}/{total}", "data": questions, "user_answers": answers}
    history.insert(0, entry)
    try:
        with open(HISTORY_FILE, "w") as f: json.dump(history, f)
    except: pass
    return history

def create_report(topic, score, total, questions, answers):
    report = f"🎓 QUIZ MASTER REPORT\nTopic: {topic}\nScore: {score}/{total}\n" + "="*50 + "\n\n"
    for i, q in enumerate(questions):
        ans = answers.get(i) or answers.get(str(i))
        report += f"Q{i+1}: {q['question']}\nSTATUS: {'✅ CORRECT' if ans == q['correct_option'] else f'❌ WRONG (Chose {ans})'}\n"
        report += f"OPTIONS:\n" + "\n".join([f" {'->' if k==q['correct_option'] else '  '} {k}: {v}" for k,v in q['options'].items()])
        report += f"\n\nEXPLANATION: {q.get('explanation', 'N/A')}\nEXTRA EDGE: {q.get('extra_edge', 'N/A')}\n\n" + "="*50 + "\n\n" 
    return report

# --- UI APP ---
if 'page' not in st.session_state: st.session_state.page = "home"
if 'quiz_data' not in st.session_state: st.session_state.quiz_data = []
if 'user_answers' not in st.session_state: st.session_state.user_answers = {}
if 'current_index' not in st.session_state: st.session_state.current_index = 0
if 'history' not in st.session_state: st.session_state.history = load_history()

with st.sidebar:
    st.title("🩺 QUIZ MASTER")
    model_choice = st.selectbox("AI Model", get_working_models())
    st.divider()
    if st.button("🏠 New Quiz"): st.session_state.page = "home"; st.rerun()
    st.subheader("📜 Recent History")
    for i, item in enumerate(st.session_state.history):
        if st.button(f"{item['topic']} ({item['score']})", key=f"h_{i}"):
            st.session_state.quiz_data, st.session_state.user_answers = item['data'], item.get('user_answers', {})
            st.session_state.current_index, st.session_state.page = 0, "scorecard"; st.rerun()

apply_dark_theme()
render_controls()

if st.session_state.page == "home":
    st.title("🚀 Generate Quiz")
    method = st.radio("Source", ["Gemini Knowledge", "Paste Text", "Upload PDF", "Upload Image"], horizontal=True)
    ctx, img = None, None
    if method == "Gemini Knowledge": topic = st.text_input("Topic")
    elif method == "Paste Text": topic = st.text_input("Topic Name"); ctx = st.text_area("Content")
    elif method == "Upload PDF":
        topic = st.text_input("Topic Name"); f = st.file_uploader("PDF", type='pdf')
        if f: reader = PyPDF2.PdfReader(f); ctx = "".join([p.extract_text() for p in reader.pages])
    elif method == "Upload Image":
        topic = st.text_input("Topic Name"); f = st.file_uploader("Image", type=['png','jpg','jpeg'])
        if f: img = Image.open(f); st.image(img, width=200)
    c1, c2 = st.columns(2)
    diff, num = c1.select_slider("Difficulty", ["Easy", "Medium", "Hard"]), c2.slider("Questions", 5, 20, 10)
    if st.button("Start Quiz", type="primary"):
        with st.spinner("Generating..."):
            st.session_state.current_topic, st.session_state.current_model = topic, model_choice
            st.session_state.current_input_type = "Image" if img else "Text/PDF" if ctx else "Topic"
            st.session_state.current_context, st.session_state.current_difficulty = (img if img else ctx), diff
            data = generate_quiz(model_choice, topic, num, diff, st.session_state.current_input_type, st.session_state.current_context)
            if data: st.session_state.quiz_data, st.session_state.user_answers, st.session_state.current_index, st.session_state.page = data, {}, 0, "quiz"; st.rerun()

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
        st.session_state.history, st.session_state.saved = save_quiz(st.session_state.current_topic, score, len(st.session_state.quiz_data), st.session_state.quiz_data, st.session_state.user_answers), True; st.rerun()
    
    wrongs = [str(i+1) for i,q in enumerate(st.session_state.quiz_data) if st.session_state.user_answers.get(i)!=q['correct_option']]
    rights = [str(i+1) for i,q in enumerate(st.session_state.quiz_data) if st.session_state.user_answers.get(i)==q['correct_option']]
    j1, j2 = st.columns(2)
    with j1: 
        st.markdown("**❌ Mistakes:**")
        if wrongs: st.markdown(" | ".join([f"[{n}](#q{n})" for n in wrongs]))
        else: st.write("None!")
    with j2:
        st.markdown("**✅ Correct:**")
        st.markdown(" | ".join([f"[{n}](#q{n})" for n in rights]))

    col1, col2, col3 = st.columns(3)
    if col1.button("🏠 Home"): st.session_state.page = "home"; del st.session_state['saved']; st.rerun()
    with col2:
        report = create_report(st.session_state.current_topic, score, len(st.session_state.quiz_data), st.session_state.quiz_data, st.session_state.user_answers)
        st.download_button("📥 Download Result", report, f"Quiz_{st.session_state.current_topic}.txt")
    if col3.button("🔄 Add 10 More"):
        with st.spinner("Adding..."):
            exist = [q['question'] for q in st.session_state.quiz_data]
            new_data = generate_quiz(st.session_state.current_model, st.session_state.current_topic, 10, st.session_state.current_difficulty, st.session_state.current_input_type, st.session_state.current_context, exist)
            if new_data: st.session_state.quiz_data.extend(new_data); del st.session_state['saved']; st.session_state.page = "quiz"; st.session_state.current_index = len(exist); st.rerun()

    for i, q in enumerate(st.session_state.quiz_data):
        ans = st.session_state.user_answers.get(i)
        st.markdown(f"<div id='q{i+1}'></div>", unsafe_allow_html=True)
        label = f"Q{i+1}: {q['question']}"
        with st.expander(label, expanded=False):
            st.write(f"**Your Answer:** {ans} | **Correct:** {q['correct_option']}")
            for opt, txt in q['options'].items():
                if opt == q['correct_option']: st.success(f"{opt}: {txt}")
                elif opt == ans: st.error(f"{opt}: {txt}")
                else: st.write(f"{opt}: {txt}")
            st.info(f"**Explanation:** {q['explanation']}"); st.warning(f"**Extra Edge:** {q['extra_edge']}")
