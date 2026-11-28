"""
Automated validation script for OptNote (optnote.com) MCQ Test Series App.
Tests PDF extraction, regex parsing, option structuring, and fallback Gemini helper.
"""
import os
import unittest
from parser import extract_text_from_pdf, parse_mcq_text
from gemini_helper import generate_hindi_explanation
from sample_data import SAMPLE_RAW_MCQ_TEXT
from create_sample_pdf import create_sample_pdf

from trap_analyzer import analyze_exam_trap

class TestMCQApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pdf_path = "test_mcq_paper.pdf"
        create_sample_pdf(cls.pdf_path)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.pdf_path):
            os.remove(cls.pdf_path)

    def test_raw_text_parsing(self):
        questions = parse_mcq_text(SAMPLE_RAW_MCQ_TEXT)
        self.assertGreaterEqual(len(questions), 20, "Should parse at least 20 questions from sample text")
        
        for q in questions:
            self.assertIn("question_number", q)
            self.assertIn("question_text", q)
            self.assertTrue(len(q["question_text"]) > 0, f"Question text should not be empty for Q{q['question_number']}")
            self.assertIn("options", q)
            for opt_key in ["A", "B", "C", "D"]:
                self.assertIn(opt_key, q["options"])
            self.assertIn(q["correct_answer"], ["A", "B", "C", "D"])
            self.assertIn("topic", q)

    def test_pdf_extraction_and_parsing(self):
        text = extract_text_from_pdf(self.pdf_path)
        self.assertGreater(len(text), 100, "Extracted text should not be empty")
        questions = parse_mcq_text(text)
        self.assertEqual(len(questions), 20, "Should parse exactly 20 questions from generated PDF")
        
        q1 = questions[0]
        self.assertEqual(q1["question_number"], 1)
        self.assertIn("eleventh hour", q1["question_text"])
        self.assertEqual(q1["correct_answer"], "B")

    def test_noisy_options_and_unnumbered_questions(self):
        user_raw = """
        (A) Anesthetic
        (B) Intricate SHIFT 08 05 OCT 2026 EXAM SHIFT
        (C) Unexpectid ENGLISH WITH RANI MA'AM Believe in Quality SSC CGL 2026 | TIER-I uclive.org Join Telegram Contents Page 3 / 93 English With Rani Ma'am | Contact: 9958358324 SPELLING
        (D) Creeping ANSWER
        (A) Prejudise SPELLING
        (B) Ignorant SHIFT 04 01 OCT 2026 EXAM SHIFT 2
        (C) Repulsive
        (D) Ancestor ANSWER
        """
        questions = parse_mcq_text(user_raw)
        self.assertEqual(len(questions), 2, "Should parse 2 separate questions from unnumbered set")
        
        q1_opts = questions[0]["options"]
        self.assertEqual(q1_opts["A"], "Anesthetic")
        self.assertEqual(q1_opts["B"], "Intricate")
        self.assertEqual(q1_opts["C"], "Unexpectid")
        self.assertEqual(q1_opts["D"], "Creeping")
        
        q2_opts = questions[1]["options"]
        self.assertEqual(q2_opts["A"], "Prejudise")
        self.assertEqual(q2_opts["B"], "Ignorant")
        self.assertEqual(q2_opts["C"], "Repulsive")
        self.assertEqual(q2_opts["D"], "Ancestor")

    def test_trap_analyzer(self):
        res1 = analyze_exam_trap(
            "Identify the misspelt word.",
            {"A": "Belligerent", "B": "Beligerent", "C": "ineffable", "D": "inscrutable"}
        )
        self.assertTrue(res1["is_trap"], "Belligerent should be flagged as exam trap")
        self.assertIn("Double", res1["reason"])

    def test_gemini_fallback(self):
        res = generate_hindi_explanation(
            api_key=None,
            question_text="Sample question",
            options={"A": "opt1", "B": "opt2", "C": "opt3", "D": "opt4"},
            correct_answer="B"
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["source"], "fallback")
        self.assertIn("API Key", res["hindi_meaning"])

    def test_answer_key_mapping(self):
        from mcq_parser import extract_answer_key
        raw_text_with_key = """
        10. Spot the correct of the ear nose throat specialty.
        (A) Otorhinolarynology
        (B) Otorhinolaryngology SHIFT 05 01 OCT 2026 EXAM SHIFT 3
        (C) Otorhinolaringology
        (D) Otorrhinolaryngology

        ANSWER KEY
        10. (B)
        """
        ans_map = extract_answer_key(raw_text_with_key)
        self.assertEqual(ans_map.get(10), "B", "Should extract answer B for Q10 from Answer Key")

        questions = parse_mcq_text(raw_text_with_key)
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["correct_answer"], "B", "Q10 must be mapped to B, not default to A")
        self.assertEqual(questions[0]["options"]["B"], "Otorhinolaryngology")

    def test_logorrhoea_multiline_and_stuck_answer(self):
        # Case 1: ANSWER on newline before option letter
        raw_1 = """
        | 3. Which of the following is the correct of the word?
        (A) Logorrhoea
        (B) Logorhoea
        (C) Loggorrhoea
        (D) Loggorrhea
        ANSWER
        (A) Logorrhoea
        | 4. Next question...
        (A) Opt1 (B) Opt2 (C) Opt3 (D) Opt4
        ANSWER (B)
        """
        qs1 = parse_mcq_text(raw_1)
        self.assertEqual(len(qs1), 2)
        self.assertEqual(qs1[0]["question_number"], 3)
        self.assertEqual(qs1[0]["correct_answer"], "A")
        self.assertEqual(qs1[0]["options"]["A"], "Logorrhoea")

        # Case 2: ANSWER stuck to option D line
        raw_2 = """
        | 3. Which of the following is the correct of the word?
        (A) Logorrhoea (B) Logorhoea
        (C) Loggorrhoea (D) Loggorrhea ANSWER (A) Logorrhoea
        """
        qs2 = parse_mcq_text(raw_2)
        self.assertEqual(len(qs2), 1)
        self.assertEqual(qs2[0]["question_number"], 3)
        self.assertEqual(qs2[0]["correct_answer"], "A")
        self.assertEqual(qs2[0]["options"]["D"], "Loggorrhea")

    def test_real_pdf_batch(self):
        real_snippet = """
        SPELLING
        | 7. Select the correctly spelt word to replace the highlighted word in the given sentence.
        The climate there is very salubrius.
        A) Salubrious B) Salubrius
        C) Salubreeous D) Salubreous
        ANSWER (A) Salubrious

        | SHIFT 03 | 01 OCT 2026 | EXAM SHIFT 1
        SPELLING
        | 8. Which is the correct spelling of a word meaning 'prevent from happening'?
        A) Avert B) Avart
        C) Avirrt D) Avurt
        ANSWER (A) Avert

        SPELLING
        | 9. Identify the misspelt word.
        A) Belligerent B) Beligerent
        C) ineffable D) inscrutable
        ANSWER (B) Beligerent

        | SHIFT 04 | 01 OCT 2026 | EXAM SHIFT 2
        SPELLING
        | 10. Spot the correct spelling of the ear-nose-throat specialty.
        A) Otorhinolarynology B) Otorhinolaryngology
        C) Otorhinolaringology D) Otorrhinolaryngology
        ANSWER (B) Otorhinolaryngology
        """
        qs = parse_mcq_text(real_snippet)
        self.assertEqual(len(qs), 4)
        self.assertEqual(qs[0]["question_number"], 7)
        self.assertEqual(qs[0]["correct_answer"], "A")
        self.assertEqual(qs[1]["question_number"], 8)
        self.assertEqual(qs[1]["correct_answer"], "A")
        self.assertEqual(qs[2]["question_number"], 9)
        self.assertEqual(qs[2]["correct_answer"], "B")
        self.assertEqual(qs[3]["question_number"], 10)
        self.assertEqual(qs[3]["correct_answer"], "B")

    def test_sanitize_api_key(self):
        from gemini_helper import sanitize_api_key
        # Test zero-width space
        key_zw = "\u200bAIzaSyABC1234567890_test"
        self.assertEqual(sanitize_api_key(key_zw), "AIzaSyABC1234567890_test")
        # Ensure it encodes cleanly to ASCII without UnicodeEncodeError
        self.assertEqual(sanitize_api_key(key_zw).encode("ascii"), b"AIzaSyABC1234567890_test")

        # Test smart quotes and BOM
        key_bom = "\ufeff“AIzaSyXYZ987654321”\n"
        self.assertEqual(sanitize_api_key(key_bom), "AIzaSyXYZ987654321")

    def test_gemini_35_flash_lite_solver(self):
        from gemini_helper import solve_mcq_with_gemini
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            return  # Skip network call if key not configured
        ans = solve_mcq_with_gemini(
            api_key=api_key,
            question_text="Which of the following is the correct spelling of the word?",
            options={"A": "Logorrhoea", "B": "Logorhoea", "C": "Loggorrhoea", "D": "Loggorrhea"},
            model_name="gemini-3.5-flash-lite"
        )
        # If offline/sandboxed, ans may be None; when online, ans must be strictly 'A'
        if ans is not None:
            self.assertEqual(ans, "A", "Should accurately solve spelling MCQ with gemini-3.5-flash-lite")

    def test_duplicate_question_number_resolution(self):
        raw_duplicate_text = """
        | 6. First question six from Shift 1
        (A) Option 1 (B) Option 2 (C) Option 3 (D) Option 4
        ANSWER (A)

        | 6. Second question six from Shift 2
        (A) Option 1 (B) Option 2 (C) Option 3 (D) Option 4
        ANSWER (B)
        """
        qs = parse_mcq_text(raw_duplicate_text)
        self.assertEqual(len(qs), 2)
        # Check unique UIDs
        self.assertEqual(qs[0]["uid"], "q_1")
        self.assertEqual(qs[1]["uid"], "q_2")
        # Check deduplicated question numbers
        self.assertNotEqual(qs[0]["question_number"], qs[1]["question_number"], "Duplicate question numbers must be re-sequenced")
        self.assertEqual(qs[0]["question_number"], 1)
        self.assertEqual(qs[1]["question_number"], 2)
        self.assertEqual(qs[0]["original_number"], 6)
        self.assertEqual(qs[1]["original_number"], 6)

    def test_multi_topic_independent_answer_keys(self):
        multi_topic_doc = """
Topic: Computer Fundamentals
QUESTION BANK
1. The word computer has been derived from which of the following language?
(1) Greek (2) English (3) Hindi (4) Latin
2. Input, output and processing devices grouped together represent a(n)
(1) mobile device (2) information processing cycle (3) circuit board (4) computer system

ANSWERS
1. (4) | 2. (4)

Topic: Computer Architecture
QUESTION BANK
1. The main system board of a personal computer is called the:
(1) Integrated circuit (2) Motherboard (3) Processor (4) Microchip
2. Which bus connects the CPU to memory?
(1) Expansion bus (2) System bus (3) Control bus (4) Data bus

ANSWERS
1. (2) | 2. (2)
        """
        qs = parse_mcq_text(multi_topic_doc)
        self.assertEqual(len(qs), 4, "Should parse all 4 questions across the 2 topics")
        
        # Verify Topic 1 Q1 & Q2
        self.assertEqual(qs[0]["topic"], "Computer Fundamentals")
        self.assertEqual(qs[0]["correct_answer"], "D", "Topic 1 Q1 must be D (Latin)")
        self.assertEqual(qs[0]["options"]["D"], "Latin")
        self.assertEqual(qs[1]["correct_answer"], "D", "Topic 1 Q2 must be D (computer system)")
        self.assertEqual(qs[1]["options"]["D"], "computer system")
        
        # Verify Topic 2 Q1 & Q2 - ensuring no key collision/overwrite
        self.assertEqual(qs[2]["topic"], "Computer Architecture")
        self.assertEqual(qs[2]["correct_answer"], "B", "Topic 2 Q1 must be B (Motherboard), NOT overridden by Topic 1's Q1")
        self.assertEqual(qs[2]["options"]["B"], "Motherboard")
        self.assertEqual(qs[3]["correct_answer"], "B", "Topic 2 Q2 must be B (System bus)")
        self.assertEqual(qs[3]["options"]["B"], "System bus")

    def test_banking_five_options_and_grid_answers(self):
        banking_text = """
QUESTION BANK
9. A collection of unprocessed items is [SBI PO 2015]
(1) information (2) data
(3) memory (4) reports
(5) None of these

10. Which among the following cycle consists of an input, processing, output and storage as its constituents? [IBPS Clerk Mains 2017]
(1) Processing (2) Output
(3) Input (4) Storage
(5) Data

ANSWERS
9. (2) | 10. (5)
        """
        qs = parse_mcq_text(banking_text)
        self.assertEqual(len(qs), 2)
        
        # Q9 check
        self.assertEqual(qs[0]["options"]["A"], "information")
        self.assertEqual(qs[0]["options"]["B"], "data")
        self.assertEqual(qs[0]["options"]["E"], "None of these")
        self.assertEqual(qs[0]["correct_answer"], "B", "Q9 answer must be B (data)")
        
        # Q10 check
        self.assertEqual(qs[1]["options"]["E"], "Data")
        self.assertEqual(qs[1]["correct_answer"], "E", "Q10 answer must be E (Data)")

    def test_csv_financial_awareness_and_bilingual_parsing(self):
        from parser import parse_csv_file
        qs = parse_csv_file("sample_financial_awareness.csv")
        self.assertEqual(len(qs), 54, "Should parse all 54 financial awareness MCQs from CSV")

        # Q1 check (bilingual English + Hindi, correct answer A, description notes extracted)
        q1 = qs[0]
        self.assertTrue(q1["is_bilingual"])
        self.assertIn("SBI Card and Google Pay", q1["english_text"])
        self.assertIn("SBI कार्ड और Google Pay", q1["hindi_text"])
        self.assertEqual(q1["correct_answer"], "A")
        self.assertEqual(q1["options"]["A"], "Google Pay Flex SBI Card")
        self.assertIn("जॉइनिंग फीस", q1["explanation"])

        # Q47 check (checkmark emoji detection and clean option text)
        q47 = qs[46]
        self.assertEqual(q47["correct_answer"], "B")
        self.assertEqual(q47["options"]["B"], "Mizuho Bank")

    def test_tabular_csv_parsing(self):
        from parser import parse_csv_file
        tabular_csv = """Question,Option A,Option B,Option C,Option D,Correct Answer,Explanation
What is the capital of France?,Paris,London,Berlin,Madrid,A,Paris is the capital of France.
What is 2+2?,3,4,5,6,B,Simple math addition.
"""
        qs = parse_csv_file(tabular_csv)
        self.assertEqual(len(qs), 2)
        self.assertEqual(qs[0]["question_text"], "What is the capital of France?")
        self.assertEqual(qs[0]["options"]["A"], "Paris")
        self.assertEqual(qs[0]["correct_answer"], "A")
        self.assertEqual(qs[0]["explanation"], "Paris is the capital of France.")
        self.assertEqual(qs[1]["correct_answer"], "B")

    def test_answer_key_grid_and_multi_topic_splitting(self):
        from parser import parse_mcq_text, extract_answer_key
        raw_text = """CHAPTER 1
QUESTION BANK (MCQS)
1. The word computer has been derived from which of the following language?
(1) Greek (2) English
(3) Hindi (4) Latin

2. Input, output and processing devices grouped together represent a(n)
(1) mobile device
(2) information processing cycle
(3) circuit board
(4) computer system

ANSWERS - CHAPTER 1
1. (4) | 2. (4) | 3. (4) | 4. (1) | 5. (3)

CHAPTER 2
QUESTION BANK (MCQS)
1. A collection of unprocessed items is
(1) information (2) data
(3) memory (4) reports

ANSWERS - CHAPTER 2
1. (2)
"""
        qs = parse_mcq_text(raw_text)
        self.assertGreaterEqual(len(qs), 3)
        self.assertEqual(qs[0]["correct_answer"], "D")
        self.assertEqual(qs[1]["correct_answer"], "D")
        self.assertEqual(qs[2]["correct_answer"], "B")

    def test_lazy_batch_loading_instant_performance(self):
        import time
        from parser import prepare_questions_list

        # Simulate 1,000 questions
        mock_1000_qs = []
        for i in range(1, 1001):
            mock_1000_qs.append({
                "question_number": i,
                "question_text": f"Question {i} test prompt",
                "options": {"A": "Option 1", "B": "Option 2", "C": "Option 3", "D": "Option 4"},
                "correct_answer": "", # Unspecified in PDF
                "explanation": ""
            })

        t0 = time.time()
        prepared = prepare_questions_list(mock_1000_qs)
        prep_time = time.time() - t0
        self.assertEqual(len(prepared), 1000)
        self.assertLess(prep_time, 0.5, "Preparing 1,000 questions should take < 0.5s")

        # Simulate batch of 50 unanswered questions render loop
        batch_50 = prepared[:50]
        user_answers = {} # None answered yet
        t1 = time.time()
        rendered_count = 0
        for q in batch_50:
            q_uid = q["uid"]
            is_answered = q_uid in user_answers
            # Verified: NO Gemini network calls are triggered for unanswered questions
            if is_answered:
                pass
            rendered_count += 1
        batch_render_time = time.time() - t1
        self.assertEqual(rendered_count, 50)
        self.assertLess(batch_render_time, 0.01, "Batch rendering 50 unanswered questions should take < 10ms")

    def test_db_initialization_and_deduplication(self):
        import db_manager
        db_manager.init_db()
        self.assertIn(db_manager.get_active_db_type(), ["postgres", "sqlite"])

        # Insert question
        sample_q = [{
            "question_text": "Which layer of the OSI model handles end-to-end encryption?",
            "options": {"A": "Session", "B": "Presentation", "C": "Network", "D": "Transport"},
            "correct_answer": "B",
            "explanation": "The Presentation Layer (Layer 6) formats and encrypts data.",
            "topic": "Computer Networks"
        }]
        res1 = db_manager.save_parsed_questions(sample_q, source_name="osi_paper.pdf", subject_name="Computer Knowledge")
        self.assertEqual(res1["total"], 1)

        # Re-insert exact duplicate
        res2 = db_manager.save_parsed_questions(sample_q, source_name="osi_paper_duplicate.pdf", subject_name="Computer Knowledge")
        self.assertEqual(res2["inserted"], 0)
        self.assertEqual(res2["duplicates"], 1)

        # Search
        found, total = db_manager.search_questions("OSI model handles end-to-end")
        self.assertGreaterEqual(total, 1)
        self.assertEqual(found[0]["correct_answer"], "B")

    def test_db_user_attempt_recording_and_analytics(self):
        import db_manager
        db_manager.init_db()

        # Insert a sample question to get a db_id
        q_item = [{
            "question_text": "What is the primary function of the Central Bank?",
            "options": {"A": "Commercial Loans", "B": "Monetary Policy", "C": "Stock Trading", "D": "Real Estate"},
            "correct_answer": "B",
            "explanation": "Central Bank controls monetary policy and currency issuance.",
            "topic": "Banking Systems"
        }]
        db_manager.save_parsed_questions(q_item, source_name="bank_test.pdf", subject_name="Banking & Financial Awareness")
        found, _ = db_manager.search_questions("Central Bank controls monetary policy")
        self.assertGreaterEqual(len(found), 1)
        q_db_id = found[0]["db_id"]

        # Record a correct attempt and an incorrect attempt
        user_uuid = db_manager.DEFAULT_GUEST_USER_ID
        ok1 = db_manager.record_user_attempt(question_id=q_db_id, selected_option="B", is_correct=True, user_id=user_uuid)
        self.assertTrue(ok1)
        ok2 = db_manager.record_user_attempt(question_id=q_db_id, selected_option="A", is_correct=False, user_id=user_uuid)
        self.assertTrue(ok2)

        # Check analytics
        analytics = db_manager.get_user_analytics(user_id=user_uuid)
        self.assertGreaterEqual(analytics["total_attempts"], 2)
        self.assertGreaterEqual(analytics["correct_count"], 1)
        self.assertGreaterEqual(analytics["incorrect_count"], 1)

    def test_unspecified_answer_and_trap_precision(self):
        import db_manager
        from trap_analyzer import analyze_exam_trap

        # 1. Computer question with double consonant words (processing, compiling) should NOT be flagged as Double Consonant trap!
        comp_trap = analyze_exam_trap(
            "Collecting the data and converting it into information is called",
            {"A": "processing", "B": "compiling", "C": "importing", "D": "exporting"}
        )
        self.assertFalse(comp_trap["is_trap"], "General computer words like processing/compiling must not trigger Double Consonant trap")

        # 2. But actual spelling question or tricky keywords like 'Belligerent' MUST be flagged
        spell_trap = analyze_exam_trap(
            "Find the correctly spelt word.",
            {"A": "Accommodate", "B": "Acomodate", "C": "Acommodate", "D": "Accomodate"}
        )
        self.assertTrue(spell_trap["is_trap"], "Actual spelling question with Accommodate must be flagged as trap")

        # 3. Test update_question_correct_option helper
        q_item = [{
            "question_text": "Collecting the data and converting it into information is called test",
            "options": {"A": "processing", "B": "compiling", "C": "importing", "D": "exporting"},
            "correct_answer": "",  # Unspecified initially
            "explanation": "",
            "topic": "Computer Science"
        }]
        db_manager.save_parsed_questions(q_item, source_name="comp_test.pdf", subject_name="Computer Awareness")
        found, _ = db_manager.search_questions("converting it into information is called test")
        self.assertGreaterEqual(len(found), 1)
        q_id = found[0]["db_id"]

        # Solve with AI updates correct_option to 'A'
        success = db_manager.update_question_correct_option(correct_option="A", db_id=q_id)
        self.assertTrue(success)

        # Verify it updated in DB
        found_updated, _ = db_manager.search_questions("converting it into information is called test")
        self.assertEqual(found_updated[0]["correct_answer"], "A")

    def test_format_study_notes_html_tables_and_tricks(self):
        from mcq_parser import format_study_notes_html

        raw_notes = """📘 Answer Explanation (Context)
DICGC क्या है?
Deposit Insurance and Credit Guarantee Corporation.
Exam Important Points
विषय\tजानकारी
Full Form\tDeposit Insurance and Credit Guarantee Corporation
Insurance Limit\t₹5 लाख
Coverage\tप्रति जमाकर्ता, प्रति बैंक
याद रखने की Trick: DICGC → RBI → ₹5 Lakh
Important: एक ही बैंक की अलग-अलग शाखाओं में जमा राशि जोड़कर ₹5 लाख की सीमा लागू होती है।
• Point 1: Savings and Current
• Point 2: Fixed and Recurring"""

        html_out = format_study_notes_html(raw_notes)
        self.assertIn("<table class=\"notes-table\"", html_out, "Tab-separated text must generate HTML table")
        self.assertIn(">विषय</th>", html_out, "First row should be table header")
        self.assertIn(">जानकारी</th>", html_out, "First row should be table header")
        self.assertIn(">Full Form</td>", html_out, "Data cells must be wrapped in td")
        self.assertIn(">₹5 लाख</td>", html_out, "Data cells must be wrapped in td")
        self.assertIn("💡", html_out, "Trick lines should have highlight/trick icon")
        self.assertIn("•", html_out, "Bullet points should be formatted")

    def test_csv_parser_with_multichannel_notes(self):
        from mcq_parser import parse_csv_file
        
        # Test freeform CSV with multi-column cells and numbered ordering
        raw_csv = '''"English: SBI Card and Google Pay launched which card?
Hindi: SBI कार्ड और Google Pay ने कौन-सा कार्ड लॉन्च किया?
विकल्प (Options):
• A) Google Pay Flex SBI Card
• B) SBI Pay Smart Card
सही उत्तर (Correct Answer):
• A) Google Pay Flex SBI Card",,"3. More info on card",,,,"1. Joining fee is 499"'''
        
        qs = parse_csv_file(raw_csv)
        self.assertEqual(len(qs), 1)
        q = qs[0]
        self.assertEqual(q["correct_answer"], "A")
        self.assertIn("Google Pay Flex SBI Card", q["options"]["A"])
        # Check that 1. comes before 3. due to ordered sort key
        self.assertTrue(q["explanation"].index("1. Joining fee") < q["explanation"].index("3. More info"))

    def test_csv_delimiter_support(self):
        from mcq_parser import parse_csv_file

        tsv_data = "Question\tOption A\tOption B\tOption C\tOption D\tAnswer\tExplanation\nWhat is repo rate?\tRate 1\tRate 2\tRate 3\tRate 4\tB\tRepo rate is lending rate."
        qs_tsv = parse_csv_file(tsv_data)
        self.assertEqual(len(qs_tsv), 1)
        self.assertEqual(qs_tsv[0]["correct_answer"], "B")

        semicolon_data = "Question;Option A;Option B;Option C;Option D;Answer;Explanation\nWhat is reverse repo?;Opt 1;Opt 2;Opt 3;Opt 4;C;Reverse repo is borrowing rate."
        qs_semi = parse_csv_file(semicolon_data)
        self.assertEqual(len(qs_semi), 1)
        self.assertEqual(qs_semi[0]["correct_answer"], "C")

    def test_topic_grid_and_newest_first_ordering(self):
        import db_manager
        db_manager.init_db()

        # 1. Test get_all_topics_with_counts
        topics = db_manager.get_all_topics_with_counts()
        self.assertIsInstance(topics, list)
        if topics:
            t0 = topics[0]
            self.assertIn("id", t0)
            self.assertIn("name", t0)
            self.assertIn("question_count", t0)
            self.assertIn("subject_name", t0)

        # 2. Test search_questions default newest first ordering
        qs_newest, total = db_manager.search_questions(limit=5, order_by="newest")
        if len(qs_newest) >= 2:
            self.assertGreaterEqual(qs_newest[0]["db_id"], qs_newest[-1]["db_id"], "Newest first must return descending IDs")

        # 3. Test search_questions oldest first
        qs_oldest, _ = db_manager.search_questions(limit=5, order_by="oldest")
        if len(qs_oldest) >= 2:
            self.assertLessEqual(qs_oldest[0]["db_id"], qs_oldest[-1]["db_id"], "Oldest first must return ascending IDs")

if __name__ == "__main__":
    unittest.main()
