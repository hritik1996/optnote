"""
High-Yield Exam Trap & Rule Exception Detection Engine.
Automatically identifies tricky, high-frequency, and rule-exception questions
from competitive exam PDFs (SSC CGL, UPSC, Banking, Defence, State PSC).
"""

import re
from typing import Dict, Any, List

EXAM_TRAP_CATEGORIES = [
    {
        'id': 'spelling_double_consonant',
        'title': 'Double-Consonant Trap (दोहरे अक्षर की गलती)',
        'pattern': r'\b\w*(?:cc|mm|rr|ss|ll|nn|pp|bb|tt|gg|ff)\w*\b',
        'keywords': [
            'accommodat', 'embarrass', 'harass', 'millennium', 'occurren',
            'committ', 'belliger', 'supercili', 'possess', 'assassin',
            'exaggerat', 'recommend', 'vaccin', 'parallel', 'bureaucra',
            'manoeuv', 'gauge', 'queue', 'grotesque', 'salubrious',
            'equanimity', 'otorhino', 'avert', 'ineffable', 'inscrutable'
        ],
        'weight': 35,
        'badge': '🔥 EXAM TRAP: Double Consonant'
    },
    {
        'id': 'spelling_ie_ei_exception',
        'title': 'IE vs EI Rule Exception ("i before e except after c" का अपवाद)',
        'pattern': r'\b\w*(?:cei|cie|wei|eig|eiv|iev|eigh|iege|leisur|hygie|soverei)\w*\b',
        'keywords': [
            'weird', 'foreign', 'seize', 'sovereign', 'forfeit', 'surfeit',
            'counterfeit', 'receipt', 'deceive', 'perceive', 'conceive',
            'leisure', 'hygiene', 'neighbour', 'weight', 'grief', 'yield'
        ],
        'weight': 40,
        'badge': '⚡ RULE EXCEPTION: IE/EI Rule'
    },
    {
        'id': 'silent_letter_greek_root',
        'title': 'Silent Letter / Greek-Latin Root (साइलेंट लेटर / कठिन रूट वर्ड)',
        'pattern': r'\b(?:pneu|psyc|kn|gn|wr|rh|otorh|rhythm|rhyme|collea|privil|maint|sepa|mischi|connois|sovereig|lieuten)\w*\b',
        'keywords': [
            'pneumonia', 'psychology', 'otorhinolaryngology', 'rhythm',
            'pterodactyl', 'lieutenant', 'colleague', 'privilege',
            'maintenance', 'separate', 'mischievous', 'connoisseur',
            'sovereignty', 'rhinitis', 'rhetoric', 'indispensable'
        ],
        'weight': 35,
        'badge': '🎯 HIGH-FREQUENCY REPEAT: Silent Root'
    },
    {
        'id': 'grammar_preposition_exception',
        'title': 'Grammar & Preposition Exception (फिक्स्ड प्रीपोजिशन अपवाद)',
        'pattern': r'\b(?:prefer\w*\s+to|senior\s+to|junior\s+to|superior\s+to|inferior\s+to|prior\s+to|lest|hardly|scarcely|no\s+sooner|prohibit|prevent\s+from|refrain\s+from|abstain\s+from)\b',
        'keywords': [
            'preferable', 'lest', 'hardly', 'scarcely', 'no sooner',
            'prevent from', 'furnitures', 'sceneries', 'informations', 'luggages', 'advices', 'prohibit'
        ],
        'weight': 40,
        'badge': '⚡ GRAMMAR EXCEPTION: Fixed Prep'
    },
    {
        'id': 'science_gk_exception',
        'title': 'Static GK / Science Anomaly (साइंस व जीके के खास अपवाद)',
        'pattern': r'\b(?:mercury|bromine|amphoteric|inert|noble\s+gas|universal\s+donor|article\s+2[01]|joint\s+sitting|tropic\s+of\s+cancer|fundamental\s+rights?|dpsp|cornea|enamel)\b',
        'keywords': [
            'mercury', 'bromine', 'amphoteric', 'noble gas', 'universal donor',
            'article 20', 'article 21', 'joint sitting', 'dpsp', 'cornea',
            'insuling', 'pancreas', 'baking soda', 'sodium bicarbonate'
        ],
        'weight': 40,
        'badge': '🏆 HIGH-YIELD GK: Science Anomaly'
    }
]

def analyze_exam_trap(question_text: str, options: Dict[str, str]) -> Dict[str, Any]:
    """
    Analyzes a question and its options to determine if it belongs to
    high-frequency exam trap categories or rule exceptions.
    Prevents false positives on general MCQs (e.g. computer/science terms with double letters).
    """
    text_corpus = (question_text + " " + " ".join(options.values())).lower()
    
    # Check if question is an actual spelling test question
    is_spelling_context = bool(re.search(r'\b(spelt|spelling|misspelt|spell|correctly spelt|incorrectly spelt)\b', text_corpus))

    matched_titles = []
    total_score = 0
    top_badge = None
    top_reason = None

    for cat in EXAM_TRAP_CATEGORIES:
        has_kw = any(kw in text_corpus for kw in cat['keywords'])
        has_regex = False

        # For spelling-based traps (double consonant, ie/ei, silent roots),
        # only match generic regex if it's an actual spelling question or if explicit keywords match
        if cat['id'] in ['spelling_double_consonant', 'spelling_ie_ei_exception', 'silent_letter_greek_root']:
            if has_kw or (is_spelling_context and bool(re.search(cat['pattern'], text_corpus))):
                has_regex = True
        else:
            has_regex = bool(re.search(cat['pattern'], text_corpus))

        if has_kw or has_regex:
            matched_titles.append(cat['title'])
            total_score += cat['weight']
            if not top_badge:
                top_badge = cat['badge']
                top_reason = cat['title']

    is_trap = (total_score >= 35) or (len(matched_titles) >= 1)
    
    return {
        "is_trap": is_trap,
        "score": min(total_score, 100),
        "badge": top_badge if is_trap else None,
        "reason": top_reason if is_trap else "Standard Practice Question",
        "categories": matched_titles
    }
