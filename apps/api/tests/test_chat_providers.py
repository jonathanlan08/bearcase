"""Chat backend resolution and the OpenAI-compatible tool loop. No network: settings are built directly and
the OpenAI client is replaced with scripted chunk iterators."""

from __future__ import annotations

import json
import types
import uuid
from itertools import pairwise
from typing import Any

import httpx
import openai
import pytest
from sqlalchemy import func, select

from bearcase.chat import openai_compat
from bearcase.chat import service as chat_service
from bearcase.chat.openai_compat import _merge_tool_call, _parse_args, openai_tools
from bearcase.chat.providers import (
    MOCK_BACKEND,
    OPTION_ORDER,
    REGISTRY,
    ChatBackend,
    models_for,
    public_options,
    resolve_chat_backend,
    validate_base_url,
    validate_model_id,
)
from bearcase.chat.tools import TOOLS
from bearcase.config import Settings
from bearcase.models import AuditEvent, ChatMessage, ChatThread, Deal, FinancialMetric

FAKE_KEY = "fake-key-must-never-appear-4f9a1c"
PROVIDER_ENV = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "OLLAMA_HOST",
    "BEARCASE_AI_MODEL",
    "BEARCASE_CHAT_PROVIDER",
    "BEARCASE_CHAT_MODEL",
    "BEARCASE_CHAT_BASE_URL",
    "BEARCASE_CHAT_API_KEY",
)


@pytest.fixture(autouse=True)
def _clean_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PROVIDER_ENV:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(f"BEARCASE_{name}", raising=False)


def settings(**kw: Any) -> Settings:
    return Settings(_env_file=None, **kw)


# ---- resolution -----------------------------------------------------------------------------------------


def test_auto_without_keys_is_mock() -> None:
    b = resolve_chat_backend(settings())
    assert b is MOCK_BACKEND and b.ready and b.kind == "mock" and b.name == "mock" and b.model == "rules-v1"


def test_auto_picks_gemini_and_anthropic_wins() -> None:
    b = resolve_chat_backend(settings(gemini_api_key=FAKE_KEY))
    assert b.ready and b.name == "gemini" and b.kind == "openai_compat" and b.label == "Google Gemini"
    assert b.base_url == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert b.model == "gemini-3.8-flash" and b.api_key == FAKE_KEY and b.free_tier is True
    b2 = resolve_chat_backend(settings(gemini_api_key=FAKE_KEY, anthropic_api_key="a"))
    assert b2.name == "anthropic" and b2.kind == "anthropic" and b2.model == "claude-haiku-4-5" and b2.base_url is None


@pytest.mark.parametrize(
    ("kw", "expected"),
    [
        ({"openai_api_key": "k", "gemini_api_key": "k", "groq_api_key": "k"}, "openai"),
        ({"gemini_api_key": "k", "groq_api_key": "k", "openrouter_api_key": "k"}, "gemini"),
        ({"groq_api_key": "k", "openrouter_api_key": "k", "ollama_host": "http://127.0.0.1:11434"}, "groq"),
        ({"openrouter_api_key": "k", "ollama_host": "http://127.0.0.1:11434"}, "openrouter"),
        ({"ollama_host": "localhost:11434"}, "ollama"),
    ],
)
def test_auto_order(kw: dict[str, Any], expected: str) -> None:
    b = resolve_chat_backend(settings(**kw))
    assert b.name == expected and b.ready


def test_auto_ollama_uses_host_and_bare_host_gets_scheme() -> None:
    b = resolve_chat_backend(settings(ollama_host="localhost:11434"))
    assert b.base_url == "http://localhost:11434/v1" and b.api_key == "ollama" and b.model == "qwen3:8b"
    explicit = resolve_chat_backend(settings(chat_provider="ollama"))
    assert explicit.ready and explicit.base_url == "http://127.0.0.1:11434/v1" and explicit.label == "Ollama (local)"


def test_explicit_provider_without_key_falls_back_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    b = resolve_chat_backend(settings(chat_provider="groq"))
    assert b.ready is False and b.name == "groq" and b.api_key is None
    assert "GROQ_API_KEY" in (b.reason or "")
    monkeypatch.setattr(chat_service, "resolve_chat_backend", lambda settings=None: b)
    assert chat_service.chat_provider_name() == "mock"


def test_explicit_anthropic_without_key_is_not_ready() -> None:
    b = resolve_chat_backend(settings(chat_provider="anthropic"))
    assert not b.ready and "ANTHROPIC_API_KEY" in (b.reason or "")


def test_chat_model_override_applies() -> None:
    b = resolve_chat_backend(settings(groq_api_key="k", chat_model="qwen/qwen3.6-27b"))
    assert b.model == "qwen/qwen3.6-27b"
    assert resolve_chat_backend(settings(groq_api_key="k")).model == "openai/gpt-oss-120b"
    # an explicitly configured BEARCASE_AI_MODEL still drives Anthropic chat; chat_model beats it
    assert resolve_chat_backend(settings(anthropic_api_key="a", ai_model="claude-sonnet-5")).model == "claude-sonnet-5"
    assert resolve_chat_backend(settings(anthropic_api_key="a", ai_model="claude-sonnet-5", chat_model="x")).model == "x"


def test_custom_base_url_validation() -> None:
    public_http = resolve_chat_backend(
        settings(chat_provider="custom", chat_base_url="http://example.com/v1", chat_model="m", chat_api_key="k")
    )
    assert not public_http.ready and public_http.reason == "base URL must use https"
    local = resolve_chat_backend(
        settings(chat_provider="custom", chat_base_url="http://localhost:1234/v1", chat_model="m", chat_api_key="k")
    )
    assert local.ready and local.base_url == "http://localhost:1234/v1" and local.api_key == "k" and local.name == "custom"
    assert local.label == "Custom OpenAI-compatible"
    no_model = resolve_chat_backend(settings(chat_provider="custom", chat_base_url="http://localhost:1234/v1", chat_api_key="k"))
    assert not no_model.ready and "BEARCASE_CHAT_MODEL" in (no_model.reason or "")
    no_url = resolve_chat_backend(settings(chat_provider="custom", chat_model="m"))
    assert not no_url.ready and "BEARCASE_CHAT_BASE_URL" in (no_url.reason or "")
    keyless_local = resolve_chat_backend(
        settings(chat_provider="custom", chat_base_url="http://127.0.0.1:1234/v1", chat_model="m")
    )
    assert keyless_local.ready and keyless_local.api_key == "local"
    keyless_public = resolve_chat_backend(
        settings(chat_provider="custom", chat_base_url="https://api.example.com/v1", chat_model="m")
    )
    assert not keyless_public.ready and "BEARCASE_CHAT_API_KEY" in (keyless_public.reason or "")
    # another provider's key is never borrowed for an operator-chosen host
    borrowed_public = resolve_chat_backend(
        settings(chat_provider="custom", chat_base_url="https://api.example.com/v1", chat_model="m", openai_api_key="sk-other")
    )
    assert not borrowed_public.ready and "BEARCASE_CHAT_API_KEY" in (borrowed_public.reason or "")
    borrowed_local = resolve_chat_backend(
        settings(chat_provider="custom", chat_base_url="http://localhost:1234/v1", chat_model="m", openai_api_key="sk-other")
    )
    assert borrowed_local.ready and borrowed_local.api_key == "local"
    proxied = resolve_chat_backend(settings(groq_api_key="k", chat_base_url="http://8.8.8.8/v1"))
    assert not proxied.ready and "https" in (proxied.reason or "")


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:11434/v1",
        "http://10.0.0.5/v1",
        "http://192.168.1.20:8080/v1",
        "http://172.16.0.1/v1",
        "http://[::1]:8000/v1",
        "http://mac-mini.local/v1",
        "https://api.example.com/v1",
    ],
)
def test_private_or_https_base_urls_are_accepted(url: str) -> None:
    assert validate_base_url(url) is None


@pytest.mark.parametrize("url", ["http://example.com/v1", "http://8.8.8.8/v1", "ftp://localhost/v1", "not a url", "https://"])
def test_bad_base_urls_are_rejected(url: str) -> None:
    assert validate_base_url(url) is not None


def test_public_options_have_contract_shape_and_no_keys() -> None:
    options = public_options()
    assert [o["provider"] for o in options] == list(OPTION_ORDER) and len(options) == 6
    for o in options:
        assert set(o) == {"provider", "label", "env", "free_tier", "free_tier_note", "default_model", "key_url", "models"}
        assert o["label"] == REGISTRY[o["provider"]].label and o["key_url"].startswith("https://")
        assert o["models"] == list(REGISTRY[o["provider"]].models) and o["models"][0] == o["default_model"]
    assert next(o for o in options if o["provider"] == "ollama")["env"] == "OLLAMA_HOST"
    assert next(o for o in options if o["provider"] == "gemini")["free_tier"] is True
    assert next(o for o in options if o["provider"] == "openai")["free_tier"] is False
    dumped = json.dumps(options)
    assert "api_key" not in dumped and FAKE_KEY not in dumped


def test_backend_repr_and_safe_dict_omit_key() -> None:
    b = resolve_chat_backend(settings(openrouter_api_key=FAKE_KEY))
    assert b.api_key == FAKE_KEY
    assert FAKE_KEY not in repr(b) and FAKE_KEY not in json.dumps(b.safe_dict())
    assert b.safe_dict()["has_key"] is True and "api_key" not in b.safe_dict()


# ---- OpenAI-compatible loop ------------------------------------------------------------------------------


def test_openai_tools_convert_every_tool() -> None:
    converted = openai_tools()
    assert len(converted) == len(TOOLS) == 8
    for original, out in zip(TOOLS, converted, strict=True):
        assert out["type"] == "function"
        assert out["function"]["name"] == original["name"]
        assert out["function"]["description"] == original["description"]
        assert out["function"]["parameters"] == original["input_schema"]


def _tc(index: int | None, id: str | None = None, name: str | None = None, arguments: str | None = None) -> Any:
    return types.SimpleNamespace(
        index=index, id=id, type="function", function=types.SimpleNamespace(name=name, arguments=arguments)
    )


def test_merge_tool_calls_handles_provider_quirks() -> None:
    pending: list[dict[str, Any]] = []
    # standard OpenAI: index on every delta, arguments streamed
    _merge_tool_call(pending, _tc(0, "call_a", "get_findings", ""))
    _merge_tool_call(pending, _tc(0, None, None, '{"kind": '))
    _merge_tool_call(pending, _tc(0, None, None, '"risk"}'))
    assert [(p["id"], p["name"], p["arguments"]) for p in pending] == [("call_a", "get_findings", '{"kind": "risk"}')]
    # Ollama-style: a second complete call that repeats index 0 with its own id
    _merge_tool_call(pending, _tc(0, "call_b", "get_scenarios", "{}"))
    assert [p["id"] for p in pending] == ["call_a", "call_b"]
    # Gemini-style: whole call in one chunk, no index, no id
    _merge_tool_call(pending, _tc(None, None, "get_adjustments", "{}"))
    assert pending[-1]["name"] == "get_adjustments" and pending[-1]["id"] == ""
    # bare continuation (no index, no id, no name) appends to the last call
    _merge_tool_call(pending, _tc(None, None, None, " "))
    assert pending[-1]["arguments"] == "{} "
    assert (
        _parse_args("") == {}
        and _parse_args("{bad") == {"error": "bad arguments"}
        and _parse_args("[1]") == {"error": "bad arguments"}
    )


def _chunk(content: str | None = None, tool_calls: list[Any] | None = None, finish_reason: str | None = None) -> Any:
    delta = types.SimpleNamespace(content=content, tool_calls=tool_calls, role=None)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(delta=delta, finish_reason=finish_reason, index=0)], usage=None)


def _usage_chunk(prompt: int, completion: int) -> Any:
    return types.SimpleNamespace(choices=[], usage=types.SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion))


class FakeCompletions:
    def __init__(self, script: Any) -> None:
        self.calls: list[dict[str, Any]] = []
        self.script = script

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.script(len(self.calls), kwargs)


class FakeClient:
    def __init__(self, script: Any) -> None:
        self.chat = types.SimpleNamespace(completions=FakeCompletions(script))


def _events(body: str) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for block in body.split("\n\n"):
        lines = block.splitlines()
        if not lines:
            continue
        event = next(line[7:] for line in lines if line.startswith("event: "))
        data = next(line[6:] for line in lines if line.startswith("data: "))
        out.append((event, json.loads(data)))
    return out


GEMINI = ChatBackend(
    name="gemini",
    label="Google Gemini",
    kind="openai_compat",
    model="gemini-3.8-flash",
    base_url=REGISTRY["gemini"].base_url,
    api_key=FAKE_KEY,
    ready=True,
    reason=None,
    free_tier=True,
)


def _install(monkeypatch: pytest.MonkeyPatch, fake: FakeClient) -> None:
    monkeypatch.setattr(chat_service, "resolve_chat_backend", lambda settings=None: GEMINI)
    monkeypatch.setattr("bearcase.api.routes.chat.resolve_chat_backend", lambda settings=None: GEMINI)
    monkeypatch.setattr(openai_compat, "make_client", lambda backend: fake)


def test_openai_compat_end_to_end(client, demo, db, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    seen: dict[str, Any] = {}

    def script(n: int, kwargs: dict[str, Any]) -> Any:
        if n == 1:
            return iter(
                [
                    _chunk(tool_calls=[_tc(0, "call_1", "get_adjustments", "{")]),
                    _chunk(tool_calls=[_tc(0, None, None, "}")]),
                    _chunk(finish_reason="tool_calls"),
                    _usage_chunk(120, 8),
                ]
            )
        tool_msg = next(m for m in kwargs["messages"] if m["role"] == "tool")
        data = json.loads(tool_msg["content"])
        verified = data["ebitda"]["ebitda_adjusted_verified"]
        seen["metric_id"] = verified["metric_id"]
        return iter(
            [
                _chunk(content=f"Verified adjusted EBITDA is {verified['value']} [M:{verified['metric_id']}]."),
                _chunk(content="\n\nOne seller add-back was rejected because the cost recurs."),
                _chunk(finish_reason="stop"),
                _usage_chunk(300, 40),
            ]
        )

    fake = FakeClient(script)
    _install(monkeypatch, fake)
    with client.stream("POST", f"/api/deals/{demo['id']}/chat", json={"message": "Why was adjusted EBITDA reduced?"}) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())
    events = _events(body)
    names = [e for e, _ in events]
    assert names[0] == "meta" and names[-1] == "done" and names[-2] == "citations"
    meta = events[0][1]
    assert meta["provider"] == "gemini" and meta["label"] == "Google Gemini" and meta["model"] == "gemini-3.8-flash"
    assert set(meta) == {"thread_id", "message_id", "provider", "model", "label"}
    tools = [d for e, d in events if e == "tool"]
    assert [(d["name"], d["status"]) for d in tools] == [("get_adjustments", "start"), ("get_adjustments", "done")]
    assert tools[0]["input"] == {} and tools[0]["label"] == "Reading add-back decisions"
    assert names.index("tool") < names.index("text")
    text = "".join(d["delta"] for e, d in events if e == "text")
    assert f"[M:{seen['metric_id']}]" in text
    citations = next(d for e, d in events if e == "citations")
    assert [m["id"] for m in citations["metrics"]] == [seen["metric_id"]] and citations["unresolved"] == 0
    assert citations["metrics"][0]["key"] == "ebitda_adjusted_verified" and citations["scope"] == "deal"
    done = events[-1][1]
    assert done["grounded"] is True and done["error"] is None and "$1,810,000" in done["content"]
    assert done["scope"] == "deal" and set(done) == {"message_id", "grounded", "scope", "content", "error", "model"}
    assert done["model"] == "gemini-3.8-flash"
    # requests: system prompt first, no temperature, usage requested, tools on the tool round, echoed tool call,
    # the output cap and low reasoning effort from settings (Gemini takes max_tokens, not max_completion_tokens)
    calls = fake.chat.completions.calls
    assert len(calls) == 2 and all("temperature" not in c and c.get("stream_options") == {"include_usage": True} for c in calls)
    assert all(c["max_tokens"] == 2048 and c["reasoning_effort"] == "low" and "max_completion_tokens" not in c for c in calls)
    assert calls[0]["stream"] is True and calls[0]["tools"] == openai_tools() and calls[0]["model"] == "gemini-3.8-flash"
    msgs = calls[1]["messages"]
    assert msgs[0]["role"] == "system" and "Northstar" in msgs[0]["content"]
    # the deal brief rides in the system prompt with the id the reply cited
    assert "## Deal brief" in msgs[0]["content"] and "<deal_brief>" in msgs[0]["content"]
    assert "$1,810,000" in msgs[0]["content"] and f"[M:{seen['metric_id'][:8]}" in msgs[0]["content"]
    assistant_turn = next(m for m in msgs if m["role"] == "assistant" and m.get("tool_calls"))
    assert assistant_turn["tool_calls"] == [
        {"id": "call_1", "type": "function", "function": {"name": "get_adjustments", "arguments": "{}"}}
    ]
    assert next(m for m in msgs if m["role"] == "tool")["tool_call_id"] == "call_1"
    # persisted
    thread = client.get(f"/api/deals/{demo['id']}/chat/threads/{meta['thread_id']}").json()
    persisted = thread["messages"][-1]
    assert persisted["provider"] == "gemini" and persisted["model"] == "gemini-3.8-flash" and persisted["grounded"] is True
    assert persisted["tool_calls"][0]["name"] == "get_adjustments" and persisted["tool_calls"][0]["result_chars"] > 100
    assert persisted["citations"]["scope"] == "deal"
    row = db.get(ChatMessage, uuid.UUID(meta["message_id"]))
    assert row is not None and row.usage == {"input_tokens": 420, "output_tokens": 48, "model": "gemini-3.8-flash"}
    # nothing leaks the key
    assert FAKE_KEY not in body
    cfg = client.get(f"/api/deals/{demo['id']}/chat/config").json()
    assert FAKE_KEY not in json.dumps(cfg)
    assert cfg["provider"] == "gemini" and cfg["label"] == "Google Gemini" and cfg["live"] is True
    assert "Google Gemini (gemini-3.8-flash)" in cfg["note"] and [o["provider"] for o in cfg["options"]] == list(OPTION_ORDER)
    # the picker is off by default: one model, no choice
    assert cfg["models"] == ["gemini-3.8-flash"] and cfg["picker"] is False


def test_no_tools_fallback(client, demo, db, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    def script(n: int, kwargs: dict[str, Any]) -> Any:
        if "tools" in kwargs:
            raise openai.BadRequestError(
                "This model does not support tools",
                response=httpx.Response(400, request=httpx.Request("POST", "https://x")),
                body=None,
            )
        return iter(
            [
                _chunk(content="The seller add-backs were reviewed and one was rejected as recurring."),
                _chunk(finish_reason="stop"),
                _usage_chunk(900, 20),
            ]
        )

    fake = FakeClient(script)
    _install(monkeypatch, fake)
    question = "Why was adjusted EBITDA reduced?"
    with client.stream("POST", f"/api/deals/{demo['id']}/chat", json={"message": question}) as resp:
        body = "".join(resp.iter_text())
    events = _events(body)
    names = [e for e, _ in events]
    assert names[0] == "meta" and names[-1] == "done" and "error" not in names
    tools = [d for e, d in events if e == "tool"]
    expected = ["list_claims", "get_adjustments", "get_financials", "get_findings", "get_scenarios", "search_evidence"]
    assert [d["name"] for d in tools if d["status"] == "start"] == expected
    assert [d["name"] for d in tools if d["status"] == "done"] == expected
    search = next(d for d in tools if d["name"] == "search_evidence" and d["status"] == "start")
    assert search["input"] == {"query": question, "limit": 8}
    done = events[-1][1]
    assert done["error"] is None and "rejected" in done["content"]
    calls = fake.chat.completions.calls
    assert len(calls) == 2 and "tools" in calls[0] and "tools" not in calls[1]
    system = calls[1]["messages"][0]
    assert system["role"] == "system" and "<deal_data>" in system["content"]
    assert "ebitda_adjusted_verified" not in system["content"]  # document text never gets system-level authority
    last = calls[1]["messages"][-1]
    assert last["role"] == "user" and last["content"].startswith("<deal_data>")
    assert last["content"].rstrip().endswith(f"Question: {question}")
    assert "ebitda_adjusted_verified" in last["content"] and len(last["content"]) < 24000 + len(question) + 500
    row = db.get(ChatMessage, uuid.UUID(events[0][1]["message_id"]))
    assert row is not None and row.usage["mode"] == "no_tools" and row.usage["input_tokens"] == 900
    assert [t["name"] for t in row.tool_calls] == expected
    assert FAKE_KEY not in body


def test_other_errors_become_error_events(client, demo, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    def script(n: int, kwargs: dict[str, Any]) -> Any:
        raise openai.AuthenticationError(
            "Incorrect API key provided", response=httpx.Response(401, request=httpx.Request("POST", "https://x")), body=None
        )

    fake = FakeClient(script)
    _install(monkeypatch, fake)
    with client.stream("POST", f"/api/deals/{demo['id']}/chat", json={"message": "Which documents are missing?"}) as resp:
        body = "".join(resp.iter_text())
    events = _events(body)
    error = next(d for e, d in events if e == "error")
    assert "rejected the API key" in error["message"] and "_API_KEY" in error["message"]
    assert "AuthenticationError" not in error["message"] and events[-1][0] == "done" and events[-1][1]["error"]
    assert len(fake.chat.completions.calls) == 1 and FAKE_KEY not in body


def test_config_explains_unready_explicit_provider(client, demo, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    unready = resolve_chat_backend(settings(chat_provider="groq"))
    monkeypatch.setattr("bearcase.api.routes.chat.resolve_chat_backend", lambda settings=None: unready)
    cfg = client.get(f"/api/deals/{demo['id']}/chat/config").json()
    assert cfg["provider"] == "mock" and cfg["label"] == "Rule-based composer" and cfg["model"] == "rules-v1"
    assert cfg["live"] is False and cfg["note"].startswith("Groq was requested but is not ready: set GROQ_API_KEY")
    assert cfg["suggested"] and len(cfg["options"]) == 6


def test_config_in_mock_mode_has_contract_shape(client, demo, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    cfg = client.get(f"/api/deals/{demo['id']}/chat/config").json()
    assert set(cfg) == {"provider", "label", "model", "live", "note", "suggested", "models", "picker", "options", "budget"}
    # the test suite pins BEARCASE_CHAT_PROVIDER=mock, which gets the explicit-selection note
    assert cfg["provider"] == "mock" and cfg["live"] is False and "rule-based composer" in cfg["note"]
    assert cfg["models"] == ["rules-v1"] and cfg["picker"] is False and len(cfg["suggested"]) == 6
    assert "Explain DSCR like I'm new to this" in cfg["suggested"] and "Which documents are missing?" in cfg["suggested"]
    # auto mode with no key anywhere tells the user what to do
    from bearcase.api.routes import chat as chat_routes

    monkeypatch.setattr(chat_routes, "get_settings", lambda: settings())
    cfg = client.get(f"/api/deals/{demo['id']}/chat/config").json()
    assert cfg["provider"] == "mock" and cfg["live"] is False and "No model key is configured" in cfg["note"]
    assert [o["provider"] for o in cfg["options"]] == list(OPTION_ORDER)


def test_describe_error_maps_provider_failures_and_redacts_keys() -> None:
    backend = ChatBackend(
        name="gemini",
        label="Google Gemini",
        kind="openai_compat",
        model="gemini-3.8-flash",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key="not-a-real-key-zz9",
        ready=True,
        reason=None,
        free_tier=True,
    )
    req = httpx.Request("POST", "https://x")
    auth = openai.AuthenticationError("bad key", response=httpx.Response(401, request=req), body=None)
    assert chat_service.describe_error(auth, backend) == (
        "Google Gemini rejected the API key. Check GEMINI_API_KEY in .env and restart the API."
    )
    # Gemini answers a bad key with a 400 whose text names the key; the text, not the status, decides.
    bad = openai.BadRequestError("Please pass a valid API key", response=httpx.Response(400, request=req), body=None)
    assert "rejected the API key" in chat_service.describe_error(bad, backend)
    limited = openai.RateLimitError("slow down", response=httpx.Response(429, request=req), body=None)
    assert "rate limit" in chat_service.describe_error(limited, backend)
    missing = openai.NotFoundError("model not found", response=httpx.Response(404, request=req), body=None)
    assert "gemini-3.8-flash" in chat_service.describe_error(missing, backend)
    busy = openai.InternalServerError("high demand", response=httpx.Response(503, request=req), body=None)
    assert "temporarily unavailable" in chat_service.describe_error(busy, backend)
    conn = openai.APIConnectionError(request=req)
    assert "Could not reach Google Gemini" in chat_service.describe_error(conn, backend)
    leaked = RuntimeError("upstream said not-a-real-key-zz9 is wrong")
    text = chat_service.describe_error(leaked, backend)
    assert "not-a-real-key-zz9" not in text and "[redacted]" in text
    assert chat_service.describe_error(RuntimeError("boom"), MOCK_BACKEND) == "RuntimeError: boom"


def _stream_once(client, demo, monkeypatch: pytest.MonkeyPatch, script: Any, message: str) -> list[tuple[str, dict[str, Any]]]:  # type: ignore[no-untyped-def]
    _install(monkeypatch, FakeClient(script))
    with client.stream("POST", f"/api/deals/{demo['id']}/chat", json={"message": message}) as resp:
        body = "".join(resp.iter_text())
    assert FAKE_KEY not in body
    return _events(body)


@pytest.mark.parametrize("finish", ["content_filter", "length", "MALFORMED_FUNCTION_CALL"])
def test_empty_round_with_abnormal_finish_is_an_error_not_a_grounded_reply(client, demo, db, monkeypatch, finish) -> None:  # type: ignore[no-untyped-def]
    events = _stream_once(client, demo, monkeypatch, lambda n, kw: iter([_chunk(content=None, finish_reason=finish)]), "Risks?")
    error = next(d for e, d in events if e == "error")
    assert finish in error["message"] and "no answer" in error["message"]
    done = events[-1][1]
    assert done["error"] and done["content"] == ""
    row = db.get(ChatMessage, uuid.UUID(events[0][1]["message_id"]))
    assert row is not None and row.error and finish in row.error


def test_truncated_answer_keeps_text_and_reports_cut_off(client, demo, db, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    script = lambda n, kw: iter([_chunk(content="No documents are missing from the deal room."), _chunk(finish_reason="length")])  # noqa: E731
    events = _stream_once(client, demo, monkeypatch, script, "Which documents are missing?")
    error = next(d for e, d in events if e == "error")
    assert "cut off" in error["message"] and "length" in error["message"]
    done = events[-1][1]
    assert done["content"].startswith("No documents") and "length" in done["error"]
    row = db.get(ChatMessage, uuid.UUID(events[0][1]["message_id"]))
    assert row is not None and row.content.startswith("No documents") and row.error


def test_usage_is_requested_and_taken_once_per_request(client, demo, db, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    seen: list[dict[str, Any]] = []

    def script(n: int, kwargs: dict[str, Any]) -> Any:
        seen.append(kwargs)
        # cumulative usage repeated on several chunks (Gemini-style) must not be summed
        return iter(
            [
                _chunk(content="No documents are missing from the deal room."),
                _usage_chunk(100, 1),
                _usage_chunk(100, 2),
                _chunk(finish_reason="stop"),
                _usage_chunk(100, 3),
            ]
        )

    events = _stream_once(client, demo, monkeypatch, script, "Which documents are missing?")
    assert seen and seen[0]["stream_options"] == {"include_usage": True}
    row = db.get(ChatMessage, uuid.UUID(events[0][1]["message_id"]))
    assert row is not None and row.error is None
    assert row.usage == {"input_tokens": 100, "output_tokens": 3, "model": "gemini-3.8-flash"}


def test_max_tool_rounds_is_reported_and_stored(client, demo, db, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def script(n: int, kwargs: dict[str, Any]) -> Any:
        call = types.SimpleNamespace(index=0, id=f"call_{n}", function=types.SimpleNamespace(name="get_findings", arguments="{}"))
        return iter([_chunk(tool_calls=[call]), _chunk(finish_reason="tool_calls")])

    events = _stream_once(client, demo, monkeypatch, script, "What are the biggest risks?")
    error = next(d for e, d in events if e == "error")
    assert "maximum number of tool rounds" in error["message"]
    row = db.get(ChatMessage, uuid.UUID(events[0][1]["message_id"]))
    assert row is not None and row.error and len(row.tool_calls) == chat_service.MAX_TOOL_ROUNDS + 1


# ---- general assistant: scope, model picker, model override -------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["gemini-2.5-flash", "openai/gpt-oss-120b", "z-ai/glm-5.2:free", "qwen3:8b", "claude-haiku-4-5", "a", "a" * 80],
)
def test_valid_model_ids(value: str) -> None:
    assert validate_model_id(value)


@pytest.mark.parametrize(
    "value",
    ["", "../x", "a b", "a" * 100, "a" * 81, "-lead", ".hidden", "/abs", "x\n", "model;rm -rf", "gemini 2.5", "ünïcode"],
)
def test_invalid_model_ids(value: str) -> None:
    assert not validate_model_id(value)


def test_models_for_lists_provider_ids_default_first() -> None:
    for spec in REGISTRY.values():
        assert all(validate_model_id(m) for m in spec.models)
        if spec.models:
            assert spec.models[0] == spec.default_model
    assert models_for(MOCK_BACKEND) == ["rules-v1"]
    s = settings(gemini_api_key="k")
    assert models_for(resolve_chat_backend(s), s) == list(REGISTRY["gemini"].models)
    assert models_for(resolve_chat_backend(s), s)[0] == "gemini-3.8-flash"
    # BEARCASE_CHAT_MODEL leads the list, whether or not it is one of the known ids, and is never repeated
    s = settings(gemini_api_key="k", chat_model="gemini-2.5-flash")
    listed = models_for(resolve_chat_backend(s), s)
    assert listed[0] == "gemini-2.5-flash" and listed.count("gemini-2.5-flash") == 1 and len(listed) == 5
    s = settings(groq_api_key="k", chat_model="meta-llama/llama-4-scout")
    assert models_for(resolve_chat_backend(s), s) == ["meta-llama/llama-4-scout", *REGISTRY["groq"].models]
    # an explicit BEARCASE_AI_MODEL drives Anthropic chat, so it must stay pickable
    s = settings(anthropic_api_key="a", ai_model="claude-sonnet-5")
    listed = models_for(resolve_chat_backend(s), s)
    assert listed[0] == "claude-sonnet-5" and listed.count("claude-sonnet-5") == 1 and len(listed) == 3
    s = settings(chat_provider="ollama")
    assert models_for(resolve_chat_backend(s), s) == list(REGISTRY["ollama"].models)
    # a custom server lists only the configured model
    s = settings(chat_provider="custom", chat_base_url="http://localhost:1234/v1", chat_model="local-model")
    assert models_for(resolve_chat_backend(s), s) == ["local-model"]


def test_config_lists_models_for_the_live_backend_and_chat_model_first(client, demo, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _install(monkeypatch, FakeClient(lambda n, kw: iter([])))
    from bearcase.api.routes import chat as chat_routes

    # picker off (the default): the configured model and nothing to choose from
    cfg = client.get(f"/api/deals/{demo['id']}/chat/config").json()
    assert cfg["live"] is True and cfg["model"] == "gemini-3.8-flash"
    assert cfg["models"] == ["gemini-3.8-flash"] and cfg["picker"] is False
    # picker on: the provider's full list, default first
    monkeypatch.setattr(chat_routes, "get_settings", lambda: settings(chat_model_picker=True))
    cfg = client.get(f"/api/deals/{demo['id']}/chat/config").json()
    assert cfg["picker"] is True and cfg["models"][0] == "gemini-3.8-flash" and cfg["models"] == list(REGISTRY["gemini"].models)
    monkeypatch.setattr(chat_routes, "get_settings", lambda: settings(chat_model_picker=True, chat_model="gemini-2.5-flash-lite"))
    cfg = client.get(f"/api/deals/{demo['id']}/chat/config").json()
    assert cfg["models"][0] == "gemini-2.5-flash-lite" and cfg["models"].count("gemini-2.5-flash-lite") == 1
    assert len(cfg["models"]) == 5
    monkeypatch.setattr(chat_routes, "get_settings", lambda: settings(chat_model_picker=True, chat_model="gemini-9-preview"))
    cfg = client.get(f"/api/deals/{demo['id']}/chat/config").json()
    assert cfg["models"][:2] == ["gemini-9-preview", "gemini-3.8-flash"] and len(cfg["models"]) == 6
    assert FAKE_KEY not in json.dumps(cfg)


def test_general_reply_has_general_scope_and_is_persisted(client, demo, db, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    prose = (
        "In general, **DSCR** compares the cash available for debt service with the debt service due.\n\n"
        "Lenders read it as a cushion: the higher it is, the more room there is before a payment is missed."
    )
    script = lambda n, kw: iter([_chunk(content=prose), _chunk(finish_reason="stop")])  # noqa: E731
    events = _stream_once(client, demo, monkeypatch, script, "Explain DSCR like I'm new to this")
    names = [e for e, _ in events]
    assert names[0] == "meta" and "tool" not in names and "error" not in names and names[-1] == "done"
    citations = next(d for e, d in events if e == "citations")
    assert citations["scope"] == "general" and citations["evidence"] == [] and citations["metrics"] == []
    assert citations["unresolved"] == 0 and citations["material_sentences"] == 0
    done = events[-1][1]
    assert done["scope"] == "general" and done["grounded"] is True and done["content"] == prose and done["error"] is None
    row = db.get(ChatMessage, uuid.UUID(events[0][1]["message_id"]))
    assert row is not None and row.citations["scope"] == "general" and row.grounded is True and row.tool_calls == []
    audit = db.scalar(select(AuditEvent).where(AuditEvent.object_id == row.id, AuditEvent.event_type == "chat.reply"))
    assert audit is not None and audit.payload["scope"] == "general" and "scope=general" in audit.summary
    # An uncited figure is never labelled general knowledge: the reply is not grounded, so its scope is "deal"
    # and the UI shows the citation warning instead of the neutral label.
    numeric = "In general, a DSCR of 1.25x is a common covenant floor; below 1.0x the business cannot cover its debt service."
    script = lambda n, kw: iter([_chunk(content=numeric), _chunk(finish_reason="stop")])  # noqa: E731
    events = _stream_once(client, demo, monkeypatch, script, "What DSCR do lenders want?")
    citations = next(d for e, d in events if e == "citations")
    assert citations["scope"] == "deal" and citations["material_sentences"] == 1 and citations["cited_sentences"] == 0
    done = events[-1][1]
    assert done["scope"] == "deal" and done["grounded"] is False and done["content"] == numeric
    row = db.get(ChatMessage, uuid.UUID(events[0][1]["message_id"]))
    assert row is not None and row.citations["scope"] == "deal" and row.grounded is False


def test_tool_call_or_resolved_marker_makes_scope_deal(client, demo, db, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # a tool ran, even though the prose carries no marker
    def script(n: int, kwargs: dict[str, Any]) -> Any:
        if n == 1:
            return iter([_chunk(tool_calls=[_tc(0, "call_1", "get_findings", "{}")]), _chunk(finish_reason="tool_calls")])
        return iter(
            [_chunk(content="There are several findings, including customer concentration."), _chunk(finish_reason="stop")]
        )

    events = _stream_once(client, demo, monkeypatch, script, "What are the biggest risks?")
    citations = next(d for e, d in events if e == "citations")
    done = events[-1][1]
    # deal scope, but not grounded: a reply that read the deal room and cites nothing gives the reader nothing to open
    assert citations["scope"] == "deal" and done["scope"] == "deal" and done["grounded"] is False and done["error"] is None
    row = db.get(ChatMessage, uuid.UUID(events[0][1]["message_id"]))
    assert row is not None and row.citations["scope"] == "deal" and [t["name"] for t in row.tool_calls] == ["get_findings"]
    # a marker resolved (an id remembered from earlier in the thread), even though no tool ran this turn
    metric = db.scalar(
        select(FinancialMetric).where(
            FinancialMetric.deal_id == uuid.UUID(demo["id"]), FinancialMetric.key == "ebitda_adjusted_verified"
        )
    )
    assert metric is not None
    cited = f"Verified adjusted EBITDA is ${metric.value:,.0f} [M:{metric.id}]."
    script2 = lambda n, kw: iter([_chunk(content=cited), _chunk(finish_reason="stop")])  # noqa: E731
    events = _stream_once(client, demo, monkeypatch, script2, "Remind me of the verified EBITDA")
    citations = next(d for e, d in events if e == "citations")
    done = events[-1][1]
    assert citations["scope"] == "deal" and [m["id"] for m in citations["metrics"]] == [str(metric.id)]
    assert done["scope"] == "deal" and done["grounded"] is True
    row = db.get(ChatMessage, uuid.UUID(events[0][1]["message_id"]))
    assert row is not None and row.citations["scope"] == "deal" and row.tool_calls == []


def test_model_override_reaches_provider_meta_and_rows(client, demo, db, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    seen: list[dict[str, Any]] = []

    def script(n: int, kwargs: dict[str, Any]) -> Any:
        seen.append(kwargs)
        return iter(
            [
                _chunk(content="In general, DSCR is cash available for debt service over debt service."),
                _chunk(finish_reason="stop"),
            ]
        )

    _install(monkeypatch, FakeClient(script))
    url = f"/api/deals/{demo['id']}/chat"
    with client.stream("POST", url, json={"message": "Explain DSCR like I'm new to this", "model": "gemini-2.5-flash"}) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())
    events = _events(body)
    meta = events[0][1]
    assert meta["provider"] == "gemini" and meta["label"] == "Google Gemini" and meta["model"] == "gemini-2.5-flash"
    assert set(meta) == {"thread_id", "message_id", "provider", "model", "label"}
    assert len(seen) == 1 and seen[0]["model"] == "gemini-2.5-flash"
    thread = client.get(f"/api/deals/{demo['id']}/chat/threads/{meta['thread_id']}").json()
    assert [(m["role"], m["provider"], m["model"]) for m in thread["messages"]] == [
        ("user", "gemini", "gemini-2.5-flash"),
        ("assistant", "gemini", "gemini-2.5-flash"),
    ]
    audit = db.scalar(select(AuditEvent).where(AuditEvent.object_id == uuid.UUID(meta["message_id"])))
    assert audit is not None and "gemini/gemini-2.5-flash" in audit.summary
    # the override is per request: a follow-up on the same thread without one uses the configured model
    with client.stream("POST", url, json={"message": "And DSCR here?", "thread_id": meta["thread_id"]}) as resp:
        follow = _events("".join(resp.iter_text()))
    assert follow[0][1]["model"] == "gemini-3.8-flash" and seen[1]["model"] == "gemini-3.8-flash"
    assert [m["model"] for m in client.get(f"/api/deals/{demo['id']}/chat/threads/{meta['thread_id']}").json()["messages"]] == [
        "gemini-2.5-flash",
        "gemini-2.5-flash",
        "gemini-3.8-flash",
        "gemini-3.8-flash",
    ]
    assert FAKE_KEY not in body


@pytest.mark.parametrize("bad", ["../x", "a b", "a" * 100, "", "-lead", "gemini\n"])
def test_invalid_model_ids_are_rejected_before_any_row_is_written(client, demo, db, monkeypatch, bad: str) -> None:  # type: ignore[no-untyped-def]
    fake = FakeClient(lambda n, kw: iter([]))
    _install(monkeypatch, fake)
    threads_before = db.scalar(select(func.count()).select_from(ChatThread))
    messages_before = db.scalar(select(func.count()).select_from(ChatMessage))
    r = client.post(f"/api/deals/{demo['id']}/chat", json={"message": "hello", "model": bad})
    assert r.status_code == 400 and r.json()["detail"] == "Unknown model id."
    assert fake.chat.completions.calls == []
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(ChatThread)) == threads_before
    assert db.scalar(select(func.count()).select_from(ChatMessage)) == messages_before


def test_model_override_is_ignored_by_the_rule_based_composer(client, demo) -> None:  # type: ignore[no-untyped-def]
    # the suite pins BEARCASE_CHAT_PROVIDER=mock and nothing is patched here
    url = f"/api/deals/{demo['id']}/chat"
    with client.stream("POST", url, json={"message": "Why was adjusted EBITDA reduced?", "model": "gemini-2.5-flash"}) as resp:
        assert resp.status_code == 200
        events = _events("".join(resp.iter_text()))
    meta = events[0][1]
    assert meta["provider"] == "mock" and meta["model"] == "rules-v1" and meta["label"] == "Rule-based composer"
    done = events[-1][1]
    assert done["scope"] == "deal" and done["grounded"] is True and done["error"] is None
    thread = client.get(f"/api/deals/{demo['id']}/chat/threads/{meta['thread_id']}").json()
    assert [(m["provider"], m["model"]) for m in thread["messages"]] == [("mock", "rules-v1"), ("mock", "rules-v1")]
    assert thread["messages"][-1]["citations"]["scope"] == "deal"


# ---- scope, code regions, model allowlist, interrupted replies -------------------------------------------


def _deal(db, demo) -> Deal:  # type: ignore[no-untyped-def]
    deal = db.get(Deal, uuid.UUID(demo["id"]))
    assert deal is not None
    return deal


def _metric(db, demo, key: str = "ebitda_adjusted_verified") -> FinancialMetric:  # type: ignore[no-untyped-def]
    metric = db.scalar(
        select(FinancialMetric).where(FinancialMetric.deal_id == uuid.UUID(demo["id"]), FinancialMetric.key == key)
    )
    assert metric is not None
    return metric


def test_numeric_marker_free_follow_up_in_a_deal_thread_is_deal_scope_and_ungrounded(client, demo, db, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    metric = _metric(db, demo)

    def first(n: int, kwargs: dict[str, Any]) -> Any:
        if n == 1:
            return iter([_chunk(tool_calls=[_tc(0, "call_1", "get_adjustments", "{}")]), _chunk(finish_reason="tool_calls")])
        return iter([_chunk(content=f"Verified adjusted EBITDA is $1,810,000 [M:{metric.id}]."), _chunk(finish_reason="stop")])

    _install(monkeypatch, FakeClient(first))
    url = f"/api/deals/{demo['id']}/chat"
    with client.stream("POST", url, json={"message": "Why was adjusted EBITDA reduced?"}) as resp:
        opening = _events("".join(resp.iter_text()))
    thread_id = opening[0][1]["thread_id"]
    assert opening[-1][1]["scope"] == "deal" and opening[-1][1]["grounded"] is True
    # the follow-up restates the number from memory: no tool, no marker
    restated = "As I said, adjusted EBITDA came to $1,810,000 after the add-backs were reviewed."
    _install(monkeypatch, FakeClient(lambda n, kw: iter([_chunk(content=restated), _chunk(finish_reason="stop")])))
    with client.stream("POST", url, json={"message": "Remind me of the number", "thread_id": thread_id}) as resp:
        events = _events("".join(resp.iter_text()))
    assert "tool" not in [e for e, _ in events]
    citations = next(d for e, d in events if e == "citations")
    assert citations["scope"] == "deal" and citations["evidence"] == [] and citations["metrics"] == []
    assert citations["material_sentences"] == 1 and citations["cited_sentences"] == 0
    done = events[-1][1]
    assert done["scope"] == "deal" and done["grounded"] is False and done["content"] == restated and done["error"] is None
    row = db.get(ChatMessage, uuid.UUID(events[0][1]["message_id"]))
    assert row is not None and row.citations["scope"] == "deal" and row.grounded is False and row.tool_calls == []
    audit = db.scalar(select(AuditEvent).where(AuditEvent.object_id == row.id, AuditEvent.event_type == "chat.reply"))
    assert audit is not None and audit.payload["scope"] == "deal" and "scope=deal, grounded=False" in audit.summary
    persisted = client.get(f"/api/deals/{demo['id']}/chat/threads/{thread_id}").json()["messages"][-1]
    assert persisted["citations"]["scope"] == "deal" and persisted["grounded"] is False


def test_markers_inside_code_are_left_literal_and_not_counted(db, demo) -> None:  # type: ignore[no-untyped-def]
    deal, metric = _deal(db, demo), _metric(db, demo)
    short = str(metric.id)[:8]
    text = (
        f"A marker looks like `[M:{short}]` and is validated on the server.\n\n"
        "```python\nrevenue = 4_200_000  # [E:deadbeef]\nprint(revenue * 1.05)\n```\n\n"
        "In general, lenders want a cushion above the covenant floor."
    )
    cleaned, citations, grounded = chat_service.resolve_citations(db, deal, text)
    assert cleaned == text  # nothing expanded, nothing dropped, nothing re-spaced
    assert citations["metrics"] == [] and citations["evidence"] == [] and citations["unresolved"] == 0
    assert citations["material_sentences"] == 0 and citations["cited_sentences"] == 0 and grounded is True
    # the same short marker in prose resolves and is expanded to the full id
    cleaned, citations, grounded = chat_service.resolve_citations(
        db, deal, f"Verified adjusted EBITDA is $1,810,000 [M:{short}]."
    )
    assert cleaned == f"Verified adjusted EBITDA is $1,810,000 [M:{metric.id}]."
    assert [m["id"] for m in citations["metrics"]] == [str(metric.id)] and grounded is True
    # an unresolvable marker in prose is dropped and counted; the same marker in a span is not
    cleaned, citations, grounded = chat_service.resolve_citations(db, deal, "See [E:deadbeef] and `[E:deadbeef]`.")
    assert cleaned == "See  and `[E:deadbeef]`." and citations["unresolved"] == 1 and grounded is False
    # an unterminated fence keeps the rest of the text verbatim
    cleaned, citations, grounded = chat_service.resolve_citations(db, deal, "Start\n\n```\n[E:deadbeef] 12\n")
    assert cleaned == "Start\n\n```\n[E:deadbeef] 12\n" and citations["unresolved"] == 0 and grounded is True


def test_headings_and_ordered_list_markers_are_not_figures(db, demo) -> None:  # type: ignore[no-untyped-def]
    deal = _deal(db, demo)
    text = "## 3 risks\n\n1. Owner salary\n2. Rent\n3) Customer concentration\n\nIn general, lenders look at coverage first."
    cleaned, citations, grounded = chat_service.resolve_citations(db, deal, text)
    assert cleaned == text and citations["material_sentences"] == 0 and grounded is True
    # a figure after the list marker still counts
    _, citations, grounded = chat_service.resolve_citations(db, deal, "## 3 risks\n\n1. Owner salary of $120,000 was added back.")
    assert citations["material_sentences"] == 1 and citations["cited_sentences"] == 0 and grounded is False
    # and so does one in a heading's paragraph body
    _, citations, grounded = chat_service.resolve_citations(db, deal, "## Add-backs\nThe seller listed 4 add-backs.")
    assert citations["material_sentences"] == 1 and grounded is False


def test_fenced_block_with_numbers_is_ignored(db, demo) -> None:  # type: ignore[no-untyped-def]
    deal = _deal(db, demo)
    text = "Here is the formula:\n\n```\ndscr = 1.25\n\ncushion = 0.25\n```\n\nThat is all."
    cleaned, citations, grounded = chat_service.resolve_citations(db, deal, text)
    assert cleaned == text and citations["material_sentences"] == 0 and citations["cited_sentences"] == 0 and grounded is True
    # a figure in the prose around the block is still material
    _, citations, grounded = chat_service.resolve_citations(db, deal, "DSCR was 1.4x.\n\n```\nx = 1\n```")
    assert citations["material_sentences"] == 1 and grounded is False


def test_model_override_outside_the_offered_list_is_rejected(client, demo, db, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fake = FakeClient(lambda n, kw: iter([_chunk(content="In general, DSCR is a coverage ratio."), _chunk(finish_reason="stop")]))
    _install(monkeypatch, fake)
    threads_before = db.scalar(select(func.count()).select_from(ChatThread))
    messages_before = db.scalar(select(func.count()).select_from(ChatMessage))
    url = f"/api/deals/{demo['id']}/chat"
    r = client.post(url, json={"message": "hello", "model": "gemini-9-preview"})
    assert r.status_code == 400 and r.json()["detail"] == "Model is not offered for the connected provider."
    r = client.post(url, json={"message": "hello", "model": "claude-haiku-4-5"})
    assert r.status_code == 400 and r.json()["detail"] == "Model is not offered for the connected provider."
    assert fake.chat.completions.calls == []
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(ChatThread)) == threads_before
    assert db.scalar(select(func.count()).select_from(ChatMessage)) == messages_before
    # an offered id is accepted
    with client.stream("POST", url, json={"message": "hello", "model": "gemini-2.5-flash-lite"}) as resp:
        assert resp.status_code == 200
        events = _events("".join(resp.iter_text()))
    assert (
        events[0][1]["model"] == "gemini-2.5-flash-lite" and fake.chat.completions.calls[-1]["model"] == "gemini-2.5-flash-lite"
    )
    # BEARCASE_CHAT_MODEL is offered too, whether or not it is a known id
    from bearcase.api.routes import chat as chat_routes

    monkeypatch.setattr(chat_routes, "get_settings", lambda: settings(chat_model="gemini-9-preview"))
    with client.stream("POST", url, json={"message": "hello", "model": "gemini-9-preview"}) as resp:
        assert resp.status_code == 200
        events = _events("".join(resp.iter_text()))
    assert events[0][1]["model"] == "gemini-9-preview" and fake.chat.completions.calls[-1]["model"] == "gemini-9-preview"


def test_message_out_always_carries_citation_lists(client, demo, db) -> None:  # type: ignore[no-untyped-def]
    deal = _deal(db, demo)
    thread = ChatThread(deal_id=deal.id, user_id=deal.owner_id, title="legacy")
    db.add(thread)
    db.flush()
    db.add(ChatMessage(thread_id=thread.id, role="user", content="hi", provider="mock", model="rules-v1", prompt_version="v0"))
    db.add(
        ChatMessage(
            thread_id=thread.id,
            role="assistant",
            content="",
            citations={},
            provider="mock",
            model="rules-v1",
            prompt_version="v0",
        )
    )
    db.commit()
    out = client.get(f"/api/deals/{demo['id']}/chat/threads/{thread.id}").json()
    assert [m["citations"] for m in out["messages"]] == [{"evidence": [], "metrics": []}, {"evidence": [], "metrics": []}]
    assert out["messages"][1]["content"] == "" and out["messages"][1]["error"] is None and out["messages"][1]["grounded"] is False


def test_disconnect_mid_stream_persists_a_stopped_reply(db, demo) -> None:  # type: ignore[no-untyped-def]
    # Starlette's TestClient buffers the whole response before returning it, so an early exit from
    # client.stream() never closes the generator; drive stream_reply directly the way the server does.
    deal = _deal(db, demo)
    thread = ChatThread(deal_id=deal.id, user_id=deal.owner_id)
    db.add(thread)
    db.commit()
    assert deal.owner_id is not None
    gen = chat_service.stream_reply(db, deal, thread, deal.owner_id, "Why was adjusted EBITDA reduced?")
    meta = _events(next(gen))[0]
    assert meta[0] == "meta" and meta[1]["provider"] == "mock"
    second = _events(next(gen))[0]
    assert second[0] == "tool" and second[1]["status"] == "start"
    gen.close()
    with pytest.raises(StopIteration):
        next(gen)
    row = db.get(ChatMessage, uuid.UUID(meta[1]["message_id"]))
    assert row is not None and row.error == "Stopped before the reply finished." and row.content == ""
    assert row.citations["evidence"] == [] and row.citations["metrics"] == [] and row.citations["scope"] == "deal"
    assert (  # a tool ran and nothing was cited, so the stopped reply is not grounded
        row.citations["unresolved"] == 0 and row.grounded is False and [t["name"] for t in row.tool_calls] == ["get_adjustments"]
    )
    audit = db.scalar(select(AuditEvent).where(AuditEvent.object_id == row.id, AuditEvent.event_type == "chat.reply"))
    assert audit is not None and audit.payload["error"] == "Stopped before the reply finished."
    assert audit.payload["tools"] == ["get_adjustments"] and "scope=deal" in audit.summary
    # what was streamed before the stop is kept: read up to the first text frame, then close
    db.expire_all()  # a real request gets a fresh session; this test reuses one
    gen = chat_service.stream_reply(db, deal, thread, deal.owner_id, "What are the biggest risks?")
    frames = [_events(next(gen))[0] for _ in range(1)]
    while frames[-1][0] != "text":
        frames.append(_events(next(gen))[0])
    gen.close()
    row2 = db.get(ChatMessage, uuid.UUID(frames[0][1]["message_id"]))
    assert row2 is not None and row2.error == "Stopped before the reply finished."
    assert row2.content == frames[-1][1]["delta"] and row2.content.strip()
    assert set(row2.citations) >= {"evidence", "metrics", "unresolved", "scope"}
    # the stopped replies are stored, shown as errors, and excluded from the history sent to the model
    db.expire_all()
    assert [(m.role, bool(m.error)) for m in thread.messages] == [("user", False), ("assistant", True)] * 2
    assert [m["role"] for m in chat_service._history(thread)] == ["user"]


# ---- speed and resilience: fast failure, the fallback chain, request knobs, the brief ------------------------


GENERAL = "In general, a covenant is a promise the borrower makes to the lender."


def _busy(status: int = 503, message: str = "The model is overloaded. Please try again later.") -> openai.APIStatusError:
    response = httpx.Response(status, request=httpx.Request("POST", "https://x"))
    body = {"error": {"message": message, "status": "UNAVAILABLE"}}
    if status >= 500:
        return openai.InternalServerError(message, response=response, body=body)
    return openai.APIStatusError(message, response=response, body=body)


def _answer(*pieces: str) -> Any:
    return iter([*(_chunk(content=p) for p in pieces), _chunk(finish_reason="stop"), _usage_chunk(50, 10)])


def _backend(name: str, model: str = "m") -> ChatBackend:
    return ChatBackend(
        name=name,
        label=name,
        kind="openai_compat",
        model=model,
        base_url=None,
        api_key="k",
        ready=True,
        reason=None,
        free_tier=True,
    )


def test_busy_model_switches_to_the_next_in_the_chain(client, demo, db, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def script(n: int, kwargs: dict[str, Any]) -> Any:
        if n == 1:
            raise _busy(503, "The model is overloaded due to high demand")
        return _answer(GENERAL)

    fake = FakeClient(script)
    _install(monkeypatch, fake)
    url = f"/api/deals/{demo['id']}/chat"
    with client.stream("POST", url, json={"message": "What is a covenant?"}) as resp:
        body = "".join(resp.iter_text())
    events = _events(body)
    assert [e for e, _ in events] == ["meta", "switch", "text", "citations", "done"]
    meta = events[0][1]
    assert meta["model"] == "gemini-3.8-flash"  # what was asked for; the switch and done say what answered
    assert events[1][1] == {
        "from": "gemini-3.8-flash",
        "to": "gemini-3.7-flash",
        "message": "gemini-3.8-flash is busy; answering with gemini-3.7-flash.",
    }
    done = events[-1][1]
    assert done["model"] == "gemini-3.7-flash" and done["error"] is None and done["content"] == GENERAL
    calls = fake.chat.completions.calls
    assert [c["model"] for c in calls] == ["gemini-3.8-flash", "gemini-3.7-flash"]
    assert calls[0]["messages"] == calls[1]["messages"]  # the next model starts from the same prompt
    thread = client.get(f"/api/deals/{demo['id']}/chat/threads/{meta['thread_id']}").json()
    assert [(m["role"], m["model"]) for m in thread["messages"]] == [
        ("user", "gemini-3.7-flash"),
        ("assistant", "gemini-3.7-flash"),
    ]
    row = db.get(ChatMessage, uuid.UUID(meta["message_id"]))
    assert row is not None and row.usage == {"model": "gemini-3.7-flash", "input_tokens": 50, "output_tokens": 10}
    audit = db.scalar(select(AuditEvent).where(AuditEvent.object_id == row.id, AuditEvent.event_type == "chat.reply"))
    assert audit is not None and "gemini/gemini-3.7-flash" in audit.summary
    assert FAKE_KEY not in body


def test_rate_limit_never_switches(client, demo, db, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def script(n: int, kwargs: dict[str, Any]) -> Any:
        raise openai.RateLimitError(
            "Resource exhausted: the model is unavailable under high demand",
            response=httpx.Response(429, request=httpx.Request("POST", "https://x")),
            body=None,
        )

    fake = FakeClient(script)
    _install(monkeypatch, fake)
    events = _stream_once(client, demo, monkeypatch, script, "What is a covenant?")
    names = [e for e, _ in events]
    assert "switch" not in names and "error" in names
    assert "rate limit" in next(d for e, d in events if e == "error")["message"]
    done = events[-1][1]
    assert done["model"] == "gemini-3.8-flash" and done["error"]
    row = db.get(ChatMessage, uuid.UUID(events[0][1]["message_id"]))
    assert row is not None and row.model == "gemini-3.8-flash" and row.usage == {"model": "gemini-3.8-flash"}


def test_no_switch_once_text_has_streamed(client, demo, db, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def broken() -> Any:
        yield _chunk(content="Adjusted EBITDA was reduced because")
        raise _busy(503)

    fake = FakeClient(lambda n, kw: broken())
    _install(monkeypatch, fake)
    with client.stream("POST", f"/api/deals/{demo['id']}/chat", json={"message": "Why was adjusted EBITDA reduced?"}) as resp:
        events = _events("".join(resp.iter_text()))
    names = [e for e, _ in events]
    assert "switch" not in names and names.index("text") < names.index("error")
    assert "temporarily unavailable" in next(d for e, d in events if e == "error")["message"]
    done = events[-1][1]
    assert done["content"].startswith("Adjusted EBITDA") and done["model"] == "gemini-3.8-flash" and done["error"]
    assert len(fake.chat.completions.calls) == 1
    row = db.get(ChatMessage, uuid.UUID(events[0][1]["message_id"]))
    assert row is not None and row.error and row.content.startswith("Adjusted EBITDA")


def test_no_switch_after_a_tool_round(client, demo, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def script(n: int, kwargs: dict[str, Any]) -> Any:
        if n == 1:
            return iter([_chunk(tool_calls=[_tc(0, "call_1", "get_findings", "{}")]), _chunk(finish_reason="tool_calls")])
        raise _busy(502)

    fake = FakeClient(script)
    _install(monkeypatch, fake)
    with client.stream("POST", f"/api/deals/{demo['id']}/chat", json={"message": "What are the biggest risks?"}) as resp:
        events = _events("".join(resp.iter_text()))
    names = [e for e, _ in events]
    assert "tool" in names and "switch" not in names and "error" in names
    assert [c["model"] for c in fake.chat.completions.calls] == ["gemini-3.8-flash", "gemini-3.8-flash"]
    assert events[-1][1]["model"] == "gemini-3.8-flash"


def test_exhausted_chain_reports_the_last_error(client, demo, db, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def script(n: int, kwargs: dict[str, Any]) -> Any:
        raise _busy(503 if n < 4 else 504, f"attempt {n} failed")

    fake = FakeClient(script)
    _install(monkeypatch, fake)
    with client.stream("POST", f"/api/deals/{demo['id']}/chat", json={"message": "What is a covenant?"}) as resp:
        body = "".join(resp.iter_text())
    events = _events(body)
    chain = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]
    switches = [d for e, d in events if e == "switch"]
    assert [(d["from"], d["to"]) for d in switches] == list(pairwise(chain))
    assert [c["model"] for c in fake.chat.completions.calls] == chain
    error = next(d for e, d in events if e == "error")
    assert "temporarily unavailable" in error["message"] and "attempt" not in error["message"]
    done = events[-1][1]
    assert done["model"] == "gemini-3.5-flash-lite" and done["error"] and done["content"] == ""
    row = db.get(ChatMessage, uuid.UUID(events[0][1]["message_id"]))
    assert row is not None and row.model == "gemini-3.5-flash-lite" and row.error
    assert FAKE_KEY not in body


def test_fallback_can_be_switched_off(client, demo, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(chat_service, "get_settings", lambda: settings(chat_model_fallback=False))
    fake = FakeClient(lambda n, kw: (_ for _ in ()).throw(_busy(503)))
    _install(monkeypatch, fake)
    with client.stream("POST", f"/api/deals/{demo['id']}/chat", json={"message": "What is a covenant?"}) as resp:
        events = _events("".join(resp.iter_text()))
    names = [e for e, _ in events]
    assert "switch" not in names and "error" in names and len(fake.chat.completions.calls) == 1


def test_rejected_request_knob_is_dropped_and_the_round_retried(client, demo, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def script(n: int, kwargs: dict[str, Any]) -> Any:
        if n == 1:
            raise openai.BadRequestError(
                "Unsupported parameter: 'reasoning_effort' is not supported with this model.",
                response=httpx.Response(400, request=httpx.Request("POST", "https://x")),
                body=None,
            )
        return _answer(GENERAL)

    fake = FakeClient(script)
    _install(monkeypatch, fake)
    with client.stream("POST", f"/api/deals/{demo['id']}/chat", json={"message": "What is a covenant?"}) as resp:
        events = _events("".join(resp.iter_text()))
    names = [e for e, _ in events]
    assert "switch" not in names and "error" not in names and "tool" not in names
    calls = fake.chat.completions.calls
    assert len(calls) == 2 and "reasoning_effort" in calls[0] and "reasoning_effort" not in calls[1]
    assert calls[1]["max_tokens"] == 2048 and "tools" in calls[1] and calls[1]["model"] == "gemini-3.8-flash"
    assert events[-1][1]["content"] == GENERAL and events[-1][1]["error"] is None
    # a 400 that names nothing we sent is a real error, reported once
    fake = FakeClient(
        lambda n, kw: (_ for _ in ()).throw(
            openai.BadRequestError(
                "bad request", response=httpx.Response(400, request=httpx.Request("POST", "https://x")), body=None
            )
        )
    )
    _install(monkeypatch, fake)
    with client.stream("POST", f"/api/deals/{demo['id']}/chat", json={"message": "What is a covenant?"}) as resp:
        events = _events("".join(resp.iter_text()))
    assert "error" in [e for e, _ in events] and len(fake.chat.completions.calls) == 1


def test_request_params_per_provider() -> None:
    s = settings(chat_max_output_tokens=777, chat_reasoning_effort="none")
    assert openai_compat.request_params(_backend("openai"), s) == {"max_completion_tokens": 777, "reasoning_effort": "none"}
    assert openai_compat.request_params(_backend("gemini"), s) == {"max_tokens": 777, "reasoning_effort": "none"}
    assert openai_compat.request_params(_backend("groq"), s) == {"max_tokens": 777, "reasoning_effort": "none"}
    for name in ("openrouter", "ollama", "custom"):
        assert openai_compat.request_params(_backend(name), s) == {"max_tokens": 777}, name
    assert openai_compat.request_params(GEMINI, settings()) == {"max_tokens": 2048, "reasoning_effort": "low"}
    with pytest.raises(ValueError):
        settings(chat_reasoning_effort="max")
    with pytest.raises(ValueError):
        settings(chat_max_output_tokens=1)


def test_chat_client_fails_fast() -> None:
    c = openai_compat.make_client(GEMINI)
    assert c.timeout == 30.0 and c.max_retries == 0 and str(c.base_url).startswith("https://generativelanguage")
    assert chat_service.CHAT_TIMEOUT_SECONDS == 30.0 and chat_service.CHAT_MAX_RETRIES == 0
    proxied = openai_compat.make_client(resolve_chat_backend(settings(openrouter_api_key=FAKE_KEY)))
    assert proxied.max_retries == 0 and proxied.default_headers.get("X-Title") == "BearCase"


def test_fallback_chain_per_provider() -> None:
    from bearcase.chat.providers import fallback_chain

    assert fallback_chain(GEMINI) == ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]
    assert fallback_chain(MOCK_BACKEND) == ["rules-v1"]
    assert fallback_chain(resolve_chat_backend(settings(groq_api_key="k"))) == ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
    assert fallback_chain(resolve_chat_backend(settings(openai_api_key="k"))) == ["gpt-5.6-luna", "gpt-4.1-mini"]
    assert fallback_chain(resolve_chat_backend(settings(anthropic_api_key="k"))) == ["claude-haiku-4-5", "claude-sonnet-5"]
    openrouter = fallback_chain(resolve_chat_backend(settings(openrouter_api_key="k")))
    assert (
        openrouter == list(REGISTRY["openrouter"].fallback)
        and len(openrouter) == 4
        and all(m.endswith(":free") for m in openrouter)
    )
    assert fallback_chain(resolve_chat_backend(settings(chat_provider="ollama"))) == ["qwen3:8b"]
    custom = resolve_chat_backend(
        settings(chat_provider="custom", chat_base_url="http://localhost:1234/v1", chat_model="local-model")
    )
    assert fallback_chain(custom) == ["local-model"]
    # an overridden model leads and the provider's chain follows, without repeats
    import dataclasses

    assert fallback_chain(dataclasses.replace(GEMINI, model="gemini-3.6-flash")) == [
        "gemini-3.6-flash",
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.5-flash-lite",
    ]
    assert chat_service.next_in_chain(["a", "b"], "a") == "b" and chat_service.next_in_chain(["a", "b"], "b") is None
    assert chat_service.next_in_chain(["a"], "x") is None
    for spec in REGISTRY.values():
        assert all(validate_model_id(m) for m in spec.fallback)
        if spec.fallback:
            assert spec.fallback[0] == spec.default_model
    # the fallback tuple is not part of the public options (the panel offers `models`, never the chain)
    assert all("fallback" not in o for o in public_options())


def test_busy_error_classification() -> None:
    req = httpx.Request("POST", "https://x")
    busy = chat_service.busy_error
    assert busy(openai.InternalServerError("x", response=httpx.Response(503, request=req), body=None))
    for status in (500, 502, 504, 529):
        assert busy(openai.APIStatusError("x", response=httpx.Response(status, request=req), body=None)), status
    limited = openai.RateLimitError("model unavailable due to high demand", response=httpx.Response(429, request=req), body=None)
    assert not busy(limited)
    assert busy(openai.BadRequestError("The model is overloaded", response=httpx.Response(400, request=req), body=None))
    assert not busy(openai.BadRequestError("bad json", response=httpx.Response(400, request=req), body=None))
    assert not busy(openai.AuthenticationError("bad key", response=httpx.Response(401, request=req), body=None))
    assert busy(openai.APIConnectionError(request=req))  # unreachable models are handed over
    assert not busy(RuntimeError("boom")) and busy(RuntimeError("service unavailable"))


ANTHROPIC = ChatBackend(
    name="anthropic",
    label="Anthropic Claude",
    kind="anthropic",
    model="claude-haiku-4-5",
    base_url=None,
    api_key=FAKE_KEY,
    ready=True,
    reason=None,
    free_tier=False,
)


class FakeAnthropicStream:
    def __init__(self, texts: list[str], stop_reason: str = "end_turn") -> None:
        self._texts = texts
        self.stop_reason = stop_reason

    def __enter__(self) -> FakeAnthropicStream:
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    @property
    def text_stream(self) -> Any:
        yield from self._texts

    def get_final_message(self) -> Any:
        usage = types.SimpleNamespace(input_tokens=30, output_tokens=7)
        return types.SimpleNamespace(usage=usage, stop_reason=self.stop_reason, content=[])


class FakeAnthropic:
    def __init__(self, script: Any) -> None:
        self.calls: list[dict[str, Any]] = []
        self.script = script
        self.messages = types.SimpleNamespace(stream=self._stream)

    def _stream(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.script(len(self.calls), kwargs)


def test_anthropic_loop_reads_the_brief_caps_output_and_switches_on_overload(client, demo, db, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import anthropic

    def script(n: int, kwargs: dict[str, Any]) -> Any:
        if n == 1:
            raise anthropic.APIStatusError(
                "Overloaded",
                response=httpx.Response(529, request=httpx.Request("POST", "https://x")),
                body={"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}},
            )
        return FakeAnthropicStream([GENERAL])

    fake = FakeAnthropic(script)
    constructed: list[dict[str, Any]] = []

    def build(**kwargs: Any) -> FakeAnthropic:
        constructed.append(kwargs)
        return fake

    monkeypatch.setattr(anthropic, "Anthropic", build)
    monkeypatch.setattr(chat_service, "resolve_chat_backend", lambda settings=None: ANTHROPIC)
    monkeypatch.setattr("bearcase.api.routes.chat.resolve_chat_backend", lambda settings=None: ANTHROPIC)
    with client.stream("POST", f"/api/deals/{demo['id']}/chat", json={"message": "What is a covenant?"}) as resp:
        body = "".join(resp.iter_text())
    events = _events(body)
    assert [e for e, _ in events] == ["meta", "switch", "text", "citations", "done"]
    assert events[0][1]["provider"] == "anthropic" and events[0][1]["model"] == "claude-haiku-4-5"
    assert events[1][1]["from"] == "claude-haiku-4-5" and events[1][1]["to"] == "claude-sonnet-5"
    done = events[-1][1]
    assert done["model"] == "claude-sonnet-5" and done["error"] is None and done["content"] == GENERAL
    assert constructed and constructed[0]["timeout"] == 30.0 and constructed[0]["max_retries"] == 0
    assert [c["model"] for c in fake.calls] == ["claude-haiku-4-5", "claude-sonnet-5"]
    for c in fake.calls:
        assert c["max_tokens"] == 2048 and c["tools"] == TOOLS
        assert "## Deal brief" in c["system"] and "<deal_brief>" in c["system"] and "Deal: Northstar" in c["system"]
    row = db.get(ChatMessage, uuid.UUID(events[0][1]["message_id"]))
    assert row is not None and row.model == "claude-sonnet-5" and row.provider == "anthropic"
    assert row.usage == {"model": "claude-sonnet-5", "input_tokens": 30, "output_tokens": 7}
    assert FAKE_KEY not in body


def test_per_model_daily_quota_429_hands_over_to_the_next_model() -> None:
    req = httpx.Request("POST", "https://x")
    per_model = openai.RateLimitError(
        "You exceeded your current quota",
        response=httpx.Response(429, request=req),
        body={"error": {"details": [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}},
    )
    assert chat_service.busy_error(per_model) is True
    project_wide = openai.RateLimitError("Too many requests", response=httpx.Response(429, request=req), body=None)
    assert chat_service.busy_error(project_wide) is False


def test_timeouts_and_connection_failures_hand_over_and_read_plainly() -> None:
    req = httpx.Request("POST", "https://x")
    assert chat_service.busy_error(openai.APITimeoutError(request=req)) is True
    assert chat_service.busy_error(openai.APIConnectionError(request=req)) is True
    text = chat_service.describe_error(openai.APITimeoutError(request=req), GEMINI)
    assert "did not answer within" in text and "seconds" in text


def test_marker_variants_are_normalised() -> None:
    out = chat_service.normalize_markers("Fact 【M:030ddf3e】【E:1959b37a,423c374f】.")
    assert out == "Fact [M:030ddf3e][E:1959b37a][E:423c374f]."
