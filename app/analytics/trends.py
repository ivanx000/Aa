"""
Skill/tool/language trend analysis over stored postings.

Reuses everything the fetcher already scraped — including postings that were
rejected by the intern filter — since the goal here is a market-wide signal
("what are companies asking for right now"), not just intern-relevant roles.

A skill is counted at most once per posting (not once per mention), so a
single posting repeating "Python" ten times doesn't drown out the signal.
"""
import re
from collections import Counter
from dataclasses import dataclass

from app.db.database import Posting


# ---------------------------------------------------------------------------
# Taxonomy: canonical name -> (category, [aliases])
# ---------------------------------------------------------------------------

SKILL_TAXONOMY: dict[str, tuple[str, list[str]]] = {
    # Languages
    "Python":     ("language", ["python"]),
    "JavaScript": ("language", ["javascript", "js"]),
    "TypeScript": ("language", ["typescript", "ts"]),
    "Java":       ("language", ["java"]),
    "C++":        ("language", ["c++"]),
    "C#":         ("language", ["c#"]),
    # Bare "go" is excluded — too common as an English verb ("go-to-market",
    # "go home") to be a reliable signal; "golang" is unambiguous.
    "Go":         ("language", ["golang"]),
    "Rust":       ("language", ["rust"]),
    "Ruby":       ("language", ["ruby"]),
    "PHP":        ("language", ["php"]),
    "Swift":      ("language", ["swift"]),
    "Kotlin":     ("language", ["kotlin"]),
    "Scala":      ("language", ["scala"]),
    "SQL":        ("language", ["sql"]),
    # Bare "C" is excluded — too often a false hit on initials, "C-suite",
    # "C.V.", "D.C.", etc. in free-text descriptions to be a reliable signal.

    # Web / app frameworks
    "React":       ("framework", ["react", "react.js", "reactjs"]),
    "Next.js":     ("framework", ["next.js", "nextjs"]),
    "Vue":         ("framework", ["vue", "vue.js", "vuejs"]),
    "Angular":     ("framework", ["angular"]),
    "Node.js":     ("framework", ["node.js", "nodejs", "node"]),
    "Express":     ("framework", ["express.js", "expressjs", "express"]),
    "Django":      ("framework", ["django"]),
    "Flask":       ("framework", ["flask"]),
    "FastAPI":     ("framework", ["fastapi"]),
    "Spring":      ("framework", ["spring boot", "spring"]),
    ".NET":        ("framework", [".net", "dotnet"]),
    "Ruby on Rails": ("framework", ["ruby on rails", "rails"]),

    # ML / data
    "TensorFlow":  ("ml", ["tensorflow"]),
    "PyTorch":     ("ml", ["pytorch"]),
    "scikit-learn": ("ml", ["scikit-learn", "sklearn"]),
    "Pandas":      ("ml", ["pandas"]),
    "NumPy":       ("ml", ["numpy"]),
    "LLM":         ("ml", ["llm", "large language model"]),
    "Spark":       ("ml", ["spark", "pyspark"]),

    # Cloud / infra
    "AWS":         ("cloud", ["aws", "amazon web services"]),
    "GCP":         ("cloud", ["gcp", "google cloud"]),
    "Azure":       ("cloud", ["azure"]),
    "Docker":      ("cloud", ["docker"]),
    "Kubernetes":  ("cloud", ["kubernetes", "k8s"]),
    "Terraform":   ("cloud", ["terraform"]),
    "CI/CD":       ("cloud", ["ci/cd", "continuous integration"]),

    # Databases
    "PostgreSQL":  ("database", ["postgresql", "postgres"]),
    "MySQL":       ("database", ["mysql"]),
    "MongoDB":     ("database", ["mongodb", "mongo"]),
    "Redis":       ("database", ["redis"]),
    "SQLite":      ("database", ["sqlite"]),
    "DynamoDB":    ("database", ["dynamodb"]),
    "Elasticsearch": ("database", ["elasticsearch"]),

    # Tools / misc
    "Git":         ("tool", ["git"]),
    "GraphQL":     ("tool", ["graphql"]),
    "REST":        ("tool", ["rest api", "restful"]),
    "Kafka":       ("tool", ["kafka"]),
    "Linux":       ("tool", ["linux"]),
}


def _build_pattern(alias: str) -> re.Pattern:
    """Boundary-safe pattern — \\b breaks on symbol-suffixed aliases like
    "C++" or ".NET" since \\b requires a word/non-word transition."""
    escaped = re.escape(alias)
    return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)


_COMPILED: dict[str, list[re.Pattern]] = {
    name: [_build_pattern(alias) for alias in aliases]
    for name, (_category, aliases) in SKILL_TAXONOMY.items()
}


@dataclass
class SkillCount:
    name: str
    category: str
    count: int
    pct: float  # percent of postings scanned that mention this skill


def _postings_matching(postings: list[Posting]) -> Counter:
    counts: Counter = Counter()
    for p in postings:
        text = f"{p.title or ''} {p.description or ''}"
        for name, patterns in _COMPILED.items():
            if any(pat.search(text) for pat in patterns):
                counts[name] += 1
    return counts


def compute_trends(postings: list[Posting], top_n: int = 15) -> list[SkillCount]:
    """Rank skills/tools/languages by how many distinct postings mention them."""
    total = len(postings)
    counts = _postings_matching(postings)
    ranked = counts.most_common(top_n)
    return [
        SkillCount(
            name=name,
            category=SKILL_TAXONOMY[name][0],
            count=count,
            pct=(count / total * 100) if total else 0.0,
        )
        for name, count in ranked
    ]
