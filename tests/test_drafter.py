from dataclasses import dataclass

from app.drafting.drafter import _parse_response, draft, tailor


# ---------------------------------------------------------------------------
# _parse_response
# ---------------------------------------------------------------------------

def test_parse_response_plain_json():
    raw = '{"blurb": "Great fit.", "keywords": ["python", "fastapi"]}'
    result = _parse_response(raw)
    assert result.blurb == "Great fit."
    assert result.keywords == ["python", "fastapi"]


def test_parse_response_strips_markdown_fences():
    raw = '```json\n{"blurb": "Great fit.", "keywords": ["python"]}\n```'
    result = _parse_response(raw)
    assert result.blurb == "Great fit."
    assert result.keywords == ["python"]


def test_parse_response_extracts_json_with_preamble():
    raw = 'Here is the JSON you asked for:\n{"blurb": "Fits well.", "keywords": []}'
    result = _parse_response(raw)
    assert result.blurb == "Fits well."
    assert result.keywords == []


def test_parse_response_falls_back_to_raw_text_on_malformed_json():
    raw = "Sorry, I can't produce valid JSON right now."
    result = _parse_response(raw)
    assert result.blurb == raw
    assert result.keywords == []


def test_parse_response_missing_fields_default_gracefully():
    raw = '{"blurb": "Just a blurb, no keywords field."}'
    result = _parse_response(raw)
    assert result.blurb == "Just a blurb, no keywords field."
    assert result.keywords == []


# ---------------------------------------------------------------------------
# draft() / tailor() — mock the Ollama client so no real LLM call happens
# ---------------------------------------------------------------------------

@dataclass
class _FakeMessage:
    content: str


@dataclass
class _FakeResponse:
    message: _FakeMessage


class _FakeClient:
    def __init__(self, host=None, response_content=""):
        self._response_content = response_content

    def chat(self, model, messages, options):
        return _FakeResponse(message=_FakeMessage(content=self._response_content))


def test_draft_returns_parsed_result(monkeypatch):
    content = '{"blurb": "Built X with Y.", "keywords": ["react", "sql"]}'
    monkeypatch.setattr(
        "app.drafting.drafter.Client",
        lambda host=None: _FakeClient(response_content=content),
    )

    result = draft("Full Stack Intern", "Remote role using React and SQL.")

    assert result.blurb == "Built X with Y."
    assert result.keywords == ["react", "sql"]


def test_tailor_returns_parsed_result(monkeypatch):
    content = (
        '{"blurb": "Tailored blurb.", "keywords": ["react"], '
        '"bullets_to_emphasize": ["Shipped feature X"], '
        '"rewrites": [{"original": "did X", "suggested": "shipped X using React"}]}'
    )
    monkeypatch.setattr(
        "app.drafting.drafter.Client",
        lambda host=None: _FakeClient(response_content=content),
    )

    result = tailor("Full Stack Intern", "Remote role using React.")

    assert result.blurb == "Tailored blurb."
    assert result.keywords == ["react"]
    assert result.bullets_to_emphasize == ["Shipped feature X"]
    assert result.rewrites == [{"original": "did X", "suggested": "shipped X using React"}]


def test_tailor_falls_back_on_malformed_json(monkeypatch):
    monkeypatch.setattr(
        "app.drafting.drafter.Client",
        lambda host=None: _FakeClient(response_content="not json at all"),
    )

    result = tailor("Full Stack Intern", "Remote role.")

    assert result.blurb == "not json at all"
    assert result.keywords == []
    assert result.bullets_to_emphasize == []
    assert result.rewrites == []
