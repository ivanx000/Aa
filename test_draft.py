"""
Manual end-to-end test: filter → draft for a single posting.
Run with: python test_draft.py

Requires Ollama running locally with the configured model pulled.
  ollama pull llama3.2
  ollama serve   (if not already running)
"""
from app.filtering.filter import is_relevant
from app.drafting.drafter import draft

SAMPLE_POSTING = {
    "title": "Software Engineer – AI/ML Platform",
    "description": """
    We're building the data infrastructure layer for ML teams at fast-growing SaaS companies.
    You'll work across our Python backend and React dashboard, helping ML engineers ship
    models faster. We use FastAPI, PostgreSQL, and deploy on AWS.

    We're looking for someone who:
    - Has experience with Python and ML tooling
    - Is comfortable owning full-stack features end to end
    - Has worked with LLMs or evaluation pipelines

    Small team (8 people), Series A, Toronto-based with remote-friendly culture.
    """,
}

if __name__ == "__main__":
    title = SAMPLE_POSTING["title"]
    description = SAMPLE_POSTING["description"]

    print(f"Posting: {title}\n")

    relevant = is_relevant(title, description)
    print(f"Filter result: {'PASS ✓' if relevant else 'FAIL ✗'}\n")

    if relevant:
        print("Generating draft...\n")
        result = draft(title, description)

        print("--- BLURB ---")
        print(result.blurb)
        print()
        print("--- RESUME KEYWORDS ---")
        for kw in result.keywords:
            print(f"  • {kw}")
        print()
    else:
        print("Posting filtered out — no draft generated.")
