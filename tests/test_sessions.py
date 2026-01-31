"""
Tests for session management functionality.

Tests session creation, persistence, continuation, listing, and deletion.
"""

import tempfile
from pathlib import Path

import pytest

from ninja_coder.driver import NinjaConfig, NinjaDriver
from ninja_coder.sessions import SessionManager


def test_session_manager_initialization():
    """Test SessionManager initialization."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        cache_dir = Path(tmp_dir)
        manager = SessionManager(cache_dir)

        assert manager.cache_dir == cache_dir
        assert manager.sessions_dir == cache_dir / "sessions"
        assert manager.sessions_dir.exists()


def test_session_creation():
    """Test session creation and persistence."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        cache_dir = Path(tmp_dir)
        manager = SessionManager(cache_dir)

        # Create session
        session = manager.create_session(
            repo_root="/tmp/test-repo",
            model="anthropic/claude-sonnet-4-5",
            system_prompt="You are a coding assistant",
            metadata={"test": "value"},
        )

        assert session.session_id is not None
        assert len(session.session_id) == 8  # UUID[:8]
        assert session.repo_root == "/tmp/test-repo"
        assert session.model == "anthropic/claude-sonnet-4-5"
        assert len(session.messages) == 1  # System prompt
        assert session.messages[0].role == "system"
        assert session.metadata["test"] == "value"

        # Verify session file exists
        session_file = cache_dir / "sessions" / f"{session.session_id}.json"
        assert session_file.exists()


def test_session_load():
    """Test session loading."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        cache_dir = Path(tmp_dir)
        manager = SessionManager(cache_dir)

        # Create session
        session = manager.create_session(
            repo_root="/tmp/test-repo",
            model="anthropic/claude-sonnet-4-5",
        )
        session.add_message("user", "Create a User class")
        manager.save_session(session)

        # Load session
        loaded = manager.load_session(session.session_id)

        assert loaded is not None
        assert loaded.session_id == session.session_id
        assert loaded.repo_root == session.repo_root
        assert loaded.model == session.model
        assert len(loaded.messages) == 1  # User message


def test_session_messages():
    """Test adding messages to session."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        cache_dir = Path(tmp_dir)
        manager = SessionManager(cache_dir)

        session = manager.create_session(
            repo_root="/tmp/test-repo",
            model="anthropic/claude-sonnet-4-5",
        )

        # Add user message
        session.add_message("user", "Create a User class")
        assert len(session.messages) == 1
        assert session.messages[0].role == "user"

        # Add assistant message
        session.add_message("assistant", "Created User class in user.py", metadata={"success": True})
        assert len(session.messages) == 2
        assert session.messages[1].role == "assistant"
        assert session.messages[1].metadata["success"] is True

        # Verify counts
        assert session.get_message_count() == 2
        assert len(session.get_user_messages()) == 1
        assert len(session.get_assistant_messages()) == 1


def test_list_sessions():
    """Test listing sessions."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        cache_dir = Path(tmp_dir)
        manager = SessionManager(cache_dir)

        # Create multiple sessions
        session1 = manager.create_session(
            repo_root="/tmp/repo1",
            model="anthropic/claude-sonnet-4-5",
        )
        session2 = manager.create_session(
            repo_root="/tmp/repo2",
            model="anthropic/claude-sonnet-4-5",
        )
        session3 = manager.create_session(
            repo_root="/tmp/repo1",
            model="anthropic/claude-sonnet-4-5",
        )

        # List all sessions
        all_sessions = manager.list_sessions()
        assert len(all_sessions) == 3

        # List repo-filtered sessions
        repo1_sessions = manager.list_sessions(repo_root="/tmp/repo1")
        assert len(repo1_sessions) == 2

        repo2_sessions = manager.list_sessions(repo_root="/tmp/repo2")
        assert len(repo2_sessions) == 1


def test_delete_session():
    """Test session deletion."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        cache_dir = Path(tmp_dir)
        manager = SessionManager(cache_dir)

        # Create session
        session = manager.create_session(
            repo_root="/tmp/test-repo",
            model="anthropic/claude-sonnet-4-5",
        )

        session_id = session.session_id
        session_file = cache_dir / "sessions" / f"{session_id}.json"

        # Verify exists
        assert session_file.exists()

        # Delete session
        deleted = manager.delete_session(session_id)
        assert deleted is True
        assert not session_file.exists()

        # Try to load deleted session
        loaded = manager.load_session(session_id)
        assert loaded is None

        # Try to delete non-existent session
        deleted = manager.delete_session(session_id)
        assert deleted is False


def test_session_summary():
    """Test session summary generation."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        cache_dir = Path(tmp_dir)
        manager = SessionManager(cache_dir)

        # Create session with messages
        session = manager.create_session(
            repo_root="/tmp/test-repo",
            model="anthropic/claude-sonnet-4-5",
            metadata={"project": "test"},
        )
        session.add_message("user", "Create a User class")
        session.add_message("assistant", "Created User class")
        session.add_message("user", "Add email validation")
        manager.save_session(session)

        # Get summary
        summary = manager.get_session_summary(session.session_id)

        assert summary is not None
        assert summary["session_id"] == session.session_id
        assert summary["repo_root"] == "/tmp/test-repo"
        assert summary["model"] == "anthropic/claude-sonnet-4-5"
        assert summary["message_count"] == 3
        assert summary["user_message_count"] == 2
        assert summary["assistant_message_count"] == 1
        assert summary["metadata"]["project"] == "test"


@pytest.mark.asyncio
async def test_driver_session_integration():
    """Test NinjaDriver integration with sessions."""
    # Note: This test requires OpenCode to be installed and configured
    # Skip if not available
    config = NinjaConfig.from_env()

    # Only run if OpenCode is configured
    if not config.bin_path or "opencode" not in config.bin_path:
        pytest.skip("OpenCode not configured, skipping integration test")

    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_root = Path(tmp_dir)

        # Create a simple test file structure
        (repo_root / "README.md").write_text("# Test Project\n")

        driver = NinjaDriver(config)

        # Test session creation (without actually executing - would need CLI)
        # Just verify the session manager is initialized
        assert driver.session_manager is not None
        assert driver.session_manager.sessions_dir.exists()


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
