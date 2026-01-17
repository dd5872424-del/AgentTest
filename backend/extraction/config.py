"""
Extraction module configuration loader.

Loads config from backend/extraction/config.yaml to keep it independent
from the main backend/config.yaml.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ExtractionConfig:
    prompts_dir: str | None = None
    chunk_size: int = 8000
    overlap: int = 500
    chunk_strategy: str = "auto"
    chapter_max: int = 20000
    llm_merge: bool = True
    retry_max: int = 3
    input: str | None = None
    input_dir: str | None = None
    output: str | None = None
    output_jsonl: str | None = None
    recursive: bool = True
    resume: bool = False
    import_db: bool = False
    estimate_tokens: bool = False
    estimate_only: bool = False
    model: str | None = None
    temperature: float | None = None


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"true", "1", "yes", "y", "on"}:
            return True
        if v in {"false", "0", "no", "n", "off"}:
            return False
    return default


def _coerce_float(value: Any, default: float | None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip() or None


@lru_cache()
def get_extraction_config() -> ExtractionConfig:
    config_path = Path(__file__).parent / "config.yaml"
    if not config_path.exists():
        return ExtractionConfig()

    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return ExtractionConfig()

    payload = data.get("extraction", data) if isinstance(data, dict) else {}

    prompts_dir = _coerce_str(payload.get("prompts_dir"))
    input_path = _coerce_str(payload.get("input"))
    input_dir = _coerce_str(payload.get("input_dir"))
    output = _coerce_str(payload.get("output"))
    output_jsonl = _coerce_str(payload.get("output_jsonl"))
    model = _coerce_str(payload.get("model"))
    chunk_strategy = _coerce_str(payload.get("chunk_strategy")) or "auto"

    return ExtractionConfig(
        prompts_dir=prompts_dir,
        chunk_size=_coerce_int(payload.get("chunk_size"), 8000),
        overlap=_coerce_int(payload.get("overlap"), 500),
        chunk_strategy=chunk_strategy,
        chapter_max=_coerce_int(payload.get("chapter_max"), 20000),
        llm_merge=_coerce_bool(payload.get("llm_merge"), True),
        retry_max=_coerce_int(payload.get("retry_max"), 3),
        input=input_path,
        input_dir=input_dir,
        output=output,
        output_jsonl=output_jsonl,
        recursive=_coerce_bool(payload.get("recursive"), True),
        resume=_coerce_bool(payload.get("resume"), False),
        import_db=_coerce_bool(payload.get("import_db"), False),
        estimate_tokens=_coerce_bool(payload.get("estimate_tokens"), False),
        estimate_only=_coerce_bool(payload.get("estimate_only"), False),
        model=model,
        temperature=_coerce_float(payload.get("temperature"), None),
    )
