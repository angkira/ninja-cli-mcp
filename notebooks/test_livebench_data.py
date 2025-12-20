"""
Tests for livebench_data.py - Debug why models aren't showing up
"""

import sys
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent))

from livebench_data import (
    fetch_livebench_scores,
    get_top_models_by_category,
    get_fastest_models,
    get_model_recommendations,
    get_model_pricing,
    fetch_model_throughput,
    get_available_models_on_openrouter,
)


def test_fetch_livebench_scores():
    """Test fetching LiveBench scores"""
    print("\n" + "=" * 80)
    print("TEST 1: Fetch LiveBench Scores")
    print("=" * 80)

    scores = fetch_livebench_scores()

    print(f"✓ Fetched {len(scores)} models")

    if scores:
        # Show first 5 models
        print("\nFirst 5 models:")
        for i, (model_name, model_scores) in enumerate(list(scores.items())[:5], 1):
            print(f"  {i}. {model_name}")
            print(f"     Scores: {model_scores}")
    else:
        print("✗ ERROR: No scores returned!")

    return scores


def test_get_available_models():
    """Test getting available models from OpenRouter"""
    print("\n" + "=" * 80)
    print("TEST 2: Get Available Models from OpenRouter")
    print("=" * 80)

    available = get_available_models_on_openrouter()

    print(f"✓ Found {len(available)} available models on OpenRouter")

    if available:
        # Show first 10 models
        print("\nFirst 10 available models:")
        for i, model in enumerate(available[:10], 1):
            print(f"  {i}. {model}")
    else:
        print("✗ WARNING: No models returned from OpenRouter!")

    return available


def test_get_top_models_by_category():
    """Test getting top models by category"""
    print("\n" + "=" * 80)
    print("TEST 3: Get Top Models by Category")
    print("=" * 80)

    # Test without filtering (should return models)
    print("\n3a. WITHOUT OpenRouter filtering:")
    top_coding_unfiltered = get_top_models_by_category("coding", top_n=10, filter_available=False)
    print(f"✓ Found {len(top_coding_unfiltered)} models")
    for i, (model, score) in enumerate(top_coding_unfiltered[:5], 1):
        print(f"  {i}. {model}: {score:.1f}%")

    # Test with filtering (might return empty if no matches)
    print("\n3b. WITH OpenRouter filtering:")
    top_coding_filtered = get_top_models_by_category("coding", top_n=10, filter_available=True)
    print(f"✓ Found {len(top_coding_filtered)} models")

    if top_coding_filtered:
        for i, (model, score) in enumerate(top_coding_filtered[:5], 1):
            print(f"  {i}. {model}: {score:.1f}%")
    else:
        print("✗ ERROR: No models after filtering! This is the problem!")
        print("\nDEBUG: Let's check if model names match...")

        # Get LiveBench scores and OpenRouter models
        scores = fetch_livebench_scores()
        available = get_available_models_on_openrouter()

        if scores and available:
            print(f"\nLiveBench models (first 5):")
            for model in list(scores.keys())[:5]:
                print(f"  - {model}")

            print(f"\nOpenRouter models (first 5):")
            for model in available[:5]:
                print(f"  - {model}")

            print("\n⚠️  The model names don't match between LiveBench and OpenRouter!")
            print("This is why filtering returns no results.")

    return top_coding_unfiltered, top_coding_filtered


def test_get_fastest_models():
    """Test getting fastest models"""
    print("\n" + "=" * 80)
    print("TEST 4: Get Fastest Models")
    print("=" * 80)

    fastest = get_fastest_models(top_n=10, min_coding_score=60.0)

    print(f"✓ Found {len(fastest)} fastest models (score ≥ 60%)")

    if fastest:
        for i, (model, speed, quality) in enumerate(fastest[:5], 1):
            print(f"  {i}. {model}: {speed:.0f} tok/s (quality: {quality:.1f}%)")
    else:
        print("✗ ERROR: No fastest models returned!")

    return fastest


def test_get_model_recommendations():
    """Test getting model recommendations"""
    print("\n" + "=" * 80)
    print("TEST 5: Get Model Recommendations")
    print("=" * 80)

    for budget in ["low", "medium", "high"]:
        rec = get_model_recommendations(budget, "quality")
        print(f"\n{budget.upper()} Budget:")
        if "error" in rec:
            print(f"  ✗ ERROR: {rec['error']}")
        else:
            print(f"  ✓ Model: {rec['model']}")
            print(f"    Quality: {rec['coding_score']:.1f}%")
            print(f"    Cost: ${rec['cost_per_token']:.2e}")


def test_model_name_matching():
    """Test if LiveBench model names match OpenRouter model names"""
    print("\n" + "=" * 80)
    print("TEST 6: Model Name Matching Analysis")
    print("=" * 80)

    scores = fetch_livebench_scores()
    available = get_available_models_on_openrouter()

    if not scores or not available:
        print("✗ Can't test - missing data")
        return

    print(f"\nLiveBench models: {len(scores)}")
    print(f"OpenRouter models: {len(available)}")

    # Try to find matches
    matches = []
    for lb_model in list(scores.keys())[:20]:  # Check first 20
        for or_model in available:
            if lb_model.lower() in or_model.lower() or or_model.lower() in lb_model.lower():
                matches.append((lb_model, or_model))
                break

    print(f"\n✓ Found {len(matches)} matches (out of first 20 LiveBench models)")

    if matches:
        print("\nMatching pairs:")
        for lb, or_model in matches[:5]:
            print(f"  LiveBench: {lb}")
            print(f"  OpenRouter: {or_model}")
            print()
    else:
        print("\n✗ NO MATCHES FOUND!")
        print("\nThis explains why filter_available=True returns empty results.")
        print("\nLiveBench uses format like: 'qwen/qwen-2.5-coder-32b-instruct'")
        print("OpenRouter might use different format.")


if __name__ == "__main__":
    print("🧪 TESTING LIVEBENCH_DATA.PY")
    print("=" * 80)

    # Run all tests
    test_fetch_livebench_scores()
    test_get_available_models()
    test_get_top_models_by_category()
    test_get_fastest_models()
    test_get_model_recommendations()
    test_model_name_matching()

    print("\n" + "=" * 80)
    print("✅ TESTS COMPLETE")
    print("=" * 80)
