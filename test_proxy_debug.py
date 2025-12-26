#!/usr/bin/env python3
"""Debug test for proxy"""
import asyncio
import os
import sys


# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from ninja_common.daemon import stdio_to_http_proxy
from ninja_common.logging_utils import get_logger, setup_logging


# Enable debug logging
setup_logging("DEBUG")
logger = get_logger(__name__)

async def test_proxy():
    """Test proxy connection"""
    url = "http://127.0.0.1:8100/sse"
    logger.info(f"Testing proxy connection to {url}")

    try:
        await asyncio.wait_for(stdio_to_http_proxy(url), timeout=5.0)
    except TimeoutError:
        logger.info("Proxy test timeout (expected)")
    except Exception as e:
        logger.error(f"Proxy test error: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(test_proxy())
