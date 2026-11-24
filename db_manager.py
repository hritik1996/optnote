"""
Database Manager for OptNote (optnote.com) MCQ Test Series & Question Bank.
Supports PostgreSQL (Local & Cloud like Supabase/Neon) with SQLite fallback.
Features:
- User-wise architecture (Guest default, ready for future Auth)
- Question De-duplication via SHA-256 Content Hash
- Multi-Subject & Topic Hierarchy
- Versioning for updated questions & explanations
- Fast Search & Filter APIs
- User Analytics & Attempt Tracking
"""
import os
import re
import json
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone

# Database Configuration (environment variables or defaults)
PG_HOST = os.getenv("PGHOST", "127.0.0.1")
PG_PORT = int(os.getenv("PGPORT", "5432"))
PG_USER = os.getenv("PGUSER", "postgres")
PG_PASSWORD = os.getenv("PGPASSWORD", "")
PG_DATABASE = os.getenv("PGDATABASE", "mcq_bank")

DEFAULT_GUEST_USER_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_GUEST_USERNAME = "guest"

# Global connection engine type: "postgres" or "sqlite"
_ACTIVE_DB_TYPE = "postgres"

def get_connection():
    """
    Returns a live connection to PostgreSQL.
    Falls back to SQLite (mcq_bank.db) if PostgreSQL is unavailable.
    """
    global _ACTIVE_DB_TYPE
    try:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            user=PG_USER,
            password=PG_PASSWORD,
            dbname=PG_DATABASE,
            connect_timeout=3
        )
        conn.autocommit = False
        _ACTIVE_DB_TYPE = "postgres"
        return conn
    except Exception as pg_err:
        import sqlite3
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcq_bank.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        _ACTIVE_DB_TYPE = "sqlite"
        return conn

def get_active_db_type() -> str:
    return _ACTIVE_DB_TYPE

def compute_content_hash(question_text: str, options: Optional[Dict[str, str]] = None) -> str:
    """
    Computes a deterministic SHA-256 hash of normalized question text and options.
    Strips noise, punctuation, markdown formatting, and whitespace to prevent duplicates.
    """
    norm = re.sub(r'[^a-zA-Z0-9\u0900-\u097F]', '', question_text.lower())
    if options:
        opt_str = "".join(re.sub(r'[^a-zA-Z0-9\u0900-\u097F]', '', str(v).lower()) for k, v in sorted(options.items()))
        norm += opt_str
    return hashlib.sha256(norm.encode('utf-8')).hexdigest()

def init_db():
    """
    Initializes database tables, indexes, default guest user, and primary subjects.
    Idempotent: safe to run multiple times.
    """
    conn = get_connection()
    is_pg = (_ACTIVE_DB_TYPE == "postgres")
    cur = conn.cursor()

    try:
        if is_pg:
            # Enable trigram extension for fuzzy searching if permissions allow
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
            except Exception:
                conn.rollback()

            cur.execute("""
            -- 1. Users Table (Future-ready for Auth)
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                username VARCHAR(100) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE,
                display_name VARCHAR(150),
                role VARCHAR(20) DEFAULT 'student',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );

            -- 2. Subjects Table
            CREATE TABLE IF NOT EXISTS subjects (
                id SERIAL PRIMARY KEY,
                name VARCHAR(150) NOT NULL UNIQUE,
                slug VARCHAR(150) NOT NULL UNIQUE,
                icon VARCHAR(10) DEFAULT '📚',
                description TEXT DEFAULT '',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );

            -- 3. Topics Table
            CREATE TABLE IF NOT EXISTS topics (
                id SERIAL PRIMARY KEY,
                subject_id INT REFERENCES subjects(id) ON DELETE CASCADE,
                name VARCHAR(200) NOT NULL,
                slug VARCHAR(200) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(subject_id, name)
            );

            -- 4. Sources / Uploaded Files Tracking Table
            CREATE TABLE IF NOT EXISTS sources (
                id SERIAL PRIMARY KEY,
                user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                file_name VARCHAR(255) NOT NULL,
                file_hash VARCHAR(64) UNIQUE NOT NULL,
                file_type VARCHAR(20) NOT NULL,
                subject_id INT REFERENCES subjects(id) ON DELETE SET NULL,
                total_questions INT DEFAULT 0,
                uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );

            -- 5. Questions Table (With De-duplication & Versioning)
            CREATE TABLE IF NOT EXISTS questions (
                id SERIAL PRIMARY KEY,
                subject_id INT REFERENCES subjects(id) ON DELETE SET NULL,
                topic_id INT REFERENCES topics(id) ON DELETE SET NULL,
                source_id INT REFERENCES sources(id) ON DELETE SET NULL,
                content_hash VARCHAR(64) UNIQUE NOT NULL,
                question_text TEXT NOT NULL,
                question_text_hi TEXT DEFAULT '',
                is_bilingual BOOLEAN DEFAULT FALSE,
                options JSONB NOT NULL,
                correct_option VARCHAR(5) DEFAULT '',
                explanation TEXT DEFAULT '',
                ai_explanation TEXT DEFAULT '',
                ai_model VARCHAR(100) DEFAULT '',
                trap_info JSONB DEFAULT '{}'::jsonb,
                exam_tags JSONB DEFAULT '[]'::jsonb,
                study_notes TEXT DEFAULT '',
                difficulty VARCHAR(20) DEFAULT 'medium',
                version INT DEFAULT 1,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_questions_content_hash ON questions(content_hash);
            CREATE INDEX IF NOT EXISTS idx_questions_topic_id ON questions(topic_id);
            CREATE INDEX IF NOT EXISTS idx_questions_subject_id ON questions(subject_id);

            -- 6. User Test Sessions Table
            CREATE TABLE IF NOT EXISTS user_test_sessions (
                id SERIAL PRIMARY KEY,
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                subject_id INT REFERENCES subjects(id) ON DELETE SET NULL,
                topic_id INT REFERENCES topics(id) ON DELETE SET NULL,
                total_questions INT NOT NULL,
                attempted_count INT DEFAULT 0,
                correct_count INT DEFAULT 0,
                incorrect_count INT DEFAULT 0,
                score_percentage NUMERIC(5, 2) DEFAULT 0.00,
                session_source VARCHAR(100) DEFAULT 'Practice',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );

            -- 7. User Question Attempts Table
            CREATE TABLE IF NOT EXISTS user_question_attempts (
                id SERIAL PRIMARY KEY,
                session_id INT REFERENCES user_test_sessions(id) ON DELETE CASCADE,
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                question_id INT REFERENCES questions(id) ON DELETE CASCADE,
                selected_option VARCHAR(5) NOT NULL,
                is_correct BOOLEAN NOT NULL,
                time_taken_seconds INT DEFAULT 0,
                attempted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );

            -- 8. User Bookmarks Table
            CREATE TABLE IF NOT EXISTS user_bookmarks (
                id SERIAL PRIMARY KEY,
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                question_id INT REFERENCES questions(id) ON DELETE CASCADE,
                notes TEXT DEFAULT '',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, question_id)
            );
            """)

            # Insert Default Guest User
            cur.execute("""
            INSERT INTO users (id, username, display_name, role)
            VALUES (%s, %s, %s, 'student')
            ON CONFLICT (username) DO NOTHING;
            """, (DEFAULT_GUEST_USER_ID, DEFAULT_GUEST_USERNAME, "Guest Learner"))

            # Insert Default Subjects
            default_subjects = [
                ("Computer Knowledge", "computer-knowledge", "💻", "Hardware, Software, Networking, Shortcuts, MS Office"),
                ("Banking & Financial Awareness", "financial-awareness", "🏦", "RBI, Monetary Policy, Banking Terms, Financial GK"),
                ("English Language & Comprehension", "english-language", "📖", "Vocabulary, Spelling, Idioms, Error Spotting"),
                ("General Studies & Static GK", "general-studies", "🌍", "History, Geography, Polity, Science, Current Affairs"),
                ("Quantitative Aptitude", "quant-aptitude", "📐", "Arithmetic, Algebra, Data Interpretation"),
                ("General / Mixed", "general-mixed", "⚡", "Mixed exam sets and unassigned subjects")
            ]
            for name, slug, icon, desc in default_subjects:
                cur.execute("""
                INSERT INTO subjects (name, slug, icon, description)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (slug) DO NOTHING;
                """, (name, slug, icon, desc))

            # Auto-migrate existing Postgres database
            cur.execute("""
            ALTER TABLE questions ADD COLUMN IF NOT EXISTS ai_explanation TEXT DEFAULT '';
            ALTER TABLE questions ADD COLUMN IF NOT EXISTS ai_model VARCHAR(100) DEFAULT '';
            """)

        else:
            # SQLite Fallback Schema
            cur.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE,
                display_name TEXT,
                role TEXT DEFAULT 'student',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                slug TEXT NOT NULL UNIQUE,
                icon TEXT DEFAULT '📚',
                description TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER REFERENCES subjects(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                slug TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(subject_id, name)
            );
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT REFERENCES users(id),
                file_name TEXT NOT NULL,
                file_hash TEXT UNIQUE NOT NULL,
                file_type TEXT NOT NULL,
                subject_id INTEGER REFERENCES subjects(id),
                total_questions INTEGER DEFAULT 0,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER REFERENCES subjects(id),
                topic_id INTEGER REFERENCES topics(id),
                source_id INTEGER REFERENCES sources(id),
                content_hash TEXT UNIQUE NOT NULL,
                question_text TEXT NOT NULL,
                question_text_hi TEXT DEFAULT '',
                is_bilingual INTEGER DEFAULT 0,
                options TEXT NOT NULL,
                correct_option TEXT DEFAULT '',
                explanation TEXT DEFAULT '',
                ai_explanation TEXT DEFAULT '',
                ai_model TEXT DEFAULT '',
                trap_info TEXT DEFAULT '{}',
                exam_tags TEXT DEFAULT '[]',
                study_notes TEXT DEFAULT '',
                difficulty TEXT DEFAULT 'medium',
                version INTEGER DEFAULT 1,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS user_test_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT REFERENCES users(id),
                subject_id INTEGER REFERENCES subjects(id),
                topic_id INTEGER REFERENCES topics(id),
                total_questions INTEGER NOT NULL,
                attempted_count INTEGER DEFAULT 0,
                correct_count INTEGER DEFAULT 0,
                incorrect_count INTEGER DEFAULT 0,
                score_percentage REAL DEFAULT 0.0,
                session_source TEXT DEFAULT 'Practice',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS user_question_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER REFERENCES user_test_sessions(id),
                user_id TEXT REFERENCES users(id),
                question_id INTEGER REFERENCES questions(id),
                selected_option TEXT NOT NULL,
                is_correct INTEGER NOT NULL,
                time_taken_seconds INTEGER DEFAULT 0,
                attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS user_bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT REFERENCES users(id),
                question_id INTEGER REFERENCES questions(id),
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, question_id)
            );
            """)

            cur.execute("""
            INSERT OR IGNORE INTO users (id, username, display_name, role)
            VALUES (?, ?, ?, 'student');
            """, (DEFAULT_GUEST_USER_ID, DEFAULT_GUEST_USERNAME, "Guest Learner"))

            default_subjects = [
                ("Computer Knowledge", "computer-knowledge", "💻", "Hardware, Software, Networking, Shortcuts, MS Office"),
                ("Banking & Financial Awareness", "financial-awareness", "🏦", "RBI, Monetary Policy, Banking Terms, Financial GK"),
                ("English Language & Comprehension", "english-language", "📖", "Vocabulary, Spelling, Idioms, Error Spotting"),
                ("General Studies & Static GK", "general-studies", "🌍", "History, Geography, Polity, Science, Current Affairs"),
                ("Quantitative Aptitude", "quant-aptitude", "📐", "Arithmetic, Algebra, Data Interpretation"),
                ("General / Mixed", "general-mixed", "⚡", "Mixed exam sets and unassigned subjects")
            ]
            for name, slug, icon, desc in default_subjects:
                cur.execute("""
                INSERT OR IGNORE INTO subjects (name, slug, icon, description)
                VALUES (?, ?, ?, ?);
                """, (name, slug, icon, desc))

            # Auto-migrate existing SQLite database
            for col_def in ["ai_explanation TEXT DEFAULT ''", "ai_model TEXT DEFAULT ''"]:
                try:
                    cur.execute(f"ALTER TABLE questions ADD COLUMN {col_def};")
                except Exception:
                    pass

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def get_or_create_subject(name: str, conn=None) -> int:
    """Returns subject_id for a given subject name, auto-creating if not found."""
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    is_pg = (_ACTIVE_DB_TYPE == "postgres")
    cur = conn.cursor()
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') or 'general'
    
    try:
        if is_pg:
            cur.execute("SELECT id FROM subjects WHERE name = %s OR slug = %s LIMIT 1;", (name, slug))
            row = cur.fetchone()
            if row:
                return row[0]
            cur.execute("""
            INSERT INTO subjects (name, slug) VALUES (%s, %s)
            ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
            RETURNING id;
            """, (name, slug))
            sub_id = cur.fetchone()[0]
            conn.commit()
            return sub_id
        else:
            cur.execute("SELECT id FROM subjects WHERE name = ? OR slug = ? LIMIT 1;", (name, slug))
            row = cur.fetchone()
            if row:
                return row[0]
            cur.execute("INSERT OR IGNORE INTO subjects (name, slug) VALUES (?, ?);", (name, slug))
            conn.commit()
            cur.execute("SELECT id FROM subjects WHERE slug = ?;", (slug,))
            return cur.fetchone()[0]
    finally:
        cur.close()
        if should_close:
            conn.close()

def get_or_create_topic(subject_id: int, topic_name: str, conn=None) -> int:
    """Returns topic_id for a given subject and topic name, auto-creating if not found."""
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    is_pg = (_ACTIVE_DB_TYPE == "postgres")
    cur = conn.cursor()
    clean_topic = topic_name.strip() or "General"
    slug = re.sub(r'[^a-z0-9]+', '-', clean_topic.lower()).strip('-') or 'general'

    try:
        if is_pg:
            cur.execute("SELECT id FROM topics WHERE subject_id = %s AND (name = %s OR slug = %s) LIMIT 1;", (subject_id, clean_topic, slug))
            row = cur.fetchone()
            if row:
                return row[0]
            cur.execute("""
            INSERT INTO topics (subject_id, name, slug) VALUES (%s, %s, %s)
            ON CONFLICT (subject_id, name) DO NOTHING
            RETURNING id;
            """, (subject_id, clean_topic, slug))
            res = cur.fetchone()
            if res:
                conn.commit()
                return res[0]
            cur.execute("SELECT id FROM topics WHERE subject_id = %s AND name = %s;", (subject_id, clean_topic))
            sub_id = cur.fetchone()[0]
            conn.commit()
            return sub_id
        else:
            cur.execute("SELECT id FROM topics WHERE subject_id = ? AND (name = ? OR slug = ?) LIMIT 1;", (subject_id, clean_topic, slug))
            row = cur.fetchone()
            if row:
                return row[0]
            cur.execute("INSERT OR IGNORE INTO topics (subject_id, name, slug) VALUES (?, ?, ?);", (subject_id, clean_topic, slug))
            conn.commit()
            cur.execute("SELECT id FROM topics WHERE subject_id = ? AND name = ?;", (subject_id, clean_topic))
            return cur.fetchone()[0]
    finally:
        cur.close()
        if should_close:
            conn.close()

def save_parsed_questions(
    questions: List[Dict[str, Any]],
    source_name: str,
    subject_name: str = "General",
    user_id: str = DEFAULT_GUEST_USER_ID,
    file_bytes: Optional[bytes] = None
) -> Dict[str, Any]:
    """
    Saves parsed MCQs into PostgreSQL/SQLite with smart de-duplication:
    - Calculates content_hash for each question.
    - If question already exists:
        - Updates explanation if existing is empty and new is available.
        - Merges exam tags (e.g. 'SBI PO 2015').
        - Bumps version if content updated.
        - Avoids duplicating question rows.
    - If question is new:
        - Inserts into questions table with version = 1.
    Returns: {"total": N, "inserted": X, "updated": Y, "duplicates": Z}
    """
    if not questions:
        return {"total": 0, "inserted": 0, "updated": 0, "duplicates": 0}

    init_db()
    conn = get_connection()
    is_pg = (_ACTIVE_DB_TYPE == "postgres")
    cur = conn.cursor()

    inserted_count = 0
    updated_count = 0
    duplicate_count = 0

    try:
        # 1. Subject & Source
        subject_id = get_or_create_subject(subject_name, conn=conn)
        
        file_hash = hashlib.sha256(file_bytes).hexdigest() if file_bytes else hashlib.sha256(f"{source_name}_{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()
        file_type = "pdf" if source_name.lower().endswith(".pdf") else ("csv" if source_name.lower().endswith(".csv") else "text")

        source_id = None
        if is_pg:
            cur.execute("""
            INSERT INTO sources (user_id, file_name, file_hash, file_type, subject_id, total_questions)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (file_hash) DO UPDATE SET total_questions = EXCLUDED.total_questions
            RETURNING id;
            """, (user_id, source_name, file_hash, file_type, subject_id, len(questions)))
            source_id = cur.fetchone()[0]
        else:
            cur.execute("""
            INSERT OR REPLACE INTO sources (user_id, file_name, file_hash, file_type, subject_id, total_questions)
            VALUES (?, ?, ?, ?, ?, ?);
            """, (user_id, source_name, file_hash, file_type, subject_id, len(questions)))
            source_id = cur.lastrowid

        # Cache topic ids to avoid redundant queries
        topic_cache = {}

        for q in questions:
            q_text = q.get("question_text", "").strip()
            if not q_text or len(q_text) < 4:
                continue

            options = q.get("options", {})
            correct_opt = q.get("correct_answer", "")
            explanation = q.get("explanation", "").strip()
            topic_str = q.get("topic", "General").strip()
            trap_info = q.get("trap_info", {})
            study_notes = q.get("study_notes", "") or explanation
            is_bi = bool(q.get("is_bilingual", False))
            q_hi = q.get("hindi_text", "")

            # Topic ID
            if topic_str not in topic_cache:
                topic_cache[topic_str] = get_or_create_topic(subject_id, topic_str, conn=conn)
            t_id = topic_cache[topic_str]

            # Content Hash
            c_hash = compute_content_hash(q_text, options)

            # Check if question already exists in DB
            if is_pg:
                cur.execute("SELECT id, explanation, exam_tags, version, correct_option, ai_explanation, ai_model FROM questions WHERE content_hash = %s;", (c_hash,))
                existing = cur.fetchone()
                if existing:
                    q_id, ex_exp, ex_tags, ex_ver, ex_ans, ex_ai, ex_model = existing
                    q["db_id"] = q_id
                    q["content_hash"] = c_hash
                    if ex_ai and not q.get("ai_explanation"):
                        q["ai_explanation"] = ex_ai
                        q["ai_model"] = ex_model or "Gemini"

                    # If existing answer was missing and new one has it, or explanation improved:
                    needs_update = False
                    new_ans = ex_ans
                    if (not ex_ans or ex_ans not in ['A', 'B', 'C', 'D', 'E']) and correct_opt in ['A', 'B', 'C', 'D', 'E']:
                        new_ans = correct_opt
                        needs_update = True
                    new_exp = ex_exp
                    if (not ex_exp or len(ex_exp) < 10) and len(explanation) > len(ex_exp):
                        new_exp = explanation
                        needs_update = True

                    if needs_update:
                        cur.execute("""
                        UPDATE questions
                        SET correct_option = %s, explanation = %s, version = version + 1, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s;
                        """, (new_ans, new_exp, q_id))
                        updated_count += 1
                    else:
                        duplicate_count += 1
                    continue

                # Insert new question
                cur.execute("""
                INSERT INTO questions (
                    subject_id, topic_id, source_id, content_hash, question_text,
                    question_text_hi, is_bilingual, options, correct_option, explanation,
                    trap_info, exam_tags, study_notes, version
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
                RETURNING id;
                """, (
                    subject_id, t_id, source_id, c_hash, q_text,
                    q_hi, is_bi, json.dumps(options), correct_opt, explanation,
                    json.dumps(trap_info), json.dumps([]), study_notes
                ))
                new_id = cur.fetchone()[0]
                q["db_id"] = new_id
                q["content_hash"] = c_hash
                inserted_count += 1

            else:
                # SQLite
                cur.execute("SELECT id, explanation, version, correct_option, ai_explanation, ai_model FROM questions WHERE content_hash = ?;", (c_hash,))
                existing = cur.fetchone()
                if existing:
                    q_id = existing[0]
                    ex_exp = existing[1] or ""
                    ex_ans = existing[3] or ""
                    ex_ai = existing[4] if len(existing) > 4 else ""
                    ex_model = existing[5] if len(existing) > 5 else "Gemini"
                    q["db_id"] = q_id
                    q["content_hash"] = c_hash
                    if ex_ai and not q.get("ai_explanation"):
                        q["ai_explanation"] = ex_ai
                        q["ai_model"] = ex_model or "Gemini"

                    needs_update = False
                    new_ans = ex_ans
                    if (not ex_ans or ex_ans not in ['A', 'B', 'C', 'D', 'E']) and correct_opt in ['A', 'B', 'C', 'D', 'E']:
                        new_ans = correct_opt
                        needs_update = True
                    new_exp = ex_exp
                    if (not ex_exp or len(ex_exp) < 10) and len(explanation) > len(ex_exp):
                        new_exp = explanation
                        needs_update = True

                    if needs_update:
                        cur.execute("""
                        UPDATE questions
                        SET correct_option = ?, explanation = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?;
                        """, (new_ans, new_exp, q_id))
                        updated_count += 1
                    else:
                        duplicate_count += 1
                    continue

                cur.execute("""
                INSERT INTO questions (
                    subject_id, topic_id, source_id, content_hash, question_text,
                    question_text_hi, is_bilingual, options, correct_option, explanation,
                    trap_info, exam_tags, study_notes, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
                """, (
                    subject_id, t_id, source_id, c_hash, q_text,
                    q_hi, int(is_bi), json.dumps(options), correct_opt, explanation,
                    json.dumps(trap_info), json.dumps([]), study_notes
                ))
                new_id = cur.lastrowid
                q["db_id"] = new_id
                q["content_hash"] = c_hash
                inserted_count += 1

        conn.commit()
        return {
            "total": len(questions),
            "inserted": inserted_count,
            "updated": updated_count,
            "duplicates": duplicate_count
        }
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def get_subjects_overview() -> List[Dict[str, Any]]:
    """Returns all subjects with total question count and total topics."""
    init_db()
    conn = get_connection()
    is_pg = (_ACTIVE_DB_TYPE == "postgres")
    cur = conn.cursor()
    try:
        query = """
        SELECT 
            s.id, s.name, s.slug, s.icon, s.description,
            COUNT(DISTINCT t.id) as topic_count,
            COUNT(DISTINCT q.id) as question_count
        FROM subjects s
        LEFT JOIN topics t ON s.id = t.subject_id
        LEFT JOIN questions q ON s.id = q.subject_id AND q.is_active = TRUE
        GROUP BY s.id, s.name, s.slug, s.icon, s.description
        ORDER BY question_count DESC, s.name ASC;
        """
        cur.execute(query)
        rows = cur.fetchall()
        result = []
        for r in rows:
            result.append({
                "id": r[0],
                "name": r[1],
                "slug": r[2],
                "icon": r[3] or "📚",
                "description": r[4] or "",
                "topic_count": r[5] or 0,
                "question_count": r[6] or 0
            })
        return result
    finally:
        cur.close()
        conn.close()

def get_topics_for_subject(subject_id: int) -> List[Dict[str, Any]]:
    """Returns topics for a given subject along with question counts."""
    init_db()
    conn = get_connection()
    is_pg = (_ACTIVE_DB_TYPE == "postgres")
    cur = conn.cursor()
    try:
        query = """
        SELECT 
            t.id, t.name, t.slug,
            COUNT(q.id) as question_count
        FROM topics t
        LEFT JOIN questions q ON t.id = q.topic_id AND q.is_active = TRUE
        WHERE t.subject_id = %s
        GROUP BY t.id, t.name, t.slug
        ORDER BY question_count DESC, t.name ASC;
        """ if is_pg else """
        SELECT 
            t.id, t.name, t.slug,
            COUNT(q.id) as question_count
        FROM topics t
        LEFT JOIN questions q ON t.id = q.topic_id AND q.is_active = 1
        WHERE t.subject_id = ?
        GROUP BY t.id, t.name, t.slug
        ORDER BY question_count DESC, t.name ASC;
        """
        cur.execute(query, (subject_id,))
        rows = cur.fetchall()
        return [{"id": r[0], "name": r[1], "slug": r[2], "question_count": r[3] or 0} for r in rows]
    finally:
        cur.close()
        conn.close()

def search_questions(
    query_text: str = "",
    subject_id: Optional[int] = None,
    topic_id: Optional[int] = None,
    trap_only: bool = False,
    limit: int = 50,
    offset: int = 0
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Searches questions by keyword (English/Hindi), subject, topic, and trap filter.
    Returns: (list_of_questions, total_count)
    """
    init_db()
    conn = get_connection()
    is_pg = (_ACTIVE_DB_TYPE == "postgres")
    cur = conn.cursor()
    
    where_clauses = ["q.is_active = TRUE" if is_pg else "q.is_active = 1"]
    params = []

    if query_text.strip():
        term = f"%{query_text.strip()}%"
        where_clauses.append("(q.question_text ILIKE %s OR q.question_text_hi ILIKE %s OR q.explanation ILIKE %s)" if is_pg 
                             else "(q.question_text LIKE ? OR q.question_text_hi LIKE ? OR q.explanation LIKE ?)")
        params.extend([term, term, term])

    if subject_id:
        where_clauses.append("q.subject_id = %s" if is_pg else "q.subject_id = ?")
        params.append(subject_id)

    if topic_id:
        where_clauses.append("q.topic_id = %s" if is_pg else "q.topic_id = ?")
        params.append(topic_id)

    if trap_only:
        where_clauses.append("(q.trap_info->>'is_trap')::boolean = true" if is_pg else "q.trap_info LIKE '%\"is_trap\": true%'")

    where_sql = " AND ".join(where_clauses)
    
    try:
        # Count total
        count_sql = f"SELECT COUNT(*) FROM questions q WHERE {where_sql};"
        cur.execute(count_sql, tuple(params))
        total_count = cur.fetchone()[0]

        # Select page
        select_sql = f"""
        SELECT 
            q.id, q.question_text, q.question_text_hi, q.is_bilingual,
            q.options, q.correct_option, q.explanation, q.trap_info,
            q.version, s.name as subject_name, t.name as topic_name,
            q.ai_explanation, q.ai_model, q.study_notes
        FROM questions q
        LEFT JOIN subjects s ON q.subject_id = s.id
        LEFT JOIN topics t ON q.topic_id = t.id
        WHERE {where_sql}
        ORDER BY q.id ASC
        LIMIT {'%s' if is_pg else '?'} OFFSET {'%s' if is_pg else '?'};
        """
        page_params = list(params) + [limit, offset]
        cur.execute(select_sql, tuple(page_params))
        rows = cur.fetchall()

        questions = []
        for r in rows:
            opts = r[4] if isinstance(r[4], dict) else json.loads(r[4] or "{}")
            trap = r[7] if isinstance(r[7], dict) else json.loads(r[7] or "{}")
            questions.append({
                "db_id": r[0],
                "question_number": len(questions) + offset + 1,
                "uid": f"q_db_{r[0]}",
                "question_text": r[1],
                "hindi_text": r[2] or "",
                "is_bilingual": bool(r[3]),
                "options": opts,
                "correct_answer": r[5] or "",
                "explanation": r[6] or "",
                "trap_info": trap,
                "version": r[8],
                "subject": r[9] or "General",
                "topic": r[10] or "General",
                "ai_explanation": r[11] or "",
                "ai_model": r[12] or "Gemini",
                "study_notes": r[13] or ""
            })

        return questions, total_count
    finally:
        cur.close()
        conn.close()

def record_user_attempt(
    question_id: int,
    selected_option: str,
    is_correct: bool,
    user_id: str = DEFAULT_GUEST_USER_ID,
    session_id: Optional[int] = None,
    time_taken_seconds: int = 0
) -> bool:
    """Records a single question attempt for analytics and future login tracking."""
    init_db()
    conn = get_connection()
    is_pg = (_ACTIVE_DB_TYPE == "postgres")
    cur = conn.cursor()
    try:
        sql = """
        INSERT INTO user_question_attempts (session_id, user_id, question_id, selected_option, is_correct, time_taken_seconds)
        VALUES (%s, %s, %s, %s, %s, %s);
        """ if is_pg else """
        INSERT INTO user_question_attempts (session_id, user_id, question_id, selected_option, is_correct, time_taken_seconds)
        VALUES (?, ?, ?, ?, ?, ?);
        """
        cur.execute(sql, (session_id, user_id, question_id, selected_option, is_correct, time_taken_seconds))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

def get_user_analytics(user_id: str = DEFAULT_GUEST_USER_ID) -> Dict[str, Any]:
    """Computes overall accuracy, total attempts, and weak topics for the user."""
    init_db()
    conn = get_connection()
    is_pg = (_ACTIVE_DB_TYPE == "postgres")
    cur = conn.cursor()
    try:
        # Total attempts & accuracy
        sql_summary = """
        SELECT 
            COUNT(*) as total_attempts,
            COUNT(CASE WHEN is_correct = TRUE THEN 1 END) as correct_count,
            COUNT(CASE WHEN is_correct = FALSE THEN 1 END) as incorrect_count
        FROM user_question_attempts
        WHERE user_id = %s;
        """ if is_pg else """
        SELECT 
            COUNT(*) as total_attempts,
            COUNT(CASE WHEN is_correct = 1 THEN 1 END) as correct_count,
            COUNT(CASE WHEN is_correct = 0 THEN 1 END) as incorrect_count
        FROM user_question_attempts
        WHERE user_id = ?;
        """
        cur.execute(sql_summary, (user_id,))
        row = cur.fetchone()
        tot = row[0] or 0
        corr = row[1] or 0
        inc = row[2] or 0
        acc = (corr / tot * 100) if tot > 0 else 0.0

        # Weak topics
        sql_weak = """
        SELECT 
            t.name as topic_name,
            COUNT(*) as attempts,
            COUNT(CASE WHEN a.is_correct = FALSE THEN 1 END) as mistakes
        FROM user_question_attempts a
        JOIN questions q ON a.question_id = q.id
        JOIN topics t ON q.topic_id = t.id
        WHERE a.user_id = %s
        GROUP BY t.name
        HAVING COUNT(CASE WHEN a.is_correct = FALSE THEN 1 END) > 0
        ORDER BY mistakes DESC
        LIMIT 5;
        """ if is_pg else """
        SELECT 
            t.name as topic_name,
            COUNT(*) as attempts,
            COUNT(CASE WHEN a.is_correct = 0 THEN 1 END) as mistakes
        FROM user_question_attempts a
        JOIN questions q ON a.question_id = q.id
        JOIN topics t ON q.topic_id = t.id
        WHERE a.user_id = ?
        GROUP BY t.name
        HAVING COUNT(CASE WHEN a.is_correct = 0 THEN 1 END) > 0
        ORDER BY mistakes DESC
        LIMIT 5;
        """
        cur.execute(sql_weak, (user_id,))
        weak_rows = cur.fetchall()
        weak_topics = [{"topic": r[0], "attempts": r[1], "mistakes": r[2]} for r in weak_rows]

        return {
            "total_attempts": tot,
            "correct_count": corr,
            "incorrect_count": inc,
            "accuracy": round(acc, 1),
            "weak_topics": weak_topics
        }
    finally:
        cur.close()
        conn.close()

def save_question_ai_explanation(
    question_text: str,
    options: Dict[str, str],
    ai_explanation: str,
    model_name: str = "gemini-3.5-flash-lite",
    correct_option: Optional[str] = None,
    db_id: Optional[int] = None,
    subject_name: str = "General"
) -> bool:
    """
    Saves or updates Gemini AI explanation for a question in PostgreSQL/SQLite.
    Finds question by db_id or content_hash. If not found in DB, auto-creates it.
    """
    if not question_text or not ai_explanation:
        return False

    init_db()
    conn = get_connection()
    is_pg = (_ACTIVE_DB_TYPE == "postgres")
    cur = conn.cursor()
    c_hash = compute_content_hash(question_text, options)

    try:
        q_id = db_id
        if not q_id:
            if is_pg:
                cur.execute("SELECT id FROM questions WHERE content_hash = %s LIMIT 1;", (c_hash,))
            else:
                cur.execute("SELECT id FROM questions WHERE content_hash = ? LIMIT 1;", (c_hash,))
            row = cur.fetchone()
            if row:
                q_id = row[0]

        if q_id:
            if is_pg:
                cur.execute("""
                UPDATE questions
                SET ai_explanation = %s,
                    ai_model = %s,
                    correct_option = COALESCE(NULLIF(%s, ''), correct_option),
                    version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
                """, (ai_explanation, model_name, correct_option or "", q_id))
            else:
                cur.execute("""
                UPDATE questions
                SET ai_explanation = ?,
                    ai_model = ?,
                    correct_option = CASE WHEN ? != '' THEN ? ELSE correct_option END,
                    version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
                """, (ai_explanation, model_name, correct_option or "", correct_option or "", q_id))
        else:
            subject_id = get_or_create_subject(subject_name, conn=conn)
            topic_id = get_or_create_topic(subject_id, "General", conn=conn)
            if is_pg:
                cur.execute("""
                INSERT INTO questions (
                    subject_id, topic_id, content_hash, question_text, options,
                    correct_option, ai_explanation, ai_model, version
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1)
                RETURNING id;
                """, (
                    subject_id, topic_id, c_hash, question_text, json.dumps(options),
                    correct_option or "", ai_explanation, model_name
                ))
            else:
                cur.execute("""
                INSERT INTO questions (
                    subject_id, topic_id, content_hash, question_text, options,
                    correct_option, ai_explanation, ai_model, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1);
                """, (
                    subject_id, topic_id, c_hash, question_text, json.dumps(options),
                    correct_option or "", ai_explanation, model_name
                ))

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

def update_question_correct_option(
    correct_option: str,
    db_id: Optional[int] = None,
    content_hash: Optional[str] = None
) -> bool:
    """
    Updates the verified correct option (A, B, C, D, E) for a question in PostgreSQL/SQLite.
    """
    if not correct_option or correct_option.upper() not in ['A', 'B', 'C', 'D', 'E']:
        return False
    correct_option = correct_option.upper()
    init_db()
    conn = get_connection()
    is_pg = (_ACTIVE_DB_TYPE == "postgres")
    cur = conn.cursor()
    try:
        if db_id:
            if is_pg:
                cur.execute("UPDATE questions SET correct_option = %s, version = version + 1, updated_at = CURRENT_TIMESTAMP WHERE id = %s;", (correct_option, db_id))
            else:
                cur.execute("UPDATE questions SET correct_option = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?;", (correct_option, db_id))
        elif content_hash:
            if is_pg:
                cur.execute("UPDATE questions SET correct_option = %s, version = version + 1, updated_at = CURRENT_TIMESTAMP WHERE content_hash = %s;", (correct_option, content_hash))
            else:
                cur.execute("UPDATE questions SET correct_option = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP WHERE content_hash = ?;", (correct_option, content_hash))
        else:
            return False
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

def get_question_ai_explanation(
    question_text: str,
    options: Optional[Dict[str, str]] = None,
    db_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """
    Retrieves saved AI explanation for a question if present in PostgreSQL/SQLite.
    Returns: {"ai_explanation": "...", "model": "...", "updated_at": "..."} or None
    """
    init_db()
    conn = get_connection()
    is_pg = (_ACTIVE_DB_TYPE == "postgres")
    cur = conn.cursor()

    try:
        if db_id:
            if is_pg:
                cur.execute("SELECT ai_explanation, ai_model, updated_at FROM questions WHERE id = %s;", (db_id,))
            else:
                cur.execute("SELECT ai_explanation, ai_model, updated_at FROM questions WHERE id = ?;", (db_id,))
        else:
            c_hash = compute_content_hash(question_text, options)
            if is_pg:
                cur.execute("SELECT ai_explanation, ai_model, updated_at FROM questions WHERE content_hash = %s;", (c_hash,))
            else:
                cur.execute("SELECT ai_explanation, ai_model, updated_at FROM questions WHERE content_hash = ?;", (c_hash,))

        row = cur.fetchone()
        if row and row[0] and str(row[0]).strip():
            return {
                "ai_explanation": str(row[0]).strip(),
                "model": row[1] or "Gemini",
                "updated_at": str(row[2]) if row[2] else ""
            }
        return None
    except Exception:
        return None
    finally:
        cur.close()
        conn.close()
