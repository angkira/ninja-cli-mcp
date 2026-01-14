"""Tools for resource management in Ninja MCP."""

from typing import Optional
from uuid import uuid4

from ninja_common.logging_utils import get_logger
from ninja_common.security import monitored, rate_limited
from ninja_resources.models import (
    ResourceCodebaseRequest,
    ResourceCodebaseResult,
    ResourceConfigRequest,
    ResourceConfigResult,
    ResourceDocsRequest,
    ResourceDocsResult,
)
from ninja_resources.resource_manager import ResourceManager


logger = get_logger(__name__)

# Global executor instance for singleton pattern
_executor_instance: Optional["ResourceToolExecutor"] = None


class ResourceToolExecutor:
    """Executor for resource MCP tools."""

    def __init__(self) -> None:
        """Initialize ResourceToolExecutor with ResourceManager."""
        self.manager = ResourceManager()

    @rate_limited(60, 60)
    @monitored
    async def resource_codebase(
        self, request: ResourceCodebaseRequest, client_id: str = "default"
    ) -> ResourceCodebaseResult:
        """
        Load codebase resources.

        Args:
            request: Resource codebase request.
            client_id: Client identifier for rate limiting.

        Returns:
            Resource codebase result with loaded structure and files.
        """
        try:
            logger.info(f"Loading codebase resource for client {client_id}")

            # Call manager to load codebase
            result = await self.manager.load_codebase(
                repo_root=request.repo_root,
                include_patterns=request.include_patterns,
                exclude_patterns=request.exclude_patterns,
                max_files=request.max_files,
            )

            resource_id = f"codebase-{uuid4()}"

            # Create structure info from result, with defaults for missing fields
            structure_data = result.get("structure", {})
            from ninja_resources.models import StructureInfo

            # Ensure all required fields are present
            structure_data.setdefault("directories", [])
            structure_data.setdefault("languages", [])
            structure_data.setdefault("file_count", 0)
            structure_data.setdefault("total_size_mb", 0.0)
            structure = StructureInfo(**structure_data)

            return ResourceCodebaseResult(
                status="ok",
                resource_id=resource_id,
                summary=result.get("summary", ""),
                structure=structure,
                files=result.get("files", []),
            )

        except Exception as e:
            logger.error(f"Error loading codebase resource: {e!s}", exc_info=True)
            return ResourceCodebaseResult(
                status="error",
                resource_id="",
                summary=f"Error: {e!s}",
                structure={
                    "directories": [],
                    "languages": [],
                    "file_count": 0,
                    "total_size_mb": 0.0,
                },
                files=[],
            )

    @rate_limited(60, 60)
    @monitored
    async def resource_config(
        self, request: ResourceConfigRequest, client_id: str = "default"
    ) -> ResourceConfigResult:
        """
        Load configuration resources.

        Args:
            request: Resource config request.
            client_id: Client identifier for rate limiting.

        Returns:
            Resource config result with loaded configuration files.
        """
        try:
            logger.info(f"Loading config resource for client {client_id}")

            # Call manager to load config
            result = await self.manager.load_config(
                repo_root=request.repo_root, config_patterns=request.include
            )

            resource_id = f"config-{uuid4()}"

            return ResourceConfigResult(
                status="ok", resource_id=resource_id, files=result.get("files", [])
            )

        except Exception as e:
            logger.error(f"Error loading config resource: {e!s}", exc_info=True)
            return ResourceConfigResult(status="error", resource_id="", files=[])

    @rate_limited(60, 60)
    @monitored
    async def resource_docs(
        self, request: ResourceDocsRequest, client_id: str = "default"
    ) -> ResourceDocsResult:
        """
        Load documentation resources.

        Args:
            request: Resource docs request.
            client_id: Client identifier for rate limiting.

        Returns:
            Resource docs result with loaded documentation files.
        """
        try:
            logger.info(f"Loading docs resource for client {client_id}")

            # Call manager to load docs
            result = await self.manager.load_docs(
                repo_root=request.repo_root, doc_patterns=request.doc_patterns
            )

            resource_id = f"docs-{uuid4()}"

            return ResourceDocsResult(
                status="ok", resource_id=resource_id, docs=result.get("entries", [])
            )

        except Exception as e:
            logger.error(f"Error loading docs resource: {e!s}", exc_info=True)
            return ResourceDocsResult(status="error", resource_id="", docs=[])


def get_executor() -> ResourceToolExecutor:
    """
    Get the singleton instance of ResourceToolExecutor.

    Returns:
        ResourceToolExecutor instance.
    """
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = ResourceToolExecutor()
    return _executor_instance
