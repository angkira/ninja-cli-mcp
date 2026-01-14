"""Prompt management for loading, saving, and managing prompts."""

from pathlib import Path

import yaml

from ninja_prompts.models import PromptTemplate, PromptVariable


class PromptManager:
    """Manages prompt templates from user and builtin sources."""

    def __init__(self):
        """Initialize prompt manager with user and builtin directories."""
        self.user_dir = Path.home() / ".ninja-mcp" / "prompts"
        # Try to find builtin prompts in package data directory
        self.builtin_dir = Path(__file__).parent.parent.parent / "data" / "builtin_prompts"

    def load_prompts(self, scope: str = "all") -> dict[str, PromptTemplate]:
        """Load prompts from specified scope.

        Args:
            scope: "user" (user saved), "global" (builtin), or "all" (both, user overrides)

        Returns:
            Dictionary of prompt_id -> PromptTemplate
        """
        prompts: dict[str, PromptTemplate] = {}

        if scope in ("global", "all"):
            prompts.update(self._load_from_directory(self.builtin_dir, "global"))

        if scope in ("user", "all"):
            prompts.update(self._load_from_directory(self.user_dir, "user"))

        return prompts

    def _load_from_directory(self, directory: Path, scope: str) -> dict[str, PromptTemplate]:
        """Load all YAML prompt files from a directory.

        Args:
            directory: Directory path to load from
            scope: "user" or "global"

        Returns:
            Dictionary of prompt_id -> PromptTemplate
        """
        prompts: dict[str, PromptTemplate] = {}

        if not directory.exists():
            return prompts

        try:
            for yaml_file in directory.glob("*.yml"):
                try:
                    with open(yaml_file) as f:
                        data = yaml.safe_load(f)
                        if data:
                            # Convert variables list to PromptVariable objects if needed
                            if "variables" in data and isinstance(data["variables"], list):
                                data["variables"] = [
                                    PromptVariable(**v) if isinstance(v, dict) else v
                                    for v in data["variables"]
                                ]
                            # Set scope
                            data["scope"] = scope
                            # Extract ID from filename if not in data
                            if "id" not in data:
                                data["id"] = yaml_file.stem
                            prompt = PromptTemplate(**data)
                            prompts[prompt.id] = prompt
                except Exception:
                    # Skip unparseable YAML files
                    continue
        except Exception:
            # Handle directory read errors gracefully
            pass

        return prompts

    def get_prompt(self, prompt_id: str) -> PromptTemplate | None:
        """Retrieve a specific prompt by ID.

        Args:
            prompt_id: The prompt identifier

        Returns:
            PromptTemplate if found, None otherwise
        """
        prompts = self.load_prompts("all")
        return prompts.get(prompt_id)

    def list_prompts(self) -> list[PromptTemplate]:
        """List all available prompts.

        Returns:
            List of PromptTemplate objects
        """
        prompts = self.load_prompts("all")
        return list(prompts.values())

    def save_prompt(self, prompt: PromptTemplate) -> str:
        """Save a prompt to user directory.

        Args:
            prompt: PromptTemplate to save

        Returns:
            The prompt ID
        """
        # Create user directory if needed
        self.user_dir.mkdir(parents=True, exist_ok=True)

        # Convert to dict for YAML
        prompt_data = prompt.model_dump(exclude={"scope", "created"})

        # Write to YAML file
        yaml_file = self.user_dir / f"{prompt.id}.yml"
        with open(yaml_file, "w") as f:
            yaml.safe_dump(prompt_data, f, default_flow_style=False)

        return prompt.id

    def delete_prompt(self, prompt_id: str) -> bool:
        """Delete a user prompt.

        Args:
            prompt_id: The prompt to delete

        Returns:
            True if deleted, False if not found
        """
        yaml_file = self.user_dir / f"{prompt_id}.yml"
        if yaml_file.exists():
            yaml_file.unlink()
            return True
        return False
