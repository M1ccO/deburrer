"""Job session management for the web UI.

Each session tracks the lifecycle of one job:
  feature → tool → operation → pipeline result → preview → NC

Sessions are in-memory (dictionary) with automatic cleanup.
No persistence — reload the page and start fresh.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

from ..api.job_schema import JobSpec


@dataclass
class JobSession:
    id: str
    feature_json: Optional[dict] = None
    job_spec: Optional[JobSpec] = None
    tool_json: Optional[dict] = None
    operation_json: Optional[dict] = None
    pipeline_result: Optional[dict] = None
    model_data: Optional[dict] = None
    step_content: Optional[bytes] = None
    step_filename: str = ""
    topology_selection: Optional[dict] = None
    fixture_data: Optional[dict] = None
    stock_data: Optional[dict] = None
    collision_status: Optional[dict] = None
    preview_json: Optional[str] = None
    nc_output: Optional[str] = None
    status: str = "created"
    errors: list = field(default_factory=list)


class SessionStore:
    def __init__(self):
        self._sessions: Dict[str, JobSession] = {}

    def create(self) -> JobSession:
        session = JobSession(id=uuid.uuid4().hex[:12])
        self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Optional[JobSession]:
        return self._sessions.get(session_id)

    def remove(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


_session_store = SessionStore()


def get_store() -> SessionStore:
    return _session_store
