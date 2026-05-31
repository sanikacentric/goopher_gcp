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

# Tiny stopword fingerprints for common languages — good enough to pick a
# starting language without a heavyweight dependency. The LLM refines from here.
_FINGERPRINTS = {
    "es": {"hola", "gracias", "pedido", "vestido", "dónde", "está", "cuánto", "tengo", "quiero"},
    "fr": {"bonjour", "merci", "commande", "robe", "où", "combien", "je", "veux"},
    "de": {"hallo", "danke", "bestellung", "kleid", "wo", "wieviel", "ich", "möchte"},
    "pt": {"olá", "obrigado", "pedido", "vestido", "onde", "quanto", "quero"},
    "hi": {"नमस्ते", "धन्यवाद", "ऑर्डर", "कहाँ", "कितना"},
    "zh": {"你好", "谢谢", "订单", "连衣裙", "多少", "在哪里"},
}

SUPPORTED = ["en", "es", "fr", "de", "pt", "hi", "zh"]


def detect_language(text: str, default: str = "en") -> str:
    """Heuristically detect language from a short message."""
    if not text:
        return default
    lowered = text.lower()
    scores: dict[str, int] = {}
    for lang, words in _FINGERPRINTS.items():
        scores[lang] = sum(1 for w in words if w in lowered)
    best = max(scores, key=scores.get) if scores else default
    return best if scores.get(best, 0) > 0 else default


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
