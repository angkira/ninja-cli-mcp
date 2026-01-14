import logging
import re
from typing import Any


logger = logging.getLogger(__name__)


class TemplateEngine:
    """
    A template engine for rendering templates with variable substitution.

    Supports:
    - Simple variable substitution: {{variable_name}}
    - Chain step output access: {{prev.step_name}}
    - Variable validation and extraction
    """

    def __init__(self):
        """Initialize the template engine."""
        pass

    def render(self, template_str: str, variables: dict[str, Any]) -> str:
        """
        Render a template string by substituting variables.

        Args:
            template_str: The template string containing {{variable}} patterns
            variables: Dictionary of variable names and their values

        Returns:
            Rendered string with variables substituted

        Raises:
            KeyError: If a required variable is missing and error_on_missing is True
        """
        # Pattern to match {{variable_name}} patterns (including prev.step_name)
        pattern = r"\{\{([.\w]+)\}\}"

        def replace_variable(match):
            var_name = match.group(1)
            if var_name in variables:
                return str(variables[var_name])
            else:
                logger.warning(f"Missing variable: {var_name}")
                return match.group(0)  # Leave as-is if missing

        try:
            result = re.sub(pattern, replace_variable, template_str)
            return result
        except Exception as e:
            logger.error(f"Error rendering template: {e}")
            raise

    def validate_variables(
        self, template_str: str, provided_variables: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Validate which variables are required and which are provided.

        Args:
            template_str: The template string to analyze
            provided_variables: Dictionary of provided variable names and values

        Returns:
            Dictionary with validation results:
            - valid: Boolean indicating if all required variables are provided
            - missing_variables: List of variable names that are required but missing
            - extra_variables: List of variable names that are provided but not used
        """
        required_variables = self.extract_variables(template_str)
        provided_variable_names = set(provided_variables.keys())
        required_variable_names = set(required_variables)

        missing_variables = list(required_variable_names - provided_variable_names)
        extra_variables = list(provided_variable_names - required_variable_names)

        valid = len(missing_variables) == 0

        return {
            "valid": valid,
            "missing_variables": missing_variables,
            "extra_variables": extra_variables,
        }

    def extract_variables(self, template_str: str) -> list[str]:
        """
        Extract all variable names from a template string.

        Args:
            template_str: The template string to analyze

        Returns:
            List of variable names found in the template
        """
        # Pattern to match {{variable_name}} patterns (including prev.step_name)
        pattern = r"\{\{([.\w]+)\}\}"
        matches = re.findall(pattern, template_str)
        return list(matches)
