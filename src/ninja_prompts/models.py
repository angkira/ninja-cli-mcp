"""Pydantic models for the prompts module."""

from datetime import datetime
from typing import List, Dict, Optional, Literal, Any
from pydantic import BaseModel, Field


class PromptVariable(BaseModel):
    """Variable definition for a prompt template."""
    
    name: str = Field(..., description="Name of the variable")
    required: bool = Field(..., description="Whether the variable is required")
    default: Optional[str] = Field(None, description="Default value for the variable")
    description: Optional[str] = Field(None, description="Description of the variable")


class PromptTemplate(BaseModel):
    """Prompt template definition."""
    
    id: str = Field(..., description="Unique identifier for the prompt")
    name: str = Field(..., description="Human-readable name of the prompt")
    description: str = Field(..., description="Description of what the prompt does")
    template: str = Field(..., description="The prompt template string")
    variables: List[PromptVariable] = Field(..., description="List of variables used in the prompt")
    tags: List[str] = Field(..., description="List of tags for categorization")
    scope: Literal["user", "global"] = Field(..., description="Scope of the prompt")
    created: datetime = Field(..., description="Creation timestamp")


class PromptRegistryRequest(BaseModel):
    """Request to the prompt registry."""
    
    action: Literal["list", "get", "create", "update", "delete"] = Field(
        ..., description="Action to perform"
    )
    prompt_id: Optional[str] = Field(None, description="ID of the prompt (for get/update/delete)")
    name: Optional[str] = Field(None, description="Name of the prompt (for create/update)")
    description: str = Field(..., description="Description of the prompt")
    template: str = Field(..., description="The prompt template string")
    variables: List[PromptVariable] = Field(..., description="List of variables used in the prompt")
    tags: List[str] = Field(..., description="List of tags for categorization")
    scope: Literal["user", "global"] = Field(..., description="Scope of the prompt")


class PromptRegistryResult(BaseModel):
    """Result from the prompt registry."""
    
    status: Literal["ok", "error"] = Field(..., description="Status of the operation")
    prompts: List[PromptTemplate] = Field(..., description="List of prompt templates")
    message: Optional[str] = Field(None, description="Optional message providing additional info")


class PromptSuggestRequest(BaseModel):
    """Request for prompt suggestions."""
    
    context: Dict[str, Any] = Field(
        ..., description="Context information including task, language, etc."
    )
    max_suggestions: int = Field(..., description="Maximum number of suggestions to return")


class PromptSuggestion(BaseModel):
    """A suggested prompt."""
    
    prompt_id: str = Field(..., description="ID of the suggested prompt")
    name: str = Field(..., description="Name of the suggested prompt")
    relevance_score: float = Field(
        ..., description="Relevance score between 0 and 1", ge=0.0, le=1.0
    )
    reason: str = Field(..., description="Reason for the suggestion")
    suggested_variables: Dict[str, str] = Field(
        ..., description="Suggested values for variables"
    )


class PromptSuggestResult(BaseModel):
    """Result from prompt suggestion."""
    
    status: Literal["ok", "error"] = Field(..., description="Status of the operation")
    suggestions: List[PromptSuggestion] = Field(..., description="List of prompt suggestions")
    message: Optional[str] = Field(None, description="Optional message providing additional info")


class PromptChainStep(BaseModel):
    """A step in a prompt chain."""
    
    name: str = Field(..., description="Name of the step")
    prompt_id: str = Field(..., description="ID of the prompt to use")
    variables: Dict[str, Any] = Field(..., description="Variables to pass to the prompt")


class PromptChainRequest(BaseModel):
    """Request for prompt chain operations."""
    
    action: Literal["list", "create", "execute"] = Field(..., description="Action to perform")
    chain_id: Optional[str] = Field(None, description="ID of the chain (for execute)")
    name: Optional[str] = Field(None, description="Name of the chain (for create)")
    steps: List[PromptChainStep] = Field(..., description="Steps in the chain")


class ChainStepOutput(BaseModel):
    """Output from a chain step."""
    
    step_name: str = Field(..., description="Name of the step")
    output: str = Field(..., description="Output from the step")


class PromptChainResult(BaseModel):
    """Result from prompt chain execution."""
    
    status: Literal["ok", "error"] = Field(..., description="Status of the operation")
    chain_id: Optional[str] = Field(None, description="ID of the chain")
    executed_steps: List[ChainStepOutput] = Field(..., description="Outputs from executed steps")
    message: Optional[str] = Field(None, description="Optional message providing additional info")
