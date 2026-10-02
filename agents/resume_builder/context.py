"""
Context for the resume chat, laid out like MCP resources: each piece of the
candidate's background or the current draft has a URI, a name and a reader.

  draft://resume            the draft's current resume (Markdown)
  draft://side_projects     the draft's current side-project ideas (Markdown)
  job://posting             the job the draft is tailored to (load_job)
  kb://section/<slug>       one "###" subsection of Docs/user_docs/user_knowledge.md
                            (or a "##" section that has none)
  project://<name>          the full write-up in Docs/user_docs/projects/<name>/*.md

The local model can't emit native tool calls, so instead of letting it ask for
resources (one extra generation per call), `select_context()` picks them on the
server by matching the user's message against each resource's name and text.
The chat then needs one LLM call per message, and the prompt carries only the
background the message is about instead of the whole ~40KB knowledge base.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from agents.qualification_check.agent import KNOWLEDGE_FILE, load_knowledge
from agents.resume_builder.agent import PROJECTS_DIR, TASK_PROMPT

# KB sections sent with every message: contact details and the skills inventory.
ALWAYS_SECTIONS = ("profile", "skills")
MAX_CONTEXT_CHARS = 24000  # matched kb/project resources; the draft and posting are always sent
MAX_MATCHES = 6

STOPWORDS = set("""
a an and are as at be but by can could do for from have how i in into is it its make me
mention more my of on or our please remove section should so than that the their them then
there these this to up use want was what when where which with would you your add change
rewrite shorter longer bullet bullets resume project projects side job about also just
""".split())


@dataclass
class Resource:
    """One MCP-style resource the chat can draw on."""
    uri: str
    name: str
    description: str
    read: Callable[[], str]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _kb_sections(knowledge_file: Path = KNOWLEDGE_FILE) -> list[tuple[str, str]]:
    """(title, text) per "###" subsection of the knowledge base, titled "<section> / <sub>";
    a "##" section without subsections is one entry. Text before the first "##" is dropped."""
    sections = []
    for block in re.split(r"(?m)^## ", load_knowledge(knowledge_file))[1:]:
        heading, _, body = block.partition("\n")
        heading = re.sub(r"^\d+\.\s*", "", heading).strip()
        subs = re.split(r"(?m)^### ", body)
        if len(subs) == 1:
            sections.append((heading, f"## {heading}\n{body.strip()}"))
            continue
        for sub in subs[1:]:
            sub_heading, _, sub_body = sub.partition("\n")
            sub_heading = re.sub(r"^\d+(\.\d+)*\s*", "", sub_heading).strip()
            sections.append((f"{heading} / {sub_heading}", f"### {heading} / {sub_heading}\n{sub_body.strip()}"))
    return sections


def _projects(projects_dir: Path = PROJECTS_DIR) -> list[tuple[str, Path]]:
    """(name, path) per projects/<name>/*.md, the same files load_projects() reads."""
    return [(path.parent.name, path) for path in sorted(projects_dir.glob("*/*.md"))]


def list_resources(draft: dict, job: dict) -> list[Resource]:
    """Every resource for one draft: the draft docs, its posting, the KB sections and projects."""
    resources = [
        Resource("draft://resume", "Current resume", "The resume being edited", lambda: draft["resume"]),
        Resource("draft://side_projects", "Current side projects", "The side-project ideas being edited",
                 lambda: draft["side_projects"]),
        Resource("job://posting", f"{job['position']} @ {job['company_name']}", "The job posting",
                 lambda: TASK_PROMPT.format(**job)),
    ]
    for title, text in _kb_sections():
        resources.append(Resource(f"kb://section/{_slug(title)}", title, "Knowledge base section",
                                  lambda text=text: text))
    for name, path in _projects():
        resources.append(Resource(f"project://{name}", name, "Full project write-up",
                                  lambda path=path: path.read_text().strip()))
    return resources


def _keywords(message: str) -> set[str]:
    words = re.findall(r"[a-z0-9+#.]+", message.lower())
    return {w.strip(".") for w in words if len(w.strip(".")) >= 3 and w.strip(".") not in STOPWORDS}


def _score(resource: Resource, keywords: set[str]) -> int:
    """Name hits count 5x body hits, so "StockMarket" picks the project over a passing mention."""
    name = resource.name.lower().replace(" ", "")
    name_words = set(re.findall(r"[a-z0-9+#.]+", resource.name.lower()))
    body = resource.read().lower()
    return sum(5 * (k in name_words or k in name) + (k in body) for k in keywords)


def select_context(message: str, draft: dict, job: dict, max_chars: int = MAX_CONTEXT_CHARS) -> list[Resource]:
    """Resources to send with one chat message: the draft docs and posting, the ALWAYS_SECTIONS,
    then the best-matching KB sections and projects (at most MAX_MATCHES, within max_chars)."""
    resources = list_resources(draft, job)
    fixed = [r for r in resources if r.uri.startswith(("draft://", "job://"))
             or any(r.uri.startswith(f"kb://section/{s}") for s in ALWAYS_SECTIONS)]
    candidates = [r for r in resources if r not in fixed]

    keywords = _keywords(message)
    scored = sorted(((_score(r, keywords), r) for r in candidates), key=lambda x: -x[0])
    picked, used = [], 0
    for score, resource in scored:
        if score == 0 or len(picked) == MAX_MATCHES:
            break
        size = len(resource.read())
        if used + size > max_chars:
            continue
        picked.append(resource)
        used += size
    return fixed + picked


def render_context(resources: list[Resource]) -> str:
    """The selected resources as one prompt section, each under its URI."""
    return "\n\n".join(f"<resource uri=\"{r.uri}\" name=\"{r.name}\">\n{r.read()}\n</resource>"
                       for r in resources)
