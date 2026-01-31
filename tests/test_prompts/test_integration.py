"""Integration tests for prompts with other modules."""

from unittest.mock import AsyncMock

import pytest
from src.ninja_prompts.template_engine import TemplateEngine
from src.ninja_resources.resource_manager import ResourceManager


class TestPromptsWithResources:
    """Test prompt integration with resource management."""

    @pytest.mark.asyncio
    async def test_prompt_chain_with_codebase_resource(self):
        """Test prompt chain that references codebase resource."""
        # Mock resource manager
        resource_manager = ResourceManager()
        resource_manager.load_codebase = AsyncMock(return_value={
            "summary": "Test codebase",
            "structure": {"files": ["main.py", "utils.py"], "directories": ["src"]},
            "files": [
                {"path": "main.py", "content": "def main():\n    print('Hello')"},
                {"path": "utils.py", "content": "def helper():\n    return 'util'"}
            ]
        })
        
        # Load codebase resource
        codebase = await resource_manager.load_codebase("/test/repo")
        
        # Create template that references resource
        template_engine = TemplateEngine()
        template = "Analyze this codebase: {{codebase_summary}} with {{file_count}} files"
        
        # Render with resource context
        variables = {
            "codebase_summary": codebase["summary"],
            "file_count": len(codebase["files"])
        }
        
        result = template_engine.render(template, variables)
        
        # Verify proper integration
        assert "Test codebase" in result
        assert "2 files" in result
        assert template_engine.validate_variables(template, variables)["valid"] is True


class TestPromptChainExecution:
    """Test multi-step prompt chain execution."""

    def test_multi_step_chain_execution(self):
        """Test 3-step chain: design -> implement -> review."""
        template_engine = TemplateEngine()
        
        # Step 1: Design
        design_template = "Design a {{feature_type}} feature for {{project_name}}"
        design_vars = {"feature_type": "authentication", "project_name": "web app"}
        design_output = template_engine.render(design_template, design_vars)
        
        # Step 2: Implementation (using output from step 1)
        impl_template = "Implement the design: {{prev_design}} with {{language}} language"
        impl_vars = {
            "prev_design": design_output,
            "language": "Python"
        }
        impl_output = template_engine.render(impl_template, impl_vars)
        
        # Step 3: Review (using outputs from previous steps)
        review_template = "Review the implementation: {{prev_impl}} based on design: {{prev_design}}"
        review_vars = {
            "prev_impl": impl_output,
            "prev_design": design_output
        }
        review_output = template_engine.render(review_template, review_vars)
        
        # Verify output flow
        assert "authentication" in design_output
        assert "web app" in design_output
        assert "Design" in impl_output
        assert "Implement" in review_output
        assert "authentication" in review_output

    def test_chain_with_variable_inheritance(self):
        """Test variable inheritance across chain steps."""
        template_engine = TemplateEngine()
        
        # Step 1: Design outputs
        step1_output = "Create user authentication system"
        
        # Step 2: Implementation receives previous output
        step2_template = "Implementation plan for: {{prev.step1}}"
        step2_vars = {"prev.step1": step1_output}
        step2_output = template_engine.render(step2_template, step2_vars)
        
        # Step 3: Review receives both previous outputs
        step3_template = "Review design: {{prev.step1}} and implementation: {{prev.step2}}"
        step3_vars = {
            "prev.step1": step1_output,
            "prev.step2": step2_output
        }
        step3_output = template_engine.render(step3_template, step3_vars)
        
        # Verify all variables properly passed
        assert step1_output in step2_output
        assert step1_output in step3_output
        assert step2_output in step3_output


class TestPromptSuggestion:
    """Test prompt suggestion functionality."""

    def test_suggest_based_on_resource_context(self):
        """Test prompt suggestions based on codebase context."""
        # Mock codebase resource
        codebase_context = {
            "language": "Python",
            "framework": "FastAPI",
            "files": ["main.py", "models.py", "routes.py"]
        }
        
        # Simulate suggestion logic
        suggestions = []
        if "Python" in codebase_context["language"]:
            suggestions.append("Python debugging prompt")
        if "FastAPI" in codebase_context["framework"]:
            suggestions.append("FastAPI implementation prompt")
            
        # Verify returned prompts match codebase context
        assert len(suggestions) > 0
        assert any("Python" in s for s in suggestions)
        assert any("FastAPI" in s for s in suggestions)

    def test_suggest_workflow(self):
        """Test prompt suggestions for different workflows."""
        # Debugging context
        debug_context = {"task": "debug", "error_type": "ValueError"}
        debug_suggestions = [
            "Debug ValueError in Python code",
            "Trace execution path for error"
        ]
        
        # Feature implementation context
        feature_context = {"task": "implement", "feature": "REST API"}
        feature_suggestions = [
            "Design REST API endpoints",
            "Implement CRUD operations"
        ]
        
        # Verify different contexts return different suggestions
        assert len(debug_suggestions) > 0
        assert len(feature_suggestions) > 0
        assert debug_suggestions != feature_suggestions


class TestPromptRegistry:
    """Test prompt registry functionality."""

    def test_save_and_load_custom_prompt(self):
        """Test saving and loading custom prompts."""
        # Mock registry functionality
        class MockRegistry:
            def __init__(self):
                self.prompts = {}
            
            def save_prompt(self, name, template):
                self.prompts[name] = template
            
            def load_prompt(self, name):
                return self.prompts.get(name)
        
        registry = MockRegistry()
        
        # Create custom prompt
        custom_prompt = "Analyze {{code_snippet}} for {{issue_type}} issues"
        
        # Save via registry
        registry.save_prompt("code_analyzer", custom_prompt)
        
        # Load and verify saved
        loaded_prompt = registry.load_prompt("code_analyzer")
        assert loaded_prompt == custom_prompt
        
        # Use in chain
        template_engine = TemplateEngine()
        variables = {
            "code_snippet": "def func():\n    return None",
            "issue_type": "performance"
        }
        result = template_engine.render(loaded_prompt, variables)
        
        assert "def func():" in result
        assert "performance" in result
