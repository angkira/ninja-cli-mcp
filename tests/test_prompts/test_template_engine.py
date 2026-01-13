import pytest
from src.ninja_prompts.template_engine import TemplateEngine


class TestTemplateEngine:
    """Test cases for the TemplateEngine class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = TemplateEngine()

    def test_render_simple_variables(self):
        """Test rendering template with simple variables."""
        template = "Hello {{name}}, welcome to {{place}}!"
        variables = {"name": "Alice", "place": "Wonderland"}
        result = self.engine.render(template, variables)
        assert result == "Hello Alice, welcome to Wonderland!"

    def test_render_missing_variables(self):
        """Test rendering template with missing variables."""
        template = "Hello {{name}}, welcome to {{place}}!"
        variables = {"name": "Alice"}
        result = self.engine.render(template, variables)
        assert result == "Hello Alice, welcome to {{place}}!"

    def test_render_empty_variables(self):
        """Test rendering template with empty variable values."""
        template = "Hello {{name}}, welcome to {{place}}!"
        variables = {"name": "", "place": "Wonderland"}
        result = self.engine.render(template, variables)
        assert result == "Hello , welcome to Wonderland!"

    def test_render_numeric_variables(self):
        """Test rendering template with numeric variable values."""
        template = "The answer is {{answer}} and count is {{count}}"
        variables = {"answer": 42, "count": 100}
        result = self.engine.render(template, variables)
        assert result == "The answer is 42 and count is 100"

    def test_extract_variables(self):
        """Test extracting variables from template."""
        template = "Hello {{name}}, welcome to {{place}}! Your score is {{score}}."
        variables = self.engine.extract_variables(template)
        assert set(variables) == {"name", "place", "score"}

    def test_extract_variables_no_matches(self):
        """Test extracting variables from template with no variables."""
        template = "Hello, welcome to our place!"
        variables = self.engine.extract_variables(template)
        assert variables == []

    def test_extract_variables_duplicate_variables(self):
        """Test extracting variables when duplicates exist."""
        template = "Hello {{name}}, {{name}}! Welcome to {{place}} and {{place}}."
        variables = self.engine.extract_variables(template)
        assert set(variables) == {"name", "place"}

    def test_validate_variables_all_provided(self):
        """Test validation when all variables are provided."""
        template = "Hello {{name}}, welcome to {{place}}!"
        provided = {"name": "Alice", "place": "Wonderland", "extra": "value"}
        result = self.engine.validate_variables(template, provided)
        assert result["valid"] is True
        assert result["missing_variables"] == []
        assert result["extra_variables"] == ["extra"]

    def test_validate_variables_missing_required(self):
        """Test validation when required variables are missing."""
        template = "Hello {{name}}, welcome to {{place}}!"
        provided = {"name": "Alice"}
        result = self.engine.validate_variables(template, provided)
        assert result["valid"] is False
        assert result["missing_variables"] == ["place"]
        assert result["extra_variables"] == []

    def test_validate_variables_empty_template(self):
        """Test validation with empty template."""
        template = "Hello, welcome!"
        provided = {"name": "Alice"}
        result = self.engine.validate_variables(template, provided)
        assert result["valid"] is True
        assert result["missing_variables"] == []
        assert result["extra_variables"] == ["name"]

    def test_render_special_characters(self):
        """Test rendering with special characters in variables."""
        template = "User: {{username}}, Email: {{email}}"
        variables = {"username": "alice@wonderland", "email": "alice+test@wonderland.com"}
        result = self.engine.render(template, variables)
        assert result == "User: alice@wonderland, Email: alice+test@wonderland.com"
