"""Proposal format and validation for NeonRP agents.

Proposals are structured documents that describe changes an agent wants to make.
They follow the Plan→Diff→Validate→Apply pipeline.
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ContextItem(BaseModel):
    """A context item representing an entity reference."""

    entity_key: str
    path: str


class PlanStep(BaseModel):
    """A step in the proposal plan."""

    step: int
    title: str
    rationale: Optional[str] = None


class Op(BaseModel):
    """Base operation model."""

    model_config = ConfigDict(extra="forbid")

    op: str
    path: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate path is relative and doesn't contain path traversal."""
        if not v:
            raise ValueError("path cannot be empty")

        # Check for absolute paths
        if v.startswith("/") or (len(v) > 1 and v[1] == ":"):
            raise ValueError(f"path must be relative, got: {v}")

        # Check for path traversal
        parts = v.replace("\\", "/").split("/")
        if ".." in parts:
            raise ValueError(f"path cannot contain '..': {v}")

        # Normalize to forward slashes
        return v.replace("\\", "/")


class UpsertTextOp(Op):
    """Upsert (create or replace) a text file."""

    op: Literal["upsert_text"] = "upsert_text"
    content: str
    content_type: str = "application/json"

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Content cannot be None for upsert_text."""
        if v is None:
            raise ValueError("content is required for upsert_text operation")
        return v


class DeleteOp(Op):
    """Delete a file."""

    op: Literal["delete"] = "delete"


class ProposalContext(BaseModel):
    """Context provided to the agent."""

    items: list[ContextItem] = Field(default_factory=list)


class Proposal(BaseModel):
    """A proposal for changes from an agent.

    This is the structured input to the Plan→Diff→Validate→Apply pipeline.
    """

    model_config = ConfigDict(extra="forbid")

    proposal_version: str = "0.1"
    agent_id: str
    run_id: str
    branch: str
    base_head_event: int
    query: str
    rationale: Optional[str] = None
    context: ProposalContext = Field(default_factory=ProposalContext)
    plan: list[PlanStep] = Field(default_factory=list)
    ops: list[UpsertTextOp | DeleteOp] = Field(default_factory=list)

    @field_validator("proposal_version", "agent_id", "run_id", "branch")
    @classmethod
    def validate_required_strings(cls, v: str) -> str:
        """Required string fields cannot be empty."""
        if not v or not v.strip():
            raise ValueError("field cannot be empty")
        return v

    @field_validator("base_head_event")
    @classmethod
    def validate_base_head_event(cls, v: int) -> int:
        """base_head_event must be a non-negative integer."""
        if v < -1:
            raise ValueError("base_head_event must be >= -1")
        return v

    @model_validator(mode="after")
    def validate_ops(self) -> "Proposal":
        """Validate all operations."""
        for i, op in enumerate(self.ops):
            # Additional validation can be added here
            if op.op not in ("upsert_text", "delete"):
                raise ValueError(f"ops[{i}]: unknown operation type '{op.op}'")
        return self


def parse_proposal(data: dict) -> Proposal:
    """Parse and validate a proposal from a dictionary.

    Args:
        data: Raw proposal data (e.g., from JSON)

    Returns:
        Validated Proposal object

    Raises:
        ValueError: If validation fails
    """
    if "proposal_version" not in data:
        raise ValueError("proposal_version is required")
    return Proposal(**data)


def parse_ops(ops_data: list[dict]) -> list[UpsertTextOp | DeleteOp]:
    """Parse a list of operation dictionaries.

    Args:
        ops_data: List of operation dictionaries

    Returns:
        List of validated Op objects

    Raises:
        ValueError: If validation fails
    """
    result = []
    for i, op_data in enumerate(ops_data):
        op_type = op_data.get("op")
        try:
            if op_type == "upsert_text":
                result.append(UpsertTextOp(**op_data))
            elif op_type == "delete":
                result.append(DeleteOp(**op_data))
            else:
                raise ValueError(f"unknown operation type: {op_type}")
        except Exception as e:
            raise ValueError(f"ops[{i}]: {e}") from e
    return result
