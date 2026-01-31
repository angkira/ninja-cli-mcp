from functools import wraps
from typing import Any

from . import prompts, resources, tools


# Store registered resources, prompts, and tools
_registered_resources = {}
_registered_prompts = {}
_registered_tools = {}

def resource(name: str):
    """Decorator to register a resource"""
    def decorator(func):
        _registered_resources[name] = func
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        return wrapper
    return decorator

def prompt(name: str):
    """Decorator to register a prompt"""
    def decorator(func):
        _registered_prompts[name] = func
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        return wrapper
    return decorator

def call_tool(name: str):
    """Decorator to register a tool"""
    def decorator(func):
        _registered_tools[name] = func
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# Register all resources
for name, func in resources.__dict__.items():
    if callable(func) and hasattr(func, '__annotations__'):
        resource(name)(func)

# Register all prompts
for name, func in prompts.__dict__.items():
    if callable(func) and hasattr(func, '__annotations__'):
        prompt(name)(func)

# Register all tools
for name, func in tools.__dict__.items():
    if callable(func) and hasattr(func, '__annotations__'):
        call_tool(name)(func)

# Expose the lists for external access
resources_list = list(_registered_resources.keys())
prompts_list = list(_registered_prompts.keys())
tools_list = list(_registered_tools.keys())

async def execute_resource(name: str, **kwargs) -> Any:
    """Execute a registered resource by name"""
    if name not in _registered_resources:
        raise ValueError(f"Resource '{name}' not found")
    func = _registered_resources[name]
    return await func(**kwargs)

async def execute_prompt(name: str, **kwargs) -> Any:
    """Execute a registered prompt by name"""
    if name not in _registered_prompts:
        raise ValueError(f"Prompt '{name}' not found")
    func = _registered_prompts[name]
    return await func(**kwargs)

async def execute_tool(name: str, **kwargs) -> Any:
    """Execute a registered tool by name"""
    if name not in _registered_tools:
        raise ValueError(f"Tool '{name}' not found")
    func = _registered_tools[name]
    return await func(**kwargs)
