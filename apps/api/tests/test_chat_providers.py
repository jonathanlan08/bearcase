"""Chat backend resolution and the OpenAI-compatible tool loop. No network: settings are built directly and
the OpenAI client is replaced with scripted chunk iterators."""

from __future__ import annotations

import json
import types
import uuid
from typing import Any

import httpx
import openai
import pytest

from bearcase.chat import openai_compat
from bearcase.chat import service as chat_service
from bearcase.chat.openai_compat import _merge_tool_call, _parse_args, openai_tools
from bearcase.chat.providers import (
    MOCK_BACKEND,
    OPTION_ORDER,
    REGISTRY,
    ChatBackend,
    public_options,
    resolve_chat_backend,
    validate_base_url,
)
from bearcase.chat.tools import TOOLS
from bearcase.config import Settings
from bearcase.models import ChatMessage

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
        assert set(o) == {"provider", "label", "env", "free_tier", "free_tier_note", "default_model", "key_url"}
        assert o["label"] == REGISTRY[o["provider"]].label and o["key_url"].startswith("https://")
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
    assert citations["metrics"][0]["key"] == "ebitda_adjusted_verified"
    done = events[-1][1]
    assert done["grounded"] is True and done["error"] is None and "$1,810,000" in done["content"]
    # requests: system prompt first, no temperature, usage requested, tools on the tool round, echoed tool call
    calls = fake.chat.completions.calls
    assert len(calls) == 2 and all("temperature" not in c and c.get("stream_options") == {"include_usage": True} for c in calls)
    assert calls[0]["stream"] is True and calls[0]["tools"] == openai_tools() and calls[0]["model"] == "gemini-3.8-flash"
    msgs = calls[1]["messages"]
    assert msgs[0]["role"] == "system" and "Northstar" in msgs[0]["content"]
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
    row = db.get(ChatMessage, uuid.UUID(meta["message_id"]))
    assert row is not None and row.usage == {"input_tokens": 420, "output_tokens": 48}
    # nothing leaks the key
    assert FAKE_KEY not in body
    cfg = client.get(f"/api/deals/{demo['id']}/chat/config").json()
    assert FAKE_KEY not in json.dumps(cfg)
    assert cfg["provider"] == "gemini" and cfg["label"] == "Google Gemini" and cfg["live"] is True
    assert "Google Gemini (gemini-3.8-flash)" in cfg["note"] and [o["provider"] for o in cfg["options"]] == list(OPTION_ORDER)


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
    assert set(cfg) == {"provider", "label", "model", "live", "note", "suggested", "options"}
    # the test suite pins BEARCASE_CHAT_PROVIDER=mock, which gets the explicit-selection note
    assert cfg["provider"] == "mock" and cfg["live"] is False and "rule-based composer" in cfg["note"]
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
    assert row is not None and row.usage == {"input_tokens": 100, "output_tokens": 3} and row.error is None


def test_max_tool_rounds_is_reported_and_stored(client, demo, db, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def script(n: int, kwargs: dict[str, Any]) -> Any:
        call = types.SimpleNamespace(index=0, id=f"call_{n}", function=types.SimpleNamespace(name="get_findings", arguments="{}"))
        return iter([_chunk(tool_calls=[call]), _chunk(finish_reason="tool_calls")])

    events = _stream_once(client, demo, monkeypatch, script, "What are the biggest risks?")
    error = next(d for e, d in events if e == "error")
    assert "maximum number of tool rounds" in error["message"]
    row = db.get(ChatMessage, uuid.UUID(events[0][1]["message_id"]))
    assert row is not None and row.error and len(row.tool_calls) == chat_service.MAX_TOOL_ROUNDS + 1
