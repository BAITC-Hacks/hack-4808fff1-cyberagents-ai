from __future__ import annotations

from .schemas import DialogState


class SessionStore:
    def __init__(self):
        self._states: dict[str, DialogState] = {}

    def get(self, session_id: str) -> DialogState:
        if session_id not in self._states:
            self._states[session_id] = DialogState(session_id=session_id)
        return self._states[session_id]

    def reset(self, session_id: str) -> None:
        self._states.pop(session_id, None)


sessions = SessionStore()
