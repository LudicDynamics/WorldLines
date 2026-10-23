import json
import os
from datetime import datetime, timezone
from pathlib import Path

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from neonrp.core.paths import get_neonrp_dir


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class GameEvent(BaseModel):
    model_config = ConfigDict(ser_json_timedelta="iso8601")

    id: int
    timestamp: datetime = Field(default_factory=_now_utc)
    type: str  # 'user' or 'system' or 'agent'
    payload: dict
    actor: Optional[str] = None  # agent_id for agent events, 'player'/'system' for others

    @field_serializer("timestamp")
    def serialize_datetime(self, v: datetime) -> str:
        return v.isoformat()


def get_event_log_path(root: Path, branch_name: str) -> Path:
    return get_neonrp_dir(root) / "events" / f"{branch_name}.jsonl"


def append_event(root: Path, branch_name: str, event: GameEvent):
    path = get_event_log_path(root, branch_name)
    path.parent.mkdir(parents=True, exist_ok=True)

    # NDJSON append
    line = json.dumps(event.model_dump(), default=str, ensure_ascii=False)

    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_events(root: Path, branch_name: str) -> list[GameEvent]:
    path = get_event_log_path(root, branch_name)
    if not path.exists():
        return []

    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    data = json.loads(line)
                    events.append(GameEvent(**data))
                except json.JSONDecodeError:
                    # Robustness: ignore malformed lines (per Architecture)
                    continue
    return events


def get_next_event_id(root: Path, branch_name: str) -> int:
    events = read_events(root, branch_name)
    if not events:
        return 0
    return events[-1].id + 1
