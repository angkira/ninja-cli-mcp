"""
Unit tests for default configuration values.

Tests that all default model configurations are set correctly.
"""

from __future__ import annotations

from ninja_common.defaults import (
    ANTHROPIC_MODELS,
    CLAUDE_CODE_MODELS,
    DEFAULT_CODER_MODEL,
    DEFAULT_MODEL_PARALLEL,
    DEFAULT_MODEL_QUICK,
    DEFAULT_MODEL_SEQUENTIAL,
    OPENROUTER_MODELS,
)


class TestDefaults:
    """Tests for default configuration values."""

    def test_default_coder_model_is_haiku(self):
        """Test that DEFAULT_CODER_MODEL is set to Haiku."""
        assert DEFAULT_CODER_MODEL == "anthropic/claude-haiku-4.5"

    def test_default_model_quick_is_haiku(self):
        """Test that DEFAULT_MODEL_QUICK is set to Haiku."""
        assert DEFAULT_MODEL_QUICK == "anthropic/claude-haiku-4.5"

    def test_default_model_sequential_is_haiku(self):
        """Test that DEFAULT_MODEL_SEQUENTIAL is set to Haiku."""
        assert DEFAULT_MODEL_SEQUENTIAL == "anthropic/claude-haiku-4.5"

    def test_default_model_parallel_is_haiku(self):
        """Test that DEFAULT_MODEL_PARALLEL is set to Haiku."""
        assert DEFAULT_MODEL_PARALLEL == "anthropic/claude-haiku-4.5"

    def test_claude_code_models_first_is_haiku(self):
        """Test that the first CLAUDE_CODE_MODELS entry is Haiku."""
        assert len(CLAUDE_CODE_MODELS) > 0
        first_model_id, first_model_name, first_model_desc = CLAUDE_CODE_MODELS[0]
        assert first_model_id == "claude-haiku-4"
        assert "Haiku" in first_model_name

    def test_anthropic_models_first_is_haiku(self):
        """Test that the first ANTHROPIC_MODELS entry is Haiku."""
        assert len(ANTHROPIC_MODELS) > 0
        first_model_id, first_model_name, first_model_desc = ANTHROPIC_MODELS[0]
        assert first_model_id == "anthropic/claude-haiku-4.5"
        assert "Haiku" in first_model_name

    def test_openrouter_models_first_is_haiku(self):
        """Test that the first OPENROUTER_MODELS entry (after comment) is Haiku."""
        assert len(OPENROUTER_MODELS) > 0
        # Find the first Claude model
        first_claude_model = None
        for model_id, model_name, model_desc in OPENROUTER_MODELS:
            if model_id.startswith("anthropic/claude"):
                first_claude_model = (model_id, model_name, model_desc)
                break

        assert first_claude_model is not None
        model_id, model_name, model_desc = first_claude_model
        assert model_id == "anthropic/claude-haiku-4.5"
        assert "Haiku" in model_name

    def test_all_haiku_models_present(self):
        """Test that Haiku models are present in all model lists."""
        # Check CLAUDE_CODE_MODELS
        claude_haiku_ids = [m[0] for m in CLAUDE_CODE_MODELS if "haiku" in m[0].lower()]
        assert len(claude_haiku_ids) > 0
        assert "claude-haiku-4" in claude_haiku_ids

        # Check ANTHROPIC_MODELS
        anthropic_haiku_ids = [m[0] for m in ANTHROPIC_MODELS if "haiku" in m[0].lower()]
        assert len(anthropic_haiku_ids) > 0
        assert "anthropic/claude-haiku-4.5" in anthropic_haiku_ids

        # Check OPENROUTER_MODELS
        openrouter_haiku_ids = [m[0] for m in OPENROUTER_MODELS if "haiku" in m[0].lower()]
        assert len(openrouter_haiku_ids) > 0
        assert "anthropic/claude-haiku-4.5" in openrouter_haiku_ids

    def test_model_list_structure(self):
        """Test that model lists have the correct structure."""
        # All model lists should be lists of tuples with 3 elements
        for model_tuple in CLAUDE_CODE_MODELS:
            assert isinstance(model_tuple, tuple)
            assert len(model_tuple) == 3
            assert isinstance(model_tuple[0], str)  # model ID
            assert isinstance(model_tuple[1], str)  # model name
            assert isinstance(model_tuple[2], str)  # model description

        for model_tuple in ANTHROPIC_MODELS:
            assert isinstance(model_tuple, tuple)
            assert len(model_tuple) == 3
            assert isinstance(model_tuple[0], str)
            assert isinstance(model_tuple[1], str)
            assert isinstance(model_tuple[2], str)

        # Check first 10 entries of OPENROUTER_MODELS (it's very long)
        for model_tuple in OPENROUTER_MODELS[:10]:
            assert isinstance(model_tuple, tuple)
            assert len(model_tuple) == 3
            assert isinstance(model_tuple[0], str)
            assert isinstance(model_tuple[1], str)
            assert isinstance(model_tuple[2], str)

    def test_haiku_model_order_consistency(self):
        """Test that Haiku is consistently the first model in Claude model lists."""
        # In CLAUDE_CODE_MODELS
        assert CLAUDE_CODE_MODELS[0][0] == "claude-haiku-4"

        # In ANTHROPIC_MODELS
        assert ANTHROPIC_MODELS[0][0] == "anthropic/claude-haiku-4.5"

        # In OPENROUTER_MODELS (first Claude model)
        first_claude_idx = None
        for idx, (model_id, _, _) in enumerate(OPENROUTER_MODELS):
            if model_id.startswith("anthropic/claude"):
                first_claude_idx = idx
                break

        assert first_claude_idx is not None
        assert OPENROUTER_MODELS[first_claude_idx][0] == "anthropic/claude-haiku-4.5"
