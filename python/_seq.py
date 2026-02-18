# _seq.py (was: matcher_engine.py — renamed for obfuscation)
# ================================================================
# String Matching Engine — STAYS AS .py (NOT compiled to .pyd)
#
# v5.9.25 (2026-02-08) — 3-AI Consensus (Antigravity + Grok + AI Studio)
#
# WHY THIS FILE EXISTS:
#   difflib.SequenceMatcher uses Python's C-API for string comparison.
#   When compiled to .pyd via Cython, Unicode string concatenation
#   (collected += " " + word) creates C-String objects that conflict
#   with SequenceMatcher's expected Python Unicode Objects.
#   Result: Segfault (silent crash) on Japanese/Chinese text.
#
# WHAT'S EXPOSED:
#   ~90 lines of string matching logic — LOW commercial value.
#   Competitor sees: "difflib.SequenceMatcher + ratio > 0.85"
#   They still can't replicate: AI pipeline, Ken Burns, subprocess orchestration.
#
# WHAT'S PROTECTED (in process_task.pyd):
#   1,170 lines of core algorithms — HIGH commercial value.
# ================================================================

from __future__ import annotations

import difflib
import gc
import re
from typing import List, Optional, Tuple


def _clean_text(text: str) -> str:
    """Normalize text for matching — remove punctuation, lowercase."""
    text = (text or "").lower()
    return re.sub(r"[.,\/#!$%\^&\*;:{}=\-_\`~()。、？「」…!]", "", text)


def _parse_script(content: str) -> List[Tuple[int, str]]:
    """Parse [V1] text format from script file."""
    pattern = r"\[[Vv](\d+)\]\s*([^\[]+)"
    return [(int(m[0]), m[1].strip()) for m in re.findall(pattern, content or "", re.DOTALL)]


def _match_words_to_script(
    all_words: List[dict],
    script_items: List[Tuple[int, str]],
    log_func=None,
) -> List[Tuple[int, float, float, str]]:
    """
    Match AI-detected words to script items using SequenceMatcher.

    3-AI Consensus Fix (Antigravity + AI Studio + Grok):
    - MAX_COLLECTED_LEN cap prevents SequenceMatcher C-level crash on long Unicode
    - gc.collect() between items prevents memory buildup
    - This function MUST stay in .py — crashes as .pyd on Japanese Unicode

    Returns:
        List of (vid, start_time, end_time, text) tuples
    """
    word_ptr = 0
    total_words = len(all_words)
    matches: List[Tuple[int, float, float, str]] = []

    # === 3-AI SAFETY LIMITS ===
    # SequenceMatcher.ratio() is O(N²) — on strings >5000 chars of Japanese Unicode,
    # it causes C-level stack overflow that kills the process silently.
    MAX_COLLECTED_LEN = 5000   # Cap: prevent SequenceMatcher segfault (AI Studio + Grok)
    GC_INTERVAL = 20           # gc.collect() every N items (Grok: prevent memory buildup)

    for item_idx, (vid, text) in enumerate(script_items):
        target = _clean_text(text)
        if not target:
            if log_func:
                log_func(f"⚠️ [V{str(vid).zfill(2)}] Skip - empty target")
            continue

        current_words: List[dict] = []
        collected = ""

        while word_ptr < total_words:
            w = all_words[word_ptr]
            if isinstance(w, dict):
                collected += " " + str(w.get("word", ""))
                current_words.append(w)
            word_ptr += 1

            # === SAFETY CAP (3-AI Consensus) ===
            # Prevent SequenceMatcher from receiving strings that crash at C level
            if len(collected) > MAX_COLLECTED_LEN:
                break

            if len(collected) < len(target) * 0.5:
                continue

            ratio = difflib.SequenceMatcher(
                None, _clean_text(collected), target
            ).ratio()
            if ratio > 0.85 or len(_clean_text(collected)) > len(target) + 20:
                break

        if not current_words:
            if log_func:
                log_func(f"⚠️ [V{str(vid).zfill(2)}] Skip - no valid words found")
            continue

        first_word = current_words[0]
        last_word = current_words[-1]
        if not isinstance(first_word, dict) or not isinstance(last_word, dict):
            if log_func:
                log_func(f"⚠️ [V{str(vid).zfill(2)}] Skip - invalid word type")
            continue

        s_time = float(first_word.get("start", 0))
        e_time = float(last_word.get("end", s_time + 0.1))
        matches.append((vid, s_time, e_time, text))

        # === GC BETWEEN ITEMS (3-AI Consensus) ===
        # Backup does this implicitly via FFmpeg I/O pauses; Phase E needs explicit gc
        if item_idx > 0 and item_idx % GC_INTERVAL == 0:
            gc.collect()

    return matches
