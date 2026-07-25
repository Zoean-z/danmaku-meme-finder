"""Small configuration helpers; no third-party dotenv dependency is needed."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_API_URL = "https://hguofichp.cn:10086/machine/Page"


def load_dotenv(path: Path = Path(".env")) -> None:
    """Load simple KEY=VALUE entries without overwriting explicit environment values."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            os.environ.setdefault(key, value)


def existing_api_url() -> str:
    return os.getenv("EXISTING_API_URL", DEFAULT_API_URL)


def existing_page_size() -> int:
    try:
        value = int(os.getenv("EXISTING_PAGE_SIZE", "50"))
    except ValueError:
        return 50
    return max(1, min(value, 500))


def user_hash_salt() -> str:
    return os.getenv("USER_HASH_SALT", "")
