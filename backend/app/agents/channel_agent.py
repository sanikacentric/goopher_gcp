"""
Multi-channel Subagent (Requirement 2A-4: Phone + Web).

Different channels need different response shaping:
  * web   — can use markdown, bullet lists, links, emoji; richer formatting.
  * phone — voice/IVR: short sentences, no markdown/URLs, spell out details,
            offer to text a link instead of reading it aloud.

The orchestrator asks this subagent for a channel "style directive" that is
injected into the prompt, and (optionally) post-processes the reply for phone.
"""
from __future__ import annotations

import re


def channel_directive(channel: str) -> str:
    """Return a prompt fragment tailoring tone/format to the channel."""
    if channel == "phone":
        return (
            "CHANNEL=PHONE (voice). Reply in short, clear spoken sentences. "
            "Do NOT use markdown, bullet points, emoji, or raw URLs. Read prices "
            "and dates naturally (e.g. 'twenty-nine ninety-nine'). Offer to text "
            "a tracking link rather than reading it digit by digit."
        )
    return (
        "CHANNEL=WEB. You may use concise markdown: short bullet lists for "
        "product options, bold for prices, and clickable links where helpful."
    )


_MD_PATTERNS = [
    (re.compile(r"[*_`#>]+"), ""),          # strip markdown markers
    (re.compile(r"\[(.*?)\]\((.*?)\)"), r"\1"),  # links -> link text only
    (re.compile(r"\n{2,}"), " "),            # collapse blank lines
    (re.compile(r"\s{2,}"), " "),            # collapse whitespace
]


def adapt_for_phone(reply: str) -> str:
    """Best-effort cleanup so a web-style reply is safe to speak over IVR."""
    out = reply
    for pattern, repl in _MD_PATTERNS:
        out = pattern.sub(repl, out)
    return out.strip()


def build_adk_agent(model: str):
    from google.adk.agents import LlmAgent  # lazy import

    return LlmAgent(
        name="channel_agent",
        model=model,
        description="Adapts reply formatting/tone for the web or phone channel.",
        instruction=(
            "You shape responses for the active channel. For phone, produce "
            "voice-friendly text with no markdown or URLs. For web, allow light "
            "markdown formatting."
        ),
    )
