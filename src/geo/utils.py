from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


def ensure_url(url: str) -> str:
    if not url:
        raise ValueError("URL is required")
    if not re.match(r"^https?://", url, re.I):
        return f"https://{url}"
    return url


def domain_from_url(url: str) -> str:
    return urlparse(ensure_url(url)).netloc.lower()


def safe_name(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", text).strip("-").lower()


def now_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def read_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def score_label(score: int) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 55:
        return "Moderate"
    if score >= 40:
        return "Below Average"
    return "Needs Attention"
