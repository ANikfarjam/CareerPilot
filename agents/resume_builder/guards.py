"""
Safeguards around the resume builder and the resume chat, so a bad model reply can't silently
replace the user's documents.

  Input:  `check_fits` refuses a prompt that would overflow the model's context. Ollama doesn't
          error on an oversized prompt: it cuts it from the front, dropping the system prompt and
          the candidate's background, and the model then answers without them (asks for the
          resume, or invents experience to fill the gaps).
  Output: `check_built_doc` rejects a build that isn't a document (e.g. a question back to the
          user); `review_edit` rejects a chat edit that holds only part of the document or reads
          like a chat reply, so it's shown in the chat instead of overwriting the doc.

Used by agents/resume_builder/agent.py (build) and agents/resume_builder/chat.py (chat).
"""

import re

from langchain_core.messages import BaseMessage

from agents.utils.langchainConfig import PROMPT_BUDGET_TOKENS

# gpt-oss averages ~4.6 characters per token on the knowledge-base prompts; 4 leaves a margin.
CHARS_PER_TOKEN = 4
HEADING = re.compile(r"(?m)^#{1,4}\s+\S")
CHAT_OPENERS = re.compile(r"^(sure|certainly|of course|i('|’)d|i would|i can|i('|’)ll|could you|can you|please|"
                          r"here('|’)s|here is|thanks|great|absolutely)\b", re.I)
# Asking for these lets an edit drop sections or most of the text.
SHRINK_WORDS = re.compile(r"\b(remove|delete|drop|cut|shorten|shorter|trim|condense|get rid|only keep|keep only|"
                          r"one[- ]page|fewer|less)\b", re.I)
MIN_KEPT_SECTIONS = 0.6  # an edit must keep this share of the doc's headings (unless asked to shrink it)
MIN_KEPT_CHARS = 0.4  # ... and of its length, even when asked to shrink it


class PromptTooLong(ValueError):
    """The prompt wouldn't fit in the model's context, so it would be truncated."""


def estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN + 1


def message_tokens(messages: list[BaseMessage]) -> int:
    return sum(estimate_tokens(m.text) for m in messages)


def check_fits(messages: list[BaseMessage], what: str, hint: str = "") -> None:
    """Raises PromptTooLong if messages exceed PROMPT_BUDGET_TOKENS (NUM_CTX minus the output)."""
    used = message_tokens(messages)
    if used > PROMPT_BUDGET_TOKENS:
        raise PromptTooLong(f"The {what} prompt is too long for the model (~{used:,} tokens, "
                            f"limit {PROMPT_BUDGET_TOKENS:,}), so it would lose your background. {hint}".strip())


def _headings(text: str) -> int:
    return len(HEADING.findall(text))


def _looks_like_chat(text: str) -> bool:
    """A conversational reply rather than a document: no headings and a chat-style opener or a
    closing question."""
    stripped = text.strip()
    return _headings(stripped) == 0 and (bool(CHAT_OPENERS.match(stripped)) or stripped.endswith("?"))


def check_built_doc(text: str, name: str) -> str:
    """The builder's output if it is a Markdown document; ValueError if the model answered with
    something else (empty, a question, a chat reply without any headings)."""
    if not text.strip() or _looks_like_chat(text) or _headings(text) == 0:
        preview = re.sub(r"\s+", " ", text.strip())[:160]
        raise ValueError(f"The model didn't return a {name} (it said: \"{preview}\"). Nothing was saved; try again.")
    return text


def review_edit(old: str, new: str, request: str) -> str | None:
    """Why a chat edit replacing old with new should NOT be applied, or None if it looks like a
    whole revised document. Catches the model returning only the part it changed, or chat text."""
    if _looks_like_chat(new):
        return "it was a chat reply, not the document"
    if not old.strip():
        return None
    shrink = bool(SHRINK_WORDS.search(request))
    old_sections, new_sections = _headings(old), _headings(new)
    if old_sections >= 2 and new_sections < old_sections * MIN_KEPT_SECTIONS and not shrink:
        return f"it kept only {new_sections} of the document's {old_sections} sections"
    if len(new) < len(old) * MIN_KEPT_CHARS:
        return f"it was only {len(new) * 100 // len(old)}% as long as the document"
    return None
