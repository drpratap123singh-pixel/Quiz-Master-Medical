import streamlit as st
import google.generativeai as genai
import json
import os
import datetime
from PIL import Image
import PyPDF2

# --- CONFIGURATION ---
# This setup works for BOTH Local Laptop and Cloud
try:
    # Try to get key from Cloud Secrets
    api_key = st.secrets["GOOGLE_API_KEY"]
except:
    # If on laptop, use this key:
    api_key = "AIzaSyBro9NqHUxSGajeoGcn3zd41aPgziED63w"

genai.configure(api_key=api_key)

# File to store history
HISTORY_FILE = "quiz_history.json"

st.set_page_config(page_title="QUIZ MASTER PRO", layout="wide", page_icon="🩺")

# --- 1. AUTO-DETECT WORKING MODELS ---
@st.cache_data
def get_working_models():
    """Asks Google which models are actually available for this API key"""
    try:
        valid_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                valid_models.append(m.name)
        # Sort to put flash models first (they are faster)
        valid_models.sort(key=lambda x: "flash" not in x)
        return valid_models
    except Exception as e:
        return ["models/gemini-1.5-flash-latest", "models/gemini-pro"]

# --- DATA MANAGER ---
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except:
            return []
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
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f)
    return history

# --- 2. REPORT GENERATOR ---
def create_text_report(topic, score, total, questions, user_answers):
    """Generates a text file string with full quiz details"""
    report = f"🎓 QUIZ MASTER REPORT\n"
    report += f"Topic: {topic}\n"
    report += f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    report += f"Final Score: {score}/{total}\n"
    report += "="*60 + "\n\n"
    
    for i, q in enumerate(questions):
        ans = user_answers.get(i) or user_answers.get(str(i))
        correct = q['correct_option']
        status = "✅ CORRECT" if ans == correct else f"❌ WRONG (You chose {ans})"
        
        report += f"Q{i+1}: {q['question']}\n"
        report += f"------------------------------------------------\n"
        for opt, txt in q['options'].items():
            marker = "  "
            if opt == correct: marker = "-> " # Mark correct answer
            report += f"{marker}{opt}: {txt}\n"
        
        report += f"\nRESULT: {status}\n"
        report += f"EXPLANATION: {q.get('explanation', 'N/A')}\n"
        report += f"EXTRA EDGE: {q.get('extra_edge', 'N/A')}\n"
        report += "="*60 + "\n\n"
        
    return report

# --- PDF EXTRACTOR ---
def extract_text_from_pdf(file):
    try:
        reader = PyPDF2.PdfReader(file)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        return None

# --- AI ENGINE ---
def generate_quiz(model_name, topic, num, difficulty, input_type, context_data=None, previous_questions=[]):
    model = genai.GenerativeModel(model_name)
    
    prompt_text = f"""
    Act as a Medical Consultant. Create a {difficulty} quiz with {num} questions.
    Topic: {topic}
    
    CRITICAL RULES:
    1. Output strictly valid JSON.
    2. Explanations must be SHORT (max 2 sentences).
    3. 'extra_edge' must be brief high-yield facts.
    """

    if previous_questions:
        past_qs_text = "\n".join(previous_questions[-50:])
        prompt_text += f"\n\nIMPORTANT: Do NOT repeat the following questions:\n{past_qs_text}\n"
    
    content_payload = [prompt_text]

    if input_type == "Text/PDF" and context_data:
        prompt_text += f"\n\nContext:\n{context_data[:15000]}..." 
        content_payload = [prompt_text]
    elif input_type == "Image" and context_data:
        prompt_text += "\n\nAnalyze this medical image."
        content_payload = [prompt_text, context_data] 

    prompt_text += """
    JSON STRUCTURE:
    [
        {
            "question": "Scenario...",
            "options": {"A": "..", "B": "..", "C": "..", "D": ".."},
            "correct_option": "A",
            "explanation": "Brief reasoning.",
            "more_explanation": "Pathophysiology.",
            "extra_edge": "High Yield Fact."
        }
    ]
    """
    
    if input_type == "Image":
        content_payload[0] = prompt_text
    else:
        content_payload = [prompt_text]

    response = model.generate_content(content_payload)
    text = response.text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)

# --- SESSION STATE ---
if 'page' not in st.session_state: st.session_state.page = "home"
if 'quiz_data' not in st.session_state: st.session_state.quiz_data = []
if 'user_answers' not in st.session_state: st.session_state.user_answers = {}
if 'current_index' not in st.session_state: st.session_state.current_index = 0
if 'history' not in st.session_state: st.session_state.history = load_history()

if 'current_topic' not in st.session_state: st.session_state.current_topic = ""
if 'current_context' not in st.session_state: st.session_state.current_context = None
if 'current_input_type' not in st.session_state: st.session_state.current_input_type = "Topic"
if 'current_difficulty' not in st.session_state: st.session_state.current_difficulty = "Medium"
if 'current_model' not in st.session_state: st.session_state.current_model = "models/gemini-1.5-flash-latest"

# --- SIDEBAR ---
with st.sidebar:
    st.title("🩺 QUIZ MASTER")
    st.subheader("⚙️ AI Brain")
    
    my_models = get_working_models()
    if my_models:
        model_choice = st.selectbox("Select Model:", my_models, index=0)
        st.caption(f"Connected to: {model_choice}")
    else:
        st.error("API Key Issue. Using Backup.")
        model_choice = "models/gemini-1.5-flash-latest"

    st.divider()
    if st.button("🏠 New Quiz"):
        st.session_state.page = "home"
        st.rerun()

    st.subheader("📜 History")
    if st.session_state.history:
        for i, item in enumerate(st.session_state.history):
            if st.button(f"{item['topic']} ({item['score']})", key=f"h_{i}"):
                st.session_state.quiz_data = item['data']
                st.session_state.user_answers = item.get('user_answers', {})
                st.session_state.current_index = 0
                st.session_state.page = "review_mode"
                st.rerun()

# --- HOME PAGE ---
if st.session_state.page == "home":
    st.markdown("## 🚀 Generate Quiz")
    
    input_method = st.radio("Input Source:", ["Gemini Knowledge", "Paste Text", "Upload PDF", "Upload Image"], horizontal=True)
    
    context = None
    img_data = None
    
    if input_method == "Gemini Knowledge":
        topic = st.text_input("Enter Topic (e.g., Parkinsonism)")
    elif input_method == "Paste Text":
        topic = st.text_input("Enter Topic Name:")
        context = st.text_area("Paste Notes:", height=150)
    elif input_method == "Upload PDF":
        topic = st.text_input("Enter Topic Name:")
        uploaded_file = st.file_uploader("Upload PDF", type=['pdf'])
        if uploaded_file:
            context = extract_text_from_pdf(uploaded_file)
            st.success("PDF Ready!")
    elif input_method == "Upload Image":
        topic = st.text_input("Enter Topic Name:")
        uploaded_file = st.file_uploader("Upload Image", type=['png', 'jpg', 'jpeg'])
        if uploaded_file:
            img_data = Image.open(uploaded_file)
            st.image(img_data, width=200)

    c1, c2 = st.columns(2)
    with c1: diff = st.select_slider("Difficulty", ["Easy", "Medium", "Hard"])
    with c2: num = st.slider("Initial Questions", 5, 20, 10) 
    
    if st.button("Start Quiz", type="primary"):
        if not topic:
            st.error("Please enter a topic.")
        else:
            with st.spinner(f"Generating..."):
                try:
                    final_type = "Topic"
                    final_ctx = None
                    if input_method == "Upload Image" and img_data:
                        final_type, final_ctx = "Image", img_data
                    elif context:
                        final_type, final_ctx = "Text/PDF", context
                    
                    st.session_state.current_topic = topic
                    st.session_state.current_input_type = final_type
                    st.session_state.current_context = final_ctx
                    st.session_state.current_difficulty = diff
                    st.session_state.current_model = model_choice

                    data = generate_quiz(model_choice, topic, num, diff, final_type, final_ctx)
                    st.session_state.quiz_data = data
                    st.session_state.user_answers = {}
                    st.session_state.current_index = 0
                    st.session_state.page = "quiz"
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
                    st.warning("If error is 'Unterminated string', select fewer questions.")

# --- QUIZ PAGE ---
elif st.session_state.page == "quiz":
    idx = st.session_state.current_index
    questions = st.session_state.quiz_data
    q = questions[idx]
    
    st.progress((idx + 1) / len(questions), text=f"Q{idx+1}/{len(questions)}")
    
    try:
        word_count = len((q.get('question', '') + str(q.get('options', ''))).split())
        st.caption(f"⏱️ Time: {int(word_count * 1.5)}s")
    except: pass

    st.markdown(f"### {q.get('question', 'Error loading question')}")
    
    opts = list(q.get('options', {}).keys())
    prev = st.session_state.user_answers.get(str(idx)) or st.session_state.user_answers.get(idx)
    
    choice = st.radio("Select:", opts, 
                      format_func=lambda x: f"{x}: {q['options'][x]}",
                      index=opts.index(prev) if prev in opts else None,
                      key=f"q_{idx}")
    
    c1, c2 = st.columns([1,1])
    if c1.button("⬅ Previous") and idx > 0:
        st.session_state.current_index -= 1
        st.rerun()
    
    if choice: st.session_state.user_answers[idx] = choice
    if idx < len(questions) - 1:
        if c2.button("Next ➡"):
            st.session_state.current_index += 1
            st.rerun()
    else:
        if c2.button("🏁 Submit"):
            st.session_state.page = "scorecard"
            st.rerun()

# --- SCORECARD ---
elif st.session_state.page == "scorecard":
    st.balloons()
    questions = st.session_state.quiz_data
    answers = st.session_state.user_answers
    
    score = 0
    for i, q in enumerate(questions):
        ans = answers.get(i) or answers.get(str(i))
        if ans == q['correct_option']: score += 1
            
    st.markdown(f"## 🏆 Score: {score} / {len(questions)}")
    
    if 'saved' not in st.session_state:
        save_quiz_to_history(st.session_state.current_topic, score, len(questions), questions, answers)
        st.session_state.saved = True
        st.success("Saved to History!")
    
    # --- DOWNLOAD & CONTINUE BUTTONS ---
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🏠 Start Fresh"):
            st.session_state.page = "home"
            del st.session_state['saved']
            st.rerun()
    
    with col2:
        report_text = create_text_report(st.session_state.current_topic, score, len(questions), questions, answers)
        st.download_button(
            label="📥 Download Result",
            data=report_text,
            file_name=f"Quiz_Result_{st.session_state.current_topic}.txt",
            mime="text/plain"
        )

    with col3:
        if st.button("🔄 Continue (Ask 10 More)"):
            with st.spinner("Adding more questions..."):
                try:
                    existing_qs = [q['question'] for q in st.session_state.quiz_data]
                    new_data = generate_quiz(
                        st.session_state.current_model,
                        st.session_state.current_topic,
                        10, 
                        st.session_state.current_difficulty,
                        st.session_state.current_input_type,
                        st.session_state.current_context,
                        previous_questions=existing_qs 
                    )
                    st.session_state.quiz_data.extend(new_data)
                    if 'saved' in st.session_state: del st.session_state['saved']
                    st.session_state.current_index = len(existing_qs)
                    st.session_state.page = "quiz"
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

    st.divider()
    st.subheader("📝 Review Answers")
    for i, q in enumerate(questions):
        ans = answers.get(i) or answers.get(str(i))
        correct = q['correct_option']
        color = "green" if ans == correct else "red"
        
        with st.expander(f"Q{i+1} [{color.upper()}]: {q['question']}"):
            st.markdown("#### Options:")
            for opt_key, opt_text in q['options'].items():
                if opt_key == correct:
                    st.success(f"✅ {opt_key}: {opt_text} (Correct)")
                elif opt_key == ans:
                    st.error(f"❌ {opt_key}: {opt_text} (Your Choice)")
                else:
                    st.write(f"⚪ {opt_key}: {opt_text}")
            
            st.info(f"**Explanation:** {q.get('explanation', 'N/A')}")
            st.warning(f"**Extra Edge:** {q.get('extra_edge', 'N/A')}")

# --- REVIEW MODE ---
elif st.session_state.page == "review_mode":
    st.markdown("## 📜 History Review")
    
    questions = st.session_state.quiz_data
    answers = st.session_state.user_answers
    
    score = 0
    for i, q in enumerate(questions):
        ans = answers.get(i) or answers.get(str(i))
        if ans == q['correct_option']: score += 1

    c1, c2 = st.columns(2)
    with c1:
        if st.button("⬅ Back"):
            st.session_state.page = "home"
            st.rerun()
    with c2:
        report_text = create_text_report("Historical Review", score, len(questions), questions, answers)
        st.download_button("📥 Download This Quiz", data=report_text, file_name="Historical_Quiz.txt")
    
    for i, q in enumerate(st.session_state.quiz_data):
        ans = st.session_state.user_answers.get(str(i)) or st.session_state.user_answers.get(i)
        correct = q['correct_option']
        icon = "✅" if ans == correct else "❌"
        
        with st.expander(f"{icon} Q{i+1}: {q['question']}"):
            st.markdown("#### Options:")
            for opt_key, opt_text in q['options'].items():
                if opt_key == correct:
                    st.success(f"✅ {opt_key}: {opt_text} (Correct)")
                elif opt_key == ans:
                    st.error(f"❌ {opt_key}: {opt_text} (Your Choice)")
                else:
                    st.write(f"⚪ {opt_key}: {opt_text}")
            
            st.info(q.get('explanation', 'N/A'))
            st.warning(q.get('extra_edge', 'N/A'))