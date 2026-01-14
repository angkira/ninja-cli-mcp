"""Pydantic models for the resources module."""


from typing import Literal

from pydantic import BaseModel, Field


class ResourceCodebaseRequest(BaseModel):
    """Request model for codebase resource analysis."""

    repo_root: str = Field(
        ..., description="Path to the repository root directory", example="/home/user/my-project"
    )
    include_patterns: list[str] = Field(
        default_factory=list,
        description="Patterns to include in the analysis",
        example=["*.py", "*.js"],
    )
    exclude_patterns: list[str] = Field(
        default_factory=list,
        description="Patterns to exclude from the analysis",
        example=["*.test.py", "__pycache__"],
    )
    max_files: int = Field(
        default=1000, description="Maximum number of files to analyze", example=500
    )
    summarize: bool = Field(default=True, description="Whether to generate summaries for files")


class FileInfo(BaseModel):
    """Information about a single file."""

    path: str = Field(..., description="Relative path to the file", example="src/main.py")
    language: str = Field(..., description="Programming language of the file", example="Python")
    lines: int = Field(..., description="Number of lines in the file", example=150)
    summary: str | None = Field(
        default=None,
        description="Summary of the file's purpose and functionality",
        example="Main entry point for the application",
    )
    functions: list[str] = Field(
        default_factory=list,
        description="List of function names in the file",
        example=["main", "process_data"],
    )
    classes: list[str] = Field(
        default_factory=list,
        description="List of class names in the file",
        example=["DataProcessor", "FileHandler"],
    )


class StructureInfo(BaseModel):
    """Information about the codebase structure."""

    directories: list[str] = Field(
        ..., description="List of directories in the codebase", example=["src", "tests", "docs"]
    )
    languages: list[str] = Field(
        ..., description="List of programming languages used", example=["Python", "JavaScript"]
    )
    file_count: int = Field(..., description="Total number of files in the codebase", example=42)
    total_size_mb: float = Field(
        ..., description="Total size of the codebase in megabytes", example=2.5
    )


class ResourceCodebaseResult(BaseModel):
    """Result model for codebase resource analysis."""

    status: Literal["ok", "error"] = Field(..., description="Status of the operation")
    resource_id: str = Field(
        ..., description="Unique identifier for the resource", example="codebase-12345"
    )
    summary: str | None = Field(
        default=None,
        description="Summary of the entire codebase",
        example="A web application for managing tasks",
    )
    structure: StructureInfo = Field(..., description="Structural information about the codebase")
    files: list[FileInfo] = Field(..., description="List of file information")


class ResourceConfigRequest(BaseModel):
    """Request model for configuration resource analysis."""

    repo_root: str = Field(
        ..., description="Path to the repository root directory", example="/home/user/my-project"
    )
    include: list[str] = Field(
        default_factory=list,
        description="Configuration files to include",
        example=[".env", "config.yaml", "settings.json"],
    )
    redact_patterns: list[str] = Field(
        default_factory=list,
        description="Patterns for content to redact in configuration files",
        example=["password", "secret", "key"],
    )


class ConfigFile(BaseModel):
    """Representation of a configuration file."""

    path: str = Field(
        ..., description="Relative path to the configuration file", example="config/settings.yaml"
    )
    content: str = Field(
        ...,
        description="Content of the configuration file (redacted as needed)",
        example="database_url: ***\napi_key: ***",
    )


class ResourceConfigResult(BaseModel):
    """Result model for configuration resource analysis."""

    status: Literal["ok", "error"] = Field(..., description="Status of the operation")
    resource_id: str = Field(
        ..., description="Unique identifier for the resource", example="config-12345"
    )
    files: list[ConfigFile] = Field(..., description="List of configuration files")


class ResourceDocsRequest(BaseModel):
    """Request model for documentation resource analysis."""

    repo_root: str = Field(
        ..., description="Path to the repository root directory", example="/home/user/my-project"
    )
    doc_patterns: list[str] = Field(
        default_factory=list,
        description="Patterns to identify documentation files",
        example=["*.md", "docs/*.rst", "README.*"],
    )
    include_structure: bool = Field(
        default=True, description="Whether to include directory structure information"
    )


class DocEntry(BaseModel):
    """Representation of a documentation entry."""

    path: str = Field(
        ...,
        description="Relative path to the documentation file",
        example="docs/getting_started.md",
    )
    title: str = Field(
        ..., description="Title of the documentation", example="Getting Started Guide"
    )
    sections: list[str] = Field(
        ...,
        description="List of section headers in the documentation",
        example=["Installation", "Configuration", "Usage"],
    )
    summary: str | None = Field(
        default=None,
        description="Summary of the documentation content",
        example="Guide for new users to install and configure the application",
    )


class ResourceDocsResult(BaseModel):
    """Result model for documentation resource analysis."""

    status: Literal["ok", "error"] = Field(..., description="Status of the operation")
    resource_id: str = Field(
        ..., description="Unique identifier for the resource", example="docs-12345"
    )
    docs: list[DocEntry] = Field(..., description="List of documentation entries")
