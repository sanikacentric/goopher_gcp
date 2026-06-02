"""
Multi-lingual Subagent (Requirement 2A-5).

Responsibilities:
  * Detect the language of an incoming message.
  * Ensure the final reply is in the customer's preferred / detected language.

It exposes two helpers used by the orchestrator and is ALSO registered as an
ADK sub-agent so the LLM can delegate translation explicitly when needed.

Detection is dependency-light: it uses a fast heuristic, then defers to the LLM
for anything ambiguous (the orchestrator already has Gemini available).
"""
from __future__ import annotations

import re

# Tiny stopword fingerprints for common languages — good enough to pick a
# starting language without a heavyweight dependency. The LLM refines from here.
#
# IMPORTANT: matching is done on WHOLE WORDS (see detect_language), so these are
# only distinctive tokens. We deliberately avoid ultra-short ambiguous tokens
# (e.g. "je", "o", "wo") because, even with word matching, they collide with
# product/English text ("Jessica" -> would have matched "je" under substring
# matching, which caused a French misdetection bug).
_FINGERPRINTS = {
    # English function words — so a clearly-English message returns "en" even
    # when the session's remembered language is something else (otherwise the
    # remembered language would "stick" because English had no positive signal).
    "en": {"the", "you", "what", "is", "are", "do", "does", "have", "want",
           "where", "show", "please", "can", "could", "would", "order", "buy",
           "place", "your", "with", "how", "much", "this", "that", "above",
           "give", "need", "and", "of", "in", "stock", "price", "available",
           "yes", "no", "it", "them", "cookies", "dress"},
    "es": {"hola", "gracias", "pedido", "vestido", "dónde", "está", "cuánto",
           "tengo", "quiero", "mi", "el", "la", "para", "cuál", "precio"},
    "fr": {"bonjour", "merci", "commande", "robe", "où", "combien", "veux",
           "bonsoir", "prix", "quel", "ma", "mon", "s'il"},
    "de": {"hallo", "danke", "bestellung", "kleid", "wieviel", "ich", "möchte",
           "wo", "preis", "mein", "wie"},
    "pt": {"olá", "obrigado", "pedido", "vestido", "onde", "quanto", "quero",
           "meu", "preço", "qual"},
    "hi": {"नमस्ते", "धन्यवाद", "ऑर्डर", "कहाँ", "कितना", "मेरा", "है"},
    "zh": {"你好", "谢谢", "订单", "连衣裙", "多少", "在哪里", "价格"},
}

SUPPORTED = ["en", "es", "fr", "de", "pt", "hi", "zh"]

# Unicode script ranges that are an unambiguous signal on their own.
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_CJK = re.compile(r"[一-鿿]")
# Word tokenizer that keeps accented Latin letters together as one word.
_WORD_RE = re.compile(r"[a-zA-ZÀ-ÿऀ-ॿ一-鿿']+")


def detect_language(text: str, default: str = "en") -> str:
    """
    Heuristically detect the language of a short message.

    Strategy:
      1. Non-Latin scripts (Devanagari, CJK) are decisive — return immediately.
      2. Otherwise tokenize into WHOLE words and count distinctive-word hits per
         language. Whole-word matching avoids false positives like "je" inside
         "Jessica" or "o"/"wo" inside ordinary English.
      3. A single hit isn't enough to override English unless it's an accented
         word (a strong signal), to keep plain-English product queries as "en".
    """
    if not text:
        return default

    # 1) Script-based shortcuts.
    if _DEVANAGARI.search(text):
        return "hi"
    if _CJK.search(text):
        return "zh"

    lowered = text.lower()
    words = set(_WORD_RE.findall(lowered))
    has_accent = bool(re.search(r"[à-ÿ]", lowered))

    scores: dict[str, int] = {}
    for lang, vocab in _FINGERPRINTS.items():
        scores[lang] = len(words & vocab)

    # English is the safe baseline: if the message carries a clear English signal
    # AND no other language scores higher, return "en". This stops a remembered
    # non-English session language from "sticking" when the shopper switches back
    # to English (English otherwise has no positive signal to override it).
    en_score = scores.get("en", 0)
    non_en = {k: v for k, v in scores.items() if k != "en"}
    best_other = max(non_en, key=non_en.get) if non_en else default
    best_other_score = non_en.get(best_other, 0)
    if en_score >= 1 and en_score >= best_other_score:
        return "en"

    # Otherwise: require 2+ matching words, or 1 match that carries an accent —
    # a lone common token shouldn't flip a sentence to another language.
    if best_other_score >= 2 or (best_other_score == 1 and has_accent):
        return best_other
    return default


def language_directive(language: str) -> str:
    """Instruction fragment that forces the model to answer in `language`."""
    names = {
        "en": "English", "es": "Spanish", "fr": "French", "de": "German",
        "pt": "Portuguese", "hi": "Hindi", "zh": "Chinese",
    }
    name = names.get(language, "English")
    return f"Respond ENTIRELY in {name}. Keep product/brand names as-is."


def build_adk_agent(model: str):
    """Optional: an ADK LlmAgent specialized for translation/localization."""
    from google.adk.agents import LlmAgent  # lazy import

    return LlmAgent(
        name="language_agent",
        model=model,
        description="Detects language and localizes replies for multi-lingual shoppers.",
        instruction=(
            "You are the localization specialist. Given a draft reply and a target "
            "language, return the reply faithfully translated into that language, "
            "preserving prices, SKUs, and brand names verbatim."
        ),
    )
