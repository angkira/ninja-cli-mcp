# OpenCode Integration

**Module:** `ninja_config.opencode_integration`
**Version:** 2.0.0
**Status:** Production Ready

## Overview

The OpenCode integration module provides bidirectional synchronization between ninja's hierarchical configuration format and OpenCode CLI's expected format. It handles environment variable setup, config transformation (snake_case ↔ camelCase), and file management for seamless integration.

## Quick Start

```python
from ninja_config.opencode_integration import OpenCodeIntegration
from ninja_config.config_schema import NinjaConfig

# Initialize integration
integration = OpenCodeIntegration()

# Sync ninja config to OpenCode
success = integration.sync_to_opencode(ninja_config)
```

## Features

- ✓ Bidirectional config sync (ninja ↔ OpenCode)
- ✓ Environment variable management
- ✓ Case conversion (snake_case ↔ camelCase)
- ✓ Secure file operations (600 permissions)
- ✓ Provider routing support
- ✓ Custom model configuration
- ✓ Comprehensive error handling
- ✓ 27 comprehensive tests

## Documentation

For complete API reference, examples, and usage guide, see:
- Examples: `examples/opencode_integration_example.py`
- Tests: `tests/test_common/test_opencode_integration.py`
- Architecture: `.agent/CONFIG_ARCHITECTURE_DESIGN.md` section 4

## Usage Examples

See `examples/opencode_integration_example.py` for 7 comprehensive examples.
