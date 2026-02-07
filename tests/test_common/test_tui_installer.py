"""
Unit tests for TUI Installer model preset defaults.

Tests that the correct default models are configured for different modules.
"""

from __future__ import annotations

from ninja_config.tui_installer import TUIInstaller


class TestTUIInstallerModelPresets:
    """Tests for TUI installer model preset configuration."""

    def test_coder_quality_tier_uses_haiku(self):
        """Test that coder Quality tier preset uses claude-haiku-4.5."""
        installer = TUIInstaller()

        # Get coder recommendations
        coder_models = installer.fetch_model_recommendations("coder")

        # Find the Quality tier model
        quality_model = None
        for model in coder_models:
            if model.get("tier") == "🎯 Quality":
                quality_model = model
                break

        # Verify Quality tier exists and uses claude-haiku-4.5
        assert quality_model is not None, "Quality tier not found in coder presets"
        assert quality_model["name"] == "anthropic/claude-haiku-4.5", (
            f"Expected 'anthropic/claude-haiku-4.5' for coder Quality tier, "
            f"got '{quality_model['name']}'"
        )

    def test_researcher_recommended_tier_uses_haiku(self):
        """Test that researcher Recommended tier preset uses claude-haiku-4.5."""
        installer = TUIInstaller()

        # Get researcher recommendations
        researcher_models = installer.fetch_model_recommendations("researcher")

        # Find the Recommended tier model
        recommended_model = None
        for model in researcher_models:
            if model.get("tier") == "🏆 Recommended":
                recommended_model = model
                break

        # Verify Recommended tier exists and uses claude-haiku-4.5
        assert recommended_model is not None, "Recommended tier not found in researcher presets"
        assert recommended_model["name"] == "anthropic/claude-haiku-4.5", (
            f"Expected 'anthropic/claude-haiku-4.5' for researcher Recommended tier, "
            f"got '{recommended_model['name']}'"
        )

    def test_coder_presets_structure(self):
        """Test that coder presets have the correct structure."""
        installer = TUIInstaller()

        # Get coder recommendations
        coder_models = installer.fetch_model_recommendations("coder")

        # Verify we have models
        assert len(coder_models) > 0, "No coder models found"

        # Verify each model has required fields
        for model in coder_models:
            assert "name" in model, "Model missing 'name' field"
            assert "tier" in model, "Model missing 'tier' field"
            assert "price" in model, "Model missing 'price' field"
            assert "speed" in model, "Model missing 'speed' field"

    def test_researcher_presets_structure(self):
        """Test that researcher presets have the correct structure."""
        installer = TUIInstaller()

        # Get researcher recommendations
        researcher_models = installer.fetch_model_recommendations("researcher")

        # Verify we have models
        assert len(researcher_models) > 0, "No researcher models found"

        # Verify each model has required fields
        for model in researcher_models:
            assert "name" in model, "Model missing 'name' field"
            assert "tier" in model, "Model missing 'tier' field"
            assert "price" in model, "Model missing 'price' field"
            assert "speed" in model, "Model missing 'speed' field"

    def test_secretary_presets_unchanged(self):
        """Test that secretary presets remain unchanged (no sonnet-4-5)."""
        installer = TUIInstaller()

        # Get secretary recommendations
        secretary_models = installer.fetch_model_recommendations("secretary")

        # Verify none of the secretary models use sonnet-4-5
        for model in secretary_models:
            assert model["name"] != "anthropic/claude-sonnet-4-5", (
                "Secretary presets should not have been changed to use sonnet-4-5"
            )

    def test_other_coder_tiers_unchanged(self):
        """Test that other coder tier presets (besides Quality) are unchanged."""
        installer = TUIInstaller()

        # Get coder recommendations
        coder_models = installer.fetch_model_recommendations("coder")

        # Check that Recommended tier still uses the versioned haiku
        recommended_model = None
        for model in coder_models:
            if model.get("tier") == "🏆 Recommended":
                recommended_model = model
                break

        if recommended_model:
            assert recommended_model["name"] == "anthropic/claude-haiku-4.5-20250929", (
                f"Expected Recommended tier to use versioned model, "
                f"got '{recommended_model['name']}'"
            )

    def test_other_researcher_tiers_unchanged(self):
        """Test that other researcher tier presets (besides Recommended) are unchanged."""
        installer = TUIInstaller()

        # Get researcher recommendations
        researcher_models = installer.fetch_model_recommendations("researcher")

        # Check that Quality tier uses gpt-4o (not changed)
        quality_model = None
        for model in researcher_models:
            if model.get("tier") == "🎯 Quality":
                quality_model = model
                break

        if quality_model:
            assert quality_model["name"] == "openai/gpt-4o", (
                f"Expected Quality tier to remain as gpt-4o, got '{quality_model['name']}'"
            )

    def test_model_name_format(self):
        """Test that model names follow the correct format."""
        installer = TUIInstaller()

        # Test all categories
        for category in ["coder", "researcher", "secretary"]:
            models = installer.fetch_model_recommendations(category)

            for model in models:
                name = model["name"]
                # Model names should contain a provider and model name
                assert "/" in name, f"Model name '{name}' missing provider separator"
                parts = name.split("/")
                assert len(parts) == 2, f"Model name '{name}' has invalid format"
                assert len(parts[0]) > 0, f"Model provider empty in '{name}'"
                assert len(parts[1]) > 0, f"Model name empty in '{name}'"
