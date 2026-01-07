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

# File to store history
HISTORY_FILE = "quiz_history.json"

st.set_page_config(page_title="QUIZ MASTER PRO", layout="wide", page_icon="🩺")

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
    entry = {
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "topic": topic,
        "score": f"{score}/{total}",
        "data": questions,
        "user_answers": user_answers
    }
    history.insert(0, entry) 
    try:
        with open(HISTORY_FILE, "w") as f: json.dump(history, f)
    except: pass
    return history

# --- REPORT GENERATOR ---
def create_text_report(topic, score, total, questions, user_answers):
    report = f"🎓 QUIZ MASTER REPORT\nTopic: {topic}\n"
    report += f"Score: {score}/{total}\n" + "="*50 + "\n\n"
    for i, q in enumerate(questions):
        ans = user_answers.get(i) or user_answers.get(str(i))
        correct = q['correct_option']
        status = "✅ CORRECT" if ans == correct else f"❌ WRONG (Chose {ans})"
        report += f"Q{i+1}: {q['question']}\n{status}\n"
        report += f"Explanation: {q.get('explanation', 'N/A')}\n"
        report += f"High Yield: {q.get('extra_edge', 'N/A')}\n" + "-"*50 + "\n"
    return report

# --- PDF EXTRACTOR ---
def extract_text_from_pdf(file):
    try:
        reader = PyPDF2.PdfReader(file)
        text = ""
        for page in reader.pages: text += page.extract_text()
        return text
    except: return None

# --- AI ENGINE (WITH AUTO-RETRY) ---
def generate_quiz(model_name, topic, num, difficulty, input_type, context_data=None, previous_questions=[]):
    model = genai.GenerativeModel(model_name)
    
    prompt = f"""
    Act as a Medical Consultant. Create a {difficulty} quiz with {num} questions.
    Topic: {topic}
    Rules: 
    1. Output VALID JSON ONLY. No Intro text.
    2. Short explanations.
    """
    
    if previous_questions:
        # Only send the last 20 questions to save tokens (prevents overload)
        prompt += f"\nAvoid these questions: {previous_questions[-20:]}"
    
    content = [prompt]
    
    if input_type == "Text/PDF" and context_data:
        prompt += f"\nContext: {context_data[:10000]}..." # Limit context to save speed
        content = [prompt]
    elif input_type == "Image" and context_data:
        prompt += "\nAnalyze image."
        content = [prompt, context_data]

    prompt += """
    JSON Format:
    [
        {
            "question": "...",
            "options": {"A": "..", "B": "..", "C": "..", "D": ".."},
            "correct_option": "A",
            "explanation": "...",
            "extra_edge": "..."
        }
    ]
    """
    if input_type != "Image": content = [prompt]
    else: content[0] = prompt

    # --- RETRY LOGIC ---
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = model.generate_content(content)
            # Check for empty response
            if not response.text: raise ValueError("Empty response")
            
            txt = response.text
            start = txt.find('[')
            end = txt.rfind(']') + 1
            if start != -1 and end != -1:
                return json.loads(txt[start:end])
            else:
                return json.loads(txt.replace("```json", "").replace("```", "").strip())

        except ResourceExhausted:
            if attempt < max_retries - 1:
                st.toast(f"⚠️ Speed limit hit. Waiting 10s... (Attempt {attempt+1}/{max_retries})")
                time.sleep(10) # Auto-wait
                continue
            else:
                st.error("❌ Quota exceeded. Please wait 1 minute and try again.")
                return []
        except Exception as e:
            st.error(f"Error: {e}")
            return []
    return []

# --- APP UI ---
if 'page' not in st.session_state: st.session_state.page = "home"
if 'quiz_data' not in st.session_state: st.session_state.quiz_data = []
if 'user_answers' not in st.session_state: st.session_state.user_answers = {}
if 'current_index' not in st.session_state: st.session_state.current_index = 0

if 'history' not in st.session_state: st.session_state.history = load_history()

# Persist settings
for key in ['current_topic', 'current_context', 'current_input_type', 'current_difficulty', 'current_model']:
    if key not in st.session_state: st.session_state[key] = None

with st.sidebar:
    st.title("🩺 QUIZ MASTER")
    models = get_working_models()
    model_choice = st.selectbox("Model", models) if models else "models/gemini-1.5-flash"
    st.divider()
    if st.button("🏠 New Quiz"):
        st.session_state.page = "home"
        st.rerun()

    st.subheader("📜 Recent History")
    if st.session_state.history:
        for i, item in enumerate(st.session_state.history):
            label = f"{item['topic']} ({item['score']})"
            if st.button(label, key=f"hist_{i}"):
                st.session_state.quiz_data = item['data']
                st.session_state.user_answers = item.get('user_answers', {})
                st.session_state.current_index = 0
                st.session_state.page = "scorecard" 
                st.rerun()

if st.session_state.page == "home":
    st.title("🚀 Generate Quiz")
    method = st.radio("Source", ["Gemini Knowledge", "Paste Text", "Upload PDF", "Upload Image"], horizontal=True)
    
    ctx = None
    img = None
    if method == "Gemini Knowledge": topic = st.text_input("Topic")
    elif method == "Paste Text": 
        topic = st.text_input("Topic Name")
        ctx = st.text_area("Content")
    elif method == "Upload PDF":
        topic = st.text_input("Topic Name")
        f = st.file_uploader("PDF", type='pdf')
        if f: ctx = extract_text_from_pdf(f)
    elif method == "Upload Image":
        topic = st.text_input("Topic Name")
        f = st.file_uploader("Image", type=['png','jpg','jpeg'])
        if f: img = Image.open(f)

    c1, c2 = st.columns(2)
    diff = c1.select_slider("Difficulty", ["Easy", "Medium", "Hard"])
    num = c2.slider("Questions", 5, 20, 10)

    if st.button("Start Quiz", type="primary"):
        with st.spinner("Generating..."):
            st.session_state.current_topic = topic
            st.session_state.current_model = model_choice
            st.session_state.current_input_type = "Image" if img else "Text/PDF" if ctx else "Topic"
            st.session_state.current_context = img if img else ctx
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
    radio_key = f"radio_{st.session_state.current_index}"
    
    prev = st.session_state.user_answers.get(st.session_state.current_index)
    idx = opts.index(prev) if prev in opts else 0
    
    sel = st.radio(
        "Choose:", 
        opts, 
        format_func=lambda x: f"{x}: {q['options'][x]}", 
        key=radio_key,
        index=idx if prev else None
    )
    
    if sel: st.session_state.user_answers[st.session_state.current_index] = sel
    
    c1, c2 = st.columns(2)
    if c1.button("Prev") and st.session_state.current_index > 0:
        st.session_state.current_index -= 1
        st.rerun()
    
    if st.session_state.current_index < len(st.session_state.quiz_data) - 1:
        if c2.button("Next"):
            st.session_state.current_index += 1
            st.rerun()
    else:
        if c2.button("Finish"):
            st.session_state.page = "scorecard"
            st.rerun()

elif st.session_state.page == "scorecard":
    st.balloons()
    score = sum([1 for i,q in enumerate(st.session_state.quiz_data) if st.session_state.user_answers.get(i)==q['correct_option']])
    st.title(f"Score: {score}/{len(st.session_state.quiz_data)}")
    
    if 'saved' not in st.session_state:
        new_history = save_quiz_to_history(
            st.session_state.current_topic, 
            score, 
            len(st.session_state.quiz_data), 
            st.session_state.quiz_data, 
            st.session_state.user_answers
        )
        st.session_state.history = new_history
        st.session_state.saved = True
        st.rerun()
    
    c1, c2 = st.columns(2)
    report = create_text_report(st.session_state.current_topic, score, len(st.session_state.quiz_data), st.session_state.quiz_data, st.session_state.user_answers)
    c1.download_button("📥 Download Report", report, "quiz_report.txt")
    
    if c2.button("🔄 Add 10 More"):
        with st.spinner("Adding (this may take 20s)..."):
            exist = [q['question'] for q in st.session_state.quiz_data]
            new_data = generate_quiz(st.session_state.current_model, st.session_state.current_topic, 10, st.session_state.current_difficulty, st.session_state.current_input_type, st.session_state.current_context, exist)
            if new_data:
                st.session_state.quiz_data.extend(new_data)
                if 'saved' in st.session_state: del st.session_state['saved']
                st.session_state.page = "quiz"
                st.session_state.current_index = len(exist)
                st.rerun()

    for i, q in enumerate(st.session_state.quiz_data):
        ans = st.session_state.user_answers.get(i)
        color = "green" if ans == q['correct_option'] else "red"
        with st.expander(f"Q{i+1} [{color}]: {q['question']}"):
            st.write(f"Correct: {q['correct_option']}")
            st.info(q['explanation'])
            st.warning(q['extra_edge'])
    
    if st.button("Home"):
        st.session_state.page = "home"
        if 'saved' in st.session_state: del st.session_state['saved']
        st.rerun()
