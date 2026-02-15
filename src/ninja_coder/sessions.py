"""
Session management for persistent conversations across tasks.

Provides session creation, persistence, and retrieval for maintaining
conversation history in multi-turn coding workflows.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ninja_common.logging_utils import get_logger


if TYPE_CHECKING:
    from pathlib import Path


logger = get_logger(__name__)


@dataclass
class SessionMessage:
    """Single message in conversation."""

    role: str  # "system", "user", "assistant"
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionMessage:
        """Create from dict."""
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Session:
    """Conversation session with persistent history."""

    session_id: str
    repo_root: str
    model: str
    created_at: datetime
    updated_at: datetime
    messages: list[SessionMessage] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_message(self, role: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        """Add message to session.

        Args:
            role: Message role (system, user, assistant).
            content: Message content.
            metadata: Optional message metadata.
        """
        msg = SessionMessage(role=role, content=content, metadata=metadata or {})
        self.messages.append(msg)
        self.updated_at = datetime.now(UTC)
        logger.debug(f"Added {role} message to session {self.session_id}")

    def get_message_count(self) -> int:
        """Get total message count."""
        return len(self.messages)

    def get_user_messages(self) -> list[SessionMessage]:
        """Get all user messages."""
        return [msg for msg in self.messages if msg.role == "user"]

    def get_assistant_messages(self) -> list[SessionMessage]:
        """Get all assistant messages."""
        return [msg for msg in self.messages if msg.role == "assistant"]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "session_id": self.session_id,
            "repo_root": self.repo_root,
            "model": self.model,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "messages": [msg.to_dict() for msg in self.messages],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Session:
        """Deserialize from dict."""
        messages = [SessionMessage.from_dict(msg) for msg in data.get("messages", [])]
        return cls(
            session_id=data["session_id"],
            repo_root=data["repo_root"],
            model=data["model"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            messages=messages,
            metadata=data.get("metadata", {}),
        )


class SessionManager:
    """Manages persistent conversation sessions."""

    def __init__(self, cache_dir: Path):
        """Initialize session manager.

        Args:
            cache_dir: Directory for session storage.
        """
        self.cache_dir = cache_dir
        self.sessions_dir = cache_dir / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Session manager initialized: {self.sessions_dir}")

    def create_session(
        self,
        repo_root: str,
        model: str,
        system_prompt: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Session:
        """Create new session.

        Args:
            repo_root: Repository root path.
            model: Model name.
            system_prompt: Optional system prompt.
            metadata: Optional session metadata.

        Returns:
            New Session instance.
        """
        session_id = str(uuid.uuid4())[:8]
        now = datetime.now(UTC)

        session = Session(
            session_id=session_id,
            repo_root=repo_root,
            model=model,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )

        if system_prompt:
            session.add_message("system", system_prompt)

        self._save_session(session)
        logger.info(f"✅ Created session {session_id} for {repo_root} (model: {model})")
        return session

    def load_session(self, session_id: str) -> Session | None:
        """Load existing session.

        Args:
            session_id: Session identifier.

        Returns:
            Session instance or None if not found.
        """
        session_file = self.sessions_dir / f"{session_id}.json"
        if not session_file.exists():
            logger.warning(f"Session {session_id} not found")
            return None

        try:
            with open(session_file) as f:
                data = json.load(f)
                session = Session.from_dict(data)
                logger.info(f"📂 Loaded session {session_id} ({len(session.messages)} messages)")
                return session
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            return None

    def save_session(self, session: Session) -> None:
        """Save session to disk.

        Args:
            session: Session to save.
        """
        self._save_session(session)
        logger.debug(f"Saved session {session.session_id}")

    def _save_session(self, session: Session) -> None:
        """Internal save implementation."""
        session_file = self.sessions_dir / f"{session.session_id}.json"
        try:
            with open(session_file, "w") as f:
                json.dump(session.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save session {session.session_id}: {e}")
            raise

    def list_sessions(self, repo_root: str | None = None) -> list[Session]:
        """List all sessions, optionally filtered by repo.

        Args:
            repo_root: Optional repo root to filter by.

        Returns:
            List of Session instances sorted by updated_at (newest first).
        """
        sessions = []
        for session_file in self.sessions_dir.glob("*.json"):
            try:
                with open(session_file) as f:
                    data = json.load(f)
                    if repo_root is None or data["repo_root"] == repo_root:
                        sessions.append(Session.from_dict(data))
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Skipping invalid session file {session_file}: {e}")
                continue

        # Sort by updated_at (most recent first)
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        logger.debug(f"Listed {len(sessions)} sessions")
        return sessions

    def delete_session(self, session_id: str) -> bool:
        """Delete session.

        Args:
            session_id: Session identifier.

        Returns:
            True if deleted, False if not found.
        """
        session_file = self.sessions_dir / f"{session_id}.json"
        if session_file.exists():
            session_file.unlink()
            logger.info(f"🗑️  Deleted session {session_id}")
            return True
        logger.warning(f"Session {session_id} not found for deletion")
        return False

    def get_session_summary(self, session_id: str) -> dict[str, Any] | None:
        """Get session summary without loading full messages.

        Args:
            session_id: Session identifier.

        Returns:
            Dict with session metadata or None if not found.
        """
        session = self.load_session(session_id)
        if not session:
            return None

        return {
            "session_id": session.session_id,
            "repo_root": session.repo_root,
            "model": session.model,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "message_count": len(session.messages),
            "user_message_count": len(session.get_user_messages()),
            "assistant_message_count": len(session.get_assistant_messages()),
            "metadata": session.metadata,
        }
