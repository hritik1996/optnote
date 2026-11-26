import re
import os
try:
    import pymupdf
except ImportError:
    import fitz as pymupdf
from typing import List, Dict, Any, Optional, Tuple
from trap_analyzer import analyze_exam_trap

def extract_text_from_pdf(pdf_source) -> str:
    """
    Extract text accurately from a PDF file using PyMuPDF (fitz).
    Handles multi-column layouts by sorting text blocks column-by-column
    so options (A), (B), (C), (D) and questions are never scrambled or interwoven.
    Guarantees no blocks or answers are ever dropped.
    """
    full_text = []
    if isinstance(pdf_source, (bytes, bytearray)):
        doc = pymupdf.open(stream=pdf_source, filetype="pdf")
    elif hasattr(pdf_source, "read"):
        doc = pymupdf.open(stream=pdf_source.read(), filetype="pdf")
    else:
        doc = pymupdf.open(pdf_source)

    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("blocks")
        if not blocks:
            text = page.get_text("text", sort=True)
            if text.strip():
                full_text.append(text)
            continue

        page_width = page.rect.width
        page_height = page.rect.height
        mid_x = page_width / 2.0
        
        # Valid text blocks: (x0, y0, x1, y1, text, block_no, block_type)
        text_blocks = [b for b in blocks if len(b) >= 5 and b[4].strip()]
        if not text_blocks:
            continue

        # Check if page has two distinct columns
        left_has_content = any((b[0] + b[2]) / 2.0 < mid_x for b in text_blocks)
        right_has_content = any((b[0] + b[2]) / 2.0 >= mid_x and b[0] >= mid_x * 0.35 for b in text_blocks)

        if left_has_content and right_has_content:
            top_headers = []
            left_blocks = []
            right_blocks = []
            bottom_footers = []

            for b in text_blocks:
                x0, y0, x1, y1, b_text = b[0], b[1], b[2], b[3], b[4].strip()
                center_x = (x0 + x1) / 2.0
                width = x1 - x0

                if width > page_width * 0.65 and y0 < page_height * 0.12:
                    top_headers.append(b)
                elif width > page_width * 0.65 and y1 > page_height * 0.90:
                    bottom_footers.append(b)
                elif center_x < mid_x:
                    left_blocks.append(b)
                else:
                    right_blocks.append(b)

            top_headers.sort(key=lambda b: (b[1], b[0]))
            left_blocks.sort(key=lambda b: (b[1], b[0]))
            right_blocks.sort(key=lambda b: (b[1], b[0]))
            bottom_footers.sort(key=lambda b: (b[1], b[0]))

            page_parts = []
            if top_headers:
                page_parts.append("\n".join(b[4].strip() for b in top_headers))
            if left_blocks:
                page_parts.append("\n".join(b[4].strip() for b in left_blocks))
            if right_blocks:
                page_parts.append("\n".join(b[4].strip() for b in right_blocks))
            if bottom_footers:
                page_parts.append("\n".join(b[4].strip() for b in bottom_footers))

            full_text.append("\n".join(page_parts))
        else:
            sorted_blocks = sorted(text_blocks, key=lambda b: (b[1], b[0]))
            full_text.append("\n".join(b[4].strip() for b in sorted_blocks))

    doc.close()
    return "\n".join(full_text)

def extract_answer_key(text: str) -> Dict[int, str]:
    """
    Extracts question-to-answer mappings from an Answer Key section
    commonly found in competitive exam PDFs (at the end of documents, chapters, or pages).
    Supports formats like:
    - 1. (4)  | 2. (4)  | 3. (4) ... (Bank PO / IBPS format)
    - 1. (B)  2. (C)  3. (B) ...
    - 1. B    2. C    3. B ...
    - 1-B, 2-C, 3-B ...
    - 1-(B), 2-(C) ...
    - Table format: Q.No Ans Q.No Ans
    """
    if not text:
        return {}
        
    answer_map: Dict[int, str] = {}
    mapping = {'1': 'A', '2': 'B', '3': 'C', '4': 'D', '5': 'E'}
    
    # 1. Search for explicit Answer Key / Solutions sections
    key_sections = re.finditer(
        r'(?:ANSWER\s*KEY|ANSWERS?|SOLUTIONS?|KEY\s*[:\-–]|उत्तर\s*(?:माला|कुंजी))\b[:\s\-–]*(.*?)(?=(?:\n[ \t]*(?:Topic|Chapter|Section|Page\s*\d+|QUESTION\s*BANK)|\Z))',
        text,
        re.IGNORECASE | re.DOTALL
    )
    
    for sec in key_sections:
        sec_text = sec.group(1)
        matches = re.finditer(
            r'\b(\d{1,4})(?:[\.\)\:\-]+[ \t]*|[ \t]+)\(?([A-Ea-e1-5])\)?(?:\b|\s*[,;\|\t\n]|\s+|$|\Z)',
            sec_text
        )
        for m in matches:
            try:
                q_num = int(m.group(1))
                val = m.group(2).upper()
                ans = mapping.get(val, val)
                if ans in ['A', 'B', 'C', 'D', 'E'] and q_num not in answer_map:
                    answer_map[q_num] = ans
            except ValueError:
                continue

    # 2. Also search for trailing grid/table matches if no explicit section header found
    if not answer_map:
        grid_matches = re.finditer(
            r'\b(\d{1,4})(?:[\.\)\:\-]+[ \t]*|[ \t]+)\(?([A-Ea-e1-5])\)?(?:\s+|,|\||\t|\n|$|\Z)',
            text
        )
        candidates = {}
        for m in grid_matches:
            try:
                q_num = int(m.group(1))
                val = m.group(2).upper()
                ans = mapping.get(val, val)
                if 1 <= q_num <= 500 and ans in ['A', 'B', 'C', 'D', 'E']:
                    candidates[q_num] = ans
            except ValueError:
                continue
        if len(candidates) >= 3:
            answer_map = candidates

    return answer_map

def clean_option_text(text: str) -> str:
    """
    Bulletproof multi-pass cleaner that strips exam shift metadata
    (e.g., 'SHIFT 08 05 OCT 2026 EXAM SHIFT', 'SHIFT 04 01 OCT 2026 EXAM SHIFT 2'),
    dates, coaching branding, URLs, telegram links, and trailing ANSWER markers.
    """
    if not text:
        return ""
    
    # 1. Remove trailing Answer / Solution / Key markers and answer tables
    text = re.sub(r'\b(?:ANSWERS?|ANS|SOLUTIONS?|EXPLANATIONS?|KEYS?|उत्तर(?:माला|कुंजी)?)\b.*$', '', text, flags=re.IGNORECASE | re.DOTALL)
    
    # 2. Multi-Pass Bulletproof Shift & Date Cleaner
    # Pass 2a: Full shift blocks with dates, exam words, brackets, dashes
    text = re.sub(
        r'[\(\[\{]?\s*(?:EXAM\s+)?SHIFT\b.*?(?:EXAM\s+SHIFT|\bSHIFT\b|\b\d{4}\b|\bOCT\b|\bNOV\b|\bSEP\b|\bAUG\b|\bJUL\b|\bJUN\b|\bMAY\b|\bAPR\b|\bMAR\b|\bFEB\b|\bJAN\b)[^\n\(\)\]]*[\)\]\}]?',
        '',
        text,
        flags=re.IGNORECASE
    )
    # Pass 2b: Any remaining SHIFT with numbers, words, or shift labels
    text = re.sub(
        r'\b(?:EXAM\s+)?SHIFT[\s\-\:\.\d\w]*',
        '',
        text,
        flags=re.IGNORECASE
    )
    # Pass 2c: Standalone date formats like '05 OCT 2026', '06-10-2026', '03/12/2022'
    text = re.sub(
        r'\b\d{1,2}[\s\-\.\/]+(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[a-z]*[\s\-\.\/]+\d{2,4}\b',
        '',
        text,
        flags=re.IGNORECASE
    )
    text = re.sub(r'\b\d{1,2}[-/.](?:\d{1,2}|[A-Za-z]{3})[-/.]\d{2,4}\b', '', text)
    
    # Pass 2d: Standalone EXAM, TIER, or Paper tags
    text = re.sub(r'\b(?:EXAM|TIER[\s\-\:]*[I|V|X\d]+)\b', '', text, flags=re.IGNORECASE)

    # 3. Remove URLs, website names, and domains (e.g. uclive.org, testbook.com)
    text = re.sub(r'https?://\S+|www\.\S+|\b[a-zA-Z0-9.\-_]+\.(?:org|com|in|net|edu|co)\b', '', text, flags=re.IGNORECASE)
    
    # 4. Remove Telegram / Social media promotions
    text = re.sub(r'\b(?:Join\s+)?(?:Telegram|YouTube|Facebook|Instagram)(?:\s*[:\-–]?\s*@?[a-zA-Z0-9_\-]+)?\b', '', text, flags=re.IGNORECASE)
    
    # 5. Remove Phone / Contact numbers
    text = re.sub(r'\b(?:Contact|Mob(?:ile)?|Ph(?:one)?|WhatsApp)?\s*[:\-–]?\s*(?:\+?91[\-\s]?)?[6-9]\d{9}\b', '', text, flags=re.IGNORECASE)
    
    # 6. Remove Page numbering (e.g. "Contents Page 3 / 93" or "Page 3 of 93")
    text = re.sub(r'\b(?:Contents\s*)?Page\s*\d+\s*(?:/\s*\d+|\bof\s*\d+)?\b', '', text, flags=re.IGNORECASE)
    
    # 7. Remove common coaching institute branding, author names & slogans
    text = re.sub(r'\b(?:English\s+With\s+Rani\s+(?:Ma\'?am|Mam|Singh)|Believe\s+in\s+Quality|UC\s*LIVE|Careerwill|Adda247|Testbook|Pinnacle|Paramount|KD\s+Campus|Neetu\s+Singh|Unacademy|Khan\s+Sir)\b', '', text, flags=re.IGNORECASE)
    
    # 8. Remove Exam header tags (e.g. SSC CGL 2026 | TIER-I)
    text = re.sub(r'[\(\[\{]?\s*\bSSC\s+(?:CGL|CHSL|CPO|MTS|GD)\s*(?:\d{4})?\s*(?:\|?\s*TIER-?[I|V|X\d]+)?[^\)\n]*[\)\]\}]?', '', text, flags=re.IGNORECASE)
    
    # 9. Remove chapter/section header words only when at the start or end of an option (e.g. 'Prejudise SPELLING')
    text = re.sub(r'^\s*(?:SPELLING(?:\s*&\s*MISSPELT\s*WORDS?)?|VOCABULARY|IDIOMS?(?:\s*&\s*PHRASES)?|ANTONYMS?|SYNONYMS?|GRAMMAR|MISSPELT(?:\s*WORDS?)?)\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(?:SPELLING(?:\s*&\s*MISSPELT\s*WORDS?)?|VOCABULARY|IDIOMS?(?:\s*&\s*PHRASES)?|ANTONYMS?|SYNONYMS?|GRAMMAR|MISSPELT(?:\s*WORDS?)?)\s*$', '', text, flags=re.IGNORECASE)
    
    # 10. Clean empty brackets or dangling punctuation
    text = re.sub(r'[\(\[\{]\s*[\)\]\}]', '', text)
    # 11. Clean checkmark emojis and bullets
    text = re.sub(r'[✅✔✓]+', '', text)
    text = text.strip("•*-– \t\n")
    text = re.sub(r'[\s\|\-_]+', ' ', text).strip()
    return text

def clean_question_text(text: str) -> str:
    """
    Cleans question text by stripping leading pipes, shift tags, watermarks,
    and website links, while strictly preserving essential words like 'spelling',
    'misspelt', and legitimate dates/numbers in GK / Financial questions.
    """
    if not text:
        return ""
    # Strip exam shift metadata
    text = re.sub(r'[\|\s\t]*(?:EXAM\s+)?SHIFT[\s\-\:\.\d\w]*', '', text, flags=re.IGNORECASE)
    # Strip watermarks and coaching branding
    text = re.sub(r'\b(?:English\s+With\s+Rani\s+(?:Ma\'?am|Mam|Singh)|Believe\s+in\s+Quality|UC\s*LIVE|Careerwill|Adda247|Testbook|Pinnacle|Paramount|KD\s+Campus|Neetu\s+Singh|Unacademy|Khan\s+Sir)\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'https?://\S+|www\.\S+|\b[a-zA-Z0-9.\-_]+\.(?:org|com|in|net|edu|co)\b', '', text, flags=re.IGNORECASE)
    # Strip standalone topic line at the very beginning (e.g. 'SPELLING\n')
    text = re.sub(r'^\s*(?:SPELLING(?:\s*&\s*MISSPELT\s*WORDS?)?|IDIOMS\s*&\s*PHRASES|VOCABULARY|ANTONYMS|SYNONYMS)\s*\n+', '', text, flags=re.IGNORECASE)
    # Clean leading pipe, question dashes, extra spaces
    text = re.sub(r'^[\|\s\t\-•]+', '', text)
    return text.strip()

def clean_and_normalize_text(text: str) -> str:
    """
    Normalizes special unicode characters, separates stuck options,
    joins multiline answers, and removes shift tags and header/footer noise lines.
    """
    unicode_replacements = {
        'Ⓐ': '(A)', 'Ⓑ': '(B)', 'Ⓒ': '(C)', 'Ⓓ': '(D)', 'Ⓔ': '(E)',
        'ⓐ': '(A)', 'ⓑ': '(B)', 'ⓒ': '(C)', 'ⓓ': '(D)', 'ⓔ': '(E)',
        '①': '(1)', '②': '(2)', '③': '(3)', '④': '(4)', '⑤': '(5)',
        '‘': "'", '’': "'", '“': '"', '”': '"',
        '–': '-', '—': '-', '\xa0': ' '
    }
    for k, v in unicode_replacements.items():
        text = text.replace(k, v)

    # 1. Separate ANSWER or KEY if stuck to an option line (e.g. "(D) Loggorrhea ANSWER (A) Logorrhoea")
    text = re.sub(
        r'([^\n\s])[ \t]*(\b(?:ANSWER|ANS(?:WER)?|KEY|CORRECT|उत्तर)[ \t]*[:\-–\.]*[ \t]*\(?[A-Ea-e1-5]\)?)',
        r'\1\n\2',
        text,
        flags=re.IGNORECASE
    )

    # 2. Join ANSWER lines split across newlines (e.g. "ANSWER\n(A) Logorrhoea" -> "ANSWER (A) Logorrhoea")
    text = re.sub(
        r'(?m)^([\|\s\t\-•]*(?:ANSWER|ANS(?:WER)?|KEY|CORRECT|उत्तर)[ \t]*[:\-–\.]*)\n[ \t]*(\(?[A-Ea-e1-5]\)?[\.\)]?[ \t]+[A-Za-z0-9]+[^\n]*)$',
        r'\1 \2',
        text,
        flags=re.IGNORECASE
    )

    # 3. Separate options that are stuck to text (e.g., "SPELLING(A) Prejudise" -> "SPELLING\n(A) Prejudise", or "(1) Greek(2) English")
    # BUT strictly preserve "ANSWER (A)" or "ANSWER (B)"
    lines_split = []
    for l in text.splitlines():
        if re.match(r'^\s*[\|\s\t\-•]*(?:ANSWER|ANS|KEY|CORRECT|उत्तर)\b', l.strip(), re.IGNORECASE):
            lines_split.append(l)
        else:
            lines_split.append(re.sub(r'([^\n\s])\s*(\([A-Ea-e1-5]\)|\[[A-Ea-e1-5]\])', r'\1\n\2', l))
    text = "\n".join(lines_split)
    
    # 4. Clean out standalone noise lines and shift tags
    filtered_lines = []
    noise_line_pattern = re.compile(
        r'^(?:Join\s+Telegram|uclive\.org|Contents\s*Page\s*\d+|English With Rani Ma\'am|Believe in Quality|\+?91[\-\s]?[6-9]\d{9}|[\|\s\t]*(?:EXAM\s+)?SHIFT\b)\b',
        re.IGNORECASE
    )
    for line in text.splitlines():
        cleaned_line = line.strip()
        if not noise_line_pattern.search(cleaned_line):
            # Also purge any shift block directly
            cleaned_line = re.sub(r'[\(\[\{]?\s*(?:EXAM\s+)?SHIFT\b.*?(?:EXAM\s+SHIFT|\bSHIFT\b|\b\d{4}\b)[^\n\(\)\]]*[\)\]\}]?', '', cleaned_line, flags=re.IGNORECASE)
            filtered_lines.append(cleaned_line)

    return "\n".join(filtered_lines)

def split_multi_topic_document(raw_text: str) -> Optional[List[Dict[str, Any]]]:
    """
    Detects and splits multi-topic / multi-chapter documents where each topic/chapter has its own
    Question Bank and Answer Key:
    Topic 1 -> Question Bank -> Questions -> Answer Key
    Topic 2 -> Question Bank -> Questions -> Answer Key
    Returns a list of section dicts: [{'topic': ..., 'questions_text': ..., 'answers_text': ...}]
    or None if document is single-topic.
    """
    if not raw_text or not raw_text.strip():
        return None

    ans_key_pattern = re.compile(
        r'(?m)^[ \t]*(?:ANSWER\s*KEY|ANSWERS|SOLUTIONS?|HINTS\s*&\s*SOLUTIONS?|ANSWERS?\s*&\s*EXPLANATIONS?|उत्तर\s*(?:माला|कुंजी))\b(?![ \t]*[:\-–]*[ \t]*(?:\([A-Ea-e1-5]\)|[A-Ea-e1-5](?:\b|[ \t]*[\.\)])))[^\n]*$',
        re.IGNORECASE
    )
    ans_matches = list(ans_key_pattern.finditer(raw_text))
    if len(ans_matches) <= 1:
        return None

    topic_pattern = re.compile(
        r'(?m)^[ \t]*(?:(?:Topic|Chapter|Section|Part|Subject)\s*[:\-–]\s*([^\n]+)|(?:CHAPTER\s*\d+[^\n]*|SECTION\s*[A-Z][^\n]*|PART\s*[A-Z][^\n]*|QUESTION\s*BANK[^\n]*))',
        re.IGNORECASE
    )

    sections = []
    prev_sec_start = 0

    for i, ans_m in enumerate(ans_matches):
        ans_start = ans_m.start()

        # Determine where this section's answer key ends and next section begins
        if i + 1 < len(ans_matches):
            next_ans_start = ans_matches[i + 1].start()
            sub_text = raw_text[ans_m.end():next_ans_start]
            t_match = topic_pattern.search(sub_text)
            if t_match:
                sec_end = ans_m.end() + t_match.start()
            else:
                q1_match = re.search(r'(?m)^[ \t]*(?:Q(?:uestion)?\s*[\.\:\-]*|\b)1[\.\)\:\-]\s+[A-Za-z]', sub_text)
                if q1_match:
                    sec_end = ans_m.end() + q1_match.start()
                else:
                    sec_end = next_ans_start
        else:
            sec_end = len(raw_text)

        q_part = raw_text[prev_sec_start:ans_start].strip()
        ans_part = raw_text[ans_start:sec_end].strip()

        # Extract topic title from q_part
        top_m = topic_pattern.search(q_part)
        if top_m:
            detected = (top_m.group(1) or top_m.group(0)).strip()
            if detected.upper() == "QUESTION BANK":
                topic_title = f"Topic {i + 1}"
            else:
                topic_title = detected.title()
        else:
            topic_title = f"Topic {i + 1}"

        sections.append({
            "topic": topic_title,
            "questions_text": q_part,
            "answers_text": ans_part
        })
        prev_sec_start = sec_end

    return sections

def parse_single_section_mcqs(
    raw_text: str,
    default_topic: str = "General English / Aptitude",
    answer_map: Optional[Dict[int, str]] = None,
    start_counter: int = 1
) -> List[Dict[str, Any]]:
    """
    Parses a contiguous section of MCQ text using an optional dedicated Answer Key.
    """
    if not raw_text or not raw_text.strip():
        return []

    text = clean_and_normalize_text(raw_text)
    lines = text.splitlines()

    questions = []
    current_topic = default_topic
    
    topic_header_regex = re.compile(
        r'^(?:(?:Topic|Section|Subject|Chapter|Part)\s*[:\-–]\s*(.+)|(?:QUESTION\s*BANK\b[^\n]*)|(SPELLING(?:\s*&\s*MISSPELT\s*WORDS?)?|IDIOMS\s*&\s*PHRASES|ONE\s*WORD\s*SUBSTITUTION|SYNONYMS|ANTONYMS|GENERAL\s*SCIENCE|STATIC\s*GK))$',
        re.IGNORECASE
    )

    q_start_regex = re.compile(
        r'^[\|\s\t]*(?:Q(?:uestion)?[\s\.\:\-]*|\b)?(\d+)[\.\)\:\-]\s*(.*)$',
        re.IGNORECASE
    )
    q_alt_regex = re.compile(r'^Q(?:uestion)?\s*[:\-]\s*(.*)$', re.IGNORECASE)

    opt_a_pattern = re.compile(r'^(?:\([Aa1]\)|\[[Aa1]\]|[Aa][\.\)]|1[\)])\s+')

    raw_blocks = []
    current_block_lines = []
    last_detected_topic = current_topic
    has_seen_opt_a = False

    ans_key_header_regex = re.compile(
        r'^[ \t]*(?:ANSWER\s*KEY|ANSWERS|SOLUTIONS?|HINTS\s*&\s*SOLUTIONS?|ANSWERS?\s*&\s*EXPLANATIONS?|उत्तर\s*(?:माला|कुंजी))\b(?![ \t]*[:\-–]*[ \t]*(?:\([A-Ea-e1-5]\)|[A-Ea-e1-5](?:\b|[ \t]*[\.\)])))[^\n]*$',
        re.IGNORECASE
    )

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_block_lines:
                current_block_lines.append("")
            continue

        if ans_key_header_regex.match(stripped):
            if current_block_lines:
                raw_blocks.append((last_detected_topic, "\n".join(current_block_lines)))
                current_block_lines = []
            break

        topic_match = topic_header_regex.match(stripped)
        if topic_match:
            detected = topic_match.group(1) or topic_match.group(2)
            if detected:
                last_detected_topic = detected.strip().title()
            continue

        is_answer_line = bool(re.match(r'^\s*[\|\s\t\-•]*(?:ANSWER|ANS(?:WER)?|KEY|CORRECT|उत्तर)\b', stripped, re.IGNORECASE))
        is_option_line = bool(re.match(r'^(?:\([A-Ea-e1-5]\)|\[[A-Ea-e1-5]\]|[A-Ea-e][\.\)]|[1-5][\)])\s+', stripped)) and not is_answer_line
        q_match = q_start_regex.match(stripped) and not is_option_line and not is_answer_line
        alt_match = q_alt_regex.match(stripped) and not is_option_line and not is_answer_line
        is_opt_a = bool(opt_a_pattern.match(stripped)) and not is_answer_line

        if (q_match or alt_match or (is_opt_a and has_seen_opt_a)) and current_block_lines:
            raw_blocks.append((last_detected_topic, "\n".join(current_block_lines)))
            current_block_lines = []
            has_seen_opt_a = False

        if is_opt_a:
            has_seen_opt_a = True

        current_block_lines.append(stripped)

    if current_block_lines:
        raw_blocks.append((last_detected_topic, "\n".join(current_block_lines)))

    q_counter = start_counter
    for topic, block in raw_blocks:
        parsed_q = parse_single_mcq_block(block, default_num=q_counter, topic=topic, answer_map=answer_map)
        if parsed_q:
            questions.append(parsed_q)
            q_counter += 1

    if len(questions) <= 1 and len(text) > 200:
        fallback_questions = fallback_regex_parser(text, current_topic, answer_map=answer_map)
        if len(fallback_questions) > len(questions):
            questions = fallback_questions

    return questions

def parse_mcq_text(raw_text: str) -> List[Dict[str, Any]]:
    """
    Robust regex/state-machine parser that converts raw extracted MCQ text
    into structured JSON-compatible dictionaries.
    Intelligently handles:
    1. Multi-topic / multi-chapter documents with independent Question Banks and separate Answer Keys.
    2. Numbered options (1), (2), (3), (4), (5) for Banking and State exams.
    3. Global Answer Key tables with grid formatting (e.g. 1. (4) | 2. (4) ...).
    4. Re-sequences and assigns globally unique UIDs to prevent Streamlit widget collisions.
    """
    if not raw_text or not raw_text.strip():
        return []

    # Check if input text is specifically CSV content (e.g. quote-enclosed columns, trailing comma rows, or explicit CSV header)
    if 'question with answer' in raw_text.lower() or '",,' in raw_text or ',,,,' in raw_text or '","' in raw_text:
        try:
            csv_qs = parse_csv_file(raw_text)
            if len(csv_qs) >= 2:
                return csv_qs
        except Exception:
            pass

    # Check for multi-topic document with multiple question banks and answer keys
    multi_sections = split_multi_topic_document(raw_text)
    if multi_sections and len(multi_sections) > 1:
        all_questions = []
        global_counter = 1
        for sec in multi_sections:
            sec_topic = sec["topic"]
            sec_q_text = sec["questions_text"]
            sec_ans_text = sec["answers_text"]

            # Dedicated answer map for this specific section
            sec_ans_map = extract_answer_key(sec_ans_text)

            # Parse questions for this specific section
            sec_qs = parse_single_section_mcqs(
                raw_text=sec_q_text,
                default_topic=sec_topic,
                answer_map=sec_ans_map,
                start_counter=global_counter
            )
            for q in sec_qs:
                all_questions.append(q)
                global_counter += 1

        # Deduplicate question numbers and assign globally unique uid
        seen_nums = set()
        has_duplicates = False
        for q in all_questions:
            num = q.get("question_number")
            if num in seen_nums:
                has_duplicates = True
                break
            seen_nums.add(num)

        for i, q in enumerate(all_questions):
            q["uid"] = f"q_{i + 1}"
            if has_duplicates:
                q["original_number"] = q.get("question_number")
                q["question_number"] = i + 1

        return all_questions

    # Standard single-topic / unified document parsing
    answer_map = extract_answer_key(raw_text)
    questions = parse_single_section_mcqs(
        raw_text=raw_text,
        default_topic="General English / Aptitude",
        answer_map=answer_map,
        start_counter=1
    )

    # Deduplicate question numbers and assign globally unique uid
    seen_nums = set()
    has_duplicates = False
    for q in questions:
        num = q.get("question_number")
        if num in seen_nums:
            has_duplicates = True
            break
        seen_nums.add(num)

    for i, q in enumerate(questions):
        q["uid"] = f"q_{i + 1}"
        if has_duplicates:
            q["original_number"] = q.get("question_number")
            q["question_number"] = i + 1

    return questions

def clean_question_preamble_and_bilingual(text: str) -> Tuple[str, str, bool]:
    """
    Cleans conversational or copy-paste preambles (e.g. '📋 कॉपी-पेस्ट के लिए टेक्स्ट')
    and extracts bilingual English and Hindi components if present.
    Returns: (english_text, hindi_text, is_bilingual)
    """
    lines = []
    for l in text.splitlines():
        ls = l.strip()
        if re.search(r'^[📋\s]*(?:कॉपी[-–\s]*पेस्ट\s*के\s*लिए\s*टेक्स्ट|Copy[-–\s]*paste)\b', ls, re.IGNORECASE):
            continue
        if re.match(r'^प्रश्न\s*\(Question\)\s*[:\-–]*$', ls, re.IGNORECASE):
            continue
        lines.append(l)
    text = "\n".join(lines).strip()

    # Conversational intro: यह प्रश्न आपसे पूछ रहा है कि "(...)"
    conv_m = re.match(r'^यह\s*प्रश्न\s*आपसे\s*पूछ\s*रहा\s*है\s*कि\s*["“](.*?)["”]\s*(?:Question\s*[:\-–]*)?(.*)$', text, re.DOTALL | re.IGNORECASE)
    if conv_m:
        hi_part = conv_m.group(1).strip()
        en_part = conv_m.group(2).strip()
        en_part = re.sub(r'^Question\s*[:\-–]*\s*', '', en_part, flags=re.IGNORECASE).strip()
        if en_part and hi_part:
            return en_part, hi_part, True

    # Explicit tags: English: ... Hindi / हिन्दी: ...
    en_m = re.search(r'(?:^|\n)[ \t]*(?:[•\*\-–]\s*)?English\s*[:\-–]\s*(.*?)(?=(?:^|\n)[ \t]*(?:[•\*\-–]\s*)?(?:Hindi|हिन्दी)\s*[:\-–]|\Z)', text, re.IGNORECASE | re.DOTALL)
    hi_m = re.search(r'(?:^|\n)[ \t]*(?:[•\*\-–]\s*)?(?:Hindi|हिन्दी)\s*[:\-–]\s*(.*?)(?=(?:^|\n)[ \t]*(?:[•\*\-–]\s*)?English\s*[:\-–]|\Z)', text, re.IGNORECASE | re.DOTALL)
    if en_m and hi_m:
        en_t = re.sub(r'^[\|\s\t\-•]+', '', en_m.group(1).strip()).strip()
        hi_t = re.sub(r'^[\|\s\t\-•]+', '', hi_m.group(1).strip()).strip()
        return en_t, hi_t, True

    # Two paragraphs: one predominantly English Latin, one Devanagari Hindi
    parts = [p.strip() for p in text.splitlines() if p.strip()]
    parts = [p for p in parts if not re.match(r'^Question\s*[:\-–]*$', p, re.IGNORECASE)]
    if len(parts) == 2:
        p0, p1 = parts[0], parts[1]
        has_deva_0 = bool(re.search(r'[\u0900-\u097F]', p0))
        has_deva_1 = bool(re.search(r'[\u0900-\u097F]', p1))
        has_lat_0 = bool(re.search(r'[A-Za-z]{3,}', p0))
        has_lat_1 = bool(re.search(r'[A-Za-z]{3,}', p1))
        if has_lat_0 and not has_deva_0 and has_deva_1:
            return p0, p1, True
        elif has_deva_0 and not has_lat_0 and has_lat_1:
            return p1, p0, True

    clean_single = re.sub(r'^Question\s*[:\-–]*\s*', '', text, flags=re.IGNORECASE).strip()
    return clean_single, "", False

def parse_single_mcq_block(block_text: str, default_num: int, topic: str, answer_map: Optional[Dict[int, str]] = None) -> Optional[Dict[str, Any]]:
    """
    Parses a single question text block into question_text, options, correct_answer, and explanation.
    Never blindly defaults to 'A'. Checks inline answer and global answer_map.
    Supports bilingual English & Hindi formatting, bullets, emojis (✅), and clean option parsing.
    """
    block_text = block_text.strip()
    if not block_text:
        return None

    # Check for Answer line (supports Hindi 'सही उत्तर (Correct Answer):', 'Correct Answer:', 'ANSWER', 'Ans: C', etc.)
    ans_regex = re.compile(
        r'(?:सही\s*उत्तर(?:\s*\([^\)]*\))?|\bCorrect\s*Answer\b|\bANSWER\b|\bANS(?:WER)?\b|\bCORRECT(?:\s*OPTION)?\b|\bKEY\b|उत्तर(?:\s*माला|\s*कुंजी)?)\s*[:\-–\.]*\s*(?:[•\*\-–]\s*)?(?:Option\s*)?(?:\(([A-Ea-e1-5])\)|\[([A-Ea-e1-5])\]|([A-Ea-e1-5])(?=[\.\)\:\-\s]|$))',
        re.IGNORECASE
    )
    ans_match = ans_regex.search(block_text)
    correct_ans = ""
    ans_start_idx = len(block_text)
    if ans_match:
        raw_ans = ans_match.group(1) or ans_match.group(2) or ans_match.group(3)
        correct_ans = normalize_option_letter(raw_ans)
        ans_start_idx = ans_match.start()

    # Check for Explanation line
    exp_text = ""
    exp_match = re.search(
        r'(?m)^[ \t]*(?:Explanation|Solutions?|Exp|Hints?)\s*[:\-–\.]*\s*(.*)',
        block_text,
        re.IGNORECASE | re.DOTALL
    )
    if not exp_match:
        exp_match = re.search(
            r'\b(?:Explanation|Solutions?|Exp|Hints?)\s*[:\-–]+\s*(.*)',
            block_text,
            re.IGNORECASE | re.DOTALL
        )
    if exp_match:
        exp_text = exp_match.group(1).strip()
        if exp_match.start() < ans_start_idx and not ans_match:
            ans_start_idx = exp_match.start()

    q_and_opts_text = block_text[:ans_start_idx].strip()

    opt_pattern = re.compile(
        r'(?:^|[\s\t\n]+)(?:[•\*\-–]\s*)?(?:\(([A-Ea-e1-5])\)|\[([A-Ea-e1-5])\]|([A-Ea-e])[\.\)]|([1-5])[\)])\s+',
        re.MULTILINE
    )

    matches = list(opt_pattern.finditer(q_and_opts_text))
    if not matches or len(matches) < 2:
        return None

    first_opt_idx = matches[0].start()
    raw_question = q_and_opts_text[:first_opt_idx].strip()

    q_num = default_num
    num_match = re.search(r'^[\|\s\t]*(?:Q(?:uestion)?[\s\.\:\-]*|\b)(\d+)[\.\)\:\-]', raw_question, flags=re.IGNORECASE | re.MULTILINE)
    if num_match:
        try:
            q_num = int(num_match.group(1))
        except ValueError:
            q_num = default_num

    q_clean = re.sub(r'^[\|\s\t]*(?:Q(?:uestion)?[\s\.\:\-]*|\b)\d+[\.\)\:\-]\s*', '', raw_question, flags=re.IGNORECASE | re.MULTILINE).strip()

    # Clean shift and metadata tags from question text while preserving words like 'spelling'
    q_clean = clean_question_text(q_clean)
    q_clean = re.sub(r'\b(?:विकल्प(?:\s*\(Options\))?|Options?)\s*[:\-–\.]*\s*$', '', q_clean, flags=re.IGNORECASE).strip()
    q_clean = q_clean.strip("•*-– \t\n")

    # Bilingual detection & preamble cleaning
    en_q, hi_q, is_bi = clean_question_preamble_and_bilingual(q_clean)

    if not q_clean or len(q_clean) < 3:
        if "Spelling" in topic:
            q_clean = "Select the incorrectly / correctly spelt word:"
        elif "Idiom" in topic:
            q_clean = "Select the most appropriate meaning of the given idiom/phrase:"
        elif "Synonym" in topic:
            q_clean = "Select the most appropriate synonym of the given word:"
        elif "Antonym" in topic:
            q_clean = "Select the most appropriate antonym of the given word:"
        else:
            q_clean = "Select the most appropriate option:"

    options = {}
    checkmark_detected = None
    for i, match in enumerate(matches):
        letter = match.group(1) or match.group(2) or match.group(3) or match.group(4)
        norm_letter = normalize_option_letter(letter)
        
        start_pos = match.end()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(q_and_opts_text)
        opt_raw = q_and_opts_text[start_pos:end_pos].strip()

        # Check if option has checkmark emoji
        if any(chk in opt_raw for chk in ["✅", "✔", "✓"]):
            checkmark_detected = norm_letter
        
        opt_clean = clean_option_text(opt_raw)
        options[norm_letter] = opt_clean

    final_keys = ['A', 'B', 'C', 'D']
    if 'E' in options:
        final_keys.append('E')
    final_options = {}
    for key in final_keys:
        final_options[key] = options.get(key, f"Option {key}")

    if not correct_ans and checkmark_detected:
        correct_ans = checkmark_detected

    # Check Answer Map if inline answer was not found
    if (not correct_ans or correct_ans not in ['A', 'B', 'C', 'D', 'E']) and answer_map and q_num in answer_map:
        correct_ans = answer_map[q_num]

    # Additional backup inline answer search:
    if not correct_ans or correct_ans not in ['A', 'B', 'C', 'D', 'E']:
        backup_ans = ans_regex.search(block_text)
        if backup_ans:
            b_let = backup_ans.group(1) or backup_ans.group(2) or backup_ans.group(3)
            correct_ans = normalize_option_letter(b_let)

    # Match answer by word if letter was omitted (e.g. "ANSWER Salubrious")
    if not correct_ans or correct_ans not in ['A', 'B', 'C', 'D', 'E']:
        word_ans = re.search(
            r'[\|\s\t\-•]*(?:ANSWER|ANS(?:WER)?|KEY|उत्तर)\s*[:\-–\.]*\s*([A-Za-z]{3,})',
            block_text,
            re.IGNORECASE
        )
        if word_ans:
            target_word = word_ans.group(1).lower().strip()
            for opt_k, opt_v in options.items():
                if target_word in opt_v.lower():
                    correct_ans = opt_k
                    break

    # DO NOT blindly default to 'A' if completely unknown
    if not correct_ans or correct_ans not in ['A', 'B', 'C', 'D', 'E']:
        correct_ans = ""

    full_display_q = f"English: {en_q}\nHindi: {hi_q}" if (is_bi and en_q and hi_q) else (en_q or q_clean)

    return {
        "question_number": q_num,
        "question_text": full_display_q,
        "english_text": en_q if is_bi else "",
        "hindi_text": hi_q if is_bi else "",
        "is_bilingual": is_bi,
        "options": final_options,
        "correct_answer": correct_ans,
        "topic": topic,
        "explanation": exp_text
    }

def parse_csv_file(file_or_content, default_topic: str = "Financial Awareness") -> List[Dict[str, Any]]:
    """
    Dynamically parses a CSV / TSV file (file path, bytes, StringIO, or raw CSV string) containing MCQs.
    Intelligently handles:
    1. Freeform cell dump (e.g. Column 0 contains bilingual questions, options, and answers; other columns contain detailed study notes / descriptions).
    2. Structured tabular CSV (columns: Question, Option A, Option B, Option C, Option D, Option E, Answer, Explanation).
    3. Bilingual questions (English + Hindi), preserving and formatting both languages cleanly.
    4. Auto-cleans bullet marks, emojis (✅), and formatting noise.
    """
    import io
    import csv

    if not file_or_content:
        return []

    # 1. Decode / read text content
    text_content = ""
    if isinstance(file_or_content, (bytes, bytearray)):
        for enc in ["utf-8-sig", "utf-8", "latin1", "cp1252"]:
            try:
                text_content = file_or_content.decode(enc)
                break
            except UnicodeDecodeError:
                continue
    elif hasattr(file_or_content, "read"):
        content = file_or_content.read()
        if isinstance(content, (bytes, bytearray)):
            for enc in ["utf-8-sig", "utf-8", "latin1", "cp1252"]:
                try:
                    text_content = content.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
        else:
            text_content = str(content)
    elif isinstance(file_or_content, str):
        if len(file_or_content) < 1024 and ("\n" not in file_or_content) and os.path.exists(file_or_content):
            for enc in ["utf-8-sig", "utf-8", "latin1", "cp1252"]:
                try:
                    with open(file_or_content, "r", encoding=enc) as f:
                        text_content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
        else:
            text_content = file_or_content

    if not text_content or not text_content.strip():
        return []

    # 2. Parse CSV rows
    t_counts = {"\t": text_content.count("\t"), ",": text_content.count(","), ";": text_content.count(";")}
    delimiter = max(t_counts, key=t_counts.get)
    if t_counts[delimiter] == 0:
        delimiter = ","
    try:
        reader = csv.reader(io.StringIO(text_content), delimiter=delimiter)
        raw_rows = list(reader)
    except Exception:
        reader = csv.reader(io.StringIO(text_content))
        raw_rows = list(reader)

    non_empty_rows = [r for r in raw_rows if any(cell.strip() for cell in r)]
    if not non_empty_rows:
        return []

    # 3. Check if structured tabular CSV (e.g. separate Question, Option A, Option B columns)
    header = [c.strip().lower() for c in non_empty_rows[0]]
    is_tabular = any("question" in h for h in header) and any("option" in h or "opt" in h or "choice" in h for h in header)

    questions = []
    if is_tabular and len(non_empty_rows) > 1:
        q_idx = next((i for i, h in enumerate(header) if "question" in h or "प्रश्न" in h), 0)
        ans_idx = next((i for i, h in enumerate(header) if "answer" in h or "ans" in h or "उत्तर" in h), None)
        exp_idx = next((i for i, h in enumerate(header) if "explanation" in h or "exp" in h or "description" in h or "note" in h), None)
        top_idx = next((i for i, h in enumerate(header) if "topic" in h or "subject" in h or "category" in h), None)

        opt_indices = {}
        for let in ["a", "b", "c", "d", "e"]:
            for i, h in enumerate(header):
                if re.search(rf'\b(?:option|opt|choice)\s*[-_]?\s*{let}\b', h) or h == let:
                    opt_indices[let.upper()] = i
                    break

        for row_num, row in enumerate(non_empty_rows[1:], 1):
            if not any(c.strip() for c in row):
                continue
            raw_q_text = row[q_idx].strip() if q_idx < len(row) else ""
            if not raw_q_text:
                continue

            opts = {}
            for let, col_i in opt_indices.items():
                if col_i < len(row):
                    opts[let] = clean_option_text(row[col_i].strip())

            if len(opts) < 2:
                parsed_block = parse_single_mcq_block(raw_q_text, default_num=row_num, topic=default_topic)
                if parsed_block:
                    opts = parsed_block.get("options", {})
                    raw_q_text = parsed_block.get("question_text", raw_q_text)

            raw_ans = row[ans_idx].strip() if (ans_idx is not None and ans_idx < len(row)) else ""
            clean_ans = normalize_option_letter(raw_ans) if raw_ans else ""
            if clean_ans not in ["A", "B", "C", "D", "E"] and opts:
                for opt_k, opt_v in opts.items():
                    if raw_ans and opt_v and raw_ans.lower() in opt_v.lower():
                        clean_ans = opt_k
                        break

            row_exp = row[exp_idx].strip() if (exp_idx is not None and exp_idx < len(row)) else ""
            row_topic = row[top_idx].strip() if (top_idx is not None and top_idx < len(row)) else default_topic

            en_t, hi_t, is_bi = clean_question_preamble_and_bilingual(raw_q_text)
            full_display_q = f"English: {en_t}\nHindi: {hi_t}" if (is_bi and en_t and hi_t) else (en_t or raw_q_text)

            questions.append({
                "question_number": row_num,
                "question_text": full_display_q,
                "english_text": en_t if is_bi else "",
                "hindi_text": hi_t if is_bi else "",
                "is_bilingual": is_bi,
                "options": opts,
                "correct_answer": clean_ans,
                "topic": row_topic or default_topic,
                "explanation": row_exp
            })
    else:
        # 4. Freeform cell format (MCQ block in one cell, study notes in other columns)
        start_row = 1 if ("question with answer" in "".join(non_empty_rows[0]).lower() or "question" in "".join(non_empty_rows[0]).lower()) else 0
        q_counter = 1

        for row in non_empty_rows[start_row:]:
            best_mcq_idx = 0
            best_score = -1

            for col_i, cell in enumerate(row):
                c_clean = cell.strip()
                if not c_clean:
                    continue
                score = 0
                if re.search(r'(?:^|[\s\t\n]+)(?:[•\*\-–]\s*)?(?:\([A-Ea-e1-5]\)|\[[A-Ea-e1-5]\]|[A-Ea-e][\.\)])\s+', c_clean):
                    score += 5
                if re.search(r'\b(?:Question|Options|Answer|विकल्प|सही\s*उत्तर|English|Hindi)\b', c_clean, re.IGNORECASE):
                    score += 3
                if len(c_clean) > 80:
                    score += 1

                if score > best_score:
                    best_score = score
                    best_mcq_idx = col_i

            mcq_cell = row[best_mcq_idx].strip() if best_mcq_idx < len(row) else ""
            desc_cells = [row[c_i].strip() for c_i in range(len(row)) if c_i != best_mcq_idx and row[c_i].strip()]

            if not mcq_cell:
                continue

            parsed = parse_single_mcq_block(mcq_cell, default_num=q_counter, topic=default_topic)
            if parsed and parsed.get("options") and len(parsed["options"]) >= 2:
                if desc_cells:
                    def _cell_sort_key(cell_text: str):
                        m = re.match(r'^\s*(\d+)[\.\)]', cell_text.strip())
                        return (0, int(m.group(1))) if m else (1, 0)
                    desc_cells_sorted = sorted(desc_cells, key=_cell_sort_key)
                    existing = parsed.get("explanation", "").strip()
                    desc_text = "\n\n".join(desc_cells_sorted)
                    parsed["explanation"] = f"{existing}\n\n{desc_text}".strip() if existing else desc_text
                parsed["uid"] = f"q_{q_counter}"
                parsed["question_number"] = q_counter
                questions.append(parsed)
                q_counter += 1

    for i, q in enumerate(questions):
        q["uid"] = f"q_{i + 1}"
        q["question_number"] = i + 1

    return questions

def normalize_option_letter(val: str) -> str:
    val = val.strip().upper()
    mapping = {'1': 'A', '2': 'B', '3': 'C', '4': 'D', '5': 'E'}
    return mapping.get(val, val)

def fallback_regex_parser(text: str, default_topic: str, answer_map: Optional[Dict[int, str]] = None) -> List[Dict[str, Any]]:
    pattern = re.compile(
        r'(?:^|\n)\s*(?:Q(?:uestion)?[\s\.\:\-]*|\b)(\d+)[\.\)\:\-]\s*(.*?)(?=(?:^|\n)\s*(?:Q(?:uestion)?[\s\.\:\-]*|\b)\d+[\.\)\:\-]|\Z)',
        re.DOTALL | re.IGNORECASE
    )
    results = []
    for match in pattern.finditer(text):
        q_num_str = match.group(1)
        block = match.group(2)
        try:
            q_num = int(q_num_str)
        except ValueError:
            q_num = len(results) + 1
        
        parsed = parse_single_mcq_block(block, default_num=q_num, topic=default_topic, answer_map=answer_map)
        if parsed:
            results.append(parsed)
    return results

def prepare_questions_list(q_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ensures every question has a globally unique 'uid', de-duplicates question numbers,
    cleans noisy shift/date metadata, and runs trap analysis.
    Guarantees no StreamlitDuplicateElementKey can ever occur.
    """
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

def format_study_notes_html(text: str) -> str:
    """
    Converts raw study notes / explanations (from CSV, PDF, or Database) into clean, modern HTML.
    Features:
    - Parses tab-separated (\\t) and markdown pipe (|) tables into responsive styled HTML <table> elements.
    - Highlights exam trick / mnemonic boxes ('याद रखने की Trick:', 'Exam Note:', 'Important:', etc.) with warm amber alert styling.
    - Highlights section headers ('Exam Important Points', 'Answer Explanation', '1. ...', etc.) with bold navy styling.
    - Formats bullet points (•, -, *) cleanly.
    - Converts markdown bold (**text**) to <strong>text</strong>.
    - Safely escapes raw HTML entities.
    """
    import html
    if not text or not str(text).strip():
        return ""
    
    lines = str(text).strip().splitlines()
    html_parts = []
    table_rows = []
    
    def flush_table():
        if not table_rows:
            return
        t_html = ['<div style="overflow-x:auto; margin:6px 0;"><table class="notes-table" style="width:100%; border-collapse:collapse; font-size:0.80rem; border:1px solid #cbd5e1; border-radius:6px; overflow:hidden;">']
        for row_i, r in enumerate(table_rows):
            if row_i == 0:
                t_html.append('<tr style="background:#e0e7ff; color:#1e3a8a; font-weight:700;">')
                for cell in r:
                    t_html.append(f'<th style="border:1px solid #c7d2fe; padding:6px 10px; text-align:left;">{html.escape(cell)}</th>')
                t_html.append('</tr>')
            else:
                bg = '#ffffff' if row_i % 2 == 1 else '#f8fafc'
                t_html.append(f'<tr style="background:{bg};">')
                for cell in r:
                    t_html.append(f'<td style="border:1px solid #e2e8f0; padding:5px 10px; color:#1e293b;">{html.escape(cell)}</td>')
                t_html.append('</tr>')
        t_html.append('</table></div>')
        html_parts.append(''.join(t_html))
        table_rows.clear()

    for line in lines:
        s = line.strip()
        if not s:
            flush_table()
            continue
        
        # Check if tab-separated line
        if '\t' in s:
            cols = [c.strip() for c in s.split('\t')]
            if len(cols) >= 2:
                table_rows.append(cols)
                continue
        elif s.startswith('|') and s.endswith('|') and s.count('|') >= 3:
            cols = [c.strip() for c in s.split('|')[1:-1]]
            if not all(c.startswith('-') for c in cols):
                table_rows.append(cols)
                continue
        
        flush_table()
        
        # Check if Heading
        if re.match(r'^(?:📘|💡|🎯|🔥|Exam Important Points|Answer Explanation|\d+\.\s+)', s, re.IGNORECASE):
            s_esc = html.escape(s)
            html_parts.append(f'<div style="font-weight:700; color:#1e40af; margin-top:8px; margin-bottom:3px; font-size:0.83rem; display:flex; align-items:center; gap:4px;">{s_esc}</div>')
        elif re.match(r'^(?:याद रखने की Trick|Trick|Exam Note|Important|ध्यान दें)[:\s]', s, re.IGNORECASE):
            s_esc = html.escape(s)
            html_parts.append(f'<div style="background:#fffbeb; border:1px solid #fde68a; border-left:3px solid #f59e0b; padding:5px 9px; border-radius:4px; margin:6px 0; font-size:0.79rem; color:#92400e; font-weight:600;">💡 {s_esc}</div>')
        elif s.startswith(('•', '-', '*')):
            item_text = re.sub(r'^[•\-\*]\s*', '', s)
            item_html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html.escape(item_text))
            html_parts.append(f'<div style="margin-left:8px; margin-bottom:2px; font-size:0.80rem; line-height:1.4;"><span style="color:#2563eb; margin-right:4px;">•</span>{item_html}</div>')
        else:
            p_html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html.escape(s))
            html_parts.append(f'<div style="margin-bottom:3px; font-size:0.80rem; line-height:1.45;">{p_html}</div>')
            
    flush_table()
    return ''.join(html_parts)


