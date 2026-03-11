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
    model = genai.GenerativeModel(model_name)
    
    # --- THE SUPER PROMPT (UPDATED FOR MARKDOWN TABLES) ---
    prompt = f"""
    Act as an expert Medical Examiner creating a {difficulty} level test for USMLE Step 2 / NEET PG.
    Generate {num} highly advanced MCQs on the topic: "{topic}".
    
    CRITICAL QUESTION RULES:
    1. Clinical Vignettes: Long scenarios asking for 'next best step' or mechanism.
    2. Match the Following: YOU MUST FORMAT THE MATCHING LISTS AS A MARKDOWN TABLE DIRECTLY INSIDE THE "question" STRING! 
       Example of required format inside the string:
       "Match the following:
       | Column 1 | Column 2 |
       |---|---|
       | 1. Disease A | P. Feature X |
       | 2. Disease B | Q. Feature Y |"
    3. Statement Analysis: e.g., "Which statement is INCORRECT?"
    
    Output VALID JSON ONLY.
    """
    if previous_questions: prompt += f"\nDO NOT repeat these questions: {previous_questions[-20:]}"
    content = [prompt]
    
    if input_type == "Text/PDF" and context_data:
        prompt += f"\nGenerate questions strictly based on this Context: {context_data[:12000]}..."
        content = [prompt]
    elif input_type == "Image" and context_data:
        prompt += "\nAnalyze the provided image(s) and generate clinical questions."
        content = [prompt]
        if isinstance(context_data, list): content.extend(context_data)
        else: content.append(context_data)
        
    prompt += '\nFormat exactly like this: [{"question":"...", "options":{"A":"..","B":"..","C":"..","D":".."}, "correct_option":"A", "explanation":"...", "extra_edge":"..."}]'
    
    max_retries, timer = 3, st.empty()
    for attempt in range(max_retries):
        try:
            response = model.generate_content(content)
            timer.empty(); txt = response.text
            start, end = txt.find('['), txt.rfind(']') + 1
            return json.loads(txt[start:end])
        except ResourceExhausted:
            for t in range(20, 0, -1):
                timer.warning(f"⚠️ Cooling down... {t}s"); time.sleep(1)
            timer.empty(); continue
        except: return []
    return []

# --- SAFE KEY EXTRACTOR ---
def get_correct_ans(q_dict):
    return q_dict.get('correct_option', q_dict.get('correct', q_dict.get('answer', 'A')))

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
        correct = get_correct_ans(q)
        report += f"Q{i+1}: \n{q['question']}\nSTATUS: {'✅ CORRECT' if ans == correct else f'❌ WRONG (Chose {ans})'}\n"
        report += f"OPTIONS:\n" + "\n".join([f" {'->' if k==correct else '  '} {k}: {v}" for k,v in q.get('options', {}).items()])
        report += f"\n\nEXPLANATION: {q.get('explanation', 'N/A')}\nEXTRA EDGE: {q.get('extra_edge', 'N/A')}\n\n" + "="*50 + "\n\n" 
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
    ctx, img_list = None, []
    
    if method == "Gemini Knowledge": topic = st.text_input("Topic")
    elif method == "Paste Text": topic = st.text_input("Topic Name"); ctx = st.text_area("Content")
    elif method == "Upload PDF":
        topic = st.text_input("Topic Name"); f = st.file_uploader("PDF", type='pdf')
        if f: reader = PyPDF2.PdfReader(f); ctx = "".join([p.extract_text() for p in reader.pages])
    elif method == "Upload Image":
        topic = st.text_input("Topic Name")
        f_list = st.file_uploader("Upload Images", type=['png','jpg','jpeg'], accept_multiple_files=True)
        if f_list:
            for file in f_list: img_list.append(Image.open(file))
    
    c1, c2 = st.columns(2)
    diff = c1.select_slider("Difficulty", ["Easy", "Medium", "Hard"])
    num = c2.slider("Questions", 5, 20, 10)
    
    if st.button("Start Quiz", type="primary"):
        with st.spinner("Generating..."):
            st.session_state.current_topic = topic
            st.session_state.current_model = model_choice
            st.session_state.current_input_type = "Image" if img_list else "Text/PDF" if ctx else "Topic"
            st.session_state.current_context = (img_list if img_list else ctx)
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
    
    # Render using Markdown so the tables display as grids!
    st.markdown(f"### Q: \n{q['question']}")
    
    opts = list(q.get('options', {}).keys())
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
    score = sum([1 for i,q in enumerate(st.session_state.quiz_data) if st.session_state.user_answers.get(i) == get_correct_ans(q)])
    st.title(f"Score: {score}/{len(st.session_state.quiz_data)}")
    
    if 'saved' not in st.session_state:
        st.session_state.history = save_quiz(st.session_state.current_topic, score, len(st.session_state.quiz_data), st.session_state.quiz_data, st.session_state.user_answers)
        st.session_state.saved = True
        st.rerun()
    
    wrongs = [str(i+1) for i,q in enumerate(st.session_state.quiz_data) if st.session_state.user_answers.get(i) != get_correct_ans(q)]
    rights = [str(i+1) for i,q in enumerate(st.session_state.quiz_data) if st.session_state.user_answers.get(i) == get_correct_ans(q)]
    
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
            c_model = st.session_state.get('current_model', get_working_models()[0])
            c_diff = st.session_state.get('current_difficulty', "Medium")
            c_type = st.session_state.get('current_input_type', "Topic")
            c_ctx = st.session_state.get('current_context', None)
            
            new_data = generate_quiz(c_model, st.session_state.current_topic, 10, c_diff, c_type, c_ctx, exist)
            if new_data: 
                st.session_state.quiz_data.extend(new_data)
                del st.session_state['saved']
                st.session_state.page = "quiz"
                st.session_state.current_index = len(exist)
                st.rerun()

    for i, q in enumerate(st.session_state.quiz_data):
        ans = st.session_state.user_answers.get(i)
        correct_ans = get_correct_ans(q)
        st.markdown(f"<div id='q{i+1}'></div>", unsafe_allow_html=True)
        
        # Kept the expander label simple so it doesn't break when a table is generated inside it
        with st.expander(f"Q{i+1} Review", expanded=False):
            st.markdown(f"**{q['question']}**") # Renders the Markdown table beautifully inside!
            st.write(f"**Your Answer:** {ans} | **Correct:** {correct_ans}")
            for opt, txt in q.get('options', {}).items():
                if opt == correct_ans: st.success(f"{opt}: {txt}")
                elif opt == ans: st.error(f"{opt}: {txt}")
                else: st.write(f"{opt}: {txt}")
            st.info(f"**Explanation:** {q.get('explanation', 'N/A')}")
            st.warning(f"**Extra Edge:** {q.get('extra_edge', 'N/A')}")
