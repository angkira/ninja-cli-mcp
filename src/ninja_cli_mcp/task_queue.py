"""
Task queue for per-repo serialization.

Ensures only one task runs at a time per repository to prevent conflicts.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, TypeVar

from ninja_cli_mcp.logging_utils import get_logger


logger = get_logger(__name__)

T = TypeVar("T")


class RepoTaskQueue:
    """
    Task queue that serializes execution per repository.
    
    Multiple repos can execute concurrently, but tasks for the same repo
    are serialized to prevent file conflicts.
    """
    
    def __init__(self):
        """Initialize the task queue."""
        self._semaphores: dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(1))
        self._task_counts: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()
    
    async def execute_with_lock(
        self,
        repo_root: str | Path,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any
    ) -> T:
        """
        Execute a function with repo-level locking.
        
        Args:
            repo_root: Repository root path (used as lock key).
            func: Async function to execute.
            *args: Positional arguments for func.
            **kwargs: Keyword arguments for func.
            
        Returns:
            Result from func.
        """
        repo_key = str(Path(repo_root).resolve())
        semaphore = self._semaphores[repo_key]
        
        # Increment task count
        async with self._lock:
            self._task_counts[repo_key] += 1
            waiting = self._task_counts[repo_key] - 1
            if waiting > 0:
                logger.info(
                    f"[{repo_key}] Task queued, {waiting} task(s) ahead"
                )
        
        try:
            async with semaphore:
                logger.debug(f"[{repo_key}] Acquired repo lock, executing task")
                result = await func(*args, **kwargs)
                return result
        finally:
            # Decrement task count
            async with self._lock:
                self._task_counts[repo_key] -= 1
                if self._task_counts[repo_key] == 0:
                    # Clean up empty entries
                    del self._task_counts[repo_key]
                    # Note: Keep semaphore around for future tasks
    
    def get_queue_status(self, repo_root: str | Path) -> dict[str, Any]:
        """
        Get queue status for a repository.
        
        Args:
            repo_root: Repository root path.
            
        Returns:
            Dict with queue statistics.
        """
        repo_key = str(Path(repo_root).resolve())
        return {
            "repo": repo_key,
            "queued_tasks": self._task_counts.get(repo_key, 0),
            "locked": self._semaphores[repo_key].locked() if repo_key in self._semaphores else False,
        }
    
    def get_all_queues_status(self) -> dict[str, dict[str, Any]]:
        """
        Get status for all repository queues.
        
        Returns:
            Dict mapping repo paths to their queue status.
        """
        return {
            repo: self.get_queue_status(repo)
            for repo in self._task_counts.keys()
        }


# Global task queue instance
_task_queue = RepoTaskQueue()


def get_task_queue() -> RepoTaskQueue:
    """Get the global task queue instance."""
    return _task_queue
