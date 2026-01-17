"""
Benchmark framework for comparing CLI tools and models.

This package provides tools for benchmarking different CLI implementations
(Aider, OpenCode) and models across various task types.
"""

from ninja_coder.benchmark.framework import BenchmarkRunner, BenchmarkResult, BenchmarkTask

__all__ = [
    "BenchmarkRunner",
    "BenchmarkResult",
    "BenchmarkTask",
]
