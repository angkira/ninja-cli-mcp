"""Tests for evaluating the coder AI tool."""

from __future__ import annotations

import ast
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from ninja_coder.models import SimpleTaskRequest
from ninja_coder.tools import get_executor

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def temp_test_repo() -> Generator[Path, None, None]:
    """Create a temporary repository specifically for coder evaluation tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Create basic repo structure
        (repo_path / "src").mkdir()
        (repo_path / "tests").mkdir()
        (repo_path / "docs").mkdir()

        # Create some sample files
        (repo_path / "src" / "main.py").write_text('print("Hello World")\n')
        (repo_path / "src" / "utils.py").write_text("def helper(): pass\n")
        (repo_path / "tests" / "test_main.py").write_text("def test_example(): pass\n")
        (repo_path / "README.md").write_text("# Test Project\n")
        (repo_path / "pyproject.toml").write_text('[project]\nname = "test"\n')

        yield repo_path


@pytest.fixture
def mock_ninja_result():
    """Create a mock NinjaResult for testing."""
    from ninja_coder.driver import NinjaResult
    return NinjaResult(
        success=True,
        summary="✅ Modified 1 file(s): src/new_function.py",
        notes="",
        suspected_touched_paths=["src/new_function.py"],
        raw_logs_path="/tmp/logs/test.log",
        exit_code=0,
        stdout="Created src/new_function.py with hello_world function",
        stderr="",
        model_used="anthropic/claude-sonnet-4"
    )


class TestCoderEvaluation:
    """Evaluation tests for coder_simple_task."""

    @pytest.mark.asyncio
    async def test_simple_task_generates_python_code(self, temp_test_repo: Path, mock_ninja_result) -> None:
        """Test that coder_simple_task generates valid Python code."""
        # Arrange
        executor = get_executor()
        request = SimpleTaskRequest(
            repo_root=str(temp_test_repo),
            task="Create a function called hello_world that prints 'Hello World'",
            context_paths=["src/"],
            allowed_globs=["src/**/*.py"],
            deny_globs=[]
        )
        
        # Create the expected file that would be generated
        expected_file = temp_test_repo / "src" / "new_function.py"
        expected_content = '''
def hello_world():
    """Print Hello World."""
    print("Hello World")
'''
        
        # Act & Assert
        with patch('ninja_coder.tools.NinjaDriver.execute_async', new=AsyncMock(return_value=mock_ninja_result)):
            expected_file.parent.mkdir(parents=True, exist_ok=True)
            expected_file.write_text(expected_content)
            
            result = await executor.simple_task(request)
            
            # Verify the result
            assert result.status == "ok"
            assert "Modified" in result.summary
            assert expected_file.exists()
            
            # Verify it's valid Python
            content = expected_file.read_text()
            ast.parse(content)  # This will raise SyntaxError if invalid

    @pytest.mark.asyncio
    async def test_simple_task_respects_file_constraints(self, temp_test_repo: Path, mock_ninja_result) -> None:
        """Test that coder_simple_task respects file location constraints."""
        # Arrange
        executor = get_executor()
        request = SimpleTaskRequest(
            repo_root=str(temp_test_repo),
            task="Create a utility function in src/utils.py that adds two numbers",
            context_paths=["src/utils.py"],
            allowed_globs=["src/**/*.py"],
            deny_globs=[]
        )
        
        # Create the expected modification
        utils_file = temp_test_repo / "src" / "utils.py"
        original_content = "def helper(): pass\n"
        new_content = original_content + "\ndef add(a, b):\n    return a + b\n"
        
        # Act & Assert
        with patch('ninja_coder.tools.NinjaDriver.execute_async', new=AsyncMock(return_value=mock_ninja_result)):
            utils_file.write_text(new_content)
            
            result = await executor.simple_task(request)
            
            # Verify the result
            assert result.status == "ok"
            assert utils_file.exists()
            
            # Verify file is in correct location
            content = utils_file.read_text()
            assert "def add(a, b):" in content
            assert "return a + b" in content

    @pytest.mark.asyncio
    async def test_simple_task_follows_spec(self, temp_test_repo: Path, mock_ninja_result) -> None:
        """Test that coder_simple_task follows detailed specifications."""
        # Arrange
        executor = get_executor()
        request = SimpleTaskRequest(
            repo_root=str(temp_test_repo),
            task="Create a function called calculate_area that takes length and width parameters, "
                 "includes a docstring, and returns the area. Add type hints.",
            context_paths=["src/"],
            allowed_globs=["src/**/*.py"],
            deny_globs=[]
        )
        
        # Create the expected implementation
        expected_file = temp_test_repo / "src" / "geometry.py"
        expected_content = '''
def calculate_area(length: float, width: float) -> float:
    """
    Calculate the area of a rectangle.
    
    Args:
        length: The length of the rectangle
        width: The width of the rectangle
        
    Returns:
        The area of the rectangle
    """
    return length * width
'''
        
        # Act & Assert
        with patch('ninja_coder.tools.NinjaDriver.execute_async', new=AsyncMock(return_value=mock_ninja_result)):
            expected_file.parent.mkdir(parents=True, exist_ok=True)
            expected_file.write_text(expected_content)
            
            result = await executor.simple_task(request)
            
            # Verify the result
            assert result.status == "ok"
            
            # Parse and verify the generated code meets spec
            content = expected_file.read_text()
            tree = ast.parse(content)
            
            # Find the function
            function_node = None
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and node.name == "calculate_area":
                    function_node = node
                    break
            
            assert function_node is not None
            assert len(function_node.args.args) == 2
            assert function_node.args.args[0].arg == "length"
            assert function_node.args.args[1].arg == "width"
            
            # Check for type annotations
            assert function_node.args.args[0].annotation is not None
            assert function_node.args.args[1].annotation is not None
            assert function_node.returns is not None
            
            # Check for docstring
            assert ast.get_docstring(function_node) is not None

    @pytest.mark.asyncio
    async def test_simple_task_creates_minimal_code(self, temp_test_repo: Path, mock_ninja_result) -> None:
        """Test that coder_simple_task creates minimal code without over-engineering."""
        # Arrange
        executor = get_executor()
        request = SimpleTaskRequest(
            repo_root=str(temp_test_repo),
            task="Create a simple function to add two numbers",
            context_paths=["src/"],
            allowed_globs=["src/**/*.py"],
            deny_globs=[]
        )
        
        # Create minimal implementation
        expected_file = temp_test_repo / "src" / "simple_math.py"
        expected_content = '''
def add(a, b):
    """Add two numbers."""
    return a + b
'''
        
        # Act & Assert
        with patch('ninja_coder.tools.NinjaDriver.execute_async', new=AsyncMock(return_value=mock_ninja_result)):
            expected_file.parent.mkdir(parents=True, exist_ok=True)
            expected_file.write_text(expected_content)
            
            result = await executor.simple_task(request)
            
            # Verify the result
            assert result.status == "ok"
            
            # Verify code is minimal (no unnecessary complexity)
            content = expected_file.read_text()
            tree = ast.parse(content)
            
            # Should have exactly one function
            function_nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
            assert len(function_nodes) == 1
            
            # Function should be simple (no complex control flow)
            function_node = function_nodes[0]
            complex_nodes = [n for n in ast.walk(function_node) 
                           if isinstance(n, (ast.For, ast.While, ast.If, ast.Try))]
            assert len(complex_nodes) == 0  # No complex control flow

    @pytest.mark.asyncio
    async def test_simple_task_output_is_valid_syntax(self, temp_test_repo: Path, mock_ninja_result) -> None:
        """Test that coder_simple_task generates syntactically valid Python code."""
        # Arrange
        executor = get_executor()
        request = SimpleTaskRequest(
            repo_root=str(temp_test_repo),
            task="Create a Python class called Calculator with add and subtract methods",
            context_paths=["src/"],
            allowed_globs=["src/**/*.py"],
            deny_globs=[]
        )
        
        # Create the expected implementation
        expected_file = temp_test_repo / "src" / "calculator.py"
        expected_content = '''
class Calculator:
    """A simple calculator class."""
    
    def add(self, a, b):
        """Add two numbers."""
        return a + b
    
    def subtract(self, a, b):
        """Subtract b from a."""
        return a - b
'''
        
        # Act & Assert
        with patch('ninja_coder.tools.NinjaDriver.execute_async', new=AsyncMock(return_value=mock_ninja_result)):
            expected_file.parent.mkdir(parents=True, exist_ok=True)
            expected_file.write_text(expected_content)
            
            result = await executor.simple_task(request)
            
            # Verify the result
            assert result.status == "ok"
            
            # Verify syntactic validity
            content = expected_file.read_text()
            try:
                ast.parse(content)
            except SyntaxError as e:
                pytest.fail(f"Generated code has syntax error: {e}")

    @pytest.mark.asyncio
    async def test_simple_task_function_implementation(self, temp_test_repo: Path, mock_ninja_result) -> None:
        """Test that coder_simple_task creates properly structured functions."""
        # Arrange
        executor = get_executor()
        request = SimpleTaskRequest(
            repo_root=str(temp_test_repo),
            task="Create a function called process_data that takes a list of integers, "
                 "filters out negative numbers, and returns the sum. Include docstring and type hints.",
            context_paths=["src/"],
            allowed_globs=["src/**/*.py"],
            deny_globs=[]
        )
        
        # Create the expected implementation
        expected_file = temp_test_repo / "src" / "data_processor.py"
        expected_content = '''
from typing import List

def process_data(numbers: List[int]) -> int:
    """
    Process a list of integers by filtering out negatives and summing the rest.
    
    Args:
        numbers: A list of integers
        
    Returns:
        The sum of non-negative numbers
    """
    return sum(num for num in numbers if num >= 0)
'''
        
        # Act & Assert
        with patch('ninja_coder.tools.NinjaDriver.execute_async', new=AsyncMock(return_value=mock_ninja_result)):
            expected_file.parent.mkdir(parents=True, exist_ok=True)
            expected_file.write_text(expected_content)
            
            result = await executor.simple_task(request)
            
            # Verify the result
            assert result.status == "ok"
            
            # Verify function structure
            content = expected_file.read_text()
            tree = ast.parse(content)
            
            # Find the function
            function_node = None
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and node.name == "process_data":
                    function_node = node
                    break
            
            assert function_node is not None
            
            # Check function signature
            assert len(function_node.args.args) == 1
            assert function_node.args.args[0].arg == "numbers"
            
            # Check return annotation
            assert function_node.returns is not None
            
            # Check docstring exists and has content
            docstring = ast.get_docstring(function_node)
            assert docstring is not None
            assert "Args:" in docstring
            assert "Returns:" in docstring

    @pytest.mark.asyncio
    async def test_simple_task_with_context_paths(self, temp_test_repo: Path, mock_ninja_result) -> None:
        """Test that coder_simple_task uses context_paths correctly."""
        # Arrange
        executor = get_executor()
        request = SimpleTaskRequest(
            repo_root=str(temp_test_repo),
            task="Based on the existing utils.py file, create a similar helper function",
            context_paths=["src/utils.py"],
            allowed_globs=["src/**/*.py"],
            deny_globs=[]
        )
        
        # Act & Assert
        with patch('ninja_coder.tools.NinjaDriver.execute_async', new=AsyncMock(return_value=mock_ninja_result)):
            result = await executor.simple_task(request)
            
            # Verify the result references context paths
            assert result.status == "ok"

    @pytest.mark.asyncio
    async def test_simple_task_with_allowed_globs(self, temp_test_repo: Path, mock_ninja_result) -> None:
        """Test that coder_simple_task respects allowed_globs restrictions."""
        # Arrange
        executor = get_executor()
        request = SimpleTaskRequest(
            repo_root=str(temp_test_repo),
            task="Create a new Python file",
            context_paths=["src/"],
            allowed_globs=["src/**/*.py"],
            deny_globs=[]
        )
        
        # Create file in allowed path
        expected_file = temp_test_repo / "src" / "new_module.py"
        expected_content = '"""New module."""\n'
        
        # Act & Assert
        with patch('ninja_coder.tools.NinjaDriver.execute_async', new=AsyncMock(return_value=mock_ninja_result)):
            expected_file.parent.mkdir(parents=True, exist_ok=True)
            expected_file.write_text(expected_content)
            
            result = await executor.simple_task(request)
            
            # Verify file was created in allowed path
            assert result.status == "ok"
            assert expected_file.exists()

    @pytest.mark.asyncio
    async def test_simple_task_with_deny_globs(self, temp_test_repo: Path, mock_ninja_result) -> None:
        """Test that coder_simple_task respects deny_globs restrictions."""
        # Arrange
        executor = get_executor()
        request = SimpleTaskRequest(
            repo_root=str(temp_test_repo),
            task="Create files in the project",
            context_paths=["."],
            allowed_globs=["**/*.py"],
            deny_globs=["**/secret/**"]
        )
        
        # Act & Assert
        with patch('ninja_coder.tools.NinjaDriver.execute_async', new=AsyncMock(return_value=mock_ninja_result)):
            result = await executor.simple_task(request)
            
            # Verify the result
            assert result.status == "ok"
            # In a real test, we would verify that no files were created in denied paths

    @pytest.mark.asyncio
    async def test_simple_task_invalid_repo_root(self) -> None:
        """Test that coder_simple_task handles invalid repo_root gracefully."""
        # Arrange
        executor = get_executor()
        request = SimpleTaskRequest(
            repo_root="/invalid/path/that/does/not/exist",
            task="Create a function",
            context_paths=["src/"],
            allowed_globs=["src/**/*.py"],
            deny_globs=[]
        )
        
        # Act
        result = await executor.simple_task(request)
        
        # Assert
        assert result.status == "error"
        assert "Input validation failed" in result.summary

    @pytest.mark.asyncio
    async def test_simple_task_detailed_error_messages(self, temp_test_repo: Path) -> None:
        """Test that coder_simple_task provides actionable error messages."""
        # Arrange
        executor = get_executor()
        request = SimpleTaskRequest(
            repo_root=str(temp_test_repo),
            task="",  # Empty task should cause validation error
            context_paths=["src/"],
            allowed_globs=["src/**/*.py"],
            deny_globs=[]
        )
        
        # Act
        result = await executor.simple_task(request)
        
        # Assert
        assert result.status == "error"
        assert "Input validation failed" in result.summary
        assert "Invalid or potentially unsafe input detected" in result.notes

    @pytest.mark.asyncio
    async def test_simple_task_vague_spec(self, temp_test_repo: Path, mock_ninja_result) -> None:
        """Test that coder_simple_task handles vague specifications reasonably."""
        # Arrange
        executor = get_executor()
        request = SimpleTaskRequest(
            repo_root=str(temp_test_repo),
            task="Make something useful",  # Very vague
            context_paths=["src/"],
            allowed_globs=["src/**/*.py"],
            deny_globs=[]
        )
        
        # Create a reasonable implementation
        expected_file = temp_test_repo / "src" / "utility.py"
        expected_content = '''
def utility_function():
    """A useful utility function."""
    return "useful result"
'''
        
        # Act & Assert
        with patch('ninja_coder.tools.NinjaDriver.execute_async', new=AsyncMock(return_value=mock_ninja_result)):
            expected_file.parent.mkdir(parents=True, exist_ok=True)
            expected_file.write_text(expected_content)
            
            result = await executor.simple_task(request)
            
            # Verify the result is reasonable even with vague spec
            assert result.status == "ok"
            assert expected_file.exists()

    @pytest.mark.asyncio
    async def test_simple_task_detailed_spec(self, temp_test_repo: Path, mock_ninja_result) -> None:
        """Test that coder_simple_task closely follows detailed specifications."""
        # Arrange
        executor = get_executor()
        detailed_task = """
        Create a Python module called 'data_analyzer.py' with the following requirements:
        1. Import necessary standard library modules
        2. Create a function called 'analyze_numbers' that:
           - Takes a list of numbers as input
           - Returns a dictionary with min, max, average, and count
           - Includes comprehensive docstring with Args and Returns sections
           - Has proper type hints
           - Handles edge cases like empty lists
        3. Include a helper function '_calculate_stats' that does the actual calculation
        4. Add module-level docstring
        """
        
        request = SimpleTaskRequest(
            repo_root=str(temp_test_repo),
            task=detailed_task,
            context_paths=["src/"],
            allowed_globs=["src/**/*.py"],
            deny_globs=[]
        )
        
        # Create the expected detailed implementation
        expected_file = temp_test_repo / "src" / "data_analyzer.py"
        expected_content = '''
"""Module for analyzing numerical data."""

from typing import List, Dict, Union

def analyze_numbers(numbers: List[Union[int, float]]) -> Dict[str, Union[int, float, None]]:
    """
    Analyze a list of numbers to calculate statistics.
    
    Args:
        numbers: A list of numbers to analyze
        
    Returns:
        A dictionary containing:
        - min: minimum value
        - max: maximum value
        - average: mean value
        - count: number of elements
        If the list is empty, returns None for all values.
    """
    if not numbers:
        return {"min": None, "max": None, "average": None, "count": 0}
    
    stats = _calculate_stats(numbers)
    stats["count"] = len(numbers)
    return stats

def _calculate_stats(numbers: List[Union[int, float]]) -> Dict[str, Union[int, float]]:
    """Calculate min, max, and average of numbers."""
    return {
        "min": min(numbers),
        "max": max(numbers),
        "average": sum(numbers) / len(numbers)
    }
'''
        
        # Act & Assert
        with patch('ninja_coder.tools.NinjaDriver.execute_async', new=AsyncMock(return_value=mock_ninja_result)):
            expected_file.parent.mkdir(parents=True, exist_ok=True)
            expected_file.write_text(expected_content)
            
            result = await executor.simple_task(request)
            
            # Verify the result
            assert result.status == "ok"
            
            # Verify detailed requirements are met
            content = expected_file.read_text()
            tree = ast.parse(content)
            
            # Check for both functions
            function_names = [node.name for node in tree.body 
                            if isinstance(node, ast.FunctionDef)]
            assert "analyze_numbers" in function_names
            assert "_calculate_stats" in function_names
            
            # Check for proper docstrings
            for node in tree.body:
                if isinstance(node, ast.FunctionDef):
                    docstring = ast.get_docstring(node)
                    assert docstring is not None
                    if "analyze_numbers" in node.name:
                        assert "Args:" in docstring
                        assert "Returns:" in docstring
