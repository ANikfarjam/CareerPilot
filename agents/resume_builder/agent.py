"""
This agent scans the passed through job and its description and related details, as well as
scans the user's knowledge base and projects, and builds a resume suitable for the given job. As
well as giving recommendations for side projects to get hands on experience.

How it works:
  Not a LangGraph: the flow is linear with two LLM calls, and it is unrelated to
  the search pipeline in agents/graph (it only reads a job that pipeline already
  saved to job_board_table).
    1. `load_job()` reads the posting from job_board_table.
    2. `load_background()` reads the candidate's knowledge base
       (Docs/user_docs/user_knowledge.md) plus the full write-up of every project
       (Docs/user_docs/projects/*/*.md); the knowledge base only summarizes them.
    3. `write_resume()` has the model write a Markdown resume tailored to the posting.
    4. `recommend_side_projects()` has the model propose side projects that close
       the posting's skill gaps.
  Two calls instead of one: max_new_tokens is shared with gpt-oss's analysis
  channel, and a resume plus recommendations in one reply risks being cut off.

Orchestration:
  - `run_resume_builder(job_id, model)` does all four and returns
    {"job", "resume", "side_projects"}. Nothing is saved.
  - POST /agents/resume/{job_id} (apis/reposetories/agents.py) serves it to the frontend.

Run it:
    python -m agents.resume_builder.agent <job_id>
    python -m agents.resume_builder.agent <job_id> --out resume.md
"""

import argparse
import uuid
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from agents.portal_search.agent import _final_channel
from agents.qualification_check.agent import KNOWLEDGE_FILE, MAX_DESCRIPTION_CHARS, _text, load_knowledge
from db.dbOps import get_job
from db.documents import read_description

PROJECTS_DIR = KNOWLEDGE_FILE.parent / "projects"


def load_projects(projects_dir: Path = PROJECTS_DIR) -> str:
    """Every projects/<name>/*.md, each under a "## <name>" heading."""
    parts = []
    for path in sorted(projects_dir.glob("*/*.md")):
        parts.append(f"## {path.parent.name}\n\n{path.read_text().strip()}")
    return "\n\n".join(parts)


def load_background(knowledge_file: Path = KNOWLEDGE_FILE, projects_dir: Path = PROJECTS_DIR) -> str:
    """Knowledge base + project write-ups, as one prompt section."""
    return (f"# Candidate knowledge base\n\n{load_knowledge(knowledge_file)}\n\n"
            f"# Candidate projects (full write-ups)\n\n{load_projects(projects_dir)}")


def load_job(job_id: uuid.UUID) -> dict:
    """The posting from job_board_table; LookupError if missing, ValueError if it has no description."""
    job = get_job(job_id)
    if job is None:
        raise LookupError(f"job {job_id} not found")
    description = _text(read_description(job.description_path))
    if not description:
        raise ValueError(f"job {job_id} has no description to tailor the resume to")
    if len(description) > MAX_DESCRIPTION_CHARS:
        description = description[:MAX_DESCRIPTION_CHARS] + "\n...[truncated]"
    return {
        "id": job.id,
        "company_name": job.company_name,
        "position": job.position,
        "job_type": job.job_type.value,
        "description": description,
    }


# ─────────────────────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────────────────────

RESUME_PROMPT = """You are a professional resume writer tailoring one candidate's resume to a job posting.

Rules:
- Use only facts from the candidate's knowledge base and projects below. Never invent
  experience, employers, titles, dates, degrees, skills or metrics.
- Pick and order content by relevance to the posting: lead with the experience,
  projects and skills that match its requirements; leave out what doesn't help.
- Use the posting's terminology where it truthfully describes the candidate's work.
- Bullets start with a strong verb and show impact; keep the metrics the knowledge base gives.
- Fit on one page.

Reply with only the resume in Markdown, no other text, in this layout:
# <Name>
<location> | <email> | <phone> | <LinkedIn> | <GitHub> | <portfolio>

## Summary
<2-3 sentences aimed at this position>

## Skills
<grouped skill lines, most relevant first>

## Experience
### <Title> — <Employer> | <Location> | <Dates>
- <bullet>

## Projects
### <Project> | <tech stack>
- <bullet>
(the 3-4 projects most relevant to the posting)

## Education
<degree, school, date, GPA / relevant coursework if it helps>

{background}"""

SIDE_PROJECTS_PROMPT = """You are a career coach helping one candidate get hands-on experience for a job posting.

Compare the posting's requirements to the candidate's knowledge base and projects below.
Find the biggest gaps: required skills, tools or domains the candidate has no evidence for.
Propose 2-3 side projects that close them. Each one should be buildable by one person in
about 1-3 weekends, build on what the candidate already knows, and end in something they
can show (a repo, a demo, a write-up).

Reply with only Markdown, no other text, in this layout:
## Gaps
- <requirement the candidate lacks>: <why it matters for this role>

## Side projects
### 1. <title>
**Closes:** <gaps it covers>
**Stack:** <languages, frameworks, services>
**What to build:** <2-3 sentences>
**Milestones:**
1. <step>
**Resume bullet once done:** <one bullet the candidate could add>

{background}"""

TASK_PROMPT = """Company: {company_name}
Position: {position}
Work type: {job_type}

Job description:
{description}"""


def _ask(model: BaseChatModel, system: str, job: dict, background: str) -> str:
    reply = model.invoke([SystemMessage(system.format(background=background)), HumanMessage(TASK_PROMPT.format(**job))])
    return _final_channel(reply.text).strip()


def write_resume(model: BaseChatModel, job: dict, background: str) -> str:
    """Markdown resume tailored to the job."""
    return _ask(model, RESUME_PROMPT, job, background)


def recommend_side_projects(model: BaseChatModel, job: dict, background: str) -> str:
    """Markdown list of the job's skill gaps and side projects that close them."""
    return _ask(model, SIDE_PROJECTS_PROMPT, job, background)


def run_resume_builder(job_id: uuid.UUID, model: BaseChatModel | None = None) -> dict:
    """Loads the job and the candidate's background, then has the model write both parts.

    Returns {"job": dict, "resume": str, "side_projects": str}.
    Raises LookupError (no such job) or ValueError (job has no description) before loading the model.
    """
    job = load_job(job_id)
    background = load_background()
    if model is None:
        from agents.utils.langchainConfig import chat_model as model  # loads the local LLM
    return {
        "job": job,
        "resume": write_resume(model, job, background),
        "side_projects": recommend_side_projects(model, job, background),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a resume and side-project ideas for a saved job.")
    parser.add_argument("job_id", type=uuid.UUID, help="id of a job in job_board_table")
    parser.add_argument("--out", type=Path, help="write the Markdown here instead of printing it")
    args = parser.parse_args()

    report = run_resume_builder(args.job_id)
    text = f"{report['resume']}\n\n---\n\n{report['side_projects']}\n"
    if args.out:
        args.out.write_text(text)
        print(f"{report['job']['position']} @ {report['job']['company_name']} -> {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
