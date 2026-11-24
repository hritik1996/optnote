# ⚡ OptNote (optnote.com) — AI-Powered Test Series & Exam Engine

An AI-powered, interactive competitive exam practice and question repository platform built with **Python**, **Streamlit**, **PostgreSQL / SQLite**, **PyMuPDF**, and **Google Gemini API** (`google-genai`).

Designed specifically for competitive exam aspirants (**SSC CGL, UPSC, Banking PO/Clerk, Railways, Defence, State PSC**), featuring automated exam trap detection, instant answer evaluation, zero-latency database caching, and AI-powered bilingual Hindi explanations.

---

## 🌟 Key Features

1. **Central Question Repository (PostgreSQL & SQLite Dual Engine)**:
   - Centralized question bank storing thousands of MCQs categorized by Subject and Topic.
   - **SHA-256 Content-Hash De-duplication**: Automatically prevents duplicate questions from being inserted when uploading new papers or PDFs.
   - Fast keyword search (English & Hindi) and subject/topic filtering.

2. **Automated Exam Trap & Rule Exception Detection (`trap_analyzer.py`)**:
   - Identifies tricky questions containing **Double-Consonant traps** (e.g. *accommodate*, *embarrass*), **IE/EI rule exceptions**, **silent Greek roots**, fixed prepositions, and high-yield static GK exceptions.
   - Flags questions with distinct badges (`🔥 EXAM TRAP`) so students can focus on error-prone concepts.

3. **Multi-Format Input Engine**:
   - **PDF Upload**: Fast extraction via **PyMuPDF** (`fitz`). Supports multi-topic answer keys at the bottom of the paper.
   - **CSV / Spreadsheet Upload**: Native support for tabular questions, bilingual columns (English + Hindi), and financial awareness study notes.
   - **Direct Raw Text Paste**: Paste MCQs directly with automatic formatting.
   - **Instant Demo Test**: 20 pre-loaded high-yield questions for instant testing.

4. **Interactive Practice Quiz & Instant Feedback**:
   - Compact 2x2 grid options with locked feedback on click.
   - **Pending Key Protection**: Questions with unspecified answer keys are never falsely marked incorrect.
   - **1-Click "Solve with AI"**: Auto-solves missing answer keys with Gemini AI and persists verified answers to the database for future practice.

5. **AI Bilingual Explanations & Zero-Latency DB Caching**:
   - Ultra-compact Hindi + English breakdown (हिन्दी अर्थ, सटीक कारण, याद रखने की ट्रिक).
   - Once generated, explanations are cached directly in the database (`ai_explanation`), enabling **0ms load time** and **zero API quota usage** on retakes.
   - On-demand `⚡ Re-ask Gemini AI` button for fresh explanations.

---

## 🚀 Quick Setup Guide

### 1. Clone the Repository
```bash
git clone https://github.com/hritik1996/optnote.git
cd optnote
```

### 2. Set Up Virtual Environment & Dependencies
```bash
# Create a virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS / Linux:
source venv/bin/activate
# On Windows:
# .\venv\Scripts\activate

# Install required packages
pip install -r requirements.txt
```

### 3. (Optional) Database Configuration
- By default, the app automatically connects to **PostgreSQL** on `localhost:5432` (database: `mcq_bank`, user: `postgres`).
- If PostgreSQL is not installed or running, it **seamlessly falls back to local SQLite** (`mcq_bank.db`) with zero configuration required.

You can customize PostgreSQL credentials via environment variables:
```bash
export PGHOST="127.0.0.1"
export PGPORT="5432"
export PGUSER="postgres"
export PGPASSWORD="your_password"
export PGDATABASE="mcq_bank"
```

### 4. Run the Application
```bash
streamlit run app.py
```
Open your browser at `http://localhost:8501`.

---

## 🧪 Running Automated Tests
Run the complete test suite to verify parsing, deduplication, trap detection, and database operations:
```bash
python3 -m unittest test_app.py
```

---

## 📂 Project Architecture

```
├── app.py                         # Streamlit application UI and routing (OptNote Engine)
├── db_manager.py                  # PostgreSQL & SQLite database engine and caching
├── gemini_helper.py               # Google GenAI client, solver, and bilingual explainer
├── mcq_parser.py                  # Multi-format MCQ extraction (PDF, CSV, Raw Text)
├── trap_analyzer.py               # High-yield exam trap and rule exception detector
├── test_app.py                    # 20 automated unit tests covering all modules
├── requirements.txt               # Python package dependencies
├── .gitignore                     # Git ignore rules for venv, DB, and cache
└── sample_financial_awareness.csv # Sample CSV test dataset
```

---

## 🛡️ License
MIT License. Free to use for personal preparation and educational institutions.
