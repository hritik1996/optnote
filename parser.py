# Re-export all functions from mcq_parser for compatibility
from mcq_parser import (
    extract_text_from_pdf,
    parse_mcq_text,
    parse_csv_file,
    clean_question_preamble_and_bilingual,
    clean_option_text,
    clean_question_text,
    clean_and_normalize_text,
    parse_single_mcq_block,
    normalize_option_letter,
    fallback_regex_parser,
    extract_answer_key,
    prepare_questions_list,
    format_study_notes_html
)

__all__ = [
    "extract_text_from_pdf",
    "parse_mcq_text",
    "parse_csv_file",
    "clean_question_preamble_and_bilingual",
    "clean_option_text",
    "clean_question_text",
    "clean_and_normalize_text",
    "parse_single_mcq_block",
    "normalize_option_letter",
    "fallback_regex_parser",
    "extract_answer_key",
    "prepare_questions_list",
    "format_study_notes_html"
]
