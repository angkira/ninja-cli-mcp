from __future__ import annotations

from types import SimpleNamespace

from ninja_config.modern_tui import NinjaConfigApp


def test_selected_api_key_uses_textual_highlighted_child_api() -> None:
    app = NinjaConfigApp()
    selected = SimpleNamespace(
        env_var="OPENAI_API_KEY",
        display_name="OpenAI",
    )
    list_view = SimpleNamespace(highlighted_child=selected)

    app.query_one = lambda *args, **kwargs: list_view  # type: ignore[method-assign]

    assert app._selected_api_key() == ("OPENAI_API_KEY", "OpenAI")
