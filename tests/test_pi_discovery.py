"""Tests for Pi model discovery."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from ninja_common.defaults import PI_MODELS
from ninja_common.pi_discovery import (
    clear_catalog_cache,
    discover_pi_model_triples,
    get_pi_catalog,
    parse_pi_list_models_output,
    read_pi_settings_current_model,
)


if TYPE_CHECKING:
    from pathlib import Path


SAMPLE_PI_LIST_MODELS = (
    "provider    model                context  max-out  thinking  images\n"
    "centralgui  deepseek-v4.1-flash  204.8K   16.4K    yes       no\n"
    "centralgui  glm-5.3-flash-nvfp4  1.0M     32.8K    yes       no\n"
    "openai      gpt-4o               128.0K   16.4K    no        yes\n"
)


def test_parse_pi_list_models_output():
    triples = parse_pi_list_models_output(SAMPLE_PI_LIST_MODELS)
    assert len(triples) == 3
    ids = [t[0] for t in triples]
    assert "deepseek-v4.1-flash" in ids
    assert "glm-5.3-flash-nvfp4" in ids
    assert "gpt-4o" in ids

    # Check display name and description
    ds_triple = next(t for t in triples if t[0] == "deepseek-v4.1-flash")
    assert ds_triple[1] == "Deepseek V4.1 Flash"
    assert "centralgui" in ds_triple[2]
    assert "thinking: yes" in ds_triple[2]


def test_parse_pi_list_models_empty():
    assert parse_pi_list_models_output("") == []
    assert parse_pi_list_models_output("No models found") == []


def test_read_pi_settings_current_model(tmp_path: Path):
    settings_dir = tmp_path / ".pi" / "agent"
    settings_dir.mkdir(parents=True)
    settings_file = settings_dir / "settings.json"
    settings_file.write_text(
        json.dumps({"defaultModel": "glm-5.3-flash-nvfp4", "defaultProvider": "centralgui"}),
        encoding="utf-8",
    )

    with patch.dict("os.environ", {"PI_CODING_AGENT_DIR": str(settings_dir)}):
        assert read_pi_settings_current_model() == "glm-5.3-flash-nvfp4"


def test_discover_pi_model_triples_fallback_static():
    with (
        patch("ninja_common.pi_discovery._which_pi", return_value=None),
        patch("ninja_common.pi_discovery.read_pi_settings_current_model", return_value=None),
    ):
        triples = discover_pi_model_triples()
        assert len(triples) >= len(PI_MODELS)
        ids = [t[0] for t in triples]
        for mid, _, _ in PI_MODELS:
            assert mid in ids


def test_discover_pi_model_triples_current_model_first():
    with (
        patch("ninja_common.pi_discovery._which_pi", return_value=None),
        patch(
            "ninja_common.pi_discovery.read_pi_settings_current_model",
            return_value="glm-5.3-flash-nvfp4",
        ),
    ):
        triples = discover_pi_model_triples()
        assert triples[0][0] == "glm-5.3-flash-nvfp4"


def test_get_pi_catalog_cached():
    clear_catalog_cache()
    with patch(
        "ninja_common.pi_discovery._run_pi_models_cli",
        return_value=[("model-a", "Model A", "desc")],
    ):
        cat1 = get_pi_catalog()
        assert "model-a" in cat1

        # Second call returns cached without invoking discovery again
        with patch("ninja_common.pi_discovery._run_pi_models_cli", return_value=[]):
            cat2 = get_pi_catalog()
            assert cat2 == cat1
    clear_catalog_cache()
