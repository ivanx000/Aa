"""
Filter layer — runs before anything hits the LLM.
A posting must pass ALL checks to proceed to drafting.

Checks (in order):
  1. Keyword match  — title/description contains a target role keyword
  2. Intern match   — posting is for an intern/co-op/student/new grad role
  3. Location match — remote (anywhere) OR onsite/hybrid in Canada
"""
import re
from app.config import settings


# ---------------------------------------------------------------------------
# 1. Keyword filter
# ---------------------------------------------------------------------------

def _keyword_match(title: str, description: str) -> bool:
    text = f"{title} {description}".lower()
    return any(
        re.search(rf"\b{re.escape(kw)}\b", text)
        for kw in settings.target_keywords
    )


# ---------------------------------------------------------------------------
# 2. Intern / student filter
# ---------------------------------------------------------------------------

_INTERN_RE = re.compile(
    r"\bintern\b|\binternship\b"
    r"|\bco-?op\b"
    r"|\bstudent\b"
    r"|\bnew\s+grad\b|\bnew\s+graduate\b"
    r"|\bentry[\s-]level\b"
    r"|\bgraduate\s+(role|position|opportunity)\b"
    r"|\bjunior\b",
    re.IGNORECASE,
)


def _intern_match(title: str, description: str) -> bool:
    """Title is checked first — a title hit is sufficient. Description is also checked."""
    return bool(_INTERN_RE.search(title)) or bool(_INTERN_RE.search(description))


# ---------------------------------------------------------------------------
# 2. Location filter
# ---------------------------------------------------------------------------

# Signals that a posting is explicitly remote
_REMOTE_RE = re.compile(
    r"\bremote\b|\bwfh\b|\bwork[\s-]from[\s-]home\b",
    re.IGNORECASE,
)

# Signals that a posting is onsite or hybrid (not remote)
_ONSITE_RE = re.compile(
    r"\bonsite\b|\bon-site\b|\bin[\s-]office\b|\bhybrid\b|\bin[\s-]person\b",
    re.IGNORECASE,
)

# Canadian cities, provinces, and country name
_CANADA_RE = re.compile(
    r"\bcanada\b"
    r"|\btoronto\b|\bvancouver\b|\bmontreal\b|\bcalgary\b|\bottawa\b"
    r"|\bwaterloo\b|\bedmonton\b|\bquebec\b|\bhalifax\b|\bvictoria\b"
    r"|\bwinnipeg\b|\bkitchener\b|\bhamilton\b|\blondon,?\s*on\b"
    r"|\bontario\b|\bbritish\s+columbia\b|\balberta\b|\bbc\b"
    r"|\bon\b(?=\s*\||\s*,|\s*$)"   # "ON" as province abbreviation
    r"|\bqc\b|\bab\b|\bns\b|\bnb\b|\bmb\b|\bsk\b",
    re.IGNORECASE,
)


def _location_ok(title: str, description: str) -> bool:
    """
    Returns True if:
    - The posting mentions remote work (we don't care where it's based), OR
    - The posting is onsite/hybrid AND is in Canada
    - No location signal at all → assume remote-friendly, allow through
    """
    text = f"{title} {description}"

    is_remote = bool(_REMOTE_RE.search(text))
    is_onsite = bool(_ONSITE_RE.search(text))
    in_canada = bool(_CANADA_RE.search(text))

    if is_remote:
        return True                      # remote anywhere → keep
    if is_onsite and not in_canada:
        return False                     # onsite/hybrid outside Canada → reject
    return True                          # no location signal, or Canada onsite → keep


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_relevant(title: str, description: str) -> bool:
    """Return True only if the posting passes all three checks."""
    return (
        _keyword_match(title, description)
        and _intern_match(title, description)
        and _location_ok(title, description)
    )


def filter_reason(title: str, description: str) -> str:
    """Return a human-readable reason for rejection (useful for debugging)."""
    if not _keyword_match(title, description):
        return "keyword_mismatch"
    if not _intern_match(title, description):
        return "not_intern_role"
    if not _location_ok(title, description):
        return "location_rejected"
    return "pass"
