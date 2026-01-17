"""
Predefined benchmark tasks for testing CLI tools and models.

This module provides a set of standard benchmark tasks covering different
complexity levels and use cases.
"""

from ninja_coder.benchmark.framework import BenchmarkTask

# Quick tasks - simple, single-pass operations
QUICK_TASKS = [
    BenchmarkTask(
        id="simple_function",
        name="Simple Function",
        description="Create a simple utility function",
        task_spec="Create a Python function called 'add_numbers' that takes two integers and returns their sum. Include type hints and a docstring.",
        expected_files=["utils.py"],
        complexity="quick",
    ),
    BenchmarkTask(
        id="hello_world",
        name="Hello World",
        description="Create a basic hello world program",
        task_spec="Create a Python file called 'hello.py' with a main function that prints 'Hello, World!'",
        expected_files=["hello.py"],
        complexity="quick",
    ),
]

# Sequential tasks - multi-step with dependencies
SEQUENTIAL_TASKS = [
    BenchmarkTask(
        id="class_with_methods",
        name="Class with Methods",
        description="Create a class with multiple methods",
        task_spec=(
            "Create a Python file called 'user.py' with a User class that has:\n"
            "- __init__ method taking name and email\n"
            "- validate_email method that checks email format\n"
            "- get_display_name method that returns formatted name\n"
            "Include type hints and docstrings for all methods."
        ),
        expected_files=["user.py"],
        complexity="sequential",
    ),
    BenchmarkTask(
        id="api_endpoint",
        name="API Endpoint",
        description="Create a REST API endpoint with validation",
        task_spec=(
            "Create a FastAPI endpoint in 'api.py' that:\n"
            "- Defines a POST /users endpoint\n"
            "- Accepts JSON with name and email fields\n"
            "- Validates the input\n"
            "- Returns appropriate status codes\n"
            "Include Pydantic models for request/response."
        ),
        expected_files=["api.py"],
        complexity="sequential",
    ),
]

# Parallel tasks - independent operations
PARALLEL_TASKS = [
    BenchmarkTask(
        id="multiple_utilities",
        name="Multiple Utility Functions",
        description="Create several independent utility functions",
        task_spec=(
            "Create the following utility functions in separate files:\n"
            "1. string_utils.py: reverse_string, capitalize_words\n"
            "2. math_utils.py: factorial, fibonacci\n"
            "3. list_utils.py: flatten_list, unique_elements\n"
            "Each function should have type hints and docstrings."
        ),
        expected_files=["string_utils.py", "math_utils.py", "list_utils.py"],
        complexity="parallel",
    ),
]

# All tasks combined
ALL_TASKS = QUICK_TASKS + SEQUENTIAL_TASKS + PARALLEL_TASKS


def get_task_by_id(task_id: str) -> BenchmarkTask | None:
    """Get a benchmark task by ID.

    Args:
        task_id: Task identifier.

    Returns:
        BenchmarkTask if found, None otherwise.
    """
    for task in ALL_TASKS:
        if task.id == task_id:
            return task
    return None


def get_tasks_by_complexity(complexity: str) -> list[BenchmarkTask]:
    """Get all tasks of a given complexity level.

    Args:
        complexity: Complexity level ('quick', 'sequential', 'parallel').

    Returns:
        List of matching tasks.
    """
    return [task for task in ALL_TASKS if task.complexity == complexity]
