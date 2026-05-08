"""
Tests for SecretsPanel and _mask() in ninja_config.modern_tui (Phase 1.4).

Strategy: unit-test widget logic directly with a fake in-memory SecretStore.
The existing test suite does not use Textual's async App.run_test() pilot,
so we follow the same pattern — pure unit tests with mocked dependencies.
Textual widget internals (compose, on_mount, etc.) are tested indirectly
through the public helper methods that execute synchronously.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ninja_config.modern_tui import SecretsPanel, _mask
from ninja_config.secrets_store import SecretStoreUnavailable


# ---------------------------------------------------------------------------
# Fake store — satisfies the SecretStore protocol in memory.
# ---------------------------------------------------------------------------


class FakeStore:
    """Minimal in-memory SecretStore for testing SecretsPanel."""

    def __init__(self, data: dict[str, str] | None = None, *, available: bool = True) -> None:
        self._data: dict[str, str] = data or {}
        self.available = available
        self._name = "fake-test-store"

    def get(self, name: str) -> str | None:
        return self._data.get(name)

    def set(self, name: str, value: str) -> None:
        if not self.available:
            raise SecretStoreUnavailable("fake store unavailable")
        self._data[name] = value

    def delete(self, name: str) -> None:
        self._data.pop(name, None)

    def list_names(self) -> list[str]:
        return sorted(self._data.keys())

    def backend_name(self) -> str:
        return self._name


# ---------------------------------------------------------------------------
# _mask() helper
# ---------------------------------------------------------------------------


class TestMask:
    def test_long_value_shows_last_four(self) -> None:
        assert _mask("sk-abc1234") == "••••1234"

    def test_exactly_five_chars_shows_last_four(self) -> None:
        assert _mask("abcde") == "••••bcde"

    def test_exactly_four_chars_returns_dots_only(self) -> None:
        # len == 4 is NOT > 4, so no preview
        assert _mask("abcd") == "••••"

    def test_three_chars_returns_dots_only(self) -> None:
        assert _mask("abc") == "••••"

    def test_empty_string_returns_dots(self) -> None:
        assert _mask("") == "••••"

    def test_one_char_returns_dots(self) -> None:
        assert _mask("x") == "••••"

    def test_masked_value_does_not_contain_most_of_original(self) -> None:
        value = "sk-or-v1-supersecretkey"
        result = _mask(value)
        # Only last 4 chars visible; the bulk of the secret is hidden.
        assert result == "••••tkey"
        assert "supersecret" not in result


# ---------------------------------------------------------------------------
# SecretsPanel — logic tests (not requiring Textual's async runtime)
# ---------------------------------------------------------------------------


class TestSecretsPanelInit:
    def test_accepts_custom_store(self) -> None:
        store = FakeStore()
        panel = SecretsPanel(store=store)
        assert panel._store is store

    def test_uses_default_store_when_none_given(self) -> None:
        fake = FakeStore()
        with patch("ninja_config.modern_tui.default_store", return_value=fake):
            panel = SecretsPanel()
        assert panel._store is fake

    def test_pending_set_initially_none(self) -> None:
        panel = SecretsPanel(store=FakeStore())
        assert panel._pending_set is None


def _pending(widget) -> list:
    """Return the pending (pre-mount) children of a Textual widget."""
    return list(getattr(widget, "_pending_children", []))


class TestSecretsPanelMakeSecretRow:
    """_make_secret_row is a synchronous factory — testable without a running TUI."""

    def test_row_for_set_secret_shows_check_mark(self) -> None:
        store = FakeStore({"OPENROUTER_API_KEY": "sk-or-abc1234"})
        panel = SecretsPanel(store=store)
        row = panel._make_secret_row("OPENROUTER_API_KEY")
        # compose_add_child adds to _pending_children before mount.
        children = _pending(row)
        # First child is the label — use .content (Static/Label API).
        label_widget = children[0]
        markup = str(label_widget.content)
        assert "✓" in markup
        assert "OPENROUTER_API_KEY" in markup
        # Masked preview should appear.
        assert "1234" in markup
        # Raw secret must NOT appear.
        assert "sk-or-abc1234" not in markup

    def test_row_for_unset_secret_shows_dot(self) -> None:
        store = FakeStore({})  # nothing stored
        panel = SecretsPanel(store=store)
        row = panel._make_secret_row("OPENROUTER_API_KEY")
        children = _pending(row)
        label_widget = children[0]
        markup = str(label_widget.content)
        assert "·" in markup
        assert "OPENROUTER_API_KEY" in markup

    def test_row_for_set_secret_has_delete_button(self) -> None:
        store = FakeStore({"OPENAI_API_KEY": "sk-test-xyz"})
        panel = SecretsPanel(store=store)
        row = panel._make_secret_row("OPENAI_API_KEY")
        btn_ids = [child.id for child in _pending(row) if hasattr(child, "id")]
        assert "del-OPENAI_API_KEY" in btn_ids

    def test_row_for_unset_secret_has_no_delete_button(self) -> None:
        store = FakeStore({})
        panel = SecretsPanel(store=store)
        row = panel._make_secret_row("OPENAI_API_KEY")
        btn_ids = [child.id for child in _pending(row) if hasattr(child, "id")]
        assert "del-OPENAI_API_KEY" not in btn_ids

    def test_row_for_set_secret_has_update_button_label(self) -> None:
        store = FakeStore({"GROQ_API_KEY": "gsk-abcdefgh"})
        panel = SecretsPanel(store=store)
        row = panel._make_secret_row("GROQ_API_KEY")
        labels = [str(child.label) for child in _pending(row) if hasattr(child, "label")]
        assert any("Update" in lbl for lbl in labels)

    def test_row_for_unset_secret_has_set_button_label(self) -> None:
        store = FakeStore({})
        panel = SecretsPanel(store=store)
        row = panel._make_secret_row("GROQ_API_KEY")
        labels = [str(child.label) for child in _pending(row) if hasattr(child, "label")]
        assert any("Set" in lbl for lbl in labels)

    def test_store_error_on_get_renders_unset(self) -> None:
        """When store.get raises, the row renders as unset — no crash."""
        store = FakeStore()
        store.get = MagicMock(side_effect=RuntimeError("backend glitch"))
        panel = SecretsPanel(store=store)
        # Should not raise.
        row = panel._make_secret_row("OPENAI_API_KEY")
        children = _pending(row)
        markup = str(children[0].content)
        assert "·" in markup


# ---------------------------------------------------------------------------
# SecretsPanel — _do_save() logic (requires a partially-initialised panel)
# ---------------------------------------------------------------------------


class _TestableSecretsPanel(SecretsPanel):
    """SecretsPanel subclass that overrides the `app` property for unit tests.

    Textual's `app` property traverses the widget tree — not available outside
    a running App.  We provide a MagicMock so business-logic tests can verify
    notify() calls without spinning up the full Textual event loop.
    """

    def __init__(self, store: FakeStore) -> None:
        super().__init__(store=store)
        self._mock_app = MagicMock()

    @property  # type: ignore[override]
    def app(self):  # type: ignore[override]
        return self._mock_app


def _make_panel_with_mounted_widgets(store: FakeStore) -> _TestableSecretsPanel:
    """Return a SecretsPanel whose key internal widgets are mocked for tests.

    We don't spin up the full Textual App — instead we mock out the query_one
    calls that _do_save / _do_delete rely on so we can exercise the business
    logic without a display loop.
    """
    panel = _TestableSecretsPanel(store=store)
    panel._is_mounted = True  # is_mounted is a read-only property backed by _is_mounted

    # Build a simple fake Input widget so _do_save can read .value.
    fake_input = MagicMock()
    fake_input.id = "secrets-value-input"
    fake_input.value = ""

    fake_label = MagicMock()
    fake_label.id = "secrets-input-label"
    fake_label.display = True

    fake_btn = MagicMock()
    fake_btn.id = "secrets-save-btn"
    fake_btn.display = True

    fake_banner = MagicMock()
    fake_banner.id = "secrets-error-banner"
    fake_banner.renderable = ""
    fake_banner.display = False

    def _query_one(selector, widget_type=None):
        mapping = {
            "#secrets-value-input": fake_input,
            "#secrets-input-label": fake_label,
            "#secrets-save-btn": fake_btn,
            "#secrets-error-banner": fake_banner,
        }
        for key, val in mapping.items():
            if key in selector:
                return val
        raise Exception(f"No mock for selector: {selector}")

    panel.query_one = _query_one
    panel._fake_input = fake_input
    panel._fake_banner = fake_banner
    return panel  # type: ignore[return-value]


class TestDoSave:
    def test_saves_value_to_store(self) -> None:
        store = FakeStore()
        panel = _make_panel_with_mounted_widgets(store)
        panel._pending_set = "OPENROUTER_API_KEY"
        panel._fake_input.value = "sk-or-new-value"

        panel._do_save()

        assert store.get("OPENROUTER_API_KEY") == "sk-or-new-value"

    def test_notifies_success(self) -> None:
        store = FakeStore()
        panel = _make_panel_with_mounted_widgets(store)
        panel._pending_set = "OPENAI_API_KEY"
        panel._fake_input.value = "sk-openai-test"

        panel._do_save()

        panel._mock_app.notify.assert_called_once()
        call_args = panel._mock_app.notify.call_args[0][0]
        assert "OPENAI_API_KEY" in call_args

    def test_clears_pending_set_after_save(self) -> None:
        store = FakeStore()
        panel = _make_panel_with_mounted_widgets(store)
        panel._pending_set = "ANTHROPIC_API_KEY"
        panel._fake_input.value = "sk-ant-val"

        panel._do_save()

        assert panel._pending_set is None

    def test_empty_value_shows_error_no_store_call(self) -> None:
        store = FakeStore()
        panel = _make_panel_with_mounted_widgets(store)
        panel._pending_set = "OPENROUTER_API_KEY"
        panel._fake_input.value = "   "  # blank

        panel._do_save()

        assert store.get("OPENROUTER_API_KEY") is None  # store untouched
        panel._mock_app.notify.assert_not_called()

    def test_no_pending_set_is_no_op(self) -> None:
        store = FakeStore()
        panel = _make_panel_with_mounted_widgets(store)
        panel._pending_set = None
        panel._fake_input.value = "some-value"

        panel._do_save()  # must not raise

        assert len(store._data) == 0

    def test_store_unavailable_shows_error_no_crash(self) -> None:
        store = FakeStore(available=False)
        panel = _make_panel_with_mounted_widgets(store)
        panel._pending_set = "OPENROUTER_API_KEY"
        panel._fake_input.value = "sk-or-test"

        panel._do_save()

        # app.notify NOT called (it's an error, not a success)
        panel._mock_app.notify.assert_not_called()
        # Error banner should have been shown.
        assert panel._fake_banner.display is True

    def test_unexpected_store_error_shows_error_no_crash(self) -> None:
        store = FakeStore()
        store.set = MagicMock(side_effect=RuntimeError("disk full"))
        panel = _make_panel_with_mounted_widgets(store)
        panel._pending_set = "GROQ_API_KEY"
        panel._fake_input.value = "gsk-value"

        panel._do_save()

        panel._mock_app.notify.assert_not_called()


# ---------------------------------------------------------------------------
# SecretsPanel — _do_delete() logic
# ---------------------------------------------------------------------------


class TestDoDelete:
    def test_first_press_arms_confirm_prompt(self) -> None:
        store = FakeStore({"OPENAI_API_KEY": "sk-123"})
        panel = _make_panel_with_mounted_widgets(store)
        # Simulate first delete button press.
        panel._do_delete("OPENAI_API_KEY")
        # Secret must still be present — not deleted yet.
        assert store.get("OPENAI_API_KEY") == "sk-123"

    def test_second_press_executes_delete(self) -> None:
        store = FakeStore({"ANTHROPIC_API_KEY": "sk-ant-xyz"})
        panel = _make_panel_with_mounted_widgets(store)
        # Arm the confirm prompt (first press).
        panel._fake_banner.renderable = "CONFIRM_DELETE:ANTHROPIC_API_KEY — press again"
        # Second press executes.
        panel._do_delete("ANTHROPIC_API_KEY")
        assert store.get("ANTHROPIC_API_KEY") is None

    def test_delete_notifies_success(self) -> None:
        store = FakeStore({"GROQ_API_KEY": "gsk-test"})
        panel = _make_panel_with_mounted_widgets(store)
        panel._fake_banner.renderable = "CONFIRM_DELETE:GROQ_API_KEY armed"
        panel._do_delete("GROQ_API_KEY")
        panel._mock_app.notify.assert_called_once()
        call_args = panel._mock_app.notify.call_args[0][0]
        assert "GROQ_API_KEY" in call_args

    def test_delete_store_error_shows_error_no_crash(self) -> None:
        store = FakeStore({"MISTRAL_API_KEY": "msk-val"})
        store.delete = MagicMock(side_effect=RuntimeError("backend error"))
        panel = _make_panel_with_mounted_widgets(store)
        panel._fake_banner.renderable = "CONFIRM_DELETE:MISTRAL_API_KEY armed"
        panel._do_delete("MISTRAL_API_KEY")
        # Should not crash; no success notification.
        panel._mock_app.notify.assert_not_called()
