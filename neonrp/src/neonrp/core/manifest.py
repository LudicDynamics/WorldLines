from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class BranchMetadata(BaseModel):
    """Metadata for a branch (main or sandbox).

    New M4 fields for sandbox support:
    - kind: 'main' or 'sandbox'
    - parent: parent branch name (for sandboxes)
    - fork_event: event ID at which sandbox was forked
    - base_save: save ID used to create the sandbox

    M6 fields for undo/redo:
    - max_event: tracks furthest event reached (for redo after undo)
    """

    head_event: int = -1
    max_event: Optional[int] = None  # For redo support
    created: datetime = Field(default_factory=_now_utc)
    kind: Literal["main", "sandbox"] = "main"
    parent: Optional[str] = None
    fork_event: Optional[int] = None
    base_save: Optional[str] = None

    @field_serializer("created")
    def serialize_datetime(self, v: datetime) -> str:
        return v.isoformat()


class EntityRecord(BaseModel):
    id: str
    kind: str
    name: str
    tags: Optional[List[str]] = None
    summary: Optional[str] = None
    path: str
    mtime: float
    hash: str


class Manifest(BaseModel):
    model_config = ConfigDict(ser_json_timedelta="iso8601")

    version: str = "0.3"
    created: datetime = Field(default_factory=_now_utc)
    current_branch: str = "main"
    branches: Dict[str, BranchMetadata] = Field(default_factory=lambda: {"main": BranchMetadata()})
    entities: Dict[str, EntityRecord] = Field(default_factory=dict)

    @field_serializer("created")
    def serialize_datetime(self, v: datetime) -> str:
        return v.isoformat()
