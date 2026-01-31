
import pytest
from src.ninja_prompts.template_engine import TemplateEngine


class TestTemplateEngine:
    """Test suite for TemplateEngine class."""

    @pytest.fixture
    def template_engine(self):
        """Create a TemplateEngine instance for testing."""
        return TemplateEngine()

    def test_render_simple(self, template_engine):
        """Test simple variable replacement."""
        template = "Hello {{name}}, welcome to {{project}}!"
        variables = {"name": "Alice", "project": "Ninja CLI"}
        result = template_engine.render(template, variables)
        assert result == "Hello Alice, welcome to Ninja CLI!"

    def test_render_missing_var(self, template_engine):
        """Test handling of missing variables."""
        template = "Hello {{name}}, welcome to {{missing_var}}!"
        variables = {"name": "Alice"}
        result = template_engine.render(template, variables)
        # Missing variables should be left as-is
        assert result == "Hello Alice, welcome to {{missing_var}}!"

    def test_render_empty_variables(self, template_engine):
        """Test rendering with empty variables dict."""
        template = "Hello {{name}}!"
        variables = {}
        result = template_engine.render(template, variables)
        # Variables should be left as-is when none provided
        assert result == "Hello {{name}}!"

    def test_render_numeric_variables(self, template_engine):
        """Test rendering with numeric variable values."""
        template = "The answer is {{answer}} and count is {{count}}"
        variables = {"answer": 42, "count": 3.14}
        result = template_engine.render(template, variables)
        assert result == "The answer is 42 and count is 3.14"

    def test_render_complex_objects(self, template_engine):
        """Test rendering with complex object values."""
        template = "User: {{user}}, Settings: {{settings}}"
        variables = {
            "user": {"name": "Alice", "id": 123},
            "settings": ["dark_mode", "notifications"]
        }
        result = template_engine.render(template, variables)
        expected = "User: {'name': 'Alice', 'id': 123}, Settings: ['dark_mode', 'notifications']"
        assert result == expected

    def test_validate_variables(self, template_engine):
        """Test variable validation with required and provided variables."""
        template = "Hello {{name}}, you are {{age}} years old and work on {{project}}."
        provided_variables = {"name": "Alice", "age": 30, "extra": "unused"}
        
        result = template_engine.validate_variables(template, provided_variables)
        
        assert result["valid"] is False  # Missing 'project'
        assert "project" in result["missing_variables"]
        assert "extra" in result["extra_variables"]
        assert "name" not in result["missing_variables"]
        assert "age" not in result["missing_variables"]

    def test_validate_variables_all_provided(self, template_engine):
        """Test validation when all required variables are provided."""
        template = "Hello {{name}}, you are {{age}} years old."
        provided_variables = {"name": "Alice", "age": 30}
        
        result = template_engine.validate_variables(template, provided_variables)
        
        assert result["valid"] is True
        assert len(result["missing_variables"]) == 0
        assert len(result["extra_variables"]) == 0

    def test_validate_variables_none_required(self, template_engine):
        """Test validation when template has no variables."""
        template = "Hello world, no variables here."
        provided_variables = {"extra": "value"}
        
        result = template_engine.validate_variables(template, provided_variables)
        
        assert result["valid"] is True
        assert len(result["missing_variables"]) == 0
        assert "extra" in result["extra_variables"]

    def test_extract_variables(self, template_engine):
        """Test extraction of all variables from template."""
        template = "Hello {{name}}, you are {{age}} years old and work on {{project}}."
        variables = template_engine.extract_variables(template)
        
        assert len(variables) == 3
        assert "name" in variables
        assert "age" in variables
        assert "project" in variables

    def test_extract_variables_duplicates(self, template_engine):
        """Test extraction handles duplicate variables correctly."""
        template = "Hello {{name}}, {{name}}, you are {{age}} years old {{age}}."
        variables = template_engine.extract_variables(template)
        
        # Should extract all occurrences
        assert len(variables) == 4
        assert variables == ["name", "name", "age", "age"]

    def test_extract_variables_none(self, template_engine):
        """Test extraction when template has no variables."""
        template = "Hello world, no variables here."
        variables = template_engine.extract_variables(template)
        
        assert len(variables) == 0
        assert variables == []

    def test_extract_variables_malformed(self, template_engine):
        """Test extraction with malformed variable patterns."""
        template = "Hello {name} and {{incomplete, this {{should}} work."
        variables = template_engine.extract_variables(template)
        
        # Only properly formed {{variable}} patterns should be extracted
        assert len(variables) == 1
        assert variables == ["should"]

    def test_render_with_special_characters(self, template_engine):
        """Test rendering with special characters in variable values."""
        template = "Special: {{special_chars}}"
        variables = {"special_chars": "!@#$%^&*()_+-=[]{}|;':\",./<>?"}
        result = template_engine.render(template, variables)
        assert result == "Special: !@#$%^&*()_+-=[]{}|;':\",./<>?"

    def test_render_with_newlines(self, template_engine):
        """Test rendering with newlines in template and variables."""
        template = "Line 1\nHello {{name}}!\nLine 3"
        variables = {"name": "Alice\nwith newline"}
        result = template_engine.render(template, variables)
        assert result == "Line 1\nHello Alice\nwith newline!\nLine 3"

    @pytest.mark.parametrize("template,variables,expected", [
        ("", {}, ""),
        ("No vars", {}, "No vars"),
        ("{{var}}", {"var": "value"}, "value"),
        ("{{a}}{{b}}", {"a": "1", "b": "2"}, "12"),
    ])
    def test_render_parametrized(self, template_engine, template, variables, expected):
        """Parametrized test for various rendering scenarios."""
        result = template_engine.render(template, variables)
        assert result == expected
