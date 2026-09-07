"""Which model answers deal chat. Resolution is pure settings logic (no network): "auto" picks the
first provider with a key, an explicit provider that is not ready falls back to the rule-based composer
with a human-readable reason, and nothing here ever exposes a key. Every provider runs the same tool
set and the same citation validation; only the transport differs."""

from __future__ import annotations

import importlib.util
import ipaddress
import os
import re
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

from bearcase.config import Settings, get_settings

Kind = Literal["mock", "anthropic", "openai_compat"]

MOCK_LABEL = "Rule-based composer"
MOCK_MODEL = "rules-v1"
OLLAMA_DEFAULT_HOST = "http://127.0.0.1:11434"
CUSTOM_LABEL = "Custom OpenAI-compatible"
# Model ids travel from the browser to a provider and into ChatMessage.model (String(80)): one leading
# alphanumeric, then the characters real ids use (dots, colons, slashes, dashes), 80 characters at most.
MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$")


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    label: str
    kind: Kind
    env: str
    base_url: str | None
    default_model: str
    free_tier: bool
    free_tier_note: str
    key_url: str
    models: tuple[str, ...]
    """Ids a user can pick in the chat panel, default first. A request may only name one of these (or
    BEARCASE_CHAT_MODEL) for a live provider; see models_for and the chat route."""
    fallback: tuple[str, ...] = ()
    """Ids tried in order when the model that should answer is busy (5xx or an overloaded message on the
    first request of a reply). The chain starts with the backend's own model; see fallback_chain."""


REGISTRY: dict[str, ProviderSpec] = {
    "anthropic": ProviderSpec(
        name="anthropic",
        label="Anthropic Claude",
        kind="anthropic",
        env="ANTHROPIC_API_KEY",
        base_url=None,
        default_model="claude-haiku-4-5",
        free_tier=False,
        free_tier_note="No ongoing free tier: a small one-time trial credit, then prepaid credits (claude-haiku-4-5 is $1 per million input tokens).",
        key_url="https://platform.claude.com/settings/keys",
        models=("claude-haiku-4-5", "claude-sonnet-5", "claude-opus-5"),
        fallback=("claude-haiku-4-5", "claude-sonnet-5"),
    ),
    "openai": ProviderSpec(
        name="openai",
        label="OpenAI",
        kind="openai_compat",
        env="OPENAI_API_KEY",
        base_url=None,
        default_model="gpt-5.6-luna",
        free_tier=False,
        free_tier_note="No free tier: prepaid credits from $5 (gpt-5.6-luna is $0.20 per million input tokens).",
        key_url="https://platform.openai.com/api-keys",
        models=("gpt-5.6-luna", "gpt-5.6-terra", "gpt-4.1-mini", "gpt-4o-mini"),
        fallback=("gpt-5.6-luna", "gpt-4.1-mini"),
    ),
    "gemini": ProviderSpec(
        name="gemini",
        label="Google Gemini",
        kind="openai_compat",
        env="GEMINI_API_KEY",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        default_model="gemini-3.8-flash",
        free_tier=True,
        free_tier_note="Free tier in Google AI Studio with no card; rate limits are per project and shown in AI Studio.",
        key_url="https://aistudio.google.com/apikey",
        models=("gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-flash-lite"),
        fallback=("gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"),
    ),
    "groq": ProviderSpec(
        name="groq",
        label="Groq",
        kind="openai_compat",
        env="GROQ_API_KEY",
        base_url="https://api.groq.com/openai/v1",
        default_model="openai/gpt-oss-120b",
        free_tier=True,
        free_tier_note="Free plan with no card: 30 requests/min, 1,000 requests/day, 8K tokens/min for gpt-oss-120b.",
        key_url="https://console.groq.com/keys",
        models=("openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b", "qwen/qwen3.8-27b"),
        fallback=("openai/gpt-oss-120b", "openai/gpt-oss-20b"),
    ),
    "openrouter": ProviderSpec(
        name="openrouter",
        label="OpenRouter",
        kind="openai_compat",
        env="OPENROUTER_API_KEY",
        base_url="https://openrouter.ai/api/v1",
        default_model="z-ai/glm-5.2:free",
        free_tier=True,
        free_tier_note="':free' models cost $0: 20 requests/min and 50/day (1,000/day after a one-time $10 credit purchase).",
        key_url="https://openrouter.ai/keys",
        models=(
            "z-ai/glm-5.2:free",
            "nvidia/nemotron-3-super-120b-a12b:free",
            "minimax/minimax-m3:free",
            "google/gemma-4-31b-it:free",
        ),
        fallback=(
            "z-ai/glm-5.2:free",
            "nvidia/nemotron-3-super-120b-a12b:free",
            "minimax/minimax-m3:free",
            "google/gemma-4-31b-it:free",
        ),
    ),
    "ollama": ProviderSpec(
        name="ollama",
        label="Ollama (local)",
        kind="openai_compat",
        env="OLLAMA_HOST",
        base_url=None,
        default_model="qwen3:8b",
        free_tier=True,
        free_tier_note="Runs on this machine for free with no key; install Ollama and pull a model (qwen3:8b is about 5 GB).",
        key_url="https://ollama.com/download",
        models=("qwen3:8b", "qwen3:4b", "llama3.1:8b", "llama3.2:3b", "mistral:7b", "gpt-oss:20b"),
    ),
    "custom": ProviderSpec(
        name="custom",
        label=CUSTOM_LABEL,
        kind="openai_compat",
        env="BEARCASE_CHAT_API_KEY",
        base_url=None,
        default_model="",
        free_tier=False,
        free_tier_note="Depends on the server you point it at.",
        key_url="",
        models=(),  # only the configured BEARCASE_CHAT_MODEL; see models_for
    ),
}

AUTO_ORDER = ("anthropic", "openai", "gemini", "groq", "openrouter", "ollama")
OPTION_ORDER = ("gemini", "groq", "openrouter", "ollama", "openai", "anthropic")


@dataclass(frozen=True, repr=False)
class ChatBackend:
    name: str
    label: str
    kind: Kind
    model: str
    base_url: str | None
    api_key: str | None
    ready: bool
    reason: str | None
    free_tier: bool

    def safe_dict(self) -> dict[str, Any]:
        """Everything except the key. Use this for logs, audit payloads, and API responses."""
        return {
            "name": self.name,
            "label": self.label,
            "kind": self.kind,
            "model": self.model,
            "base_url": self.base_url,
            "has_key": bool(self.api_key),
            "ready": self.ready,
            "reason": self.reason,
            "free_tier": self.free_tier,
        }

    def __repr__(self) -> str:
        fields = ", ".join(f"{k}={v!r}" for k, v in self.safe_dict().items())
        return f"ChatBackend({fields})"


MOCK_BACKEND = ChatBackend(
    name="mock",
    label=MOCK_LABEL,
    kind="mock",
    model=MOCK_MODEL,
    base_url=None,
    api_key=None,
    ready=True,
    reason=None,
    free_tier=True,
)


def public_options() -> list[dict[str, Any]]:
    """Provider choices for the chat config endpoint, ordered free-first. Contains no key material."""
    return [
        {
            "provider": spec.name,
            "label": spec.label,
            "env": spec.env,
            "free_tier": spec.free_tier,
            "free_tier_note": spec.free_tier_note,
            "default_model": spec.default_model,
            "key_url": spec.key_url,
            "models": list(spec.models),
        }
        for spec in (REGISTRY[n] for n in OPTION_ORDER)
    ]


def validate_model_id(value: str) -> bool:
    """True when a model id sent by a client is safe to forward to a provider and store."""
    return isinstance(value, str) and MODEL_ID.fullmatch(value) is not None


def models_for(backend: ChatBackend, settings: Settings | None = None) -> list[str]:
    """Model ids a user may pick for the backend that answers, default first. BEARCASE_CHAT_MODEL, when set,
    leads the list, and the backend's current model is always present (custom servers list only that)."""
    if backend.kind == "mock":
        return [MOCK_MODEL]
    s = settings or get_settings()
    spec = REGISTRY.get(backend.name)
    candidates = [s.chat_model or "", backend.model, *(spec.models if spec else ())]
    return [m for m in dict.fromkeys(candidates) if m]


def fallback_chain(backend: ChatBackend) -> list[str]:
    """Models tried for one reply, in order: the backend's own model first, then the provider's fallback ids.
    Ollama, custom servers, and the rule-based composer have no fallback, so the chain is just their model."""
    spec = REGISTRY.get(backend.name)
    candidates = [backend.model, *(spec.fallback if spec else ())]
    return [m for m in dict.fromkeys(candidates) if m]


def _is_private_host(host: str) -> bool:
    h = host.lower().rstrip(".")
    if h in {"localhost", "0.0.0.0"} or h.endswith(".localhost") or h.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local


def validate_base_url(url: str) -> str | None:
    """Return a human-readable problem with an OpenAI-compatible base URL, or None when it is acceptable.
    Plain http is only allowed for loopback and private-network hosts so keys never travel in the clear."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return "base URL is not a valid URL"
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return "base URL must be an http(s) URL such as https://host/v1"
    if parts.scheme == "http" and not _is_private_host(parts.hostname):
        return "base URL must use https"
    return None


def _key_for(settings: Settings, name: str) -> str | None:
    return {
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
        "gemini": settings.gemini_api_key,
        "groq": settings.groq_api_key,
        "openrouter": settings.openrouter_api_key,
    }.get(name)


def _anthropic_env_credential() -> bool:
    # The Anthropic SDK reads these itself; BEARCASE only needs to know one is present.
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def _has_credentials(settings: Settings, name: str) -> bool:
    if name == "ollama":
        return bool(settings.ollama_host)
    if name == "anthropic":
        return bool(settings.anthropic_api_key) or _anthropic_env_credential()
    return bool(_key_for(settings, name))


def _not_ready(spec: ProviderSpec, model: str, reason: str) -> ChatBackend:
    return ChatBackend(
        name=spec.name,
        label=spec.label,
        kind=spec.kind,
        model=model,
        base_url=None,
        api_key=None,
        ready=False,
        reason=reason,
        free_tier=spec.free_tier,
    )


def _ollama_base_url(settings: Settings) -> str:
    host = (settings.ollama_host or OLLAMA_DEFAULT_HOST).strip()
    if "://" not in host:  # the Ollama CLI accepts bare host:port
        host = f"http://{host}"
    return host.rstrip("/") + "/v1"


def _model_for(settings: Settings, spec: ProviderSpec) -> str:
    if settings.chat_model:
        return settings.chat_model
    if spec.name == "anthropic" and "ai_model" in settings.model_fields_set:
        return settings.ai_model  # an explicitly configured BEARCASE_AI_MODEL keeps working for chat
    return spec.default_model


def _build(settings: Settings, name: str) -> ChatBackend:
    spec = REGISTRY[name]
    model = _model_for(settings, spec)
    if spec.kind == "anthropic":
        if importlib.util.find_spec("anthropic") is None:
            return _not_ready(spec, model, "the anthropic package is not installed")
        key = settings.anthropic_api_key
        if not key and not _anthropic_env_credential():
            return _not_ready(spec, model, f"set {spec.env} (or BEARCASE_{spec.env}) in .env")
        return ChatBackend(
            name=name,
            label=spec.label,
            kind="anthropic",
            model=model,
            base_url=None,
            api_key=key,
            ready=True,
            reason=None,
            free_tier=spec.free_tier,
        )
    if importlib.util.find_spec("openai") is None:
        return _not_ready(spec, model, "the openai package is not installed")
    if name == "custom":
        if not settings.chat_base_url:
            return _not_ready(spec, model, "set BEARCASE_CHAT_BASE_URL to the server's OpenAI-compatible base URL")
        problem = validate_base_url(settings.chat_base_url)
        if problem:
            return _not_ready(spec, model, problem)
        if not model:
            return _not_ready(spec, model, "set BEARCASE_CHAT_MODEL to the model id the server expects")
        # Only the dedicated key: another provider's key must never be sent to an operator-chosen host.
        key = settings.chat_api_key
        if not key:
            host = urlsplit(settings.chat_base_url).hostname or ""
            if not _is_private_host(host):
                return _not_ready(spec, model, "set BEARCASE_CHAT_API_KEY")
            key = "local"  # local servers such as LM Studio accept any key
        return ChatBackend(
            name=name,
            label=spec.label,
            kind="openai_compat",
            model=model,
            base_url=settings.chat_base_url,
            api_key=key,
            ready=True,
            reason=None,
            free_tier=False,
        )
    if name == "ollama":
        ollama_url = _ollama_base_url(settings)
        problem = validate_base_url(ollama_url)
        if problem:
            return _not_ready(spec, model, f"OLLAMA_HOST is not usable: {problem}")
        base_url: str | None = ollama_url
        provider_key: str | None = "ollama"
    else:
        provider_key = _key_for(settings, name)
        if not provider_key:
            return _not_ready(spec, model, f"set {spec.env} (or BEARCASE_{spec.env}) in .env")
        base_url = settings.chat_base_url or spec.base_url
        if settings.chat_base_url:
            problem = validate_base_url(settings.chat_base_url)
            if problem:
                return _not_ready(spec, model, f"BEARCASE_CHAT_BASE_URL is not usable: {problem}")
    return ChatBackend(
        name=name,
        label=spec.label,
        kind="openai_compat",
        model=model,
        base_url=base_url,
        api_key=provider_key,
        ready=True,
        reason=None,
        free_tier=spec.free_tier,
    )


def resolve_chat_backend(settings: Settings | None = None) -> ChatBackend:
    """Pick the chat backend from settings. Auto order: anthropic, openai, gemini, groq, openrouter,
    ollama (only when OLLAMA_HOST is set), then the rule-based composer. An explicit provider is returned
    even when it is not ready so callers can explain why; they must fall back to MOCK_BACKEND themselves."""
    s = settings or get_settings()
    choice = s.chat_provider
    if choice == "mock":
        return MOCK_BACKEND
    if choice == "auto":
        for name in AUTO_ORDER:
            if _has_credentials(s, name):
                return _build(s, name)
        return MOCK_BACKEND
    return _build(s, choice)


def effective_backend(settings: Settings | None = None) -> ChatBackend:
    """The backend that will actually answer: the resolved one when ready, else the rule-based composer."""
    backend = resolve_chat_backend(settings)
    return backend if backend.ready else MOCK_BACKEND
