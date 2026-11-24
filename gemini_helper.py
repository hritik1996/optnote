import os
import re
from typing import Dict, Any, Optional, List

def sanitize_api_key(api_key: Optional[str]) -> Optional[str]:
    """
    Sanitizes Gemini API key by removing zero-width characters (e.g. \\u200b, \\ufeff),
    invisible Unicode spaces, smart quotes, and non-ASCII artifacts.
    Guarantees the key contains strictly valid ASCII characters.
    """
    if not api_key:
        return None
    key_str = str(api_key).strip()
    # Check if standard Google AI Studio key format (AIzaSy...)
    match = re.search(r'(AIzaSy[a-zA-Z0-9_\-]+)', key_str)
    if match:
        return match.group(1).strip()
    # Otherwise strip all non-ASCII characters and whitespace
    clean_ascii = key_str.encode("ascii", errors="ignore").decode("ascii").strip()
    clean_key = re.sub(r'[^a-zA-Z0-9_\-]', '', clean_ascii)
    return clean_key if clean_key else None

def get_gemini_client(api_key: Optional[str] = None):
    """
    Initializes and returns a Google GenAI client using the google-genai SDK.
    Sanitizes the API key to guarantee pure ASCII headers without UnicodeEncodeError.
    Enforces api_version='v1beta' so all Gemini models (gemini-2.0-flash, gemini-1.5-flash, gemini-1.5-pro)
    are recognized and supported for generateContent.
    """
    try:
        from google import genai
        from google.genai import types
        http_opts = types.HttpOptions(api_version='v1beta')
        clean_key = sanitize_api_key(api_key)
        if clean_key:
            return genai.Client(api_key=clean_key, http_options=http_opts)
        elif os.environ.get("GEMINI_API_KEY"):
            clean_env_key = sanitize_api_key(os.environ.get("GEMINI_API_KEY"))
            if clean_env_key:
                return genai.Client(api_key=clean_env_key, http_options=http_opts)
        return None
    except Exception:
        return None

def solve_mcq_with_gemini(
    api_key: Optional[str],
    question_text: str,
    options: Dict[str, str],
    model_name: str = "gemini-3.5-flash-lite"
) -> Optional[str]:
    """
    Uses Gemini to accurately solve an MCQ when the PDF has no answer key.
    Automatically chains through high-quota models (gemini-3.5-flash-lite, gemini-3.5-flash, gemini-2.5-flash).
    Returns 'A', 'B', 'C', or 'D'.
    """
    client = get_gemini_client(api_key)
    if not client:
        return None
    
    opts_lines = "\n".join([f"({k}) {v}" for k, v in sorted(options.items()) if v])
    prompt = f"""You are a competitive exam expert (SSC CGL / Banking / UPSC).
Question: {question_text}
Options:
{opts_lines}

Which option is the strictly correct answer?
Return ONLY the single uppercase letter (A, B, C, D, or E). No extra words."""

    from google.genai import types
    config = types.GenerateContentConfig(
        max_output_tokens=500,
        temperature=0.0
    )

    models_to_try = []
    for m in [model_name, "gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-2.5-flash"]:
        if m and m not in models_to_try:
            models_to_try.append(m)

    for m in models_to_try:
        try:
            response = client.models.generate_content(
                model=m,
                contents=prompt,
                config=config
            )
            text = response.text.strip().upper() if response.text else ""
            match = re.search(r'\b([A-E])\b', text)
            if match:
                return match.group(1)
        except Exception:
            continue
    return None

def clean_gemini_output(text: str) -> str:
    """
    Strips unnecessary conversational preambles like 'निश्चित रूप से...', 'Sure, here is...'
    and keeps only the crisp, high-yield explanation.
    """
    if not text:
        return ""
    # Strip common conversational opening lines
    text = re.sub(
        r'^(?:निश्चित रूप से[^\n]*\n*|यहाँ आपके प्रश्न[^\n]*\n*|Sure[^\n]*\n*|Here is[^\n]*\n*|Certainly[^\n]*\n*)',
        '',
        text.strip(),
        flags=re.IGNORECASE
    )
    return text.strip()

def generate_hindi_explanation(
    api_key: Optional[str],
    question_text: str,
    options: Dict[str, str],
    correct_answer: str,
    existing_explanation: str = "",
    model_name: str = "gemini-3.5-flash-lite"
) -> Dict[str, Any]:
    """
    Calls Gemini to generate an ultra-compact, high-yield Hindi & English explanation.
    Seamlessly falls back across high-quota models (gemini-3.5-flash-lite, gemini-3.5-flash, gemini-2.5-flash)
    to prevent rate limit (429) stops.
    """
    solved_ans = None
    if not correct_answer or correct_answer not in ['A', 'B', 'C', 'D', 'E']:
        solved_ans = solve_mcq_with_gemini(api_key, question_text, options, model_name=model_name)
        if solved_ans in ['A', 'B', 'C', 'D', 'E']:
            correct_answer = solved_ans

    correct_opt_text = options.get(correct_answer, "")

    client = get_gemini_client(api_key)
    if not client:
        return {
            "success": False,
            "source": "fallback",
            "hindi_meaning": "API Key Not Provided",
            "content": existing_explanation if existing_explanation else f"Correct Answer is Option ({correct_answer}) — {correct_opt_text}",
            "solved_correct_answer": solved_ans
        }

    from google.genai import types

    system_instruction = (
        "You are an ultra-concise competitive exam tutor (SSC CGL, UPSC, Banking).\n"
        "STRICT RULES:\n"
        "1. NO introductory or conversational fluff (NEVER say 'निश्चित रूप से...', 'Sure', 'Here is...').\n"
        "2. Keep the entire response under 50 words total in simple, easy Hindi/Hinglish.\n"
        "3. Provide exactly 3 short bullet points:\n"
        "   • अर्थ: [1-2 simple Hindi words]\n"
        "   • कारण: [1 crisp line: why ({correct_answer}) is correct]\n"
        "   • Trick: [1 short line memory trick or rule]\n"
        "4. Zero wasted tokens."
    )

    opts_line = " | ".join([f"({k}) {v}" for k, v in sorted(options.items()) if v])
    prompt = f"""Question: {question_text}
Options: {opts_line}
Correct Answer: Option ({correct_answer}) -> {correct_opt_text}

Provide the 3 short bullet points now."""

    models_to_try = []
    for m in [model_name, "gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-2.5-flash"]:
        if m and m not in models_to_try:
            models_to_try.append(m)

    last_error = ""
    for m in models_to_try:
        try:
            config = types.GenerateContentConfig(
                max_output_tokens=800,
                temperature=0.2,
                system_instruction=system_instruction
            )
            response = client.models.generate_content(
                model=m,
                contents=prompt,
                config=config
            )
            raw_text = response.text.strip() if response.text else ""
            cleaned_text = clean_gemini_output(raw_text)
            if cleaned_text:
                return {
                    "success": True,
                    "source": "gemini",
                    "model": m,
                    "content": cleaned_text,
                    "solved_correct_answer": solved_ans
                }
        except Exception as err:
            last_error = str(err)
            err_lower = last_error.lower()
            if "api_key_invalid" in err_lower or "400" in err_lower or "not valid" in err_lower:
                break
            if "nodename nor servname" in err_lower or "errno 8" in err_lower or "connecterror" in err_lower:
                # Network is completely disconnected; break immediately to avoid repeated socket timeouts
                break
            # On 429 quota exhaustion or 503 unavailable on one model (e.g. gemini-2.5-flash daily limit),
            # seamlessly try next available model in fallback chain:
            continue

    if "nodename nor servname" in last_error or "ConnectError" in last_error or "Errno 8" in last_error:
        user_friendly_error = "Internet / Network Disconnected: Google Gemini server se DNS/Network connect nahi ho pa raha hai."
        err_source = "offline"
    elif "ascii" in last_error.lower() and "encode" in last_error.lower():
        user_friendly_error = "API Key Unicode Error: API Key me invisible characters copy ho gaye the. Key sanitize kar di gayi hai, dobara try karein."
        err_source = "error"
    elif "API_KEY_INVALID" in last_error or "400" in last_error or "API key not valid" in last_error:
        user_friendly_error = "Invalid API Key: Kripya sidebar me sahi Gemini API Key dalein."
        err_source = "error"
    elif "RESOURCE_EXHAUSTED" in last_error or "429" in last_error:
        user_friendly_error = "Google Quota Exceeded (429): Google AI Studio rate limit reach ho gayi hai. Model switch karein ya 1 minute baad try karein."
        err_source = "error"
    elif "503" in last_error or "unavailable" in last_error.lower():
        user_friendly_error = "Google Server Busy (503): Google Gemini par temporary traffic spike hai. Kripya 5 second baad dobara try karein."
        err_source = "error"
    else:
        user_friendly_error = last_error
        err_source = "error"

    return {
        "success": False,
        "source": err_source,
        "error_msg": user_friendly_error,
        "content": f"💡 Correct Option ({correct_answer}) — {correct_opt_text}. {existing_explanation}"
    }
