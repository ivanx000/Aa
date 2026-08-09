"""
Drafting step — generates a tailored blurb + resume keyword list via Ollama.
Returns a DraftResult with both fields so they can be stored and reviewed separately.
Reads facts.yaml once at import time; restart the server to pick up edits.
"""
import json
import re
import yaml
from pathlib import Path
from dataclasses import dataclass
from ollama import Client
from app.config import settings

FACTS_PATH = Path(__file__).resolve().parents[2] / "facts.yaml"
_facts: dict = {}


@dataclass
class DraftResult:
    blurb: str
    keywords: list[str]


@dataclass
class TailoringResult:
    blurb: str
    keywords: list[str]
    bullets_to_emphasize: list[str]   # existing resume bullets to highlight/move up
    rewrites: list[dict]              # [{"original": ..., "suggested": ...}]


def _load_facts() -> dict:
    global _facts
    if not _facts:
        with open(FACTS_PATH) as f:
            _facts = yaml.safe_load(f)
    return _facts


def _build_prompt(title: str, description: str, facts: dict) -> str:
    profile = facts.get("profile", {})
    experience = facts.get("experience", [])
    projects = facts.get("projects", [])
    talking_points = facts.get("talking_points", {})
    preferences = facts.get("preferences", {})

    project_lines = "\n".join(
        f"- {p['name']} ({', '.join(p['stack'])}): {p['description'].strip()}"
        for p in projects
    )

    exp_lines = "\n".join(
        f"- {e['role']} @ {e['company']} ({e['dates']}): {'; '.join(e['bullets'])}"
        for e in experience
    )

    return f"""You are helping a candidate apply for a job. Given the candidate facts and job posting below, produce two things:

1. A "why I'm a good fit" blurb (3-5 sentences)
2. A list of resume keywords — specific skills, tools, or phrases from the job posting that match the candidate's background and should appear in their resume

RULES for the blurb:
- Lead with the 1-2 projects or experiences that most directly match the posting — name them explicitly
- Include at least one concrete number or technical detail from the facts
- Do NOT invent anything not in the facts
- Tone: {preferences.get('tone', 'honest and specific')}
- Avoid: {preferences.get('avoid', 'overstating impact')}
- Do not start with "I" — open with a project name, skill, or concrete claim

RULES for keywords:
- 6-10 keywords or short phrases pulled directly from the job posting
- Only include ones the candidate can honestly claim based on the facts
- Prefer specific technical terms over generic ones (e.g. "FastAPI" over "backend development")

Respond with ONLY valid JSON in this exact format, no explanation:
{{
  "blurb": "...",
  "keywords": ["keyword1", "keyword2", ...]
}}

CANDIDATE FACTS:
Name: {profile.get('name')}
Role: {profile.get('role')}
Specialization: {profile.get('specialization')}

Experience:
{exp_lines}

Projects:
{project_lines}

Talking points:
- AI/ML: {talking_points.get('ai_ml', '').strip()}
- Full-stack: {talking_points.get('fullstack', '').strip()}
- Systems: {talking_points.get('systems', '').strip()}

JOB POSTING:
Title: {title}
Description (first 1500 chars):
{description[:1500]}

JSON response:"""


def _parse_response(raw: str) -> DraftResult:
    """Extract JSON from model output, tolerating markdown fences or extra text."""
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()

    # Find the first { ... } block in case there's preamble
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)

    try:
        data = json.loads(cleaned)
        return DraftResult(
            blurb=data.get("blurb", "").strip(),
            keywords=data.get("keywords", []),
        )
    except json.JSONDecodeError:
        # Fallback: return raw output as blurb with empty keywords
        return DraftResult(blurb=raw.strip(), keywords=[])


def _build_tailor_prompt(title: str, description: str, facts: dict) -> str:
    profile = facts.get("profile", {})
    experience = facts.get("experience", [])
    projects = facts.get("projects", [])
    preferences = facts.get("preferences", {})

    # Collect all resume bullets
    all_bullets = []
    for e in experience:
        for b in e.get("bullets", []):
            all_bullets.append(f"[{e['company']}] {b}")
    for p in projects:
        all_bullets.append(f"[{p['name']}] {p['description'].strip()[:120]}")

    bullets_block = "\n".join(f"- {b}" for b in all_bullets)

    return f"""You are helping a candidate tailor their resume and application for a specific job.

Given the job posting and the candidate's existing resume bullets below, return a JSON object with:
1. "blurb": A 3-5 sentence "why I'm a good fit" paragraph
2. "keywords": 6-10 specific technical terms from the posting the candidate can honestly claim
3. "bullets_to_emphasize": 3-5 existing bullets (copied exactly) that are most relevant to this role — these should be moved to the top of the resume
4. "rewrites": Up to 3 objects with "original" (existing bullet) and "suggested" (reworded to better match the posting's language/keywords) — only rewrite if there's a clear improvement, do not fabricate

RULES:
- Only use facts present in the candidate's existing bullets — do not invent experience
- Prefer adding the posting's exact terminology to existing bullets over making things up
- Tone: {preferences.get('tone', 'honest and specific')}
- Avoid: {preferences.get('avoid', 'overstating impact')}

Respond with ONLY valid JSON, no explanation.

CANDIDATE RESUME BULLETS:
{bullets_block}

JOB POSTING:
Title: {title}
Description (first 2000 chars):
{description[:2000]}

JSON response:"""


def draft(title: str, description: str) -> DraftResult:
    facts = _load_facts()
    prompt = _build_prompt(title, description, facts)

    client = Client(host=settings.ollama_host)
    response = client.chat(
        model=settings.ollama_model,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.3},
    )
    return _parse_response(response.message.content)


def tailor(title: str, description: str) -> TailoringResult:
    facts = _load_facts()
    prompt = _build_tailor_prompt(title, description, facts)

    client = Client(host=settings.ollama_host)
    response = client.chat(
        model=settings.ollama_model,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.3},
    )

    raw = response.message.content.strip()
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)

    try:
        data = json.loads(cleaned)
        return TailoringResult(
            blurb=data.get("blurb", "").strip(),
            keywords=data.get("keywords", []),
            bullets_to_emphasize=data.get("bullets_to_emphasize", []),
            rewrites=data.get("rewrites", []),
        )
    except json.JSONDecodeError:
        return TailoringResult(blurb=raw, keywords=[], bullets_to_emphasize=[], rewrites=[])
