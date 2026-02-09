"""
Orion Agent — Tier 1: Working (Session) Memory (v6.4.0)

Current session state that lives in RAM.
Manages immediate context for the current turn.

Migrated from Orion_MVP/memory/working_memory.py.

Location: In-process (RAM) — not persisted
Duration: Seconds to minutes (current session)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class DeliberationRecord:
    """Record of a single deliberation round."""
    iteration: int
    builder_output: str
    reviewer_output: str
    decision: str
    timestamp: str


@dataclass
class WorkingMemory:
    """
    Layer 1: Working Memory (Seconds – Minutes)

    Current session state, not persisted.
    Manages immediate context for the current request.

    Key Features:
    - Current request being processed
    - Deliberation history for this request
    - Quality feedback from iterations
    - Session timing
    """

    # Current request state
    current_request: str = ""
    current_intent: Optional[Any] = None
    current_domain: Optional[str] = None

    # Deliberation state
    deliberation_history: List[DeliberationRecord] = field(default_factory=list)
    iteration_count: int = 0
    quality_feedback: List[str] = field(default_factory=list)

    # Session timing
    session_start: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    request_start: Optional[str] = None

    # Context accumulation
    accumulated_context: Dict[str, Any] = field(default_factory=dict)

    def reset_for_new_request(self, request: str, intent: Optional[Any] = None):
        """Reset working memory for a new request."""
        self.current_request = request
        self.current_intent = intent
        self.current_domain = None
        self.deliberation_history = []
        self.iteration_count = 0
        self.quality_feedback = []
        self.request_start = datetime.now(timezone.utc).isoformat()
        self.accumulated_context = {}

    def record_deliberation(
        self,
        builder_output: str,
        reviewer_output: str,
        decision: str,
    ):
        """Record a deliberation round."""
        record = DeliberationRecord(
            iteration=self.iteration_count,
            builder_output=builder_output[:500],
            reviewer_output=reviewer_output[:500],
            decision=decision,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self.deliberation_history.append(record)

    def add_quality_feedback(self, feedback: str):
        """Add quality feedback for retry."""
        self.quality_feedback.append(feedback)
        self.iteration_count += 1

    def get_context_for_retry(self) -> str:
        """Get context for retry attempt including previous feedback."""
        if not self.quality_feedback:
            return ""
        lines = ["## Previous Attempt Feedback"]
        for i, feedback in enumerate(self.quality_feedback, 1):
            lines.append(f"Attempt {i}: {feedback}")
        lines.append("\nFix these issues in your response.")
        return "\n".join(lines)

    def set_domain(self, domain: str):
        """Set the detected domain for this request."""
        self.current_domain = domain

    def add_context(self, key: str, value: Any):
        """Add context that accumulates during processing."""
        self.accumulated_context[key] = value

    def get_context(self, key: str) -> Optional[Any]:
        """Get accumulated context."""
        return self.accumulated_context.get(key)

    def get_session_duration_seconds(self) -> float:
        """Get duration of current session in seconds."""
        start = datetime.fromisoformat(self.session_start)
        now = datetime.now(timezone.utc)
        return (now - start).total_seconds()

    def get_request_duration_seconds(self) -> Optional[float]:
        """Get duration of current request in seconds."""
        if not self.request_start:
            return None
        start = datetime.fromisoformat(self.request_start)
        now = datetime.now(timezone.utc)
        return (now - start).total_seconds()

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of working memory state."""
        return {
            "current_request": self.current_request[:100] if self.current_request else None,
            "domain": self.current_domain,
            "iteration_count": self.iteration_count,
            "deliberation_rounds": len(self.deliberation_history),
            "quality_feedback_count": len(self.quality_feedback),
            "session_duration_seconds": round(self.get_session_duration_seconds(), 1),
            "request_duration_seconds": round(self.get_request_duration_seconds() or 0, 1),
        }
