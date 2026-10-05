"""
This agent generate and update a knowledge base about user. The usere should drop their existing resume/s
and other suplement files such as: projects (.md or pdf), published papers (.md or pdf), achivements (competion achivements like hacketon).
so other agents can easily use the generated knowledgebase.md file loceted and also it adjust the portals yaml positives and negative and add or drop portals.

Where to drop files (under Docs/user_docs/, .md / .txt / .pdf):
    workexperience/    resumes
    education/         transcripts, degrees, certificates
    projects/<name>/   one folder per project (write-ups, reports)
    papers/            published papers
    achievements/      hackathons, competitions, awards
  Anything else under Docs/user_docs/ is read too, as "other". PDFs are converted
  with poppler's pdftotext (-layout keeps resumes' columns readable).

How it works:
  Not a LangGraph: the flow is linear, like resume_builder.
    1. `collect_documents()` reads every source file, grouped by the folders above.
    2. The current Docs/user_docs/user_knowledge.md is split into its "## " sections;
       each one is the previous version the model updates, so facts the user added
       by hand (or that came from documents since deleted) are kept.
    3. One LLM call per section (`write_section()`), each given only the document
       kinds that section is written from. Projects get one call per projects/<name>/
       folder plus one for projects only the resumes / old knowledge base mention.
       Section by section because num_predict (4096) is shared with gpt-oss's
       analysis channel and the whole knowledge base is longer than that.
    4. `write_quick_reference()` summarizes the compiled sections for qualification
       matching (strongest matches, gaps, experience level).
    5. The old file is copied to user_knowledge.prev.md and the new one written.
    6. `propose_portal_changes()` has the model compare the knowledge base to
       portals.yml's title_filter and tracked companies and reply with JSON;
       `apply_portal_changes()` edits portals.yml line by line so its comments
       survive (yaml.safe_dump would drop them). Dropped companies are set to
       `enabled: false`, not deleted.

Orchestration:
  - `run_knowledge_base(model)` does all of the above and returns
    {"knowledge_file", "knowledge", "documents", "portals"}.
  - Its output is read by qualification_check (KNOWLEDGE_FILE), resume_builder and
    portal_search (portals.yml).

Run it:
    python -m agents.knowledge_base.agent
    python -m agents.knowledge_base.agent --dry-run        # print, write nothing
    python -m agents.knowledge_base.agent --skip-portals   # leave portals.yml alone
"""

import argparse
import datetime
import json
import re
import shutil
import subprocess
from pathlib import Path

import yaml
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.portal_search.agent import PORTALS_FILE, _final_channel
from agents.qualification_check.agent import KNOWLEDGE_FILE, MAX_ATTEMPTS, _text

USER_DOCS_DIR = KNOWLEDGE_FILE.parent
PREVIOUS_FILE = KNOWLEDGE_FILE.with_suffix(".prev.md")
DOC_SUFFIXES = (".md", ".txt", ".pdf")
MAX_SOURCE_CHARS = 20000  # per document; long papers/transcripts are mostly references and boilerplate

# Document kind -> folder under Docs/user_docs.
FOLDERS = {
    "resumes": "workexperience",
    "education": "education",
    "projects": "projects",
    "papers": "papers",
    "achievements": "achievements",
}
KINDS = (*FOLDERS, "other")

# Kind -> (label, what to drop there): the setup guide on the knowledge base page.
FOLDER_GUIDE = {
    "resumes": ("Resumes", "Your resumes. Several versions are fine; where they disagree the newest wins."),
    "education": ("Education", "Transcripts, diplomas and certificates (e.g. CCNA)."),
    "projects": ("Projects", "One folder per project (projects/<name>/) with its write-up. "
                             "Images and other files in it are ignored."),
    "papers": ("Published papers", "Papers you wrote or co-wrote."),
    "achievements": ("Achievements", "Hackathons, competition results, awards and scholarships."),
    "other": ("Other", "Anything else placed directly in Docs/user_docs, e.g. a bio or a LinkedIn export."),
}

PROJECTS = "Projects"
QUICK_REFERENCE = "Quick Reference for Qualification Matching"

# (heading, what the section holds, document kinds it is written from), in file order.
# Projects is written per project (see write_projects) and slotted in after Skills.
SECTIONS = [
    ("Profile & Contact",
     "a table of name, location, phone, email, LinkedIn, GitHub, portfolio, current role, highest "
     "degree and enrollment status; then a **Summary:** paragraph (2-3 sentences) and a "
     "**Main areas:** line",
     ("resumes", "education", "other")),
    ("Work Experience",
     'one "### <Title> — <Employer>" per job, newest first, with a bold "<Location> · <Dates>" line '
     "and bullets of what the candidate did, the tools used and the measured impact",
     ("resumes", "other")),
    ("Education",
     'one "### <School> — <Degree or certificate>" per entry, newest first, with dates, GPA, '
     "relevant coursework and honors",
     ("education", "resumes", "other")),
    ("Skills",
     'grouped skill lists ("### Programming Languages", "### AI / LLM / Agents", "### Machine '
     'Learning & Deep Learning", "### Cloud & Deployment", ...); after each skill, in parentheses, '
     "where it was used (job, project, course) so its depth is clear",
     KINDS),
    ("Publications",
     'one "### <Title>" per published paper with venue, date, co-authors, link, and 2-3 bullets on '
     "the contribution and methods",
     ("papers", "resumes", "other")),
    ("Achievements & Awards",
     'one "### <Name>" per hackathon, competition result, award, scholarship or honor, with '
     "date, organizer, placement and what was built or done",
     ("achievements", "resumes", "education", "other")),
]


# ─────────────────────────────────────────────────────────
# DOCUMENTS
# ─────────────────────────────────────────────────────────

def read_document(path: Path) -> str:
    """Plain text of a .md/.txt file, or of a PDF via pdftotext; truncated at MAX_SOURCE_CHARS."""
    if path.suffix.lower() == ".pdf":
        text = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                              capture_output=True, text=True, check=True).stdout
    else:
        text = path.read_text(errors="replace")
    text = text.strip()
    if len(text) > MAX_SOURCE_CHARS:
        text = text[:MAX_SOURCE_CHARS] + "\n...[truncated]"
    return text


def is_document(path: Path, docs_dir: Path = USER_DOCS_DIR) -> bool:
    """A file the agent reads: .md/.txt/.pdf, not hidden, not the knowledge base or its backup."""
    rel = path.relative_to(docs_dir)
    return (path.is_file() and path.suffix.lower() in DOC_SUFFIXES
            and not any(part.startswith(".") for part in rel.parts)
            and rel not in {Path(KNOWLEDGE_FILE.name), Path(PREVIOUS_FILE.name)})


def kind_of(rel: Path) -> str:
    """Document kind of a path relative to Docs/user_docs, from its top-level folder."""
    folder_kinds = {folder: kind for kind, folder in FOLDERS.items()}
    return folder_kinds.get(rel.parts[0], "other") if len(rel.parts) > 1 else "other"


def collect_documents(docs_dir: Path = USER_DOCS_DIR, kinds=KINDS) -> dict[str, list[tuple[str, str]]]:
    """Every source document of these kinds under docs_dir: {"resumes": [(relative path, text), ...], ...}.

    Every kind is a key (other kinds are empty lists); empty documents are skipped.
    """
    docs = {kind: [] for kind in KINDS}
    for path in sorted(docs_dir.rglob("*")):
        if not is_document(path, docs_dir):
            continue
        rel = path.relative_to(docs_dir)
        if (kind := kind_of(rel)) in kinds and (text := read_document(path)):
            docs[kind].append((rel.as_posix(), text))
    return docs


def _tree(path: Path, docs_dir: Path) -> dict:
    """{"name", "path", "is_dir", "size", "usable", "children"} for path and everything under it."""
    rel = path.relative_to(docs_dir).as_posix()
    if path.is_dir():
        children = [_tree(child, docs_dir) for child in sorted(path.iterdir(), key=lambda c: (c.is_file(), c.name.lower()))
                    if not child.name.startswith(".")]
        return {"name": path.name, "path": rel, "is_dir": True, "size": None, "usable": False, "children": children}
    return {"name": path.name, "path": rel, "is_dir": False, "size": path.stat().st_size,
            "usable": is_document(path, docs_dir), "children": []}


def scan_user_docs(docs_dir: Path = USER_DOCS_DIR) -> list[dict]:
    """What is in each kind's folder, for the knowledge base page: per kind
    {"kind", "folder", "label", "description", "exists", "documents", "tree"}, where documents
    counts the files the agent would read and tree lists everything (images, too)."""
    folders = []
    for kind in KINDS:
        label, description = FOLDER_GUIDE[kind]
        if kind == "other":  # the top-level files and unknown folders
            folder, exists = "", docs_dir.is_dir()
            entries = [p for p in sorted(docs_dir.iterdir(), key=lambda p: p.name.lower())
                       if p.name not in FOLDERS.values() and (p.is_dir() and not p.name.startswith(".")
                                                              or is_document(p, docs_dir))] if exists else []
        else:
            folder = FOLDERS[kind]
            exists = (docs_dir / folder).is_dir()
            entries = [p for p in sorted((docs_dir / folder).iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
                       if not p.name.startswith(".")] if exists else []
        files = [f for p in entries for f in ([p] if p.is_file() else p.rglob("*"))]
        folders.append({
            "kind": kind, "folder": folder, "label": label, "description": description, "exists": exists,
            "documents": sum(is_document(f, docs_dir) for f in files),
            "tree": [_tree(p, docs_dir) for p in entries],
        })
    return folders


def create_folders(docs_dir: Path = USER_DOCS_DIR) -> None:
    """Creates Docs/user_docs and every kind's folder that doesn't exist yet."""
    for folder in FOLDERS.values():
        (docs_dir / folder).mkdir(parents=True, exist_ok=True)


def group_projects(project_docs: list[tuple[str, str]]) -> dict[str, list[tuple[str, str]]]:
    """projects/<name>/... documents by <name>; a file directly in projects/ is its own project."""
    groups = {}
    for rel, text in project_docs:
        parts = Path(rel).parts
        name = parts[1] if len(parts) > 2 else Path(parts[1]).stem
        groups.setdefault(name, []).append((rel, text))
    return groups


def split_sections(markdown: str, level: int = 2) -> dict[str, str]:
    """{heading: body} for each heading of this level ("## 3. Education" -> "Education")."""
    marks = "#" * level
    parts = re.split(rf"^{marks} (?:[\d.]+\s+)?(.+?)\s*$", markdown, flags=re.MULTILINE)
    # parts = [preamble, heading, body, heading, body, ...]
    return {heading: re.sub(r"\n-{3,}\s*$", "", body.strip()).strip()
            for heading, body in zip(parts[1::2], parts[2::2])}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


# ─────────────────────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────────────────────

SECTION_PROMPT = """You maintain one candidate's knowledge base: a Markdown file that other agents read
to screen job postings and write tailored resumes for this candidate. You are writing one
section of it.

Section: {heading}
It holds: {holds}

Rules:
- Use only facts from the current section and the source documents. Never invent
  employers, titles, dates, degrees, skills, links or metrics.
- The current section is the previous version. Keep its facts unless a source document
  corrects them, and add what the documents show that it lacks. Merge duplicates.
- Where documents disagree, trust the most specific and most recent one.
- Be concise and factual. Keep metrics, dates, links and tool names; bold the key technologies.
- If nothing in the current section or the documents belongs in this section, reply with
  exactly: NONE

Reply with only the section's content in Markdown, without the "## {heading}" line and
with no other text."""

SOURCES_PROMPT = """# Current section

{current}

# Source documents

{sources}"""

PROJECT_HOLDS = ('"### <Project title>", then a bold "<dates> · <context (course, job, hackathon, '
                 'personal)>" line, links (live, code) if given, 3-6 bullets on what was built, the '
                 'methods and the results, and a "**Stack:**" line')

OTHER_PROJECTS_HOLDS = ("the candidate's projects that are NOT one of these, which already have their own "
                        "write-ups: {names}. For each: " + PROJECT_HOLDS)

QUICK_REFERENCE_PROMPT = """You maintain one candidate's knowledge base, which an agent reads to rate how well
job postings fit the candidate. Write its last section, "{heading}", from the rest of the
knowledge base (given below) and its previous version.

It holds, as short bullet lists:
**Strongest matches (production and project evidence):** skill areas backed by jobs or deployed projects
**Secondary / academic-level:** skills seen only in coursework or small projects
**Not shown in the documents (treat as gaps unless the user says otherwise):** common
  requirements for the candidate's target roles that the knowledge base has no evidence for
**Experience level:** years and kind of experience, and the role titles and seniority that fit best

Use only facts from the knowledge base. Reply with only the section's content in Markdown,
without the "## {heading}" line and with no other text.

# Previous version

{current}"""

PORTALS_PROMPT = """You tune a job search for one candidate. The search scans the career portals of the
tracked companies and keeps a posting only if its title contains at least one "positive"
keyword and no "negative" keyword (case-insensitive substring match).

From the candidate's knowledge base, propose changes so the search finds roles the
candidate is qualified for and skips the rest:
- positive: title phrases for roles that fit the candidate's skills and seniority. Prefer
  specific phrases ("ml engineer") over bare words ("engineer", "ai") that match almost
  any tech role.
- negative: title phrases for roles to skip (other fields, far too senior, non-engineering).
- companies_add: companies that hire for the candidate's target roles and aren't tracked
  yet (re-adding a disabled one enables it again). Only add companies whose careers page
  URL you are sure of.
- companies_drop: enabled companies that don't hire for the candidate's target roles.
Only change what the knowledge base gives a reason for; empty lists are fine.

Reply with only this JSON object, no other text:
{{
  "positive_add": ["<keyword>", ...],
  "positive_remove": ["<current positive keyword>", ...],
  "negative_add": ["<keyword>", ...],
  "negative_remove": ["<current negative keyword>", ...],
  "companies_add": [{{"name": "<company>", "careers_url": "https://..."}}, ...],
  "companies_drop": ["<enabled company name>", ...],
  "reasoning": "<1-3 sentences: why these changes>"
}}

# Current title filter
positive: {positive}
negative: {negative}

# Tracked companies
enabled: {enabled}
disabled: {disabled}"""


# ─────────────────────────────────────────────────────────
# KNOWLEDGE BASE
# ─────────────────────────────────────────────────────────

def _format_sources(docs: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"===== {rel} =====\n{text}" for rel, text in docs) or "(none)"


def _ask(model: BaseChatModel, system: str, prompt: str) -> str:
    reply = model.invoke([SystemMessage(system), HumanMessage(prompt)])
    return _final_channel(reply.text).strip()


def _section_body(reply: str, heading: str) -> str:
    """The model's reply without a stray "## heading" line or code fence; "" for NONE."""
    reply = re.sub(r"^```(?:markdown|md)?\s*\n(.*?)\n```$", r"\1", reply.strip(), flags=re.DOTALL)
    reply = re.sub(rf"^##\s+(?:[\d.]+\s+)?{re.escape(heading)}\s*\n", "", reply).strip()
    return "" if reply.upper() == "NONE" else reply


def write_section(model: BaseChatModel, heading: str, holds: str, current: str,
                  docs: list[tuple[str, str]]) -> str:
    """Updated body of one section ("" if it has nothing in it)."""
    reply = _ask(model, SECTION_PROMPT.format(heading=heading, holds=holds),
                 SOURCES_PROMPT.format(current=current or "(empty: new section)", sources=_format_sources(docs)))
    return _section_body(reply, heading)


def write_projects(model: BaseChatModel, docs: dict[str, list[tuple[str, str]]], current: str) -> str:
    """Projects section: one call per projects/<name>/ folder, plus one for projects only
    the resumes or the previous knowledge base mention."""
    previous = [f"### {heading}\n{body}" for heading, body in split_sections(current, level=3).items()]
    groups = group_projects(docs["projects"])
    blocks = []
    for name, project_docs in groups.items():
        # The previous write-up of this project: the "### " block whose title contains the folder name.
        matches = [block for block in previous if _norm(name) in _norm(block.splitlines()[0])]
        previous = [block for block in previous if block not in matches]
        if body := write_section(model, f"{PROJECTS}: {name}", PROJECT_HOLDS, "\n\n".join(matches), project_docs):
            blocks.append(body)

    holds = OTHER_PROJECTS_HOLDS.format(names=", ".join(groups) or "(none)")
    others = write_section(model, PROJECTS, holds, "\n\n".join(previous), docs["resumes"] + docs["other"])
    if others:
        blocks.append(others)
    return "\n\n".join(blocks)


def write_quick_reference(model: BaseChatModel, knowledge: str, current: str) -> str:
    reply = _ask(model, QUICK_REFERENCE_PROMPT.format(heading=QUICK_REFERENCE, current=current or "(none)"),
                 knowledge)
    return _section_body(reply, QUICK_REFERENCE)


def assemble(title: str, sections: list[tuple[str, str]], n_documents: int) -> str:
    """The knowledge base Markdown: header, then "## N. heading" per non-empty section."""
    today = datetime.date.today().isoformat()
    parts = [f"{title}\n\n"
             f"> Source of truth for the Qualification Check and Resume Builder agents. Compiled by the\n"
             f"> knowledge_base agent from {n_documents} documents in `Docs/user_docs/`.\n"
             f"> Last compiled: {today}."]
    for i, (heading, body) in enumerate(((h, b) for h, b in sections if b), start=1):
        parts.append(f"## {i}. {heading}\n\n{body}")
    return "\n\n---\n\n".join(parts) + "\n"


def build_knowledge(model: BaseChatModel, docs: dict[str, list[tuple[str, str]]], previous_text: str = "") -> str:
    """The updated knowledge base Markdown from the documents and the previous version."""
    previous = split_sections(previous_text)
    sections = []
    for heading, holds, kinds in SECTIONS:
        section_docs = [doc for kind in kinds for doc in docs[kind]]
        sections.append((heading, write_section(model, heading, holds, previous.get(heading, ""), section_docs)))
        if heading == "Skills":
            sections.append((PROJECTS, write_projects(model, docs, previous.get(PROJECTS, ""))))

    title = next((line for line in previous_text.splitlines() if line.startswith("# ")), "# User Knowledge Base")
    n_documents = sum(len(d) for d in docs.values())
    body = assemble(title, sections, n_documents)
    sections.append((QUICK_REFERENCE, write_quick_reference(model, body, previous.get(QUICK_REFERENCE, ""))))
    return assemble(title, sections, n_documents)


# ─────────────────────────────────────────────────────────
# PORTALS
# ─────────────────────────────────────────────────────────

def load_portal_config(path: Path = PORTALS_FILE) -> dict:
    """{"positive", "negative": [keywords], "enabled", "disabled": [company names]} from portals.yml."""
    data = yaml.safe_load(path.read_text())
    title_filter = data.get("title_filter") or {}
    companies = data.get("tracked_companies") or []
    return {
        "positive": list(title_filter.get("positive") or []),
        "negative": list(title_filter.get("negative") or []),
        "enabled": [c["name"] for c in companies if c.get("enabled", True)],
        "disabled": [c["name"] for c in companies if not c.get("enabled", True)],
    }


def _parse_portal_changes(text: str) -> dict:
    """Validated changes from the model's reply; ValueError says what to fix."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("Your reply has no JSON object.")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"Your JSON is invalid: {e}.") from e

    changes = {key: [k for k in data.get(key) or [] if isinstance(k, str) and k.strip()]
               for key in ("positive_add", "positive_remove", "negative_add", "negative_remove", "companies_drop")}
    changes["companies_add"] = []
    for company in data.get("companies_add") or []:
        if not isinstance(company, dict) or not _text(company.get("name")):
            raise ValueError('Each "companies_add" item needs a "name".')
        url = _text(company.get("careers_url"))
        if not url.startswith(("https://", "http://")):
            raise ValueError(f'"{company["name"]}" needs a "careers_url" starting with https://.')
        changes["companies_add"].append({"name": _text(company["name"]), "careers_url": url})
    changes["reasoning"] = _text(data.get("reasoning"))
    return changes


def propose_portal_changes(model: BaseChatModel, knowledge: str, path: Path = PORTALS_FILE) -> dict:
    """The model's changes to portals.yml (see PORTALS_PROMPT), retried up to MAX_ATTEMPTS if malformed."""
    config = load_portal_config(path)
    messages = [
        SystemMessage(PORTALS_PROMPT.format(**{k: json.dumps(v) for k, v in config.items()})),
        HumanMessage(f"# Candidate knowledge base\n\n{knowledge}"),
    ]
    for attempt in range(1, MAX_ATTEMPTS + 1):
        text = _final_channel(model.invoke(messages).text)
        try:
            return _parse_portal_changes(text)
        except ValueError as e:
            if attempt == MAX_ATTEMPTS:
                raise
            messages += [AIMessage(text), HumanMessage(f"{e}\nReply again with only the corrected JSON object.")]


# portals.yml is edited as text so its comments survive; these find the lines to change.

def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _is_content(line: str) -> bool:
    return bool(line.strip()) and not line.lstrip().startswith("#")


def _find_block(lines: list[str], key: str, indent: int, start: int = 0) -> tuple[int, int]:
    """(index of the "key:" line at this indent, index of the last content line of its block)."""
    head = re.compile(rf"^ {{{indent}}}{re.escape(key)}:")
    for i in range(start, len(lines)):
        if head.match(lines[i]):
            last = i
            for j in range(i + 1, len(lines)):
                line = lines[j]
                if not _is_content(line):
                    continue
                if _indent(line) < indent or (_indent(line) == indent and not line.lstrip().startswith("- ")):
                    break
                last = j
            return i, last
    raise ValueError(f'"{key}:" not found in portals.yml')


def _item_value(line: str):
    """Value of a "- item" line (a "- name: X" entry gives {"name": X}); None for other lines."""
    stripped = line.strip()
    if not stripped.startswith("- "):
        return None
    try:
        return yaml.safe_load(stripped[2:])
    except yaml.YAMLError:
        return None


def _edit_keywords(lines: list[str], key: str, add: list[str], remove: list[str]) -> tuple[list[str], list[str]]:
    """Adds/removes title_filter.<key> keywords (case-insensitive); returns (added, removed)."""
    filter_line, _ = _find_block(lines, "title_filter", 0)
    head, last = _find_block(lines, key, 2, start=filter_line)
    items = {i: _item_value(lines[i]) for i in range(head + 1, last + 1)}
    items = {i: v for i, v in items.items() if isinstance(v, str)}
    if not items:
        raise ValueError(f"title_filter.{key} has no list items to edit")

    current = {v.lower() for v in items.values()}
    added = [kw for kw in dict.fromkeys(add) if kw.lower() not in current]
    remove_lower = {kw.lower() for kw in remove}
    removed = [v for v in items.values() if v.lower() in remove_lower]

    item_line = lines[max(items)]
    new = [f"{' ' * _indent(item_line)}- {json.dumps(kw, ensure_ascii=False)}\n" for kw in added]
    lines = lines[:max(items) + 1] + new + lines[max(items) + 1:]
    drop = {i for i, v in items.items() if v.lower() in remove_lower}
    return [line for i, line in enumerate(lines) if i not in drop], (added, removed)


def _company_entries(lines: list[str]) -> tuple[dict[str, tuple[int, int]], int]:
    """({lowercased name: (first, last line) of its entry}, last content line of tracked_companies)."""
    head, last = _find_block(lines, "tracked_companies", 0)
    starts = [i for i in range(head + 1, last + 1)
              if isinstance(v := _item_value(lines[i]), dict) and "name" in v]
    entries = {}
    for n, start in enumerate(starts):
        end = starts[n + 1] - 1 if n + 1 < len(starts) else last
        while not _is_content(lines[end]):
            end -= 1
        entries[str(_item_value(lines[start])["name"]).lower()] = (start, end)
    return entries, last


def _set_enabled(lines: list[str], entry: tuple[int, int], enabled: bool, note: str) -> list[str]:
    start, end = entry
    indent = " " * (_indent(lines[start]) + 2)
    new = f"{indent}enabled: {str(enabled).lower()}  # {note}\n"
    for i in range(start, end + 1):
        if re.match(r"^\s+enabled:", lines[i]):
            return lines[:i] + [new] + lines[i + 1:]
    return lines[:end + 1] + [new] + lines[end + 1:]


def apply_portal_changes(changes: dict, path: Path = PORTALS_FILE, dry_run: bool = False,
                         by: str = "the knowledge_base agent") -> dict:
    """Applies the changes to portals.yml (unless dry_run) and returns the ones that aren't no-ops
    (`by` names who made them in the notes left in the file):
    {"positive_added", "positive_removed", "negative_added", "negative_removed",
     "companies_added", "companies_enabled", "companies_disabled", "reasoning"}."""
    today = datetime.date.today().isoformat()
    lines = path.read_text().splitlines(keepends=True)
    applied = {"reasoning": changes.get("reasoning", "")}

    for key in ("positive", "negative"):
        lines, (applied[f"{key}_added"], applied[f"{key}_removed"]) = _edit_keywords(
            lines, key, changes.get(f"{key}_add", []), changes.get(f"{key}_remove", []))

    config = load_portal_config(path)
    disabled = {name.lower() for name in config["disabled"]}
    applied.update(companies_added=[], companies_enabled=[], companies_disabled=[])
    for company in changes.get("companies_add", []):
        entries, last = _company_entries(lines)
        name = company["name"]
        if name.lower() in disabled:
            lines = _set_enabled(lines, entries[name.lower()], True, f"re-enabled by {by} {today}")
            applied["companies_enabled"].append(name)
        elif name.lower() not in entries:
            indent = " " * _indent(lines[next(iter(entries.values()))[0]]) if entries else "  "
            lines = lines[:last + 1] + [
                "\n",
                f"{indent}- name: {json.dumps(name, ensure_ascii=False)}\n",
                f"{indent}  careers_url: {json.dumps(company['careers_url'])}\n",
                f"{indent}  enabled: true\n",
                f"{indent}  # note: added by {by} {today}; check the careers_url\n",
            ] + lines[last + 1:]
            applied["companies_added"].append(company)
    for name in changes.get("companies_drop", []):
        entries, _ = _company_entries(lines)
        if name.lower() in entries and name.lower() not in disabled:
            lines = _set_enabled(lines, entries[name.lower()], False, f"dropped by {by} {today}")
            applied["companies_disabled"].append(name)

    if config["positive"] and len(config["positive"]) + len(applied["positive_added"]) == len(applied["positive_removed"]):
        raise ValueError("the changes would remove every positive keyword; the search would match nothing")

    text = "".join(lines)
    _check_portals(text, config, applied)
    if not dry_run:
        path.write_text(text)
    return applied


def _check_portals(text: str, before: dict, applied: dict) -> None:
    """Raises if the edited portals.yml doesn't parse or doesn't hold exactly the applied changes."""
    data = yaml.safe_load(text)
    title_filter = data["title_filter"]
    for key in ("positive", "negative"):
        removed = {kw.lower() for kw in applied[f"{key}_removed"]}
        expected = [kw for kw in before[key] if kw.lower() not in removed] + applied[f"{key}_added"]
        if title_filter[key] != expected:
            raise RuntimeError(f"editing title_filter.{key} in portals.yml went wrong; nothing was written")
    enabled = {c["name"].lower() for c in data["tracked_companies"] if c.get("enabled", True)}
    expected = ({n.lower() for n in before["enabled"]} - {n.lower() for n in applied["companies_disabled"]}
                | {n.lower() for n in applied["companies_enabled"]}
                | {c["name"].lower() for c in applied["companies_added"]})
    if enabled != expected:
        raise RuntimeError("editing tracked_companies in portals.yml went wrong; nothing was written")


# ─────────────────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────────────────

def run_knowledge_base(model: BaseChatModel | None = None, docs_dir: Path = USER_DOCS_DIR,
                       knowledge_file: Path = KNOWLEDGE_FILE, portals_file: Path = PORTALS_FILE,
                       update_portals: bool = True, dry_run: bool = False, kinds=KINDS) -> dict:
    """Rebuilds the knowledge base from the documents of these kinds and tunes portals.yml to it.

    Returns {"knowledge_file": Path, "knowledge": str, "documents": [relative paths],
             "portals": applied changes (see apply_portal_changes) or None}.
    With dry_run nothing is written. Raises ValueError (no documents) before loading the model.
    """
    docs = collect_documents(docs_dir, kinds)
    documents = [rel for kind in KINDS for rel, _ in docs[kind]]
    if not documents:
        raise ValueError(f"no {', '.join(DOC_SUFFIXES)} documents of kinds {', '.join(kinds)} in {docs_dir}")
    previous_text = knowledge_file.read_text() if knowledge_file.exists() else ""
    if model is None:
        from agents.utils.langchainConfig import chat_model as model  # loads the local LLM

    knowledge = build_knowledge(model, docs, previous_text)
    if not dry_run:
        if previous_text:
            shutil.copy2(knowledge_file, knowledge_file.with_name(PREVIOUS_FILE.name))
        knowledge_file.write_text(knowledge)

    portals = None
    if update_portals:
        portals = apply_portal_changes(propose_portal_changes(model, knowledge, portals_file), portals_file, dry_run)
    return {"knowledge_file": knowledge_file, "knowledge": knowledge, "documents": documents, "portals": portals}


def _portal_summary(applied: dict) -> str:
    lines = []
    for key, values in applied.items():
        if key != "reasoning" and values:
            names = [v["name"] if isinstance(v, dict) else v for v in values]
            lines.append(f"  {key.replace('_', ' ')}: {', '.join(names)}")
    return "\n".join(lines or ["  no changes"]) + (f"\n  why: {applied['reasoning']}" if applied["reasoning"] else "")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild the user's knowledge base from Docs/user_docs and tune portals.yml to it.")
    parser.add_argument("--dry-run", action="store_true", help="print the knowledge base and portal changes, write nothing")
    parser.add_argument("--skip-portals", action="store_true", help="leave portals.yml alone")
    args = parser.parse_args()

    report = run_knowledge_base(update_portals=not args.skip_portals, dry_run=args.dry_run)
    if args.dry_run:
        print(report["knowledge"])
    else:
        print(f"{len(report['documents'])} documents -> {report['knowledge_file']}")
    if report["portals"] is not None:
        print(f"portals.yml{' (dry run, not written)' if args.dry_run else ''}:\n{_portal_summary(report['portals'])}")


if __name__ == "__main__":
    main()
