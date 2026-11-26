import streamlit as st
import os
import re
import streamlit.components.v1 as components
import time
import json
import math
from typing import List, Dict, Any, Optional

# Load local .env variables if present
_env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_file):
    try:
        with open(_env_file, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    _k, _v = _k.strip(), _v.strip().strip('"').strip("'")
                    if _k and _k not in os.environ:
                        os.environ[_k] = _v
    except Exception:
        pass

import db_manager
from mcq_parser import (
    extract_text_from_pdf,
    parse_mcq_text,
    parse_csv_file,
    clean_option_text,
    clean_question_text,
    format_study_notes_html
)
try:
    from mcq_parser import prepare_questions_list
except ImportError:
    def prepare_questions_list(q_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not q_list:
            return []
        seen_nums = set()
        has_duplicates = False
        for q in q_list:
            num = q.get("question_number")
            if num in seen_nums:
                has_duplicates = True
                break
            seen_nums.add(num)
        for i, q in enumerate(q_list):
            q["uid"] = f"q_{i + 1}"
            if has_duplicates:
                q["original_number"] = q.get("question_number")
                q["question_number"] = i + 1
            if "question_text" in q:
                q["question_text"] = clean_question_text(q["question_text"])
            if "options" in q:
                for opt_key in list(q["options"].keys()):
                    q["options"][opt_key] = clean_option_text(q["options"][opt_key])
            if "trap_info" not in q:
                q["trap_info"] = analyze_exam_trap(q.get("question_text", ""), q.get("options", {}))
        return q_list

from gemini_helper import generate_hindi_explanation, solve_mcq_with_gemini, sanitize_api_key, get_gemini_client
from sample_data import SAMPLE_RAW_MCQ_TEXT
from trap_analyzer import analyze_exam_trap

# ==========================================
# PAGE CONFIGURATION & THEME STYLING
# ==========================================
st.set_page_config(
    page_title="OptNote.com — AI Test Series & Question Bank",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Ultra-Compact Modern Exam Layout, Fixed Sticky Header & 2x2 Grid Options
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

/* Keep Streamlit header transparent & ensure the sidebar expand/collapse button is always accessible */
header[data-testid="stHeader"] {
    background: transparent !important;
    z-index: 1000 !important;
}

[data-testid="stSidebarCollapsedControl"] {
    display: flex !important;
    visibility: visible !important;
    z-index: 999999 !important;
    background: #f8fafc !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 6px !important;
    margin-left: 8px !important;
    margin-top: 8px !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1) !important;
}

/* Prevent Streamlit from fading out / dimming questions when running */
div[data-testid="stAppViewContainer"] [data-testid="stVerticalBlock"] {
    opacity: 1 !important;
    filter: none !important;
    transition: none !important;
}
.stApp[data-test-script-state="running"] [data-testid="stVerticalBlock"] > div {
    opacity: 1 !important;
}
div[data-testid="stAppViewBlockContainer"] {
    opacity: 1 !important;
}

/* Compact Container Spacing */
.block-container {
    padding-top: 1.2rem !important;
    padding-bottom: 2rem !important;
    max-width: 1080px !important;
}

/* Sidebar Custom Compact Styling */
[data-testid="stSidebarUserContent"] {
    padding-top: 0.7rem !important;
    padding-bottom: 1rem !important;
    padding-left: 0.75rem !important;
    padding-right: 0.75rem !important;
}
[data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] {
    gap: 0.45rem !important;
}

/* Ultra-Compact Question Border Container */
[data-testid="stVerticalBlockBorderWrapper"] {
    margin-bottom: 4px !important;
    border-radius: 8px !important;
    border: 1px solid #e2e8f0 !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02) !important;
    background: #ffffff;
}
[data-testid="stVerticalBlockBorderWrapper"] > div {
    padding: 5px 10px !important;
}

@media (prefers-color-scheme: dark) {
    [data-testid="stVerticalBlockBorderWrapper"] {
        border-color: #334155 !important;
        background: #1e293b !important;
    }
}

/* Permanent Sticky Header - Fixed at top 0 with highest z-index */
.sticky-scoreboard {
    position: sticky !important;
    top: 0 !important;
    z-index: 99999 !important;
    background: rgba(255, 255, 255, 0.98) !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 7px !important;
    padding: 4px 12px !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05) !important;
    margin-bottom: 6px !important;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
}

div[data-testid="stElementContainer"]:has(.sticky-scoreboard) {
    position: sticky !important;
    top: 0 !important;
    z-index: 99999 !important;
    background: transparent !important;
}

div[data-testid="stVerticalBlock"]:has(> div > div > .sticky-scoreboard) {
    overflow: visible !important;
}

@media (prefers-color-scheme: dark) {
    .sticky-scoreboard {
        background: rgba(22, 27, 34, 0.98) !important;
        border: 1px solid #4a5568 !important;
        box-shadow: 0 3px 10px rgba(0, 0, 0, 0.4) !important;
    }
}

/* Micro Badges */
.q-badge {
    display: inline-block;
    padding: 1px 5px;
    border-radius: 4px;
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    margin-right: 3px;
    line-height: 1.3;
}
.q-badge-indigo {
    background: #e0e7ff;
    color: #4338ca;
}
.q-badge-emerald {
    background: #d1fae5;
    color: #065f46;
}
.q-badge-amber {
    background: #fef3c7;
    color: #92400e;
}
.q-badge-trap {
    background: #fef2f2;
    color: #b91c1c;
    border: 1px solid #fecaca;
}

/* 2x2 Grid for Interactive Radio Buttons */
div[data-testid="stRadio"] > label {
    display: none !important;
}

div[data-testid="stRadio"] div[role="radiogroup"] {
    display: grid !important;
    grid-template-columns: 1fr 1fr !important;
    gap: 3px !important;
}

@media (max-width: 640px) {
    div[data-testid="stRadio"] div[role="radiogroup"] {
        grid-template-columns: 1fr !important;
    }
}

div[data-testid="stRadio"] div[role="radiogroup"] > label {
    background: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 5px !important;
    padding: 3px 8px !important;
    margin: 0 !important;
    width: 100% !important;
    cursor: pointer !important;
    transition: all 0.12s ease !important;
    font-size: 0.81rem !important;
    font-weight: 500 !important;
    min-height: 27px !important;
    display: flex !important;
    align-items: center !important;
    line-height: 1.25 !important;
}

div[data-testid="stRadio"] div[role="radiogroup"] > label:hover {
    background: #f1f5f9 !important;
    border-color: #6366f1 !important;
}

@media (prefers-color-scheme: dark) {
    div[data-testid="stRadio"] div[role="radiogroup"] > label {
        background: #1e293b !important;
        border-color: #334155 !important;
        color: #e2e8f0 !important;
    }
    div[data-testid="stRadio"] div[role="radiogroup"] > label:hover {
        background: #334155 !important;
        border-color: #818cf8 !important;
    }
}

/* 2x2 Grid for Evaluated / Locked Options */
.options-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 3px;
    margin: 2px 0;
}

@media (max-width: 640px) {
    .options-grid {
        grid-template-columns: 1fr;
    }
}

.option-box {
    padding: 3px 8px;
    border-radius: 5px;
    font-size: 0.81rem;
    min-height: 27px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border: 1px solid #e2e8f0;
    background: #f8fafc;
    box-sizing: border-box;
    line-height: 1.25;
}

@media (prefers-color-scheme: dark) {
    .option-box {
        background: #1e293b;
        border-color: #334155;
    }
}

.opt-correct {
    border-color: #10b981 !important;
    background-color: #ecfdf5 !important;
    color: #065f46 !important;
    font-weight: 600;
}

.opt-incorrect {
    border-color: #ef4444 !important;
    background-color: #fef2f2 !important;
    color: #991b1b !important;
    font-weight: 600;
}

.opt-muted {
    opacity: 0.65;
}

/* Micro Question Card Buttons */
div[data-testid="stVerticalBlockBorderWrapper"] button {
    min-height: 25px !important;
    height: 27px !important;
    padding: 1px 8px !important;
    font-size: 0.76rem !important;
    border-radius: 5px !important;
}

/* Clean Micro Explanation Box */
.exp-box {
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
    border-left: 3px solid #10b981;
    border-radius: 5px;
    padding: 4px 8px;
    margin-top: 3px;
    font-size: 0.79rem;
    line-height: 1.32;
}

@media (prefers-color-scheme: dark) {
    .exp-box {
        background: #14281e;
        border-color: #065f46;
        border-left: 3px solid #10b981;
    }
}

.gemini-tag {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
    color: white !important;
    font-size: 0.65rem;
    font-weight: 700;
    padding: 1px 5px;
    border-radius: 3px;
    margin-bottom: 2px;
}

/* Metric Display Cards */
.metric-card {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 7px;
    padding: 5px 8px;
    text-align: center;
}
@media (prefers-color-scheme: dark) {
    .metric-card {
        background: #2d3748;
        border-color: #4a5568;
    }
}
/* Scrollable Study Notes Container */
.notes-scroll {
    max-height: 200px;
    overflow-y: auto;
    overflow-x: auto;
    scrollbar-width: thin;
    scrollbar-color: #cbd5e1 #f8fafc;
}
.notes-scroll::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}
.notes-scroll::-webkit-scrollbar-track {
    background: #f8fafc;
    border-radius: 4px;
}
.notes-scroll::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 4px;
}
.notes-scroll::-webkit-scrollbar-thumb:hover {
    background: #94a3b8;
}

/* Styled Table for Study Notes */
.notes-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.80rem;
    margin: 8px 0;
    background: #ffffff;
    border-radius: 6px;
    overflow: hidden;
}
.notes-table th {
    background: #e0e7ff;
    color: #1e3a8a;
    font-weight: 700;
    padding: 6px 10px;
    border: 1px solid #c7d2fe;
    text-align: left;
}
.notes-table td {
    padding: 5px 10px;
    border: 1px solid #e2e8f0;
    color: #1e293b;
}

@media (prefers-color-scheme: dark) {
    .notes-scroll {
        scrollbar-color: #475569 #1e293b;
    }
    .notes-scroll::-webkit-scrollbar-track {
        background: #1e293b;
    }
    .notes-scroll::-webkit-scrollbar-thumb {
        background: #475569;
    }
    .notes-table {
        background: #1e293b;
    }
    .notes-table th {
        background: #312e81;
        color: #e0e7ff;
        border-color: #4338ca;
    }
    .notes-table td {
        border-color: #334155;
        color: #cbd5e1;
    }
}
</style>
""", unsafe_allow_html=True)

# Study Notes Dialog Modal (Large screen popup)
if hasattr(st, "dialog"):
    @st.dialog("📖 Study Notes & Detailed Exam Facts", width="large")
    def show_study_notes_modal(q_num: int, topic: str, notes_html: str):
        st.markdown(
            f"""<div style="display:flex; justify-content:space-between; align-items:center; border-bottom:2px solid #e2e8f0; padding-bottom:8px; margin-bottom:10px;">
<div style="font-size:1.0rem; font-weight:700; color:#1e40af;">📌 Question {q_num} • {topic}</div>
<div style="font-size:0.72rem; background:#eff6ff; color:#2563eb; padding:2px 8px; border-radius:12px; font-weight:600;">Full Study Notes & Tables</div>
</div>""",
            unsafe_allow_html=True
        )
        st.markdown(
            f"""<div class="notes-scroll" style="max-height:68vh; overflow-y:auto; overflow-x:auto; padding:6px 4px;">
{notes_html}
</div>""",
            unsafe_allow_html=True
        )
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("✕ Close Notes (बंद करें)", key="close_notes_dialog_btn", type="primary", use_container_width=True):
            st.rerun()
else:
    def show_study_notes_modal(q_num: int, topic: str, notes_html: str):
        st.info(f"Question {q_num} • {topic}")
        st.markdown(notes_html, unsafe_allow_html=True)



# ==========================================
# SESSION STATE INITIALIZATION & AUTO-CLEANING
# ==========================================
if "questions" not in st.session_state:
    st.session_state.questions = []
if "screen" not in st.session_state:
    st.session_state.screen = "upload"  # "upload", "batch_setup", "quiz", "summary"
if "batch_size" not in st.session_state:
    st.session_state.batch_size = 10
if "current_batch_idx" not in st.session_state:
    st.session_state.current_batch_idx = 0
if "user_answers" not in st.session_state:
    st.session_state.user_answers = {}
if "gemini_cache" not in st.session_state:
    st.session_state.gemini_cache = {}
if "gemini_api_key" not in st.session_state or not st.session_state.gemini_api_key:
    st.session_state.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
if "gemini_model" not in st.session_state or not st.session_state.gemini_model:
    st.session_state.gemini_model = "gemini-3.5-flash-lite"
if "active_source" not in st.session_state:
    st.session_state.active_source = "None"
if "traps_only_mode" not in st.session_state:
    st.session_state.traps_only_mode = False
if "questions_prepared" not in st.session_state:
    st.session_state.questions_prepared = False
if "user_id" not in st.session_state:
    st.session_state.user_id = db_manager.DEFAULT_GUEST_USER_ID
if "user_name" not in st.session_state:
    st.session_state.user_name = "Guest Learner"

# Auto-clean questions in memory, de-duplicate question numbers, and ensure unique uids (only once upon load)
if st.session_state.questions and not st.session_state.get("questions_prepared", False):
    st.session_state.questions = prepare_questions_list(st.session_state.questions)
    st.session_state.questions_prepared = True


# ==========================================
# SIDEBAR: COMPACT CONTROLS & SETTINGS
# ==========================================
with st.sidebar:
    st.markdown("### ⚡ OptNote.com")
    st.caption("AI-Powered Competitive Exam Engine")

    st.divider()

    # 1. Google Gemini AI Settings (Clean, Compact, and Directly Visible)
    st.markdown("#### 🤖 Google Gemini AI")
    raw_gemini_key = st.text_input(
        "Gemini API Key",
        value=st.session_state.gemini_api_key,
        type="password",
        placeholder="AIzaSy...",
        help="Generates real-time Hindi explanations, translations, and auto-solving."
    )
    cleaned_key = sanitize_api_key(raw_gemini_key) or ""
    if cleaned_key != st.session_state.gemini_api_key:
        st.session_state.gemini_api_key = cleaned_key
        st.session_state.gemini_cache = {}
        st.rerun()

    model_choices = ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-2.5-flash"]
    curr_idx = model_choices.index(st.session_state.gemini_model) if st.session_state.gemini_model in model_choices else 0
    selected_model = st.selectbox(
        "Gemini Model",
        options=model_choices,
        index=curr_idx,
        format_func=lambda m: {
            "gemini-3.5-flash-lite": "⚡ 3.5 Flash-Lite (Fastest)",
            "gemini-3.5-flash": "🚀 3.5 Flash (Balanced)",
            "gemini-2.5-flash": "🧠 2.5 Flash (Deep Thinking)"
        }.get(m, m)
    )
    if selected_model != st.session_state.gemini_model:
        st.session_state.gemini_model = selected_model
        st.session_state.gemini_cache = {}
        st.rerun()

    st.session_state.auto_ai_exp = st.checkbox(
        "⚡ Auto-fetch AI Explanations",
        value=st.session_state.get("auto_ai_exp", False),
        help="Turn OFF for 0ms instant practice. Turn ON to auto-call Gemini after every click."
    )

    if st.session_state.gemini_api_key:
        st.success("Gemini AI Active 🟢", icon="✨")
    else:
        st.info("Offline Mode Active", icon="📶")

    st.divider()

    # 2. Live Session Status (Only when test is in progress)
    total_q = len(st.session_state.questions)
    if total_q > 0:
        st.markdown("#### 📊 Current Session")
        attempted_q = len(st.session_state.user_answers)
        correct_count = sum(
            1 for q in st.session_state.questions
            if q.get("uid", f"q_{q['question_number']}") in st.session_state.user_answers
            and q.get("correct_answer") in ['A', 'B', 'C', 'D', 'E']
            and st.session_state.user_answers[q.get("uid", f"q_{q['question_number']}")] == q["correct_answer"]
        )
        pending_key_count = sum(
            1 for q in st.session_state.questions
            if q.get("uid", f"q_{q['question_number']}") in st.session_state.user_answers
            and (not q.get("correct_answer") or q.get("correct_answer") not in ['A', 'B', 'C', 'D', 'E'])
        )
        col_sb1, col_sb2 = st.columns(2)
        with col_sb1:
            st.metric("Total MCQs", total_q)
        with col_sb2:
            st.metric("Attempted", f"{attempted_q}/{total_q}")

        if pending_key_count > 0:
            st.caption(f"Score: **{correct_count}** correct • 📝 {pending_key_count} key pending")
        else:
            st.caption(f"Score: **{correct_count}** correct")

        if st.session_state.screen != "upload":
            if st.button("🏠 Exit to Home Screen", key="sb_btn_home", use_container_width=True):
                st.session_state.screen = "upload"
                st.rerun()

        if st.session_state.screen != "quiz":
            if st.button("✍️ Back to Practice Quiz", key="sb_btn_quiz", use_container_width=True):
                st.session_state.screen = "quiz"
                st.rerun()

        if st.session_state.screen != "summary" and attempted_q > 0:
            if st.button("📊 View Test Results", key="sb_btn_results", use_container_width=True):
                st.session_state.screen = "summary"
                st.rerun()

        st.divider()

    # 3. Database Info (Single compact line)
    db_engine = db_manager.get_active_db_type().capitalize()
    db_badge = "🐘 PostgreSQL (Port 5432)" if db_engine == "Postgres" else "📁 SQLite"
    st.caption(f"{db_badge} • 👤 {st.session_state.user_name}")

    # 4. Clear Session / Reset App
    if st.button("🔄 Reset App & Clear Data", key="sb_clear_btn", use_container_width=True):
        st.session_state.questions = []
        st.session_state.questions_prepared = False
        st.session_state.user_answers = {}
        st.session_state.gemini_cache = {}
        st.session_state.current_batch_idx = 0
        st.session_state.screen = "upload"
        st.session_state.active_source = "None"
        st.session_state.traps_only_mode = False
        st.rerun()


# ==========================================
# SCREEN 1: HOME & PDF UPLOAD / TEXT PASTE
# ==========================================
if st.session_state.screen == "upload":
    st.markdown("""
    <div style="text-align: center; padding: 10px 0 5px 0;">
        <h2 style="font-weight: 800; font-size: 1.8rem; margin-bottom: 4px;">
            ⚡ OptNote.com — MCQ Test Series Engine
        </h2>
        <p style="font-size: 0.95rem; color: #64748b; max-width: 600px; margin: 0 auto 15px auto;">
            Upload your competitive exam PDF or paste raw MCQs. Automatic <b>Exam Trap & Exception Detection</b>, compact practice, instant evaluation, and real-time AI Hindi explanations!
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Resume Banner if test is already loaded in memory
    if st.session_state.questions:
        total_loaded = len(st.session_state.questions)
        attempted_cnt = len(st.session_state.user_answers)
        c_res1, c_res2, c_res3 = st.columns([2.5, 1, 1])
        with c_res1:
            st.info(f"⚡ **Active Test Session:** {total_loaded} questions loaded ({attempted_cnt}/{total_loaded} attempted) from `{st.session_state.active_source}`")
        with c_res2:
            if st.button("✍️ Resume Practice", key="up_resume_quiz", type="primary", use_container_width=True):
                st.session_state.screen = "quiz"
                st.rerun()
        with c_res3:
            if st.button("📊 View Results", key="up_resume_sum", use_container_width=True):
                st.session_state.screen = "summary"
                st.rerun()

    tab_pdf, tab_csv, tab_text, tab_demo, tab_bank = st.tabs([
        "📄 Upload Exam PDF",
        "📊 Upload CSV / Spreadsheet",
        "📝 Paste Raw Text / CSV",
        "🚀 Instant Demo Test (20 Qs)",
        "📚 Central Question Bank (PostgreSQL)"
    ])

    # Tab 1: Upload PDF
    with tab_pdf:
        st.markdown("##### Upload your Question Paper / Test Series PDF")
        st.caption("Supports PyMuPDF extraction with intelligent header/footer, shift tag, and exam trap analysis.")
        
        col_sub_p1, col_sub_p2 = st.columns([1.2, 1])
        with col_sub_p1:
            pdf_subject = st.selectbox(
                "Assign Subject / Category:",
                ["General / Mixed", "Computer Knowledge", "Banking & Financial Awareness", "English Language & Comprehension", "General Studies & Static GK", "Quantitative Aptitude"],
                key="pdf_subject_sel"
            )
        with col_sub_p2:
            pdf_sync = st.checkbox("💾 Sync & De-duplicate to PostgreSQL", value=True, key="pdf_sync_check")

        uploaded_file = st.file_uploader(
            "Choose a PDF file",
            type=["pdf"],
            help="Upload any competitive exam PDF (SSC CGL, UPSC, Bank PO, NDA, CDS, etc.)"
        )
        if uploaded_file is not None:
            if st.button("📥 Parse and Load Questions from PDF", type="primary", use_container_width=True):
                with st.spinner("Extracting text, cleaning shift metadata, and analyzing exam traps..."):
                    try:
                        raw_text = extract_text_from_pdf(uploaded_file)
                        parsed = parse_mcq_text(raw_text)
                        if parsed:
                            if pdf_sync:
                                db_res = db_manager.save_parsed_questions(
                                    questions=parsed,
                                    source_name=uploaded_file.name,
                                    subject_name=pdf_subject,
                                    user_id=st.session_state.user_id,
                                    file_bytes=uploaded_file.getvalue()
                                )
                                st.toast(f"💾 Synced to DB: {db_res['inserted']} new, {db_res['duplicates']} duplicates skipped, {db_res['updated']} updated!", icon="🗄️")

                            st.session_state.questions = prepare_questions_list(parsed)
                            st.session_state.questions_prepared = True
                            st.session_state.user_answers = {}
                            st.session_state.current_batch_idx = 0
                            st.session_state.screen = "batch_setup"
                            st.session_state.active_source = f"PDF: {uploaded_file.name}"
                            st.rerun()
                        else:
                            st.error("No structured MCQs could be parsed. Check PDF formatting or try pasting raw text.", icon="⚠️")
                    except Exception as e:
                        st.error(f"Error parsing PDF: {str(e)}", icon="❌")

    # Tab 2: Upload CSV / Spreadsheet
    with tab_csv:
        st.markdown("##### Upload your Question Bank CSV / Spreadsheet")
        st.caption("Supports Financial Awareness, Banking, bilingual questions (English + Hindi), options, and custom study notes columns.")
        
        col_sub_c1, col_sub_c2 = st.columns([1.2, 1])
        with col_sub_c1:
            csv_subject = st.selectbox(
                "Assign Subject / Category:",
                ["Banking & Financial Awareness", "Computer Knowledge", "English Language & Comprehension", "General Studies & Static GK", "Quantitative Aptitude", "General / Mixed"],
                key="csv_subject_sel"
            )
        with col_sub_c2:
            csv_sync = st.checkbox("💾 Sync & De-duplicate to PostgreSQL", value=True, key="csv_sync_check")

        uploaded_csv = st.file_uploader(
            "Choose a CSV / TSV file",
            type=["csv", "tsv", "txt"],
            help="Upload CSV with questions, options, answers, and study notes/descriptions."
        )
        if uploaded_csv is not None:
            if st.button("📥 Parse and Load Questions from CSV", type="primary", use_container_width=True):
                with st.spinner("Reading spreadsheet, detecting bilingual questions, and extracting study notes..."):
                    try:
                        parsed = parse_csv_file(uploaded_csv)
                        if parsed:
                            if csv_sync:
                                db_res = db_manager.save_parsed_questions(
                                    questions=parsed,
                                    source_name=uploaded_csv.name,
                                    subject_name=csv_subject,
                                    user_id=st.session_state.user_id,
                                    file_bytes=uploaded_csv.getvalue()
                                )
                                st.toast(f"💾 Synced to DB: {db_res['inserted']} new, {db_res['duplicates']} duplicates skipped, {db_res['updated']} updated!", icon="🗄️")

                            st.session_state.questions = prepare_questions_list(parsed)
                            st.session_state.questions_prepared = True
                            st.session_state.user_answers = {}
                            st.session_state.current_batch_idx = 0
                            st.session_state.screen = "batch_setup"
                            st.session_state.active_source = f"CSV: {uploaded_csv.name}"
                            st.rerun()
                        else:
                            st.error("No questions could be parsed from the CSV. Please check formatting.", icon="⚠️")
                    except Exception as e:
                        st.error(f"Error parsing CSV: {str(e)}", icon="❌")

    # Tab 3: Paste Raw Text
    with tab_text:
        st.markdown("##### Paste MCQ Text Directly")
        col_sub_t1, col_sub_t2 = st.columns([1.2, 1])
        with col_sub_t1:
            text_subject = st.selectbox(
                "Assign Subject / Category:",
                ["General / Mixed", "English Language & Comprehension", "Computer Knowledge", "Banking & Financial Awareness", "General Studies & Static GK", "Quantitative Aptitude"],
                key="text_subject_sel"
            )
        with col_sub_t2:
            text_sync = st.checkbox("💾 Sync & De-duplicate to PostgreSQL", value=True, key="text_sync_check")

        raw_input_text = st.text_area(
            "Paste MCQs here",
            height=180,
            placeholder="1. Select the most appropriate synonym...\n(A) Option 1\n(B) Option 2\n(C) Option 3\n(D) Option 4\nAnswer: B",
            help="Paste standard MCQ text format with Questions, Options A/B/C/D, and Answer lines."
        )
        col_t1, col_t2 = st.columns([1, 1])
        with col_t1:
            if st.button("📋 Load Example Format into Box", use_container_width=True):
                st.session_state.raw_sample = SAMPLE_RAW_MCQ_TEXT
                st.rerun()
        with col_t2:
            if st.button("📥 Parse Pasted Text", type="primary", use_container_width=True):
                text_to_parse = raw_input_text.strip() if raw_input_text.strip() else st.session_state.get("raw_sample", "")
                if text_to_parse:
                    with st.spinner("Parsing questions and identifying exam traps..."):
                        parsed = parse_mcq_text(text_to_parse)
                        if not parsed or len(parsed) <= 1:
                            csv_fallback = parse_csv_file(text_to_parse)
                            if len(csv_fallback) > len(parsed or []):
                                parsed = csv_fallback
                        if parsed:
                            if text_sync:
                                db_res = db_manager.save_parsed_questions(
                                    questions=parsed,
                                    source_name="Pasted_Text",
                                    subject_name=text_subject,
                                    user_id=st.session_state.user_id
                                )
                                st.toast(f"💾 Synced to DB: {db_res['inserted']} new, {db_res['duplicates']} duplicates skipped, {db_res['updated']} updated!", icon="🗄️")

                            st.session_state.questions = prepare_questions_list(parsed)
                            st.session_state.questions_prepared = True
                            st.session_state.user_answers = {}
                            st.session_state.current_batch_idx = 0
                            st.session_state.screen = "batch_setup"
                            st.session_state.active_source = "Pasted Text"
                            st.rerun()
                        else:
                            st.error("Could not parse MCQs. Ensure options (A, B, C, D) are present.", icon="⚠️")
                else:
                    st.warning("Please paste some MCQ text first!")

    # Tab 4: Instant Demo Test
    with tab_demo:
        st.markdown("##### 🎯 Quick 1-Click Test Drive")
        st.write("Test all features immediately with our pre-loaded **20-Question High-Yield Test Series** covering English Idioms, General Science, and Static GK.")
        demo_sync = st.checkbox("💾 Sync Demo Questions to PostgreSQL", value=True, key="demo_sync_check")

        if st.button("⚡ Launch 20-Question Demo Test", type="primary", use_container_width=True):
            with st.spinner("Loading demo questions..."):
                parsed = parse_mcq_text(SAMPLE_RAW_MCQ_TEXT)
                if demo_sync:
                    db_manager.save_parsed_questions(
                        questions=parsed,
                        source_name="Demo_Test_Paper",
                        subject_name="English Language & Comprehension",
                        user_id=st.session_state.user_id
                    )
                st.session_state.questions = prepare_questions_list(parsed)
                st.session_state.questions_prepared = True
                st.session_state.user_answers = {}
                st.session_state.current_batch_idx = 0
                st.session_state.screen = "batch_setup"
                st.session_state.active_source = "Demo Test Dataset"
                st.rerun()

    # Tab 5: Browse Database & Question Bank
    with tab_bank:
        st.markdown("##### 📚 Central Question Repository (PostgreSQL)")
        st.caption("Browse saved MCQs across all subjects, search questions by keyword (English/Hindi), and launch custom test series.")

        overview = db_manager.get_subjects_overview()
        total_in_db = sum(s["question_count"] for s in overview)

        # Subject Cards Row
        c_sub1, c_sub2, c_sub3 = st.columns(3)
        with c_sub1:
            st.metric("Total Questions in DB", f"{total_in_db:,}", f"{len(overview)} Subjects")
        with c_sub2:
            top_sub = max(overview, key=lambda s: s["question_count"]) if overview and total_in_db > 0 else None
            top_title = f"{top_sub['icon']} {top_sub['name'][:22]}" if top_sub else "No questions yet"
            top_count = f"{top_sub['question_count']:,} Qs" if top_sub else "0 Qs"
            st.metric("Top Subject", top_count, top_title)
        with c_sub3:
            db_engine = db_manager.get_active_db_type().capitalize()
            st.metric("Database Engine", db_engine, "mcq_bank (Port 5432)" if db_engine == "Postgres" else "Local SQLite")

        st.divider()

        # Search Controls
        col_s1, col_s2, col_s3 = st.columns([1.5, 1.2, 1])
        with col_s1:
            search_kw = st.text_input("🔍 Search by Keyword (English / Hindi / Option)", placeholder="e.g. computer, inflation, spelling, etc.")
        with col_s2:
            sub_options = [("All Subjects", None)] + [(f"{s['icon']} {s['name']}", s['id']) for s in overview]
            selected_sub_label = st.selectbox("Filter by Subject:", [o[0] for o in sub_options])
            selected_sub_id = next(o[1] for o in sub_options if o[0] == selected_sub_label)
        with col_s3:
            topic_options = [("All Topics", None)]
            if selected_sub_id:
                topics_list = db_manager.get_topics_for_subject(selected_sub_id)
                topic_options += [(f"{t['name']} ({t['question_count']})", t['id']) for t in topics_list]
            selected_top_label = st.selectbox("Filter by Topic:", [o[0] for o in topic_options])
            selected_top_id = next(o[1] for o in topic_options if o[0] == selected_top_label)

        col_f1, col_f2 = st.columns([1, 1])
        with col_f1:
            bank_trap_only = st.checkbox("🔥 Exam Traps Only", value=False, key="db_filter_trap")
        with col_f2:
            max_limit = st.slider("Max Questions to Load:", min_value=10, max_value=200, value=50, step=10, key="db_limit_slider")

        # Query Database
        db_qs, total_matched = db_manager.search_questions(
            query_text=search_kw,
            subject_id=selected_sub_id,
            topic_id=selected_top_id,
            trap_only=bank_trap_only,
            limit=max_limit
        )

        st.info(f"Found **{total_matched:,} matching questions** in Database. Ready to practice **{len(db_qs)}**.")

        if db_qs:
            if st.button(f"🚀 Launch Test Series with these {len(db_qs)} Questions", type="primary", use_container_width=True):
                st.session_state.questions = prepare_questions_list(db_qs)
                st.session_state.questions_prepared = True
                st.session_state.user_answers = {}
                st.session_state.current_batch_idx = 0
                st.session_state.screen = "batch_setup"
                st.session_state.active_source = f"Database: {selected_sub_label} ({len(db_qs)} Qs)"
                st.rerun()

            # Preview matching questions
            with st.expander(f"👁️ Preview Questions ({min(5, len(db_qs))} shown)", expanded=False):
                for preview_q in db_qs[:5]:
                    st.markdown(f"**Q. {preview_q['question_text']}**")
                    opts = preview_q.get("options", {})
                    opt_line = " | ".join(f"({k}) {v}" for k, v in sorted(opts.items()))
                    st.caption(f"{opt_line} — **Ans: ({preview_q['correct_answer']})**")
                    st.divider()


# ==========================================
# SCREEN 2: PRE-TEST BATCH SETUP SCREEN
# ==========================================
elif st.session_state.screen == "batch_setup":
    all_questions = st.session_state.questions
    total_q = len(all_questions)
    trap_questions = [q for q in all_questions if q.get("trap_info", {}).get("is_trap")]
    trap_count = len(trap_questions)

    # Top Navigation Bar
    col_bs_nav1, col_bs_nav2, col_bs_nav3 = st.columns([1.3, 2.4, 1.3])
    with col_bs_nav1:
        if st.button("⬅️ Back to Bank / Upload", key="bs_top_back", use_container_width=True):
            st.session_state.screen = "upload"
            st.rerun()
    with col_bs_nav3:
        if st.button("🚀 Start Test Now", key="bs_top_start", type="primary", use_container_width=True):
            st.session_state.screen = "quiz"
            st.rerun()
    
    # Confirmation Banner
    st.success(f"🎉 **Successfully loaded {total_q} questions** from `{st.session_state.active_source}`!", icon="✅")
    
    # Metric Summary Row
    topics = list(set(q.get("topic", "General") for q in all_questions))
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        st.markdown(f"""
        <div class="metric-card">
            <span style="font-size: 0.75rem; color: #64748b;">Total Questions</span>
            <h3 style="margin: 2px 0 0 0; color: #4338ca;">{total_q}</h3>
        </div>
        """, unsafe_allow_html=True)
    with col_m2:
        st.markdown(f"""
        <div class="metric-card">
            <span style="font-size: 0.75rem; color: #64748b;">Detected Topics</span>
            <h3 style="margin: 2px 0 0 0; color: #065f46;">{len(topics)}</h3>
        </div>
        """, unsafe_allow_html=True)
    with col_m3:
        st.markdown(f"""
        <div class="metric-card">
            <span style="font-size: 0.75rem; color: #64748b;">Answer Keys Verified</span>
            <h3 style="margin: 2px 0 0 0; color: #92400e;">100%</h3>
        </div>
        """, unsafe_allow_html=True)
    with col_m4:
        st.markdown(f"""
        <div class="metric-card" style="border-color: #fca5a5; background: #fff5f5;">
            <span style="font-size: 0.75rem; color: #b91c1c; font-weight:700;">🔥 Exam Traps / Exceptions</span>
            <h3 style="margin: 2px 0 0 0; color: #dc2626;">{trap_count}</h3>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    
    # Highlight Trap Feature Box
    if trap_count > 0:
        st.markdown(f"""
        <div style="background: #fef2f2; border: 1.5px solid #fecaca; border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
            <div>
                <b style="color: #991b1b; font-size: 0.95rem;">🔥 High-Yield Exam Traps & Rule Exceptions Detected ({trap_count} Questions)</b>
                <div style="color: #7f1d1d; font-size: 0.82rem; margin-top: 2px;">
                    Questions with double-consonant traps, IE/EI rule exceptions, Greek silent roots, and frequently repeated TCS patterns.
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.subheader("⚙️ Batch Configuration")

    # Select Active Question Pool (All vs Traps Only)
    col_p1, col_p2 = st.columns([1.5, 1])
    with col_p1:
        pool_choice = st.radio(
            "Target Question Mode:",
            options=["Complete Test Series (All Questions)", f"🔥 High-Yield Traps & Exceptions Only ({trap_count} Questions)"],
            index=0 if not st.session_state.traps_only_mode else 1,
            horizontal=True
        )
        st.session_state.traps_only_mode = bool("Traps" in pool_choice)

    active_questions = trap_questions if (st.session_state.traps_only_mode and trap_count > 0) else all_questions
    active_total = len(active_questions)

    # Batch Size Selector
    col_b1, col_b2 = st.columns([2, 1])
    with col_b1:
        batch_size_option = st.radio(
            "Select Questions Per Batch:",
            options=[10, 20, 25, 50, "Custom"],
            horizontal=True,
            index=0 if active_total >= 10 else 4
        )
    with col_b2:
        if batch_size_option == "Custom":
            custom_size = st.number_input(
                "Custom Size",
                min_value=1,
                max_value=max(1, active_total),
                value=min(15, max(1, active_total))
            )
            st.session_state.batch_size = int(custom_size)
        else:
            st.session_state.batch_size = int(batch_size_option)

    batch_size = st.session_state.batch_size
    num_batches = math.ceil(active_total / batch_size) if active_total > 0 else 1

    # Batch Selector Grid / Dropdown
    batch_labels = []
    for i in range(num_batches):
        start_idx = i * batch_size + 1
        end_idx = min((i + 1) * batch_size, active_total)
        batch_slice = active_questions[start_idx - 1:end_idx]
        attempted_in_batch = sum(
            1 for q in batch_slice
            if q["question_number"] in st.session_state.user_answers
        )
        status = "✨ Fresh" if attempted_in_batch == 0 else f"📝 Attempted ({attempted_in_batch}/{len(batch_slice)})"
        batch_labels.append(f"Batch {i + 1}: Questions {start_idx} – {end_idx} [{status}]")

    selected_batch_str = st.selectbox(
        "Choose Which Batch to Attempt:",
        options=batch_labels,
        index=min(st.session_state.current_batch_idx, max(0, num_batches - 1))
    )
    st.session_state.current_batch_idx = batch_labels.index(selected_batch_str)

    st.markdown("<br>", unsafe_allow_html=True)
    
    col_btn1, col_btn2 = st.columns([1, 1])
    with col_btn1:
        if st.button("⬅️ Upload Different PDF", use_container_width=True):
            st.session_state.screen = "upload"
            st.rerun()
    with col_btn2:
        if st.button("🚀 Start Test Now", type="primary", use_container_width=True):
            st.session_state.screen = "quiz"
            st.rerun()


# ==========================================
# SCREEN 3: LIVE INTERACTIVE QUIZ INTERFACE
# ==========================================
elif st.session_state.screen == "quiz":
    all_questions = st.session_state.questions
    trap_questions = [q for q in all_questions if q.get("trap_info", {}).get("is_trap")]
    active_questions = trap_questions if (st.session_state.traps_only_mode and trap_questions) else all_questions
    
    total_q = len(active_questions)
    batch_size = st.session_state.batch_size
    num_batches = math.ceil(total_q / batch_size) if total_q > 0 else 1
    batch_idx = min(st.session_state.current_batch_idx, max(0, num_batches - 1))

    start_q_idx = batch_idx * batch_size
    end_q_idx = min(start_q_idx + batch_size, total_q)
    batch_questions = active_questions[start_q_idx:end_q_idx]

    # Calculate batch stats
    batch_q_ids = [q.get("uid", f"q_{q['question_number']}") for q in batch_questions]
    batch_attempted = [qid for qid in batch_q_ids if qid in st.session_state.user_answers]
    batch_correct = [
        q.get("uid", f"q_{q['question_number']}") for q in batch_questions
        if q.get("uid", f"q_{q['question_number']}") in st.session_state.user_answers
        and st.session_state.user_answers[q.get("uid", f"q_{q['question_number']}")] == q["correct_answer"]
    ]

    total_batch_qs = len(batch_questions)
    attempted_count = len(batch_attempted)
    correct_count = len(batch_correct)
    accuracy_pct = (correct_count / attempted_count * 100) if attempted_count > 0 else 0
    traps_in_batch = sum(1 for q in batch_questions if q.get("trap_info", {}).get("is_trap"))

    # Instant smooth scroll to top on batch change with staggered triggers
    components.html(f"""
    <script>
    function doScrollTop() {{
        try {{
            var targets = [
                window.parent.document.querySelector('section[data-testid="stMain"]'),
                window.parent.document.querySelector('[data-testid="stAppViewContainer"]'),
                window.parent.document.querySelector('.main'),
                window.parent.document.documentElement,
                window.parent.document.body,
                window.parent
            ];
            for (var i = 0; i < targets.length; i++) {{
                if (targets[i]) {{
                    if (typeof targets[i].scrollTo === 'function') {{
                        targets[i].scrollTo({{top: 0, behavior: 'instant'}});
                    }}
                    targets[i].scrollTop = 0;
                }}
            }}
        }} catch(err) {{}}
    }}
    doScrollTop();
    setTimeout(doScrollTop, 50);
    setTimeout(doScrollTop, 150);
    </script>
    <!-- batch_{batch_idx}_{time.time()} -->
    """, height=0, width=0)

    # ------------------------------------------
    # PERMANENT STICKY SCOREBOARD WITH BATCH NAV
    # ------------------------------------------
    st.markdown(f"""<div class="sticky-scoreboard">
<div style="display: flex; align-items: center; gap: 6px;">
<span class="q-badge q-badge-indigo">BATCH {batch_idx + 1}/{num_batches}</span>
<span style="font-weight: 700; font-size: 0.88rem;">Q{start_q_idx + 1}–Q{end_q_idx} ({total_batch_qs} Qs)</span>
{f'<span class="q-badge q-badge-trap">🔥 {traps_in_batch} Traps in Batch</span>' if traps_in_batch > 0 else ''}
</div>
<div style="display: flex; align-items: center; gap: 10px;">
<div><span style="color: #64748b; font-size: 0.7rem; font-weight: 700;">ATTEMPTED: </span><span style="font-weight: 800; font-size: 0.9rem; color: #1e293b;">{attempted_count}/{total_batch_qs}</span></div>
<div><span style="color: #64748b; font-size: 0.7rem; font-weight: 700;">SCORE: </span><span style="font-weight: 800; font-size: 0.9rem; color: #10b981;">{correct_count}/{attempted_count} ({accuracy_pct:.0f}%)</span></div>
</div>
</div>""", unsafe_allow_html=True)

    # Slim Progress Bar
    progress_val = attempted_count / total_batch_qs if total_batch_qs > 0 else 0
    st.progress(progress_val)

    # ------------------------------------------
    # TOP BATCH NAVIGATION & FILTER CONTROL BAR
    # ------------------------------------------
    filter_options = ["All", f"🔥 Exam Traps ({traps_in_batch})", "Unanswered", "Missed (Review)", "Solved (Correct)"]
    col_t_home, col_t_prev, col_t_filter, col_t_next = st.columns([1.1, 1.2, 3.2, 1.3])
    
    with col_t_home:
        if st.button("🏠 Home", key="top_home_btn", use_container_width=True, help="Exit to Home / Question Bank"):
            st.session_state.screen = "upload"
            st.rerun()

    with col_t_prev:
        if batch_idx > 0:
            if st.button("⬅️ Prev Batch", key="top_prev_btn", use_container_width=True):
                st.session_state.current_batch_idx = batch_idx - 1
                st.rerun()
        else:
            st.button("⬅️ Prev Batch", key="top_prev_disabled", disabled=True, use_container_width=True, help="You are on the first batch")

    with col_t_filter:
        filter_opt = st.radio(
            "Filter:",
            options=filter_options,
            horizontal=True,
            label_visibility="collapsed",
            key=f"filter_radio_batch_{batch_idx}"
        )

    with col_t_next:
        if batch_idx + 1 < num_batches:
            if st.button("Next Batch ➡️", key="top_next_btn", type="primary", use_container_width=True):
                st.session_state.current_batch_idx = batch_idx + 1
                st.rerun()
        else:
            if st.button("📊 Results", key="top_finish_btn", type="primary", use_container_width=True):
                st.session_state.screen = "summary"
                st.rerun()

    # ------------------------------------------
    # UNIFIED ULTRA-COMPACT QUESTION CARDS
    # ------------------------------------------
    for q_data in batch_questions:
        q_uid = q_data.get("uid", f"q_{q_data['question_number']}")
        q_num = q_data["question_number"]
        q_text = clean_question_text(q_data["question_text"])
        options = q_data["options"]
        correct_opt = q_data["correct_answer"]
        topic = q_data.get("topic", "General")
        existing_exp = q_data.get("explanation", "")
        trap_info = q_data.get("trap_info") or analyze_exam_trap(q_text, options)

        is_answered = q_uid in st.session_state.user_answers
        user_pick = st.session_state.user_answers.get(q_uid, None)

        has_verified_key = bool(correct_opt and correct_opt in ['A', 'B', 'C', 'D', 'E'])

        # Lazy Auto-solve: ONLY invoked when a question is answered and its answer was missing from the PDF.
        # Uses on-demand trigger or auto_ai_exp toggle to avoid blocking subsequent questions.
        if is_answered and not has_verified_key and st.session_state.gemini_api_key:
            auto_solve_key = f"auto_solved_{q_uid}"
            should_solve = st.session_state.get("auto_ai_exp", False) or st.session_state.get(f"solve_req_{q_uid}", False)
            if should_solve:
                if auto_solve_key not in st.session_state or st.session_state[auto_solve_key] == "FAILED":
                    with st.spinner(f"🔍 Verifying answer for Q{q_num} with AI..."):
                        solved_letter = solve_mcq_with_gemini(
                            api_key=st.session_state.gemini_api_key,
                            question_text=q_text,
                            options={k: clean_option_text(v) for k, v in options.items()},
                            model_name=st.session_state.gemini_model
                        )
                    if solved_letter in ['A', 'B', 'C', 'D', 'E']:
                        st.session_state[auto_solve_key] = solved_letter
                        correct_opt = solved_letter
                        q_data["correct_answer"] = solved_letter
                        has_verified_key = True
                        db_manager.update_question_correct_option(
                            correct_option=solved_letter,
                            db_id=q_data.get("db_id"),
                            content_hash=q_data.get("content_hash") or db_manager.compute_content_hash(q_text, options)
                        )
                        if "db_id" in q_data:
                            db_manager.record_user_attempt(
                                question_id=q_data["db_id"],
                                selected_option=user_pick,
                                is_correct=(user_pick == solved_letter),
                                user_id=st.session_state.user_id
                            )
                    else:
                        st.session_state[auto_solve_key] = "FAILED"
                elif st.session_state[auto_solve_key] in ['A', 'B', 'C', 'D', 'E']:
                    correct_opt = st.session_state[auto_solve_key]
                    q_data["correct_answer"] = correct_opt
                    has_verified_key = True

        is_correct = (user_pick == correct_opt) if (is_answered and has_verified_key) else False

        # Apply Quick Filter
        if "Exam Traps" in filter_opt and not trap_info.get("is_trap"):
            continue
        elif filter_opt == "Unanswered" and is_answered:
            continue
        elif filter_opt == "Missed (Review)" and (not is_answered or not has_verified_key or is_correct):
            continue
        elif filter_opt == "Solved (Correct)" and (not is_answered or not is_correct):
            continue

        # Single unified container with compact border
        with st.container(border=True):
            # Top header row
            if is_answered:
                if has_verified_key:
                    if is_correct:
                        status_html = f'<span class="q-badge q-badge-emerald">✓ SOLVED ({user_pick})</span>'
                    else:
                        status_html = f'<span class="q-badge" style="background:#fee2e2; color:#b91c1c;">✗ MISSED ({user_pick})</span>'
                else:
                    status_html = f'<span class="q-badge" style="background:#e0f2fe; color:#0369a1; border: 1px solid #bae6fd;">📝 RECORDED ({user_pick}) • KEY PENDING</span>'
            else:
                status_html = '<span class="q-badge" style="background:#f1f5f9; color:#64748b;">⏳ UNANSWERED</span>'

            trap_badge_html = (
                f'<span class="q-badge q-badge-trap">{trap_info.get("badge", "🔥 EXAM TRAP")}</span>'
                if trap_info.get("is_trap") else ''
            )
            
            is_bi = q_data.get("is_bilingual", False)
            en_t = q_data.get("english_text", "")
            hi_t = q_data.get("hindi_text", "")
            if is_bi and en_t and hi_t:
                q_body_html = f"""<div style="margin: 2px 0 4px 0; display: flex; flex-direction: column; gap: 2px;">
<div style="font-size: 0.88rem; font-weight: 600; line-height: 1.3; color: inherit;">
<span style="display:inline-block; font-size:0.64rem; font-weight:700; background:#e0e7ff; color:#3730a3; padding:1px 5px; border-radius:3px; margin-right:4px; vertical-align:middle;">ENG</span>{en_t}
</div>
<div style="font-size: 0.84rem; font-weight: 500; line-height: 1.3; color: #334155;">
<span style="display:inline-block; font-size:0.64rem; font-weight:700; background:#fef3c7; color:#92400e; padding:1px 5px; border-radius:3px; margin-right:4px; vertical-align:middle;">HIN</span>{hi_t}
</div>
</div>"""
            else:
                q_body_html = f"""<div style="font-size: 0.88rem; font-weight: 600; line-height: 1.3; color: inherit; margin: 2px 0 4px 0;">{q_text}</div>"""

            st.markdown(f"""<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;">
<div><span class="q-badge q-badge-indigo">Q{q_num}</span><span class="q-badge q-badge-amber">{topic}</span>{trap_badge_html}</div>
<div>{status_html}</div>
</div>
{q_body_html}""", unsafe_allow_html=True)

            # Option selection logic
            if not is_answered:
                # Dynamic Grid via CSS on st.radio (supports 4 or 5 options)
                opt_keys = [k for k in ["A", "B", "C", "D", "E"] if k in options]
                selected_choice = st.radio(
                    f"Options Q{q_num}:",
                    options=opt_keys,
                    format_func=lambda k: f"({k})  {clean_option_text(options.get(k, ''))}",
                    index=None,
                    key=f"radio_{q_uid}",
                    label_visibility="collapsed"
                )
                if selected_choice is not None:
                    st.session_state.user_answers[q_uid] = selected_choice
                    if "db_id" in q_data:
                        db_manager.record_user_attempt(
                            question_id=q_data["db_id"],
                            selected_option=selected_choice,
                            is_correct=(selected_choice == correct_opt) if has_verified_key else False,
                            user_id=st.session_state.user_id
                        )
                    st.rerun()

                if existing_exp:
                    with st.expander("📖 Peek Study Notes / Context (Optional)", expanded=False):
                        formatted_peek_html = format_study_notes_html(existing_exp)
                        st.markdown(f"""<div class="notes-scroll" style="max-height: 180px; overflow-y: auto; overflow-x: auto; padding: 8px 12px; background: #f8fafc; border-radius: 6px; border: 1px solid #e2e8f0; border-left: 3px solid #3b82f6;">
{formatted_peek_html}
</div>""", unsafe_allow_html=True)
                        if st.button("🔍 Open Notes in Popup", key=f"pre_popup_{q_uid}", use_container_width=True):
                            show_study_notes_modal(q_num, topic, formatted_peek_html)

            else:
                # LOCKED STATE: Grid Feedback (supports 4 or 5 options)
                boxes = []
                opt_keys = [k for k in ["A", "B", "C", "D", "E"] if k in options]
                for opt_k in opt_keys:
                    opt_val = clean_option_text(options.get(opt_k, ""))
                    if has_verified_key:
                        if opt_k == correct_opt and opt_k == user_pick:
                            cls = "option-box opt-correct"
                            badge_html = "<span style='font-size:0.68rem; font-weight:700;'>✓ YOUR ANSWER (CORRECT)</span>"
                        elif opt_k == user_pick and opt_k != correct_opt:
                            cls = "option-box opt-incorrect"
                            badge_html = "<span style='font-size:0.68rem; font-weight:700;'>✗ YOUR ANSWER (INCORRECT)</span>"
                        elif opt_k == correct_opt and user_pick != correct_opt:
                            cls = "option-box opt-correct"
                            badge_html = "<span style='font-size:0.68rem; font-weight:700;'>✓ CORRECT ANSWER</span>"
                        else:
                            cls = "option-box opt-muted"
                            badge_html = ""
                    else:
                        # Key was missing from PDF/DB (pending AI solve)
                        if opt_k == user_pick:
                            cls = "option-box"
                            badge_html = "<span style='font-size:0.68rem; font-weight:700; color:#0284c7;'>⏺ YOUR CHOICE (PENDING KEY)</span>"
                        else:
                            cls = "option-box opt-muted"
                            badge_html = ""

                    boxes.append(f"""<div class="{cls}"><div><strong>({opt_k})</strong> {opt_val}</div><div>{badge_html}</div></div>""")

                grid_html = f"""<div class="options-grid">{''.join(boxes)}</div>"""
                st.markdown(grid_html, unsafe_allow_html=True)

                # Fetch or retrieve explanation
                if q_uid not in st.session_state.gemini_cache:
                    is_forced = st.session_state.get(f"force_ai_{q_uid}", False)
                    is_auto = st.session_state.get("auto_ai_exp", False)

                    # 1. Check if AI explanation already exists in memory or Database
                    saved_ai = q_data.get("ai_explanation", "")
                    saved_model = q_data.get("ai_model", "Gemini")
                    if not saved_ai and not is_forced:
                        db_exp_info = db_manager.get_question_ai_explanation(
                            question_text=q_text,
                            options=options,
                            db_id=q_data.get("db_id")
                        )
                        if db_exp_info:
                            saved_ai = db_exp_info["ai_explanation"]
                            saved_model = db_exp_info.get("model", "Gemini")
                            q_data["ai_explanation"] = saved_ai
                            q_data["ai_model"] = saved_model

                    # 2. If user specifically requested AI (is_forced) or auto-fetch is ON (and no saved explanation yet):
                    if (is_forced or (is_auto and not saved_ai)) and st.session_state.gemini_api_key:
                        with st.spinner(f"⚡ Fetching AI explanation for Q{q_num}..."):
                            explanation_data = generate_hindi_explanation(
                                api_key=st.session_state.gemini_api_key,
                                question_text=q_text,
                                options={k: clean_option_text(v) for k, v in options.items()},
                                correct_answer=correct_opt,
                                existing_explanation=existing_exp,
                                model_name=st.session_state.gemini_model
                            )
                            # Persist AI explanation to Database so next time it is re-used!
                            if explanation_data.get("solved_correct_answer") and not has_verified_key:
                                solved_key = explanation_data["solved_correct_answer"]
                                correct_opt = solved_key
                                q_data["correct_answer"] = solved_key
                                has_verified_key = True
                                db_manager.update_question_correct_option(
                                    correct_option=solved_key,
                                    db_id=q_data.get("db_id"),
                                    content_hash=q_data.get("content_hash") or db_manager.compute_content_hash(q_text, options)
                                )

                            if explanation_data.get("success") and explanation_data.get("source") == "gemini":
                                ai_content = explanation_data.get("content", "").strip()
                                db_manager.save_question_ai_explanation(
                                    question_text=q_text,
                                    options={k: clean_option_text(v) for k, v in options.items()},
                                    ai_explanation=ai_content,
                                    model_name=st.session_state.gemini_model,
                                    correct_option=correct_opt if has_verified_key else "",
                                    db_id=q_data.get("db_id")
                                )
                                q_data["ai_explanation"] = ai_content
                                q_data["ai_model"] = st.session_state.gemini_model

                            st.session_state.gemini_cache[q_uid] = explanation_data
                            if f"force_ai_{q_uid}" in st.session_state:
                                del st.session_state[f"force_ai_{q_uid}"]

                    elif saved_ai:
                        # Re-use saved AI explanation from Database! (Instant 0ms, zero API quota)
                        explanation_data = {
                            "success": True,
                            "source": "gemini",
                            "content": saved_ai,
                            "model": saved_model,
                            "from_db": True
                        }
                        st.session_state.gemini_cache[q_uid] = explanation_data

                    elif existing_exp:
                        explanation_data = {
                            "success": True,
                            "source": "study_notes",
                            "content": existing_exp
                        }
                        st.session_state.gemini_cache[q_uid] = explanation_data
                    else:
                        explanation_data = {
                            "success": bool(existing_exp),
                            "source": "study_notes" if existing_exp else "fallback",
                            "content": existing_exp if existing_exp else (f"Correct Answer is Option ({correct_opt})" if has_verified_key else "Answer unspecified in PDF")
                        }
                        st.session_state.gemini_cache[q_uid] = explanation_data
                else:
                    explanation_data = st.session_state.gemini_cache[q_uid]

                # Render single clean explanation block with Trap Reason
                trap_explanation_snippet = (
                    f"<div style='margin-top:3px; color:#b91c1c; font-size:0.78rem; font-weight:600;'>⚠️ Exam Trap Alert: {trap_info.get('reason')}</div>"
                    if trap_info.get("is_trap") else ""
                )

                # Format study notes / description from CSV or PDF
                if existing_exp:
                    formatted_notes_html = format_study_notes_html(existing_exp)
                    is_long_note = len(existing_exp) > 220 or ("\t" in existing_exp) or ("|" in existing_exp)
                    notes_snippet = f"""<div class="notes-scroll" style="margin-top: 8px; padding: 10px 14px; background: #f8fafc; border-left: 3px solid #2563eb; border-radius: 6px; font-size: 0.82rem; line-height: 1.5; color: #1e293b; max-height: 200px; overflow-y: auto; overflow-x: auto; border: 1px solid #e2e8f0; border-left: 3px solid #2563eb;">
<div style="font-weight: 700; color: #1e40af; margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center;">
<div style="display: flex; align-items: center; gap: 4px;">
<span>📖</span> <span>Study Notes & Financial Facts</span>
</div>
{"<span style='font-size:0.70rem; color:#64748b; font-weight:500; background:#f1f5f9; padding:1px 6px; border-radius:4px;'>↕️ Scrollable</span>" if is_long_note else ""}
</div>
<div>{formatted_notes_html}</div>
</div>"""
                else:
                    formatted_notes_html = ""
                    notes_snippet = ""

                if explanation_data.get("source") == "gemini":
                    raw_content = explanation_data.get("content", "").strip()
                    formatted_lines = []
                    for line in raw_content.splitlines():
                        line_s = line.strip()
                        if line_s:
                            # Convert markdown bold to html strong
                            line_html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', line_s)
                            formatted_lines.append(f"<div style='margin-bottom: 2px;'>{line_html}</div>")
                    content_html = "".join(formatted_lines)
                    model_badge = explanation_data.get("model", "Gemini")
                    db_indicator = ' <span style="background:rgba(255,255,255,0.25); border-radius:3px; padding:0 3px; margin-left:3px; font-size:0.60rem;">💾 From DB</span>' if explanation_data.get("from_db") else ' <span style="background:rgba(255,255,255,0.25); border-radius:3px; padding:0 3px; margin-left:3px; font-size:0.60rem;">💾 Saved to DB</span>'
                    exp_html = f"""<div class="exp-box">
<div class="gemini-tag">⚡ Quick AI Solution ({model_badge}){db_indicator}</div>
{trap_explanation_snippet}
<div style="font-size:0.83rem; line-height:1.4; margin-top:3px; color:inherit;">{content_html}</div>
{notes_snippet}
</div>"""
                elif explanation_data.get("source") == "offline":
                    ans_title = f"💡 Correct Answer: Option ({correct_opt}) — {clean_option_text(options.get(correct_opt, ''))}" if has_verified_key else "💡 Answer: Unspecified in PDF"
                    offline_msg = (
                        f"📶 Offline Mode: AI server se connect nahi ho paya. Verified answer Option ({correct_opt}) show ho raha hai."
                        if has_verified_key
                        else "📶 Offline Mode: AI server se connect nahi ho paya (is question ka official answer PDF me missing tha). Niche '🔍 Solve with AI' se verify karein."
                    )
                    exp_html = f"""<div class="exp-box" style="border-left: 3px solid #f59e0b; background: #fffbeb;">
<div style="font-weight:700; color:#065f46; font-size:0.83rem;">{ans_title}</div>
{trap_explanation_snippet}
<div style="margin-top:4px; color:#b45309; font-size:0.75rem; font-weight:600;">{offline_msg}</div>
{notes_snippet}
</div>"""
                elif explanation_data.get("source") == "error":
                    err_msg = explanation_data.get("error_msg", "API Request Failed")
                    if has_verified_key:
                        ans_title = f"💡 Correct Answer: Option ({correct_opt}) — {clean_option_text(options.get(correct_opt, ''))}"
                    else:
                        ans_title = "💡 Answer: Unspecified in PDF"
                    exp_html = f"""<div class="exp-box" style="border-left: 3px solid #ef4444; background: #fff1f2;">
<div style="font-weight:700; color:#065f46; font-size:0.83rem;">{ans_title}</div>
{trap_explanation_snippet}
<div style="margin-top:4px; color:#b91c1c; font-size:0.75rem; font-weight:600;">⚠️ Gemini Notice: {err_msg}</div>
<div style="font-size:0.72rem; color:#64748b; margin-top:1px;">Please check your API Key or select a different Gemini Model from the sidebar.</div>
{notes_snippet}
</div>"""
                else:
                    tip_snippet = "<div style='margin-top:2px; font-size:0.72rem; color:#64748b;'>💡 Enter Gemini API Key in sidebar for Hindi translation & mnemonics.</div>" if not st.session_state.gemini_api_key else ""
                    if has_verified_key:
                        ans_title = f"💡 Correct Answer: Option ({correct_opt}) — {clean_option_text(options.get(correct_opt, ''))}"
                    else:
                        ans_title = "💡 Answer: Unspecified in PDF (Use '🔍 Solve with AI' below to find official answer)"
                    exp_html = f"""<div class="exp-box">
<div style="font-weight:700; color:#065f46; font-size:0.83rem;">{ans_title}</div>
{trap_explanation_snippet}
{notes_snippet}
{tip_snippet}
</div>"""

                st.markdown(exp_html, unsafe_allow_html=True)

                # Action buttons for this specific question
                if existing_exp:
                    col_notes_btn, col_retry, col_reset = st.columns([0.40, 0.36, 0.24])
                    with col_notes_btn:
                        if st.button("📖 Read Notes in Popup", key=f"popup_{q_uid}", use_container_width=True, help="Open complete study notes, facts & tables in a popup modal"):
                            show_study_notes_modal(q_num, topic, formatted_notes_html)
                else:
                    col_filler, col_retry, col_reset = st.columns([0.48, 0.30, 0.22])
                with col_retry:
                    # If answer is missing and not yet verified, provide prominent Solve with AI button
                    if not has_verified_key:
                        if st.session_state.gemini_api_key:
                            if st.button("🔍 Solve with AI", key=f"solve_btn_{q_uid}", type="primary", use_container_width=True, help="Auto-solve correct answer with Gemini AI and update database"):
                                st.session_state[f"solve_req_{q_uid}"] = True
                                st.session_state[f"force_ai_{q_uid}"] = True
                                st.rerun()
                        else:
                            st.caption("🔑 Enter Gemini Key")
                    elif explanation_data.get("source") in ["error", "offline"]:
                        if st.button("⚡ Retry AI", key=f"retry_exp_{q_uid}", use_container_width=True, help="Retry fetching AI solution"):
                            if q_uid in st.session_state.gemini_cache:
                                del st.session_state.gemini_cache[q_uid]
                            auto_solve_key = f"auto_solved_{q_uid}"
                            if auto_solve_key in st.session_state:
                                del st.session_state[auto_solve_key]
                            st.session_state[f"force_ai_{q_uid}"] = True
                            st.rerun()
                    elif explanation_data.get("source") == "gemini":
                        # Question already has an AI explanation, but user can re-ask anytime to get a fresh one!
                        if st.session_state.gemini_api_key:
                            if st.button("⚡ Re-ask Gemini AI", key=f"reask_ai_{q_uid}", use_container_width=True, help="Fetch fresh AI explanation from Gemini & update database"):
                                if q_uid in st.session_state.gemini_cache:
                                    del st.session_state.gemini_cache[q_uid]
                                st.session_state[f"force_ai_{q_uid}"] = True
                                st.rerun()
                    elif explanation_data.get("source") in ["study_notes", "fallback"]:
                        if st.session_state.gemini_api_key:
                            if st.button("⚡ Ask Gemini AI", key=f"ask_ai_{q_uid}", use_container_width=True, help="Get AI Hindi explanation & trick"):
                                if q_uid in st.session_state.gemini_cache:
                                    del st.session_state.gemini_cache[q_uid]
                                st.session_state[f"force_ai_{q_uid}"] = True
                                st.rerun()
                with col_reset:
                    if st.button("↩️ Re-attempt Q", key=f"reset_{q_uid}", use_container_width=True, help=f"Reset Q{q_num} to choose your answer again"):
                        if q_uid in st.session_state.user_answers:
                            del st.session_state.user_answers[q_uid]
                        if q_uid in st.session_state.gemini_cache:
                            del st.session_state.gemini_cache[q_uid]
                        if f"radio_{q_uid}" in st.session_state:
                            del st.session_state[f"radio_{q_uid}"]
                        if f"force_ai_{q_uid}" in st.session_state:
                            del st.session_state[f"force_ai_{q_uid}"]
                        if f"solve_req_{q_uid}" in st.session_state:
                            del st.session_state[f"solve_req_{q_uid}"]
                        st.rerun()

    # ------------------------------------------
    # BOTTOM NAVIGATION WITH BOTH PREVIOUS & NEXT
    # ------------------------------------------
    st.markdown("<br>", unsafe_allow_html=True)
    col_prev, col_retry, col_settings, col_next, col_home = st.columns([1.2, 1.1, 1.1, 1.3, 1.1])
    
    # 1. Previous Batch Button
    with col_prev:
        if batch_idx > 0:
            if st.button("⬅️ Previous Batch", key="btn_bot_prev", use_container_width=True):
                st.session_state.current_batch_idx = batch_idx - 1
                st.rerun()
        else:
            st.button("⬅️ Previous Batch", key="btn_bot_prev_dis", disabled=True, use_container_width=True, help="You are on the first batch")

    # 2. Retry Current Batch
    with col_retry:
        if st.button("🔄 Retry Batch", key="btn_bot_retry", use_container_width=True):
            for q in batch_questions:
                qid = q.get("uid", f"q_{q['question_number']}")
                if qid in st.session_state.user_answers:
                    del st.session_state.user_answers[qid]
                if qid in st.session_state.gemini_cache:
                    del st.session_state.gemini_cache[qid]
                if f"radio_{qid}" in st.session_state:
                    del st.session_state[f"radio_{qid}"]
            st.rerun()

    # 3. Batch Settings
    with col_settings:
        if st.button("⚙️ Settings", key="btn_bot_settings", use_container_width=True):
            st.session_state.screen = "batch_setup"
            st.rerun()

    # 4. Next Batch Button
    with col_next:
        if batch_idx + 1 < num_batches:
            if st.button("Next Batch ➡️", key="btn_bot_next", type="primary", use_container_width=True):
                st.session_state.current_batch_idx = batch_idx + 1
                st.rerun()
        else:
            if st.button("📊 Final Results", key="btn_bot_results", type="primary", use_container_width=True):
                st.session_state.screen = "summary"
                st.rerun()

    # 5. Home / Bank Button
    with col_home:
        if st.button("🏠 Home / Bank", key="btn_bot_home", use_container_width=True, help="Exit test and return to Question Bank"):
            st.session_state.screen = "upload"
            st.rerun()


# ==========================================
# SCREEN 4: MARATHON BATCH SUMMARY & RESULTS
# ==========================================
elif st.session_state.screen == "summary":
    total_q = len(st.session_state.questions)
    attempted_q = len(st.session_state.user_answers)
    verified_attempted_q = sum(
        1 for q in st.session_state.questions
        if q.get("uid", f"q_{q['question_number']}") in st.session_state.user_answers
        and q.get("correct_answer") in ['A', 'B', 'C', 'D', 'E']
    )
    pending_key_q = attempted_q - verified_attempted_q
    correct_q = sum(
        1 for q in st.session_state.questions
        if q.get("uid", f"q_{q['question_number']}") in st.session_state.user_answers
        and q.get("correct_answer") in ['A', 'B', 'C', 'D', 'E']
        and st.session_state.user_answers[q.get("uid", f"q_{q['question_number']}")] == q["correct_answer"]
    )
    incorrect_q = verified_attempted_q - correct_q
    unanswered_q = total_q - attempted_q
    score_pct = (correct_q / total_q * 100) if total_q > 0 else 0
    accuracy_pct = (correct_q / verified_attempted_q * 100) if verified_attempted_q > 0 else 0

    # Calculate Traps Mastery
    traps_total = sum(1 for q in st.session_state.questions if q.get("trap_info", {}).get("is_trap"))
    traps_correct = sum(
        1 for q in st.session_state.questions
        if q.get("trap_info", {}).get("is_trap")
        and q.get("uid", f"q_{q['question_number']}") in st.session_state.user_answers
        and q.get("correct_answer") in ['A', 'B', 'C', 'D', 'E']
        and st.session_state.user_answers[q.get("uid", f"q_{q['question_number']}")] == q["correct_answer"]
    )

    # ------------------------------------------
    # TOP ROUTING BAR (Return Home, Retake, or Review)
    # ------------------------------------------
    col_sum_nav1, col_sum_nav2, col_sum_nav3, col_sum_nav4 = st.columns([1.3, 1.3, 1.1, 1.3])
    with col_sum_nav1:
        if st.button("🏠 Home / Question Bank", key="sum_top_home", type="primary", use_container_width=True):
            st.session_state.screen = "upload"
            st.rerun()
    with col_sum_nav2:
        if st.button("✍️ Back to Quiz Questions", key="sum_top_quiz", use_container_width=True):
            st.session_state.screen = "quiz"
            st.rerun()
    with col_sum_nav3:
        if st.button("⚙️ Batch Setup", key="sum_top_setup", use_container_width=True):
            st.session_state.screen = "batch_setup"
            st.rerun()
    with col_sum_nav4:
        if st.button("🔄 Retake from Batch 1", key="sum_top_retake", use_container_width=True):
            st.session_state.user_answers = {}
            st.session_state.current_batch_idx = 0
            st.session_state.screen = "quiz"
            st.rerun()

    st.markdown("""
    <div style="text-align: center; padding: 10px 0;">
        <h2 style="font-weight: 800; font-size: 1.8rem; margin-bottom: 2px;">
            📊 OptNote Performance Report
        </h2>
        <p style="color: #64748b; font-size: 0.92rem;">
            Detailed analytics, score breakdown, and rule exception mastery.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Performance Banner
    if score_pct >= 80:
        st.success(f"🏆 **Outstanding Performance!** You scored **{correct_q} / {total_q}** ({score_pct:.1f}%). Excellent readiness!", icon="🌟")
    elif score_pct >= 50:
        st.info(f"👍 **Good Effort!** You scored **{correct_q} / {total_q}** ({score_pct:.1f}%). Review incorrect questions below.", icon="📈")
    else:
        st.warning(f"📚 **Keep Practicing!** You scored **{correct_q} / {total_q}** ({score_pct:.1f}%). Revise concepts to boost retention.", icon="💡")

    # Score Metrics
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Score", f"{correct_q} / {total_q}", f"{score_pct:.1f}%")
    with c2:
        acc_label = f"{accuracy_pct:.1f}%" if verified_attempted_q > 0 else "N/A"
        st.metric("Accuracy", acc_label, f"{pending_key_q} pending" if pending_key_q > 0 else None)
    with c3:
        st.metric("🔥 Traps Mastered", f"{traps_correct} / {traps_total}")
    with c4:
        st.metric("Incorrect / Skipped", f"{incorrect_q} / {unanswered_q}")

    st.markdown("<br>", unsafe_allow_html=True)

    # Detailed Question Review
    st.subheader("🔍 Question-by-Question Review")
    with st.expander("Click to view review of all questions", expanded=True):
        for q in st.session_state.questions:
            q_uid = q.get("uid", f"q_{q['question_number']}")
            q_num = q["question_number"]
            user_pick = st.session_state.user_answers.get(q_uid, None)
            correct_opt = q["correct_answer"]
            opts = q["options"]
            trap_info = q.get("trap_info", {})
            has_key = bool(correct_opt and correct_opt in ['A', 'B', 'C', 'D', 'E'])

            if user_pick is None:
                status_icon = "⚪ Skipped"
                status_color = "#64748b"
            elif not has_key:
                status_icon = "🔵 Answer Recorded (Key Pending)"
                status_color = "#0284c7"
            elif user_pick == correct_opt:
                status_icon = "🟢 Correct"
                status_color = "#10b981"
            else:
                status_icon = "🔴 Incorrect"
                status_color = "#ef4444"

            trap_tag = f" | <b style='color:#b91c1c;'>🔥 {trap_info.get('badge')}</b>" if trap_info.get("is_trap") else ""
            correct_display = f"Option ({correct_opt}) — {clean_option_text(opts.get(correct_opt, ''))}" if has_key else "Unspecified in Source PDF"

            st.markdown(f"""
            <div style="border-left: 3px solid {status_color}; padding: 6px 12px; margin: 6px 0; background: rgba(0,0,0,0.02); border-radius: 6px;">
                <strong>Q{q_num}. {clean_option_text(q['question_text'])}</strong><br>
                <span style="font-size:0.82rem; color: #475569;">
                    Your Answer: <b>{user_pick if user_pick else 'None'}</b> | Correct: <b>{correct_display}</b> | Status: <b>{status_icon}</b>{trap_tag}
                </span>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    
    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    with col_s1:
        if st.button("🏠 Home / Question Bank", key="sum_bot_home", type="primary", use_container_width=True):
            st.session_state.screen = "upload"
            st.rerun()
    with col_s2:
        if st.button("✍️ Back to Quiz / Review", key="sum_bot_quiz", use_container_width=True):
            st.session_state.screen = "quiz"
            st.rerun()
    with col_s3:
        if st.button("⚙️ Batch Settings", key="sum_bot_setup", use_container_width=True):
            st.session_state.screen = "batch_setup"
            st.rerun()
    with col_s4:
        if st.button("🔄 Retake from Batch 1", key="sum_bot_retake", use_container_width=True):
            st.session_state.user_answers = {}
            st.session_state.current_batch_idx = 0
            st.session_state.screen = "quiz"
            st.rerun()
