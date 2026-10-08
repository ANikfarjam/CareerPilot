"""
Chat that edits a saved resume draft (db/models.py ResumeDraft) on the user's request.

How it works:
  One LLM call per message, streamed token by token.
    1. `select_context()` (agents/resume_builder/context.py) picks the MCP-style
       resources the message needs: the draft docs and posting always, plus the
       knowledge-base sections and project write-ups the message mentions.
    2. The model gets CHAT_PROMPT with those resources, the last HISTORY_TURNS
       chat messages and the new message. It replies with a short answer and,
       only for the docs it changes, the full revised doc in a ```resume or
       ```side_projects block (full replacement: more reliable than patches).
    3. `stream_chat()` turns the token stream into events:
         {"type": "status", "state": "thinking"}   gpt-oss is in its analysis channel
         {"type": "token", "target": "chat" | "resume" | "side_projects", "text"}
         {"type": "result", "reply", "resume"?, "side_projects"?, "drive"?}   last event;
         a doc edit that guards.review_edit rejects (only part of the doc, or chat text) is
         moved into the reply instead of replacing the doc;
         drive lists the docs the reply asked to export to Google Drive (agents/resume_builder/drive.py)
       The analysis channel is never sent: Ollama streams it as reasoning
       (chunk.text stays empty), so tokens flow once the final answer starts.

Orchestration:
  WS /agents/resume/drafts/{draft_id}/chat (apis/reposetories/agents.py) runs
  `stream_chat` and saves the result with db.dbOps.update_draft.
"""

import re
from typing import Iterator

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.resume_builder.context import render_context, select_context
from agents.resume_builder.guards import check_fits, message_tokens, review_edit
from agents.utils.langchainConfig import PROMPT_BUDGET_TOKENS

HISTORY_TURNS = 6  # chat messages (user + assistant) sent back to the model
DOC_TARGETS = ("resume", "side_projects")
FENCE_OPEN = re.compile(r"^```(resume|side_projects|drive)\s*$")
FENCE_CLOSE = re.compile(r"^```\s*$")

CHAT_PROMPT = """You are a resume editor. The candidate already has a resume and side-project ideas
tailored to one job posting, and asks you to change them.

Rules:
- Use only facts from the resources below (the knowledge base, project write-ups, the current
  docs). Never invent experience, employers, titles, dates, degrees, skills or metrics. If the
  candidate asks for something the resources don't support, say so instead of making it up.
- Keep the layout of the current docs; keep the resume to one page.
- Change only what the candidate asks for.
- A doc block replaces the WHOLE doc. It must hold every section of that doc, including the
  ones you didn't change. Never put only the changed part, a single section or a few bullets
  in a doc block: that would delete the rest of the doc.
- If the candidate asks to see, draft or suggest just one part (a section, some bullets, a
  summary) without asking to put it in the doc, write that part in your reply, not in a block.
- Never put conversation, questions, explanations or placeholders like [Your Name] in a doc
  block: it holds only the document itself.
- If a request needs facts the resources don't have (years of experience, metrics, dates,
  employers), say what's missing in your reply and leave the doc as it is; never guess.

Reply format:
1. One to three sentences to the candidate: what you changed, or your answer if they only asked
   a question.
2. Only if you changed a doc, the full revised doc in a fenced block tagged with its name, with
   nothing after it:
```resume
<the whole revised resume in Markdown>
```
```side_projects
<the whole revised side-project ideas in Markdown>
```
Leave out the block of a doc you didn't change.
3. Only if the candidate asks to export, save or upload docs to Google Drive, end with a drive
   block listing the docs to export, one per line (resume, side_projects); the app uploads them
   after your reply and adds the links, so don't write any links yourself:
```drive
resume
```

Resources:
{context}"""


class _Router:
    """Splits the final channel into chat text and fenced doc blocks as it streams in.
    A ```drive block (the docs to export to Google Drive) is collected but never streamed.

    A line is held back until it is clearly not a fence (doesn't start with "`") or is complete,
    so fence lines are never sent as tokens."""

    def __init__(self):
        self.target = "chat"
        self.parts = {"chat": [], "resume": [], "side_projects": [], "drive": []}
        self.seen = set()  # doc targets that had a block
        self.line = ""  # the current, incomplete line
        self.line_sent = False  # part of self.line already went out as a token
        self.sent_len = 0  # how much of self.line went out

    def _emit(self, text: str) -> Iterator[dict]:
        if text:
            self.parts[self.target].append(text)
            if self.target != "drive":
                yield {"type": "token", "target": self.target, "text": text}

    def _finish_line(self, line: str) -> Iterator[dict]:
        if not self.line_sent:
            if self.target == "chat" and (m := FENCE_OPEN.match(line.strip())):
                self.target = m.group(1)
                self.seen.add(self.target)
                return
            if self.target != "chat" and FENCE_CLOSE.match(line.strip()):
                self.target = "chat"
                return
            yield from self._emit(line + "\n")
        else:
            yield from self._emit(line[self.sent_len:] + "\n")

    def feed(self, text: str) -> Iterator[dict]:
        for piece in re.split(r"(\n)", text):
            if piece == "\n":
                yield from self._finish_line(self.line)
                self.line, self.line_sent = "", False
            elif piece:
                self.line += piece
                if self.line_sent:
                    yield from self._emit(piece)
                    self.sent_len = len(self.line)
                elif not self.line.lstrip().startswith("`"):
                    yield from self._emit(self.line)
                    self.line_sent, self.sent_len = True, len(self.line)

    def close(self) -> Iterator[dict]:
        if self.line:
            if self.line_sent:
                yield from self._emit(self.line[self.sent_len:])
            elif not (FENCE_OPEN.match(self.line.strip()) or FENCE_CLOSE.match(self.line.strip())):
                yield from self._emit(self.line)
        self.line = ""

    def result(self) -> dict:
        out = {"type": "result", "reply": "".join(self.parts["chat"]).strip()}
        for target in DOC_TARGETS:
            doc = "".join(self.parts[target]).strip()
            if target in self.seen and doc:
                out[target] = doc
        drive = [t for t in re.findall(r"\w+", "".join(self.parts["drive"])) if t in DOC_TARGETS]
        if drive:
            out["drive"] = list(dict.fromkeys(drive))
        return out


# Complementary prompt: repeated after every message (never saved to the history), because a
# long context makes the local model drift from the system prompt's rules.
GUARD_REMINDER = """

---
(Reminder from the app, not the candidate: answer in one to three sentences. A ```resume or
```side_projects block must contain the WHOLE revised doc with every section, or leave the block
out; put a single section or a few bullets you're showing in the reply instead. Use only facts
from the resources; never guess or use placeholders.)"""


def build_messages(draft: dict, job: dict, message: str) -> list:
    """System prompt with the selected resources, the recent chat history, then the new message
    with GUARD_REMINDER. Drops the oldest history turns if the prompt wouldn't fit the context;
    PromptTooLong if it still doesn't."""
    system = SystemMessage(CHAT_PROMPT.format(context=render_context(select_context(message, draft, job))))
    history = [HumanMessage(m["content"]) if m["role"] == "user" else AIMessage(m["content"])
               for m in draft["messages"][-HISTORY_TURNS:]]
    latest = HumanMessage(message + GUARD_REMINDER)
    while history and message_tokens([system, *history, latest]) > PROMPT_BUDGET_TOKENS:
        history = history[1:]
    messages = [system, *history, latest]
    check_fits(messages, "chat", hint="Ask about fewer things at once, or clear the chat.")
    return messages


def apply_guards(result: dict, draft: dict, message: str) -> dict:
    """Drops doc edits that review_edit rejects (only part of the doc, or chat text), so they
    don't overwrite the draft, and shows that text in the reply instead."""
    for target, label in (("resume", "resume"), ("side_projects", "side projects")):
        if target not in result:
            continue
        reason = review_edit(draft[target], result[target], message)
        if reason:
            text = result.pop(target)
            result["reply"] += (f"\n\n*I didn't apply this to your {label}, because {reason}. "
                                f"Here it is so you can copy what you need:*\n\n{text}")
    return result


def stream_chat(model: BaseChatModel, draft: dict, job: dict, message: str) -> Iterator[dict]:
    """Streams the reply to one chat message as status/token events, ending with a result event.

    draft is a db.dbOps.get_draft dict (its messages are the history); job is a load_job dict."""
    router = _Router()
    writing = False
    yield {"type": "status", "state": "thinking"}
    for chunk in model.stream(build_messages(draft, job, message)):
        text = chunk.text
        if not writing:
            text = text.lstrip()
            if not text:  # still reasoning
                continue
            writing = True
            yield {"type": "status", "state": "writing"}
        yield from router.feed(text)
    yield from router.close()
    yield apply_guards(router.result(), draft, message)
