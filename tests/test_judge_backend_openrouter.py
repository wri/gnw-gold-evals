from types import SimpleNamespace

from goldset.evaluators import llm_judges
from goldset.judge_config import (
    JUDGE_BACKEND_ENV_VAR,
    JUDGE_BACKEND_OPENROUTER_JEV,
    OPENROUTER_JEV_MODEL,
)


def _patch_openrouter(monkeypatch, answers, captured):
    class FakeDecisions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return {"answers": answers}

    class FakeOpenRouter:
        def __init__(self, api_key):
            captured["api_key"] = api_key
            self.alpha = SimpleNamespace(decisions=FakeDecisions())

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(llm_judges, "OpenRouter", FakeOpenRouter)


def test_openrouter_expected_text_judge(monkeypatch):
    captured: dict = {}
    _patch_openrouter(monkeypatch, {"decision": {"noul": 0.83}}, captured)
    monkeypatch.setenv(JUDGE_BACKEND_ENV_VAR, JUDGE_BACKEND_OPENROUTER_JEV)
    monkeypatch.setenv("OPENROUTER_API_KEY", "router-key")

    result = llm_judges.llm_judge_expected_text(
        "mentions 30m resolution",
        "The output is rendered at 30-meter by 30-meter pixels.",
        include_reason=True,
    )

    assert result["score"] == 1
    assert "OpenRouter Decisions" in result["reason"]
    assert captured["api_key"] == "router-key"
    assert captured["model"] == OPENROUTER_JEV_MODEL


def test_openrouter_agent_answer_judge(monkeypatch):
    captured: dict = {}
    _patch_openrouter(
        monkeypatch,
        {
            "answer_eval_type": {"choice": "numeric"},
            "matches": {"noul": 0.64, "confidence": 0.91},
        },
        captured,
    )
    monkeypatch.setenv(JUDGE_BACKEND_ENV_VAR, JUDGE_BACKEND_OPENROUTER_JEV)
    monkeypatch.setenv("OPENROUTER_API_KEY", "router-key")

    verdict = llm_judges.llm_judge(
        "42 hectares",
        "A total of 42 hectares were affected.",
        include_reason=True,
    )

    assert verdict["score"] == 1
    assert "type=numeric" in verdict["reason"]
    assert "answer_eval_type" in captured["questions"]
    assert "matches" in captured["questions"]


def test_openrouter_clarification_judge(monkeypatch):
    captured: dict = {}
    _patch_openrouter(monkeypatch, {"decision": {"noul": 0.72}}, captured)
    monkeypatch.setenv(JUDGE_BACKEND_ENV_VAR, JUDGE_BACKEND_OPENROUTER_JEV)
    monkeypatch.setenv("OPENROUTER_API_KEY", "router-key")

    judgement = llm_judges.llm_judge_clarification(
        {"messages": [SimpleNamespace(content="Could you pick one district?")]},
        "Show me stats",
    )

    assert judgement["is_clarification"] is True
    assert "noul=0.72" in judgement["explanation"]
