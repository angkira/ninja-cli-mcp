"""Configuration helper functions."""

from typing import Any


def get_config_value(config: dict[str, Any], key: str, default: Any = None) -> Any:
    """Get configuration value with fallback to default.
    
    Args:
        config: Configuration dictionary
        key: Configuration key to retrieve
        default: Default value if key not found
        
    Returns:
        Configuration value or default
    """
    return config.get(key, default)


def set_config_value(config: dict[str, Any], key: str, value: Any) -> dict[str, Any]:
    """Set configuration value and return updated config.
    
    Args:
        config: Configuration dictionary
        key: Configuration key to set
        value: Value to set
        
    Returns:
        Updated configuration dictionary
    """
    config[key] = value
    return config
