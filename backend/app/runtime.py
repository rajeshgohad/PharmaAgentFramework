"""Mutable runtime state for the API key.

The Anthropic key can be provided via .env (loaded at import) OR set at runtime
through the UI. It is held in memory only — never written to disk — so it lasts
for the life of the server process ("this session") and clears on restart.
"""
from __future__ import annotations

from . import config

_state = {
    "api_key": config.ANTHROPIC_API_KEY,
    "model": config.CLAUDE_MODEL,
    "model_complex": config.CLAUDE_MODEL_COMPLEX,
}


def get_api_key() -> str:
    return _state["api_key"]


def set_api_key(key: str) -> None:
    _state["api_key"] = (key or "").strip()


def clear_api_key() -> None:
    _state["api_key"] = ""


def llm_enabled() -> bool:
    return bool(_state["api_key"])


def model() -> str:
    return _state["model"]


def model_complex() -> str:
    return _state["model_complex"]
