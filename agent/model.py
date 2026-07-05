"""Closed-source LLM client for the PlanetCoaster AI Builder.

Wraps three families of models behind a single ``call_model`` function:

* **Anthropic Claude** (``claude-*``) - text + vision, JSON output.
* **Google Gemini** (``gemini-*``) - text + vision, JSON output.
* **OpenAI-compatible** (OpenAI, OpenRouter, or any base_url) - text + vision.

Keys and endpoints are read from ``config.json`` (written by the Settings tab in
the Gradio UI) with environment-variable fallbacks so the agent also works
head-less / from Pinokio env vars.

``call_model`` always tries to return parsed JSON when ``expect_json=True``; if
the model wraps its answer in prose or a ```json ``` fence we still recover it.
"""

from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "provider": "Anthropic Claude",
    "model": "claude-3-5-sonnet-latest",
    "anthropic_api_key": "",
    "gemini_api_key": "",
    "openai_api_key": "",
    "openai_base_url": "https://api.openai.com/v1",
    "max_output_tokens": 8192,
    "temperature": 0.4,
}

# provider name -> handful of sensible default models to show in the UI dropdown
PROVIDER_MODELS: dict[str, list[str]] = {
    "Anthropic Claude": [
        "claude-3-5-sonnet-latest",
        "claude-3-5-haiku-latest",
        "claude-3-opus-latest",
    ],
    "Google Gemini": [
        "gemini-2.0-flash",
        "gemini-2.5-pro-preview-05-06",
        "gemini-2.5-flash-preview-05-20",
    ],
    "OpenAI-Compatible": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4.1",
    ],
}


# ── config ──────────────────────────────────────────────────────────────────
def load_config() -> dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text()))
        except (json.JSONDecodeError, OSError):
            pass
    # environment fallbacks (do not overwrite a value already set in config.json)
    for key, env in (
        ("anthropic_api_key", "ANTHROPIC_API_KEY"),
        ("gemini_api_key", "GEMINI_API_KEY"),
        ("openai_api_key", "OPENAI_API_KEY"),
    ):
        if not cfg.get(key) and os.getenv(env):
            cfg[key] = os.environ[env]
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


# ── helpers ───────────────────────────────────────────────────────────────--
def _encode_image(path: str) -> tuple[str, str]:
    """Return (base64_data, media_type) for an image file."""
    data = base64.b64encode(Path(path).read_bytes()).decode()
    ext = Path(path).suffix.lower().lstrip(".")
    media_type = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "gif": "image/gif",
    }.get(ext, "image/png")
    return data, media_type


def _extract_json(text: str) -> Any:
    """Best-effort recovery of a JSON object/array embedded in model output."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            pass
    # fall back to first {...} or [...] blob
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("Model did not return valid JSON:\n" + text[:2000])


class ModelError(RuntimeError):
    """Raised when a model call cannot be completed (missing key, API error…)."""


# ── public API ────────────────────────────────────────────────────────────--
def call_model(
    prompt: str,
    images: list[str] | None = None,
    system: str | None = None,
    expect_json: bool = False,
    cfg: dict[str, Any] | None = None,
) -> Any:
    """Send *prompt* (+ optional *images*) to the configured model.

    Returns parsed JSON when ``expect_json`` is True, otherwise the raw string.
    """
    cfg = cfg or load_config()
    provider = cfg.get("provider", "Anthropic Claude")
    model = cfg.get("model") or (PROVIDER_MODELS.get(provider) or ["" ])[0]
    images = images or []

    if provider == "Anthropic Claude":
        text = _call_anthropic(cfg, model, prompt, images, system)
    elif provider == "Google Gemini":
        text = _call_gemini(cfg, model, prompt, images, system)
    elif provider == "OpenAI-Compatible":
        text = _call_openai(cfg, model, prompt, images, system)
    else:
        raise ModelError(f"Unknown provider: {provider!r}")

    return _extract_json(text) if expect_json else text


def _call_anthropic(cfg, model, prompt, images, system):
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise ModelError("anthropic package not installed (pip install anthropic)") from exc
    key = cfg.get("anthropic_api_key")
    if not key:
        raise ModelError("Anthropic API key not set (Settings tab or ANTHROPIC_API_KEY).")

    client = anthropic.Anthropic(api_key=key)
    content: list[dict[str, Any]] = []
    for img in images:
        data, media_type = _encode_image(img)
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": data},
        })
    content.append({"type": "text", "text": prompt})

    resp = client.messages.create(
        model=model,
        max_tokens=int(cfg.get("max_output_tokens", 8192)),
        temperature=float(cfg.get("temperature", 0.4)),
        system=system or "",
        messages=[{"role": "user", "content": content}],
    )
    return "".join(block.text for block in resp.content if block.type == "text")


def _call_gemini(cfg, model, prompt, images, system):
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:  # pragma: no cover
        raise ModelError("google-genai package not installed (pip install google-genai)") from exc
    key = cfg.get("gemini_api_key")
    if not key:
        raise ModelError("Gemini API key not set (Settings tab or GEMINI_API_KEY).")

    client = genai.Client(api_key=key)
    parts: list[Any] = []
    for img in images:
        data, media_type = _encode_image(img)
        parts.append(types.Part.from_bytes(data=base64.b64decode(data), mime_type=media_type))
    parts.append(types.Part.from_text(text=prompt))

    resp = client.models.generate_content(
        model=model,
        contents=parts,
        config=types.GenerateContentConfig(
            system_instruction=system or None,
            temperature=float(cfg.get("temperature", 0.4)),
            max_output_tokens=int(cfg.get("max_output_tokens", 8192)),
        ),
    )
    return resp.text or ""


def _call_openai(cfg, model, prompt, images, system):
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise ModelError("openai package not installed (pip install openai)") from exc
    key = cfg.get("openai_api_key")
    if not key:
        raise ModelError("OpenAI API key not set (Settings tab or OPENAI_API_KEY).")

    client = OpenAI(api_key=key, base_url=cfg.get("openai_base_url") or None)
    user_content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for img in images:
        data, media_type = _encode_image(img)
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{media_type};base64,{data}"},
        })
    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_content})

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=float(cfg.get("temperature", 0.4)),
        max_tokens=int(cfg.get("max_output_tokens", 8192)),
    )
    return resp.choices[0].message.content or ""
