#!/usr/bin/env python3
"""
Model recommendation system using LiveBench data.
Called by install_interactive.sh to get model suggestions.
"""

import csv
import io
import json
import re
import sys
import urllib.request
from collections import defaultdict
from typing import Any


# LiveBench CSV date - update as needed
LIVEBENCH_DATE = "2025_11_25"


def _extract_base_model_name(model_name: str) -> str:
    """
    Extracts the base model name, removing variations.

    Examples:
    - claude-opus-4-5-20251101-medium-effort -> claude-opus-4-5
    - gpt-5.1-codex-max-high -> gpt-5.1-codex
    - deepseek-v3.2-thinking -> deepseek-v3.2
    """
    # Remove common suffixes
    suffixes_to_remove = [
        "-high-effort",
        "-medium-effort",
        "-low-effort",
        "-high",
        "-medium",
        "-low",
        "-thinking-64k",
        "-thinking-32k",
        "-thinking",
        "-nothinking",
        "-base",
        "-preview",
        "-exp",
        ":free",
    ]

    base = model_name.lower()

    # Remove suffixes
    for suffix in suffixes_to_remove:
        if suffix in base:
            base = base.split(suffix)[0]

    # Remove dates (format YYYYMMDD or YYYY-MM-DD)
    base = re.sub(r"-\d{8}", "", base)  # -20251101
    base = re.sub(r"-\d{4}-\d{2}-\d{2}", "", base)  # -2025-11-01
    base = re.sub(r"-\d{4}_\d{2}_\d{2}", "", base)  # -2025_11_01

    return base.strip("-")


def deduplicate_models(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Removes duplicate models, keeping only unique base names with best scores.

    Args:
        models: List of models with score

    Returns:
        List of unique models (best variant of each base model)
    """
    grouped = defaultdict(list)

    # Group by base name
    for model in models:
        base_name = _extract_base_model_name(model["name"])
        grouped[base_name].append(model)

    unique_models = []

    for base_name, variants in grouped.items():
        # Take variant with best score
        best = max(variants, key=lambda x: x["score"])
        unique_models.append({**best, "base_name": base_name})

    # Sort by score
    unique_models.sort(key=lambda x: x["score"], reverse=True)

    return unique_models


def fetch_livebench_models() -> list[dict[str, Any]]:
    """Fetch coding models from LiveBench."""
    try:
        url = f"https://livebench.ai/table_{LIVEBENCH_DATE}.csv"
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0")

        with urllib.request.urlopen(req, timeout=10) as response:
            csv_data = response.read().decode("utf-8")

        reader = csv.DictReader(io.StringIO(csv_data))
        models = []

        for row in reader:
            model = row["model"]

            # Get coding-specific scores
            code_gen = float(row.get("code_generation", 0) or 0)
            code_comp = float(row.get("code_completion", 0) or 0)
            python_score = float(row.get("python", 0) or 0)

            # Calculate average coding score
            coding_scores = [s for s in [code_gen, code_comp, python_score] if s > 0]

            if coding_scores:
                avg_coding = sum(coding_scores) / len(coding_scores)
                models.append(
                    {
                        "name": model,
                        "score": avg_coding,
                        "code_gen": code_gen,
                        "code_comp": code_comp,
                        "python": python_score,
                    }
                )

        return sorted(models, key=lambda x: x["score"], reverse=True)

    except Exception:
        # Fallback to hardcoded list if LiveBench fails
        return []


def get_model_pricing(model_name: str) -> float:
    """Estimate model price per 1M tokens."""
    name = model_name.lower()

    if "opus-4" in name or "o1" in name:
        return 15.0
    elif "sonnet-4" in name or "gpt-4o" in name or "sonnet-3.5" in name:
        return 3.0
    elif "gemini-2.0-flash" in name or "gemini-flash" in name:
        return 0.075
    elif "haiku" in name or "gpt-4o-mini" in name:
        return 0.15
    elif "deepseek-v3" in name or "deepseek-coder" in name:
        return 0.14
    elif "qwen-2.5-coder-32b" in name:
        return 0.30
    elif "qwen" in name or "llama" in name:
        return 0.05
    elif "phi" in name:
        return 0.0  # Free
    else:
        return 1.0


def get_model_speed(model_name: str) -> str:
    """Estimate model speed category."""
    name = model_name.lower()

    if "flash" in name or "mini" in name or "phi" in name:
        return "⚡ Very Fast"
    elif "haiku" in name or "turbo" in name or "qwen" in name:
        return "🚀 Fast"
    elif "sonnet" in name or "gpt-4o" in name:
        return "⚖️ Balanced"
    elif "opus" in name or "o1" in name:
        return "🐢 Slow"
    else:
        return "⚖️ Medium"


def normalize_model_name(name: str) -> str:
    """Convert LiveBench name to OpenRouter format."""
    name = name.lower()

    # Map LiveBench names to OpenRouter format
    mappings = {
        "claude-opus-4": "anthropic/claude-opus-4",
        "claude-sonnet-4": "anthropic/claude-sonnet-4",
        "claude-sonnet-3.5": "anthropic/claude-sonnet-3.5",
        "claude-haiku-4.5": "anthropic/claude-haiku-4.5-20250929",
        "gpt-4o": "openai/gpt-4o",
        "gpt-4o-mini": "openai/gpt-4o-mini",
        "o1": "openai/o1",
        "o1-mini": "openai/o1-mini",
        "gemini-2.0-flash-thinking-exp": "google/gemini-2.0-flash-thinking-exp",
        "gemini-2.0-flash-exp": "google/gemini-2.0-flash-exp",
        "gemini-flash": "google/gemini-flash-1.5",
        "deepseek-v3": "deepseek/deepseek-chat",
        "deepseek-coder-v2": "deepseek/deepseek-coder",
        "qwen-2.5-coder-32b": "qwen/qwen-2.5-coder-32b-instruct",
        "qwen2.5-72b": "qwen/qwen-2.5-72b-instruct",
        "llama-3.3-70b": "meta-llama/llama-3.3-70b-instruct",
        "phi-4": "microsoft/phi-4",
    }

    # Try exact match first
    for key, value in mappings.items():
        if key in name:
            return value

    # If no match, try to construct reasonable name
    if "claude" in name:
        return f"anthropic/{name}"
    elif "gpt" in name or "o1" in name:
        return f"openai/{name}"
    elif "gemini" in name:
        return f"google/{name}"
    elif "qwen" in name:
        return f"qwen/{name}"
    elif "llama" in name:
        return f"meta-llama/{name}"
    elif "phi" in name:
        return f"microsoft/{name}"
    elif "deepseek" in name:
        return f"deepseek/{name}"

    return name


def get_model_recommendations(category: str) -> list[dict[str, Any]]:
    """
    Get model recommendations by category.

    Categories:
    - coder: Best for code generation (Coder module)
    - researcher: Best for research/synthesis (Researcher module)
    - secretary: Best for quick summaries (Secretary module)
    """
    # Try to fetch from LiveBench
    livebench_models = fetch_livebench_models()

    # Fallback models if LiveBench fails
    fallback_models = {
        "coder": [
            {"name": "qwen/qwen-2.5-coder-32b-instruct", "score": 85.0, "price": 0.30, "speed": "🚀 Fast"},
            {"name": "anthropic/claude-sonnet-4", "score": 90.0, "price": 3.0, "speed": "⚖️ Balanced"},
            {"name": "google/gemini-2.0-flash-exp", "score": 82.0, "price": 0.075, "speed": "⚡ Very Fast"},
            {"name": "deepseek/deepseek-chat", "score": 80.0, "price": 0.14, "speed": "🚀 Fast"},
            {"name": "anthropic/claude-haiku-4.5-20250929", "score": 75.0, "price": 0.15, "speed": "⚡ Very Fast"},
            {"name": "openai/gpt-4o", "score": 88.0, "price": 3.0, "speed": "⚖️ Balanced"},
            {"name": "openai/gpt-4o-mini", "score": 70.0, "price": 0.15, "speed": "⚡ Very Fast"},
        ],
        "researcher": [
            {"name": "anthropic/claude-sonnet-4", "score": 92.0, "price": 3.0, "speed": "⚖️ Balanced"},
            {"name": "openai/gpt-4o", "score": 88.0, "price": 3.0, "speed": "⚖️ Balanced"},
            {"name": "google/gemini-2.0-flash-exp", "score": 82.0, "price": 0.075, "speed": "⚡ Very Fast"},
            {"name": "anthropic/claude-sonnet-3.5", "score": 85.0, "price": 3.0, "speed": "⚖️ Balanced"},
            {"name": "deepseek/deepseek-chat", "score": 78.0, "price": 0.14, "speed": "🚀 Fast"},
        ],
        "secretary": [
            {"name": "anthropic/claude-haiku-4.5-20250929", "score": 75.0, "price": 0.15, "speed": "⚡ Very Fast"},
            {"name": "google/gemini-2.0-flash-exp", "score": 82.0, "price": 0.075, "speed": "⚡ Very Fast"},
            {"name": "openai/gpt-4o-mini", "score": 70.0, "price": 0.15, "speed": "⚡ Very Fast"},
            {"name": "qwen/qwen-2.5-coder-32b-instruct", "score": 80.0, "price": 0.30, "speed": "🚀 Fast"},
            {"name": "deepseek/deepseek-chat", "score": 75.0, "price": 0.14, "speed": "🚀 Fast"},
        ],
    }

    if livebench_models:
        # Deduplicate models to remove variants (keep best of each base model)
        unique_models = deduplicate_models(livebench_models)

        # Use LiveBench data, enrich with pricing and speed
        recommendations = []
        for m in unique_models[:20]:  # Top 20 unique models
            normalized = normalize_model_name(m["name"])
            recommendations.append({
                "name": normalized,
                "score": m["score"],
                "price": get_model_pricing(m["name"]),
                "speed": get_model_speed(m["name"]),
            })
    else:
        recommendations = fallback_models.get(category, fallback_models["coder"])

    # Sort by different criteria based on category
    if category == "coder":
        # Balance quality and speed
        recommendations.sort(key=lambda x: x["score"] * 0.6 + (100 if "Fast" in x["speed"] else 50), reverse=True)
    elif category == "researcher":
        # Prioritize quality
        recommendations.sort(key=lambda x: x["score"], reverse=True)
    elif category == "secretary":
        # Prioritize speed and low cost
        recommendations.sort(key=lambda x: (100 if "Fast" in x["speed"] else 0) - x["price"], reverse=True)

    # Add display-friendly tier labels
    for i, model in enumerate(recommendations[:7]):  # Top 7
        if i == 0:
            model["tier"] = "🏆 Recommended"
        elif model["price"] < 0.2:
            model["tier"] = "💰 Budget"
        elif "Very Fast" in model["speed"]:
            model["tier"] = "⚡ Speed"
        elif model["score"] > 85:
            model["tier"] = "🎯 Quality"
        else:
            model["tier"] = "⚖️ Balanced"

    return recommendations[:7]  # Top 7 models


def main():
    """CLI interface for the installer."""
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: get_recommended_models.py <category>"}))
        sys.exit(1)

    category = sys.argv[1]

    if category not in ["coder", "researcher", "secretary"]:
        print(json.dumps({"error": f"Invalid category: {category}"}))
        sys.exit(1)

    try:
        recommendations = get_model_recommendations(category)
        print(json.dumps(recommendations, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
