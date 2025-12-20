"""
Model selection system based on REAL data from LiveBench.
Fetches CSV with current coding benchmarks, creates 4 rankings.

📌 HOW TO UPDATE DATA:
1. Open https://livebench.ai/
2. In JavaScript console check which CSV is being loaded:
   - Open DevTools (F12) -> Network -> filter "csv"
   - Find URL like "table_2025_11_25.csv"
3. Update the LIVEBENCH_DATE variable below to the found date
4. Restart the notebook

Example: if you see "table_2025_12_15.csv", then LIVEBENCH_DATE = "2025_12_15"
"""

import csv
import io
import json
import time
import urllib.request
from typing import Dict, List


# Cache
_CACHE = None
_CACHE_TIME = 0
_CACHE_DURATION = 3600

# 📅 Date of the latest CSV from LiveBench - UPDATE HERE!
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
        "-instruct",
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
    import re

    base = re.sub(r"-\d{8}", "", base)  # -20251101
    base = re.sub(r"-\d{4}-\d{2}-\d{2}", "", base)  # -2025-11-01
    base = re.sub(r"-\d{4}_\d{2}_\d{2}", "", base)  # -2025_11_01

    return base.strip("-")


def deduplicate_models(models: List[Dict], strategy: str = "best") -> List[Dict]:
    """
    Removes duplicate models, keeping only unique base names.

    Args:
        models: List of models with coding_score
        strategy: 'best' (best score) or 'average' (average score)

    Returns:
        List of unique models
    """
    from collections import defaultdict

    grouped = defaultdict(list)

    # Group by base name
    for model in models:
        base_name = _extract_base_model_name(model["model"])
        grouped[base_name].append(model)

    unique_models = []

    for base_name, variants in grouped.items():
        if strategy == "best":
            # Take variant with best score
            best = max(variants, key=lambda x: x["coding_score"])
            unique_models.append({**best, "base_name": base_name, "variants_count": len(variants)})
        elif strategy == "average":
            # Average scores of all variants
            avg_score = sum(v["coding_score"] for v in variants) / len(variants)
            # Take first variant as representative, but with averaged score
            representative = variants[0].copy()
            representative["coding_score"] = avg_score
            representative["base_name"] = base_name
            representative["variants_count"] = len(variants)
            unique_models.append(representative)

    # Sort by coding_score
    unique_models.sort(key=lambda x: x["coding_score"], reverse=True)

    return unique_models


def fetch_top_models(
    top_n: int = 100, unique: bool = False, dedup_strategy: str = "best"
) -> List[Dict]:
    """
    Fetches top-N models from LiveBench.
    Takes REAL data from CSV with coding benchmarks.

    Args:
        top_n: Number of models in top
        unique: If True, removes duplicates (variations of one model)
        dedup_strategy: 'best' (best score) or 'average' (average score)

    Returns:
        List of models with coding_score
    """
    global _CACHE, _CACHE_TIME

    # Check cache
    if _CACHE and (time.time() - _CACHE_TIME) < _CACHE_DURATION:
        print(f"✅ Using cache ({len(_CACHE)} models)")
        cached = _CACHE[:] if not unique else deduplicate_models(_CACHE, dedup_strategy)
        return cached[:top_n]

    print(f"🔄 Loading data from LiveBench (real benchmark, date: {LIVEBENCH_DATE})...")

    try:
        # LiveBench CSV with REAL coding benchmarks
        url = f"https://livebench.ai/table_{LIVEBENCH_DATE}.csv"

        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0")

        print(f"  📊 Downloading CSV from LiveBench...")

        with urllib.request.urlopen(req, timeout=15) as response:
            csv_data = response.read().decode("utf-8")

        print(f"  ✅ CSV downloaded")

        # Parse CSV
        reader = csv.DictReader(io.StringIO(csv_data))
        models = []

        for row in reader:
            model = row["model"]

            # Take coding-specific columns
            code_gen = float(row.get("code_generation", 0) or 0)
            code_comp = float(row.get("code_completion", 0) or 0)
            python_score = float(row.get("python", 0) or 0)
            js_score = float(row.get("javascript", 0) or 0)
            ts_score = float(row.get("typescript", 0) or 0)

            # Calculate average coding score
            coding_scores = [
                s for s in [code_gen, code_comp, python_score, js_score, ts_score] if s > 0
            ]

            if coding_scores:
                avg_coding = sum(coding_scores) / len(coding_scores)
                models.append(
                    {
                        "model": model,
                        "coding_score": avg_coding,
                        "base_name": _extract_base_model_name(model),
                        "code_generation": code_gen,
                        "code_completion": code_comp,
                        "python": python_score,
                    }
                )

        # Sort by coding_score
        models.sort(key=lambda x: x["coding_score"], reverse=True)

        print(f"✅ Loaded {len(models)} models from LiveBench")

        # Remove duplicates if needed
        if unique:
            before_count = len(models)
            models = deduplicate_models(models, dedup_strategy)
            print(f"🔄 After deduplication: {len(models)} unique models (was {before_count})")

        # Top-3 for debug
        if len(models) >= 3:
            print(
                f"📊 Top-3: {models[0]['model'][:40]} ({models[0]['coding_score']:.1f}%), "
                f"{models[1]['model'][:40]} ({models[1]['coding_score']:.1f}%), "
                f"{models[2]['model'][:40]} ({models[2]['coding_score']:.1f}%)"
            )

        _CACHE = models
        _CACHE_TIME = time.time()

        return models[:top_n]

    except Exception as e:
        print(f"⚠️ Error loading from LiveBench: {e}")
        print(f"💡 Try updating LIVEBENCH_DATE in code or check https://livebench.ai/")

        # Return empty list - DO NOT use fallback
        return []


def get_model_pricing(model_name: str) -> float:
    """Get model price (average per token) - using heuristics."""
    name_lower = model_name.lower()

    # Heuristics based on model size and type
    if "claude-sonnet-4" in name_lower or "gpt-4o" in name_lower:
        return 0.000005  # $5 per 1M tokens
    elif "claude-sonnet-3.5" in name_lower or "grok" in name_lower:
        return 0.000003  # $3 per 1M tokens
    elif (
        "gemini-flash" in name_lower or "haiku" in name_lower or "qwen-2.5-coder-14b" in name_lower
    ):
        return 0.0000005  # $0.5 per 1M tokens
    elif "gpt-4o-mini" in name_lower or "phi" in name_lower:
        return 0.0000003  # $0.3 per 1M tokens
    elif "deepseek" in name_lower or "llama" in name_lower:
        return 0.0000002  # $0.2 per 1M tokens
    elif "qwen-2.5-coder-32b" in name_lower:
        return 0.0000015  # $1.5 per 1M tokens
    else:
        return 0.000001  # $1 per 1M tokens (default)


def estimate_model_speed(model_name: str) -> float:
    """Estimate model speed (tokens/sec) heuristically."""
    name_lower = model_name.lower()

    if "flash" in name_lower:
        return 200.0
    elif "turbo" in name_lower or "haiku" in name_lower:
        return 150.0
    elif "7b" in name_lower or "8b" in name_lower or "phi" in name_lower:
        return 120.0
    elif "70b" in name_lower or "32b" in name_lower:
        return 80.0
    elif "340b" in name_lower:
        return 50.0
    else:
        return 100.0


def enrich_models_with_metrics(models: List[Dict]) -> List[Dict]:
    """Enrich models with price and speed."""
    print(f"💰 Adding prices and speeds...")

    for model in models:
        model["price"] = get_model_pricing(model["model"])
        model["speed"] = estimate_model_speed(model["model"])

    return models


def get_top_by_quality(models: List[Dict], top_n: int = 3) -> List[Dict]:
    """Top-N smartest models."""
    sorted_models = sorted(models, key=lambda x: x["coding_score"], reverse=True)
    return sorted_models[:top_n]


def get_top_by_speed(models: List[Dict], top_n: int = 3) -> List[Dict]:
    """Top-N fastest models."""
    sorted_models = sorted(models, key=lambda x: x["speed"], reverse=True)
    return sorted_models[:top_n]


def get_top_by_price(models: List[Dict], top_n: int = 3) -> List[Dict]:
    """Top-N cheapest models."""
    sorted_models = sorted(models, key=lambda x: x["price"])
    return sorted_models[:top_n]


def get_top_overall(models: List[Dict], top_n: int = 3) -> List[Dict]:
    """Top-N best overall: balance of quality, price, and speed."""
    # Normalize metrics to 0-1
    max_score = max(m["coding_score"] for m in models)
    min_price = min(m["price"] for m in models)
    max_price = max(m["price"] for m in models)
    max_speed = max(m["speed"] for m in models)

    for m in models:
        # Higher is better
        quality_norm = m["coding_score"] / max_score
        speed_norm = m["speed"] / max_speed
        # Price is opposite - lower is better
        price_norm = 1 - ((m["price"] - min_price) / (max_price - min_price + 0.000001))

        # Overall score = weighted average
        m["overall_score"] = (quality_norm * 0.4) + (price_norm * 0.3) + (speed_norm * 0.3)

    sorted_models = sorted(models, key=lambda x: x["overall_score"], reverse=True)
    return sorted_models[:top_n]


if __name__ == "__main__":
    print("=" * 80)
    print("SIMPLIFIED MODEL SELECTION SYSTEM")
    print("=" * 80)

    # Load top-20
    models = fetch_top_models(top_n=20)
    models = enrich_models_with_metrics(models)

    print(f"\n📊 Loaded {len(models)} unique models\n")

    # 4 rankings
    print("🏆 TOP-3 SMARTEST:")
    for i, m in enumerate(get_top_by_quality(models, 3), 1):
        print(f"  {i}. {m['model'][:45]:45s} | score: {m['coding_score']:.1f}")

    print("\n💰 TOP-3 CHEAPEST:")
    for i, m in enumerate(get_top_by_price(models, 3), 1):
        print(f"  {i}. {m['model'][:45]:45s} | price: ${m['price']:.2e}")

    print("\n⚡ TOP-3 FASTEST:")
    for i, m in enumerate(get_top_by_speed(models, 3), 1):
        print(f"  {i}. {m['model'][:45]:45s} | speed: {m['speed']:.0f} tok/s")

    print("\n🎯 TOP-3 BEST OVERALL:")
    for i, m in enumerate(get_top_overall(models, 3), 1):
        print(f"  {i}. {m['model'][:45]:45s} | overall: {m['overall_score']:.3f}")
