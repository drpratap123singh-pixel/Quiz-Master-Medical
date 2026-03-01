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

# --- UI ENGINE: BULLETPROOF WHITE THEME (From Exam Simulator) ---
if 'font_size' not in st.session_state: st.session_state.font_size = 20

def apply_quiz_ui():
    f_size = st.session_state.font_size
    st.markdown(f"""
        <style>
        /* 1. FORCE MAIN BACKGROUND WHITE */
        .stApp {{ background-color: #ffffff !important; color: #000000 !important; }}
        
        /* 2. FORCE TEXT BLACK & VISIBLE */
        p, div, label, span, h1, h2, h3, h4, .stMarkdown, .stRadio label, li {{
            font-size: {f_size}px !important;
            color: #000000 !important;
            opacity: 1.0 !important;
            filter: none !important;
            transition: none !important;
        }}

        /* 3. WHITE INPUT BOXES & TEXT AREAS */
        .stTextInput input, .stTextArea textarea {{
            background-color: #ffffff !important;
            color: #000000 !important;
            border: 1px solid #000000 !important;
        }}
        
        /* Dropdowns */
        div[data-baseweb="select"] > div {{
            background-color: #ffffff !important;
            color: #000000 !important;
            border: 1px solid #000000 !important;
        }}
        ul[data-baseweb="menu"] {{ background-color: #ffffff !important; }}
        li[data-baseweb="option"] {{ color: #000000 !important; }}

        /* 4. SIDEBAR */
        [data-testid="stSidebar"] {{
            background-color: #f8f9fa !important;
            border-right: 1px solid #cccccc !important;
        }}

        /* 5. EXPANDERS (For Scorecard) */
        .streamlit-expanderHeader {{
            background-color: #f0f2f6 !important;
            color: #000000 !important;
            border: 1px solid #000000 !important;
            opacity: 1.0 !important;
        }}
        .streamlit-expanderHeader:hover, .streamlit-expanderHeader:active, .streamlit-expanderHeader:focus {{
            background-color: #f0f2f6 !important;
            color: #000000 !important;
            opacity: 1.0 !important;
        }}
        .stExpander {{
            background-color: #ffffff !important;
            border: 1px solid #000000 !important;
        }}

        /* 6. BUTTONS */
        .stButton>button, div[data-testid="stDownloadButton"]>button {{
            background-color: #ffffff !important;
            color: #000000 !important;
            border: 1px solid #000000 !important;
            font-weight: bold !important;
        }}
        
        /* History Sidebar Buttons */
        [data-testid="stSidebar"] button {{
            text-align: left !important;
            border: none !important;
            background: transparent !important;
        }}
        </style>
    """, unsafe_allow_html=True)

# --- TOP BAR CONTROLS ---
def render_controls():
    c1, c2, c3 = st.columns([8, 1, 1])
    with c2:
        if st.button("➖"): 
            st.session_state.font_size = max(12, st.session_state.font_size - 2); st.rerun()
    with c3:
        if st.button("➕"): 
            st.session_state.font_size = min(46, st.session_state.font_size + 2); st.rerun()

# --- AI CORE ---
@st.cache_data
def get_working_models():
    try:
        valid = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        valid.sort(key=lambda x: "flash" not in x)
        return valid
    except: return ["models/gemini-1.5-flash", "models/gemini-pro"]

def generate_quiz(model_name, topic, num, difficulty, input_type, context_data=None, previous_questions=[]):
    model = genai.GenerativeModel(model_name)
    prompt = f"Act as a Medical Consultant. Create a {difficulty} quiz with {num} questions on {topic}. Output VALID JSON ONLY. Short explanations."
    if previous_questions: prompt += f"\nAvoid these: {previous_questions[-20:]}"
    content = [prompt]
    if input_type == "Text/PDF" and context_data:
        prompt += f"\nContext: {context_data[:10000]}..."; content = [prompt]
    elif input_type == "Image" and context_data:
        prompt += "\nAnalyze image."; content = [prompt, context_data]
    prompt += "\nFormat: [{\"question\":\"...\", \"options\":{\"A\":\"..\",\"B\":\"..\",\"C\":\"..\",\"D\":\"..\"}, \"correct_option\":\"A\", \"explanation\":\"...\", \"extra_edge\":\"...\"}]"
    
    max_retries, timer = 3, st.empty()
    for attempt in range(max_retries):
        try:
            response = model.generate_content(content if input_type=="Image" else [prompt])
            timer.empty(); txt = response.text
            start, end = txt.find('['), txt.rfind(']') + 1
            return json.loads(txt[start:end])
        except ResourceExhausted:
            for t in range(20, 0, -1):
                timer.warning(f"⚠️ Cooling down... {t}s"); time.sleep(1)
            timer.empty(); continue
        except: return []
    return []

# --- STORAGE ---
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
        correct = q['correct_option']
        report += f"Q{i+1}: {q['question']}\nSTATUS: {'✅ CORRECT' if ans == correct else f'❌ WRONG (Chose {ans})'}\n"
        report += f"OPTIONS:\n" + "\n".join([f" {'->' if k==correct else '  '} {k}: {v}" for k,v in q['options'].items()])
        report += f"\n\nEXPLANATION: {q.get('explanation', 'N/A')}\nEXTRA EDGE: {q.get('extra_edge', 'N/A')}\n\n"
        report += "="*50 + "\n\n" 
    return report

# --- UI LOGIC ---
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
    
    # --- FIXED: AttributeError & IndentationError resolved below ---
    for i, item in enumerate(st.session_state.history):
        if st.button(f"{item['topic']} ({item['score']})", key=f"h_{i}"):
            st.session_state.quiz_data = item['data']
            st.session_state.user_answers = item.get('user_answers', {})
            st.session_state.current_topic = item['topic'] 
            st.session_state.saved = True 
            st.session_state.current_index = 0
            st.session_state.page = "scorecard"
            st.rerun()

apply_quiz_ui()
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
    diff = c1.select_slider("Difficulty", ["Easy", "Medium", "Hard"])
    num = c2.slider("Questions", 5, 20, 10)
    
    if st.button("Start Quiz", type="primary"):
        with st.spinner("Generating..."):
            st.session_state.current_topic = topic
            st.session_state.current_model = model_choice
            st.session_state.current_input_type = "Image" if img else "Text/PDF" if ctx else "Topic"
            st.session_state.current_context = (img if img else ctx)
            st.session_state.current_difficulty = diff
            
            data = generate_quiz(model_choice, topic, num, diff, st.session_state.current_input_type, st.session_state.current_context)
            if data: 
                st.session_state.quiz_data = data
                st.session_state.user_answers = {}
                st.session_state.current_index = 0
                st.session_state.page = "quiz"
                st.rerun()

elif st.session_state.page == "quiz":
    q = st.session_state.quiz_data[st.session_state.current_index]
    st.progress((st.session_state.current_index + 1) / len(st.session_state.quiz_data))
    st.subheader(f"Q: {q['question']}")
    
    opts = list(q['options'].keys())
    prev = st.session_state.user_answers.get(st.session_state.current_index)
    sel = st.radio("Choose:", opts, format_func=lambda x: f"{x}: {q['options'][x]}", key=f"r_{st.session_state.current_index}", index=opts.index(prev) if prev in opts else None)
    
    if sel: st.session_state.user_answers[st.session_state.current_index] = sel
    
    c1, c2 = st.columns(2)
    if c1.button("Prev") and st.session_state.current_index > 0: 
        st.session_state.current_index -= 1
        st.rerun()
    
    if st.session_state.current_index < len(st.session_state.quiz_data) - 1:
        if c2.button("Next"): 
            st.session_state.current_index += 1
            st.rerun()
    elif c2.button("Finish"): 
        st.session_state.page = "scorecard"
        st.rerun()

elif st.session_state.page == "scorecard":
    st.balloons()
    score = sum([1 for i,q in enumerate(st.session_state.quiz_data) if st.session_state.user_answers.get(i)==q['correct_option']])
    st.title(f"Score: {score}/{len(st.session_state.quiz_data)}")
    
    if 'saved' not in st.session_state:
        st.session_state.history = save_quiz(st.session_state.current_topic, score, len(st.session_state.quiz_data), st.session_state.quiz_data, st.session_state.user_answers)
        st.session_state.saved = True
        st.rerun()
    
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
    if col1.button("🏠 Home"): 
        st.session_state.page = "home"
        del st.session_state['saved']
        st.rerun()
    with col2:
        report = create_report(st.session_state.current_topic, score, len(st.session_state.quiz_data), st.session_state.quiz_data, st.session_state.user_answers)
        st.download_button("📥 Download Result", report, f"Quiz_{st.session_state.current_topic}.txt")
    if col3.button("🔄 Add 10 More"):
        with st.spinner("Adding..."):
            exist = [q['question'] for q in st.session_state.quiz_data]
            new_data = generate_quiz(st.session_state.current_model, st.session_state.current_topic, 10, st.session_state.current_difficulty, st.session_state.current_input_type, st.session_state.current_context, exist)
            if new_data: 
                st.session_state.quiz_data.extend(new_data)
                del st.session_state['saved']
                st.session_state.page = "quiz"
                st.session_state.current_index = len(exist)
                st.rerun()

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
            st.info(f"**Explanation:** {q['explanation']}")
            st.warning(f"**Extra Edge:** {q.get('extra_edge', 'N/A')}")
