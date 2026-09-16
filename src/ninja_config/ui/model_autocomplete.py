"""Per-role provider + model autocomplete widget for the modern TUI.

Replaces the old pattern of synchronously preloading five ``ListView`` card
lists in ``on_mount`` (one ``opencode models`` subprocess per role ≈ 14s of
empty screen). Instead each role gets a :class:`ModelRolePicker`:

- a :class:`~textual.widgets.Select` for the provider (static fallback options
  at compose time, real discovery applied lazily by a background worker),
- an :class:`~textual.widgets.Input` with debounced (~280ms) autocomplete that
  filters the process-cached model list in a ``@work(thread=True)`` worker,
- a :class:`~textual.widgets.ListView` dropdown for matches with a
  ``LoadingIndicator`` / ``"Searching…"`` placeholder while the worker runs and
  ``"No models found"`` on empty results,
- ``Enter`` on raw text saves it as a custom model id via ``ConfigManager``.

Heavy work only starts when the Models tab is opened
(:meth:`ModelRolePicker.load_providers`), so the first frame stays <0.5s.

Fully keyboard driven: ``Down`` in the input jumps to the suggestions,
``Up``/``Down`` + ``Enter`` pick, ``Esc`` clears the dropdown and returns
focus to the input. ``Tab``/``Shift+Tab`` focus cycling is native Textual.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual import events, on, work
from textual.containers import Vertical
from textual.widgets import (
    Input,
    ListItem,
    ListView,
    LoadingIndicator,
    Select,
    Static,
)

from ninja_common.defaults import OPERATOR_STATIC_MODELS, PERPLEXITY_MODELS, PROVIDER_MODELS
from ninja_config.model_selector import (
    PROVIDER_DISPLAY_NAMES,
    Model,
    native_provider_for_operator,
    normalize_operator,
    operator_providers,
)
from ninja_config.ui.model_cache import (
    cached_discover_providers,
    cached_get_junie_models,
    cached_get_provider_models,
    filter_models,
)


if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.timer import Timer

    from ninja_common.config_manager import ConfigManager

#: Minimum typed characters before a provider query is issued.
MIN_QUERY_LEN: int = 2
#: Debounce delay between keystroke and worker dispatch (seconds).
DEBOUNCE_DELAY: float = 0.28
#: Max suggestions shown in the dropdown.
MAX_SUGGESTIONS: int = 30


def _native_provider_models(provider: str) -> set[str]:
    """Return the known model ids for a native provider (codex, junie, …).

    For junie the dynamic catalogue (CLI probe → settings.json → static) is
    consulted so newly listed ids are still classified under ``junie``;
    failures fall back to the static list.
    """
    if provider == "junie":
        try:
            return {m.id for m in cached_get_junie_models()}
        except Exception:
            pass
    return {mid for mid, _name, _desc in PROVIDER_MODELS.get(provider, [])}


def resolve_search_models(operator: str, provider: str) -> list[Model]:
    """Resolve the searchable model list for ``(operator, provider)``.

    Junie is resolved dynamically at search time (cached CLI probe, TTL) —
    never from the static list alone; the static catalogue in
    :func:`static_models_for_provider` remains the last-resort fallback when
    discovery yields nothing.

    Args:
        operator: Operator id (e.g. ``"junie"``).
        provider: Provider id (e.g. ``"junie"``).

    Returns:
        Candidate models (possibly empty — callers apply static fallbacks).
    """
    if operator == "junie":
        try:
            return cached_get_junie_models()
        except Exception:
            return []
    return cached_get_provider_models(operator, provider)


def guess_provider(model_id: str, operator: str | None = None) -> str:
    """Guess the provider prefix from a stored model id (cheap, no I/O).

    Args:
        model_id: Stored model id.
        operator: Optional ``NINJA_CODE_BIN`` value. When the id belongs to the
            operator's native model list (e.g. Codex's flat ``gpt-5.6-luna``),
            the native provider is returned instead of the generic prefix guess
            (which would otherwise classify ``gpt*`` as ``openai``).
    """
    if not model_id:
        return "openrouter"
    native = native_provider_for_operator(operator) if operator else None
    if native and model_id in _native_provider_models(native):
        return native
    low = model_id.lower()
    if low.startswith("sonar") or "perplexity" in low:
        return "perplexity"
    if low.startswith("opencode-go/"):
        return "opencode-go"
    if low.startswith("zai-coding-plan/"):
        return "zai-coding-plan"
    if low.startswith("zai/"):
        return "zai"
    if low.startswith("opencode/"):
        return "opencode"
    if low.startswith("gemini") or "google/" in low:
        return "google"
    if low.startswith("junie/"):
        return "junie"
    if low.startswith("claude") or "anthropic/" in low:
        return "anthropic"
    if low.startswith("gpt") or low.startswith("o1") or low.startswith("o3") or "openai/" in low:
        return "openai"
    return "openrouter"


def static_models_for_provider(provider: str, operator: str | None = None) -> list[Model]:
    """Static fallback models used when the operator CLI yields nothing.

    When ``operator`` is a native one, its own catalogue is used so the fallback
    never suggests another operator's model ids.
    """
    op = normalize_operator(operator) if operator else None
    if provider == "perplexity":
        triples = list(PERPLEXITY_MODELS)
    elif op and op in OPERATOR_STATIC_MODELS:
        triples = list(OPERATOR_STATIC_MODELS[op])
    elif op == "opencode":
        # OpenCode models are discovered dynamically (`opencode models
        # <provider>`); never substitute a hardcoded list.
        return []
    elif op == "agy":
        # Antigravity models are discovered dynamically (`agy models`);
        # never substitute another provider's list.
        return []
    elif provider in PROVIDER_MODELS:
        triples = list(PROVIDER_MODELS[provider])
    else:
        triples = list(PROVIDER_MODELS.get("openrouter", []))
    return [
        Model(id=mid, name=name, description=desc, provider=provider) for mid, name, desc in triples
    ]


class ModelSuggestion(ListItem):
    """One dropdown row; carries the ids the save path needs."""

    def __init__(self, model: Model, role: str, env_var: str, current: bool = False) -> None:
        self.model_id: str = model.id
        self.role: str = role
        self.env_var: str = env_var
        badge = "[#a3be8c]✓ current[/#a3be8c]" if current else "[dim]○[/dim]"
        super().__init__(
            Static(f"[bold]{model.name}[/bold]  {badge}\n[dim]{model.id}[/dim]"),
            classes="model-card current" if current else "model-card",
        )


class PlaceholderItem(ListItem):
    """Non-selectable hint row (ignored by the selection handler)."""

    def __init__(self, text: str) -> None:
        super().__init__(Static(f"[dim]{text}[/dim]"), classes="model-placeholder")


class ModelRolePicker(Vertical):
    """Provider Select + debounced model autocomplete for a single role."""

    def __init__(
        self,
        *,
        role: str,
        env_var: str,
        default: str,
        config: ConfigManager,
        operator_env: str = "NINJA_CODE_BIN",
        debounce: float = DEBOUNCE_DELAY,
    ) -> None:
        super().__init__(classes="model-picker")
        self.role = role
        self.env_var = env_var
        self.default = default
        self._config = config
        #: Config key holding this role's operator (coder roles share
        #: NINJA_CODE_BIN; secretary/agent have their own).
        self.operator_env = operator_env
        self._debounce = debounce
        self._provider = self._resolve_provider()
        self._providers_ready = False
        self._providers_loading = False
        self._debounce_timer: Timer | None = None
        self._last_query: str = ""

    # ── compose (sync only — no subprocess, no discovery) ─────────────

    def _native_provider(self) -> str | None:
        """Native provider id for the configured operator (codex, junie, …)."""
        return native_provider_for_operator(self._config.get(self.operator_env))

    def _resolve_provider(self) -> str:
        """Provider to show for the configured operator.

        A native operator (codex/junie/claude/agy) exposes exactly one
        provider, so the picker follows it even when the stored model id still
        carries another operator's prefix (e.g. an OpenRouter id after switching
        the coder operator to codex).
        """
        native = self._native_provider()
        if native:
            return native
        operator = normalize_operator(self._config.get(self.operator_env))
        if operator == "aider":
            # Aider is OpenRouter-backed: its model ids (openrouter/…) must not
            # be classified under their inner provider (anthropic/google/…).
            return "openrouter"
        return guess_provider(self._config.get(self.env_var) or self.default, operator)

    @staticmethod
    def _provider_label(provider: str) -> str:
        return PROVIDER_DISPLAY_NAMES.get(provider, provider.replace("-", " ").title())

    def _initial_options(self) -> list[tuple[str, object]]:
        """Static provider options; always contains the current value (Select crashes otherwise)."""
        native = self._native_provider()
        if native:
            # Native operators (codex/junie/…) expose only their own models.
            opts: list[tuple[str, object]] = [(self._provider_label(native), native)]
        elif self._operator() == "aider":
            opts = [("OpenRouter", "openrouter")]
        elif self._provider:
            # OpenCode providers are discovered dynamically (background worker);
            # show only the current one until discovery lands — no hardcoded list.
            opts = [(self._provider_label(self._provider), self._provider)]
        else:
            opts = []
        if self._provider and all(pid != self._provider for _, pid in opts):
            opts.append((self._provider_label(self._provider), self._provider))
        return opts

    def compose(self) -> ComposeResult:
        current = self._config.get(self.env_var) or self.default
        yield Static(f"Current: [#a3be8c]{current}[/#a3be8c]", id=f"lbl-{self.role}")
        options = self._initial_options()
        provider_select = Select(
            options,
            prompt="Provider…",
            value=self._provider if self._provider else Select.BLANK,
            id=f"prov-select-{self.role}",
        )
        # Only OpenCode has a real provider sub-selection; native operators and
        # Aider have exactly one provider, so the dropdown is hidden for them.
        provider_select.display = len(options) > 1
        yield provider_select
        yield Input(
            placeholder="Type ≥2 chars to search — Enter saves custom id…",
            id=f"model-input-{self.role}",
        )
        yield LoadingIndicator(id=f"loading-{self.role}", classes="model-loading")
        yield Static(
            "Providers load when the Models tab opens.",
            id=f"status-{self.role}",
            classes="model-status",
        )
        suggest = ListView(id=f"suggest-{self.role}", classes="model-suggest")
        yield suggest

    def on_mount(self) -> None:
        try:
            self.query_one(f"#loading-{self.role}", LoadingIndicator).display = False
            suggest = self.query_one(f"#suggest-{self.role}", ListView)
            suggest.append(PlaceholderItem("Pick a provider ↑, then type ≥2 chars."))
        except Exception:
            pass

    # ── lazy provider discovery (called once by the app on tab open) ──

    def load_providers(self) -> None:
        """Start background provider discovery (idempotent, cheap to call)."""
        if self._providers_ready or self._providers_loading:
            return
        self._providers_loading = True
        try:
            self.query_one(f"#loading-{self.role}", LoadingIndicator).display = True
            self.query_one(f"#status-{self.role}", Static).update("Loading providers…")
        except Exception:
            pass
        self._fetch_providers()

    def _post(self, callback, *args) -> None:
        """``call_from_thread`` that no-ops if the app/loop is already gone."""
        try:
            if not getattr(self.app, "is_running", True):
                return
            self.app.call_from_thread(callback, *args)
        except Exception:
            pass

    @work(thread=True, exclusive=True)
    def _fetch_providers(self) -> None:
        # Operator-aware: native operators are handled in _apply_providers, but
        # Aider is OpenRouter-backed (not OpenCode discovery) and must not list
        # OpenCode providers it cannot run.
        if self._operator() == "aider":
            providers = operator_providers("aider")
        else:
            providers = cached_discover_providers()
        self._post(self._apply_providers, providers)

    def _apply_providers(self, providers: list[tuple[str, str, str]]) -> None:
        self._providers_ready = True
        self._providers_loading = False
        try:
            select = self.query_one(f"#prov-select-{self.role}", Select)
            if self.role == "researcher":
                wanted = [(p, d) for p, d, _ in providers if p in ("openrouter", "perplexity")]
                if not any(p == "openrouter" for p, _ in wanted):
                    wanted.insert(0, ("openrouter", "OpenRouter"))
            else:
                # Native operators (codex/junie/…) expose only their own
                # models — opencode provider discovery never lists them.
                native = self._native_provider()
                if native:
                    wanted = [(native, self._provider_label(native))]
                else:
                    # OpenCode: providers the CLI actually exposes (dynamic),
                    # including Anthropic/Google/etc. once configured. No
                    # hardcoded provider exclusion.
                    wanted = [(p, d) for p, d, _ in providers]
                    if not wanted and self._provider:
                        wanted = [(self._provider_label(self._provider), self._provider)]
            # Select options are (label, value) tuples.
            if self._provider and all(v != self._provider for v, _ in wanted):
                wanted.append((self._provider, self._provider_label(self._provider)))
            select.set_options([(label, value) for value, label in wanted])
            values = [value for _, value in [(label, value) for value, label in wanted]]
            if self._provider in values:
                select.value = self._provider
            select.display = len(wanted) > 1
            self.query_one(f"#loading-{self.role}", LoadingIndicator).display = False
            self.query_one(f"#status-{self.role}", Static).update(
                "Type ≥2 chars to search — ↓ for list, Enter saves."
            )
        except Exception:
            pass
        self._warm_models()

    def refresh_providers(self) -> None:
        """Force re-discovery on next tick (used by app refresh after cache clear)."""
        self._providers_ready = False
        self._providers_loading = False
        self.load_providers()

    def on_operator_changed(self) -> None:
        """Re-resolve providers/models after the active operator was switched.

        Recomputes the provider from the stored model under the new operator,
        rebuilds the Select options (native provider first), and re-discovers.
        """
        self._provider = self._resolve_provider()
        self._providers_ready = False
        self._providers_loading = False
        try:
            select = self.query_one(f"#prov-select-{self.role}", Select)
            select.set_options(self._initial_options())
            if self._provider:
                select.value = self._provider
        except Exception:
            pass
        self.clear_suggestions("Provider updated — type ≥2 chars to search.")
        self.load_providers()

    # ── provider switching ────────────────────────────────────────────

    @on(Select.Changed)
    def on_select_changed(self, event: Select.Changed) -> None:
        select_id = f"prov-select-{self.role}"
        if event.select.id != select_id:
            return
        value = event.value
        if value is None or value == Select.BLANK:
            return
        new_provider = str(value)
        if new_provider == self._provider:
            # Spurious mount-time Changed (Select re-affirms its initial value)
            # or a programmatic re-set — no provider switch, no warm-up.
            return
        self._provider = new_provider
        self.clear_suggestions("Type ≥2 chars to search — ↓ for list, Enter saves.")
        if self._providers_ready:
            # Before initial discovery completes (e.g. user racing the Models
            # tab) warming is pointless: _apply_providers warms explicitly.
            self._warm_models()

    @work(thread=True, exclusive=True)
    def _warm_models(self) -> None:
        """Preload this provider's models into the process cache (no UI churn)."""
        cached_get_provider_models(self._operator(), self._provider)

    # ── debounced autocomplete ────────────────────────────────────────

    @on(Input.Changed)
    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != f"model-input-{self.role}":
            return
        query = event.value or ""
        if self._debounce_timer is not None:
            try:
                self._debounce_timer.stop()
            except Exception:
                pass
            self._debounce_timer = None
        if len(query.strip()) < MIN_QUERY_LEN:
            try:
                self.query_one(f"#loading-{self.role}", LoadingIndicator).display = False
            except Exception:
                pass
            if not query.strip():
                self.clear_suggestions("Type ≥2 chars to search — ↓ for list, Enter saves.")
            return
        self._last_query = query
        try:
            self._debounce_timer = self.set_timer(self._debounce, self._fire_debounced)
        except Exception:
            self._fire_debounced()

    def _fire_debounced(self) -> None:
        self._debounce_timer = None
        try:
            query = self.query_one(f"#model-input-{self.role}", Input).value or ""
        except Exception:
            return
        if len(query.strip()) < MIN_QUERY_LEN or query != self._last_query:
            return
        try:
            self.query_one(f"#loading-{self.role}", LoadingIndicator).display = True
            self.query_one(f"#status-{self.role}", Static).update("Searching…")
            suggest = self.query_one(f"#suggest-{self.role}", ListView)
            suggest.clear()
            suggest.append(PlaceholderItem("Searching…"))
        except Exception:
            pass
        self._search_models(query, self._provider)

    @work(thread=True)
    def _search_models(self, query: str, provider: str) -> None:
        operator = self._operator()
        models = resolve_search_models(operator, provider)
        if not models:
            models = static_models_for_provider(provider, operator)
        results = filter_models(models, query, MAX_SUGGESTIONS)
        self._post(self._show_results, query, provider, results)

    def _show_results(self, query: str, provider: str, results: list[Model]) -> None:
        try:
            current_input = self.query_one(f"#model-input-{self.role}", Input).value or ""
        except Exception:
            return
        if current_input != query or provider != self._provider:
            return  # Stale — user kept typing or switched provider.
        try:
            self.query_one(f"#loading-{self.role}", LoadingIndicator).display = False
            suggest = self.query_one(f"#suggest-{self.role}", ListView)
            status = self.query_one(f"#status-{self.role}", Static)
            suggest.clear()
            if not results:
                status.update("No models found — Enter saves custom id.")
                suggest.append(PlaceholderItem("No models found."))
                return
            current = self._config.get(self.env_var) or self.default
            for model in results:
                suggest.append(
                    ModelSuggestion(model, self.role, self.env_var, current=(model.id == current))
                )
            suggest.index = 0
            status.update(f"{len(results)} match(es) — ↑↓ + Enter, Esc clears.")
        except Exception:
            pass

    # ── selection + custom save ───────────────────────────────────────

    @on(ListView.Selected)
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != f"suggest-{self.role}":
            return
        item = event.item
        model_id = getattr(item, "model_id", None)
        if not model_id:
            return  # Placeholder row — ignore.
        self._save(str(model_id))

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != f"model-input-{self.role}":
            return
        raw = (event.value or "").strip()
        if not raw:
            return
        try:
            suggest = self.query_one(f"#suggest-{self.role}", ListView)
            highlighted = getattr(suggest, "highlighted_child", None)
            highlighted_id = getattr(highlighted, "model_id", None)
            if highlighted_id and raw.lower() in str(highlighted_id).lower():
                self._save(str(highlighted_id))
                return
        except Exception:
            pass
        self._save(raw)  # Custom model id.

    def save_current_input(self) -> None:
        """Save whatever is in the input box (wired to the app's ``s`` binding)."""
        try:
            value = (self.query_one(f"#model-input-{self.role}", Input).value or "").strip()
        except Exception:
            return
        if not value:
            try:
                self.app.notify(f"Type a model id for {self.role} first.", timeout=3)
            except Exception:
                pass
            return
        self._save(value)

    def _save(self, model_id: str) -> None:
        self._config.set(self.env_var, model_id)
        try:
            self.query_one(f"#lbl-{self.role}", Static).update(
                f"Current: [#a3be8c]{model_id}[/#a3be8c]"
            )
            self.query_one(f"#model-input-{self.role}", Input).value = ""
            self.clear_suggestions(f"Saved {model_id} — type to search again.")
        except Exception:
            pass
        try:
            self.app.notify(f"Model set: {model_id}", timeout=3)
        except Exception:
            pass

    # ── keyboard: Down jumps into the list, Esc clears + returns ──────

    def on_key(self, event: events.Key) -> None:
        focused = self.screen.focused if self.screen else None
        focused_id = getattr(focused, "id", "") or ""
        if event.key == "escape" and focused_id in (
            f"model-input-{self.role}",
            f"suggest-{self.role}",
        ):
            try:
                suggest = self.query_one(f"#suggest-{self.role}", ListView)
                has_matches = any(hasattr(child, "model_id") for child in suggest.children)
            except Exception:
                has_matches = False
            if has_matches:
                self.clear_suggestions("Type ≥2 chars to search — ↓ for list, Enter saves.")
                try:
                    self.query_one(f"#model-input-{self.role}", Input).focus()
                except Exception:
                    pass
            else:
                # Nothing to clear — release focus so app-level keys (1-6, s, /) work.
                try:
                    self.screen.set_focus(None)
                except Exception:
                    pass
            event.stop()
            event.prevent_default()
        elif event.key == "down" and focused_id == f"model-input-{self.role}":
            try:
                suggest = self.query_one(f"#suggest-{self.role}", ListView)
                if any(hasattr(child, "model_id") for child in suggest.children):
                    suggest.focus()
                    event.stop()
                    event.prevent_default()
            except Exception:
                pass

    # ── helpers ───────────────────────────────────────────────────────

    def clear_suggestions(self, status_text: str = "") -> None:
        """Empty the dropdown; optionally set the status line."""
        try:
            suggest = self.query_one(f"#suggest-{self.role}", ListView)
            suggest.clear()
            if status_text:
                self.query_one(f"#status-{self.role}", Static).update(status_text)
        except Exception:
            pass

    def refresh_label(self) -> None:
        """Re-render the current-model label (used by app refresh)."""
        try:
            current = self._config.get(self.env_var) or self.default
            self.query_one(f"#lbl-{self.role}", Static).update(
                f"Current: [#a3be8c]{current}[/#a3be8c]"
            )
        except Exception:
            pass

    def _operator(self) -> str:
        return normalize_operator(self._config.get(self.operator_env))
