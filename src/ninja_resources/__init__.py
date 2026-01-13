"""Resource management module for Ninja MCP."""

__version__ = "0.2.0"

from ninja_resources.models import (
    ResourceCodebaseRequest,
    FileInfo,
    StructureInfo,
    ResourceCodebaseResult,
    ResourceConfigRequest,
    ConfigFile,
    ResourceConfigResult,
    ResourceDocsRequest,
    DocEntry,
    ResourceDocsResult,
)

from ninja_resources.resource_manager import ResourceManager
from ninja_resources.tools import ResourceToolExecutor

_executor = None

def get_executor() -> ResourceToolExecutor:
    global _executor
    if _executor is None:
        _executor = ResourceToolExecutor()
    return _executor

__all__ = [
    "ResourceCodebaseRequest",
    "FileInfo",
    "StructureInfo",
    "ResourceCodebaseResult",
    "ResourceConfigRequest",
    "ConfigFile",
    "ResourceConfigResult",
    "ResourceDocsRequest",
    "DocEntry",
    "ResourceDocsResult",
    "ResourceManager",
    "ResourceToolExecutor",
    "get_executor",
]
