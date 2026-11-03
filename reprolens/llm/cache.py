"""On-disk cache for model responses, keyed by exactly what produced them.

Development means running the same figure through the same prompt many times.
Without a cache that is paid for on every iteration, and the cost is invisible
until the bill arrives. Keyed on (model, prompt, input) so any change to any of
the three is a miss, which is the behaviour that makes it safe to leave on.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(".cache/llm.sqlite3")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS responses (
    key        TEXT PRIMARY KEY,
    model      TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    payload    TEXT NOT NULL
)
"""


def digest(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()[:32]


class ResponseCache:
    def __init__(self, path: Path = DEFAULT_PATH) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._connection.execute(_SCHEMA)
        self._connection.commit()

    @staticmethod
    def key(model: str, prompt: str, payload: bytes | str) -> str:
        return f"{model}:{digest(prompt)}:{digest(payload)}"

    def get(self, key: str) -> Any | None:
        row = self._connection.execute(
            "SELECT payload FROM responses WHERE key = ?", (key,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, model: str, value: Any) -> None:
        self._connection.execute(
            "INSERT OR REPLACE INTO responses (key, model, payload) VALUES (?, ?, ?)",
            (key, model, json.dumps(value)),
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()
