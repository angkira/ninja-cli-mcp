"""
Unit tests for TUIInstaller.

Tests cover constructor, save helpers, interactive configuration methods,
and the main run() flow. All InquirerPy calls are mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ninja_config.config_shared import DAEMON_CONFIG, APIKeyDef
from ninja_config.tui_installer import TUIInstaller, _exec, run_tui_installer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_installer(**overrides):
    with patch("ninja_config.tui_installer.ConfigManager") as MockCM, \
         patch("ninja_config.tui_installer.detect_tools", return_value={}), \
         patch("ninja_config.tui_installer.detect_ides", return_value={}):
        mock_mgr = MagicMock()
        mock_mgr.list_all.return_value = {}
        MockCM.return_value = mock_mgr
        inst = TUIInstaller()
    for k, v in overrides.items():
        setattr(inst, k, v)
    return inst


# ---------------------------------------------------------------------------
# _exec helper
# ---------------------------------------------------------------------------

class TestExec:
    def test_returns_value_directly(self):
        assert _exec("hello") == "hello"

    def test_calls_execute_if_present(self):
        obj = MagicMock()
        obj.execute.return_value = 42
        del obj.spam  # ensure hasattr only for execute
        assert _exec(obj) == 42
        obj.execute.assert_called_once()

    def test_no_execute_attr(self):
        class NoExec:
            pass
        obj = NoExec()
        assert _exec(obj) is obj


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------

class TestConstructor:
    @patch("ninja_config.tui_installer.detect_ides", return_value={"claude": "/path"})
    @patch("ninja_config.tui_installer.detect_tools", return_value={"aider": "/usr/local/bin/aider"})
    @patch("ninja_config.tui_installer.ConfigManager")
    def test_creates_config_manager(self, MockCM, mock_tools, mock_ides):
        mock_mgr = MagicMock()
        mock_mgr.list_all.return_value = {"K": "V"}
        MockCM.return_value = mock_mgr
        inst = TUIInstaller()
        MockCM.assert_called_once()
        assert inst.config_mgr is mock_mgr

    @patch("ninja_config.tui_installer.detect_ides", return_value={})
    @patch("ninja_config.tui_installer.detect_tools", return_value={"aider": "/bin/aider"})
    @patch("ninja_config.tui_installer.ConfigManager")
    def test_calls_detect_tools(self, MockCM, mock_tools, mock_ides):
        MockCM.return_value.list_all.return_value = {}
        TUIInstaller()
        mock_tools.assert_called_once()

    @patch("ninja_config.tui_installer.detect_ides", return_value={"vscode": "/path"})
    @patch("ninja_config.tui_installer.detect_tools", return_value={})
    @patch("ninja_config.tui_installer.ConfigManager")
    def test_calls_detect_ides(self, MockCM, mock_tools, mock_ides):
        MockCM.return_value.list_all.return_value = {}
        TUIInstaller()
        mock_ides.assert_called_once()

    @patch("ninja_config.tui_installer.detect_ides", return_value={})
    @patch("ninja_config.tui_installer.detect_tools", return_value={})
    @patch("ninja_config.tui_installer.ConfigManager")
    def test_modules_starts_empty(self, MockCM, mock_tools, mock_ides):
        MockCM.return_value.list_all.return_value = {}
        inst = TUIInstaller()
        assert inst.modules == []


# ---------------------------------------------------------------------------
# _save / _save_batch
# ---------------------------------------------------------------------------

class TestSave:
    def test_save_calls_config_mgr_set(self):
        inst = _make_installer()
        inst._save("FOO", "bar")
        inst.config_mgr.set.assert_called_once_with("FOO", "bar")
        assert inst.config["FOO"] == "bar"

    def test_save_batch_calls_config_mgr_update(self):
        inst = _make_installer()
        updates = {"A": "1", "B": "2"}
        inst._save_batch(updates)
        inst.config_mgr.update.assert_called_once_with(updates)
        assert inst.config["A"] == "1"
        assert inst.config["B"] == "2"


# ---------------------------------------------------------------------------
# _ask_key
# ---------------------------------------------------------------------------

class TestAskKey:
    def _key_def(self, env_var="TEST_KEY", display_name="Test", url="http://x",
                 module="coder", description="desc"):
        return APIKeyDef(env_var, display_name, url, module, description)

    @patch("ninja_config.tui_installer.save_secret")
    @patch("ninja_config.tui_installer.inquirer")
    @patch("ninja_config.tui_installer.get_secret", return_value="existing_secret_value")
    def test_existing_key_user_confirms(self, mock_get, mock_inq, mock_save):
        mock_inq.confirm.return_value.execute.return_value = True
        inst = _make_installer()
        inst._ask_key(self._key_def())
        mock_save.assert_not_called()

    @patch("ninja_config.tui_installer.save_secret")
    @patch("ninja_config.tui_installer.inquirer")
    @patch("ninja_config.tui_installer.get_secret", return_value="existing_secret_value")
    def test_existing_key_user_declines_enters_new(self, mock_get, mock_inq, mock_save):
        mock_inq.confirm.return_value.execute.return_value = False
        mock_inq.secret.return_value.execute.return_value = "new_key_123"
        inst = _make_installer()
        inst._ask_key(self._key_def())
        mock_save.assert_called_once_with("TEST_KEY", "new_key_123")

    @patch("ninja_config.tui_installer.save_secret")
    @patch("ninja_config.tui_installer.inquirer")
    @patch("ninja_config.tui_installer.get_secret", return_value=None)
    def test_no_existing_key_enters_new(self, mock_get, mock_inq, mock_save):
        mock_inq.secret.return_value.execute.return_value = "brand_new_key"
        inst = _make_installer()
        inst._ask_key(self._key_def())
        mock_save.assert_called_once_with("TEST_KEY", "brand_new_key")

    @patch("ninja_config.tui_installer.save_secret")
    @patch("ninja_config.tui_installer.inquirer")
    @patch("ninja_config.tui_installer.get_secret", return_value=None)
    def test_no_existing_key_user_skips(self, mock_get, mock_inq, mock_save):
        mock_inq.secret.return_value.execute.return_value = ""
        inst = _make_installer()
        inst._ask_key(self._key_def())
        mock_save.assert_not_called()


# ---------------------------------------------------------------------------
# _configure_coder
# ---------------------------------------------------------------------------

class TestConfigureCoder:
    @patch("ninja_config.tui_installer.save_secret")
    @patch("ninja_config.tui_installer.inquirer")
    @patch("ninja_config.tui_installer.get_secret", return_value=None)
    @patch("ninja_config.tui_installer.shutil.which", return_value="/bin/aider")
    def test_selects_aider(self, mock_which, mock_get, mock_inq, mock_save):
        mock_inq.select.return_value.execute.return_value = "aider"
        mock_inq.secret.return_value.execute.return_value = ""
        inst = _make_installer()
        inst.modules = ["coder"]
        inst.tools = {}
        inst._configure_coder()
        assert inst.config.get("NINJA_CODE_BIN") == "aider"

    @patch("ninja_config.tui_installer.save_secret")
    @patch("ninja_config.tui_installer.inquirer")
    @patch("ninja_config.tui_installer.get_secret", return_value=None)
    @patch("ninja_config.tui_installer.shutil.which", return_value=None)
    @patch("ninja_config.tui_installer.subprocess")
    def test_aider_auto_install(self, mock_sub, mock_which, mock_get, mock_inq, mock_save):
        mock_inq.select.return_value.execute.return_value = "aider"
        mock_inq.secret.return_value.execute.return_value = ""
        mock_sub.run.return_value = MagicMock(returncode=0)
        inst = _make_installer()
        inst.modules = ["coder"]
        inst.tools = {}
        inst._configure_coder()
        mock_sub.run.assert_any_call(
            ["pipx", "install", "aider-chat"],
            capture_output=True, text=True, check=False,
        )

    @patch("ninja_config.tui_installer.save_secret")
    @patch("ninja_config.tui_installer.inquirer")
    @patch("ninja_config.tui_installer.get_secret", return_value=None)
    @patch("ninja_config.tui_installer.shutil.which", return_value="/bin/opencode")
    def test_custom_path(self, mock_which, mock_get, mock_inq, mock_save):
        mock_inq.select.return_value.execute.return_value = "__custom"
        mock_inq.text.return_value.execute.return_value = "/custom/path/bin"
        mock_inq.secret.return_value.execute.return_value = ""
        inst = _make_installer()
        inst.modules = ["coder"]
        inst.tools = {"opencode": "/bin/opencode"}
        inst._configure_coder()
        assert inst.config.get("NINJA_CODE_BIN") == "/custom/path/bin"


# ---------------------------------------------------------------------------
# _configure_researcher
# ---------------------------------------------------------------------------

class TestConfigureResearcher:
    @patch("ninja_config.tui_installer.inquirer")
    def test_duckduckgo_no_key_prompt(self, mock_inq):
        mock_inq.select.return_value.execute.return_value = "duckduckgo"
        inst = _make_installer()
        inst.modules = ["researcher"]
        with patch.object(inst, "_ask_key") as mock_ask:
            inst._configure_researcher()
            mock_ask.assert_not_called()
        assert inst.config.get("NINJA_SEARCH_PROVIDER") == "duckduckgo"

    @patch("ninja_config.tui_installer.inquirer")
    def test_serper_prompts_key(self, mock_inq):
        mock_inq.select.return_value.execute.return_value = "serper"
        inst = _make_installer()
        inst.modules = ["researcher"]
        with patch.object(inst, "_ask_key") as mock_ask:
            inst._configure_researcher()
            called_vars = [c.args[0].env_var for c in mock_ask.call_args_list]
            assert "SERPER_API_KEY" in called_vars

    @patch("ninja_config.tui_installer.inquirer")
    def test_perplexity_prompts_key(self, mock_inq):
        mock_inq.select.return_value.execute.return_value = "perplexity"
        inst = _make_installer()
        inst.modules = ["researcher"]
        with patch.object(inst, "_ask_key") as mock_ask:
            inst._configure_researcher()
            called_vars = [c.args[0].env_var for c in mock_ask.call_args_list]
            assert "PERPLEXITY_API_KEY" in called_vars


# ---------------------------------------------------------------------------
# _configure_models
# ---------------------------------------------------------------------------

class TestConfigureModels:
    @patch("ninja_config.tui_installer.inquirer")
    def test_coder_model_saved(self, mock_inq):
        mock_inq.select.return_value.execute.return_value = "openrouter/anthropic/claude-haiku-4.5"
        inst = _make_installer()
        inst.modules = ["coder"]
        inst._configure_models()
        assert inst.config.get("NINJA_CODER_MODEL") == "openrouter/anthropic/claude-haiku-4.5"

    @patch("ninja_config.tui_installer.inquirer")
    def test_researcher_model_saved(self, mock_inq):
        mock_inq.select.return_value.execute.return_value = "sonar-pro"
        inst = _make_installer()
        inst.modules = ["researcher"]
        inst._configure_models()
        assert inst.config.get("NINJA_RESEARCHER_MODEL") == "sonar-pro"

    @patch("ninja_config.tui_installer.inquirer")
    def test_custom_model(self, mock_inq):
        mock_inq.select.return_value.execute.return_value = "__custom"
        mock_inq.text.return_value.execute.return_value = "my/custom-model"
        inst = _make_installer()
        inst.modules = ["coder"]
        inst._configure_models()
        assert inst.config.get("NINJA_CODER_MODEL") == "my/custom-model"

    @patch("ninja_config.tui_installer.inquirer")
    def test_coder_choices_include_zai_models(self, mock_inq):
        captured_choices = []
        def capture_choices(**kwargs):
            captured_choices.extend(kwargs.get("choices", []))
            m = MagicMock()
            m.execute.return_value = "some_model"
            return m
        mock_inq.select.side_effect = capture_choices
        inst = _make_installer()
        inst.modules = ["coder"]
        inst._configure_models()
        choice_values = [
            c.value for c in captured_choices
            if hasattr(c, "value")
        ]
        from ninja_common.defaults import ZAI_MODELS
        for mid, _name, _desc in ZAI_MODELS:
            assert mid in choice_values, f"ZAI model {mid} not in coder choices"

    @patch("ninja_config.tui_installer.inquirer")
    def test_skips_non_model_modules(self, mock_inq):
        mock_inq.select.return_value.execute.return_value = "x"
        inst = _make_installer()
        inst.modules = ["resources", "prompts"]
        inst._configure_models()
        mock_inq.select.assert_not_called()


# ---------------------------------------------------------------------------
# _configure_daemon
# ---------------------------------------------------------------------------

class TestConfigureDaemon:
    @patch("ninja_config.tui_installer.inquirer")
    def test_accept_daemon(self, mock_inq):
        mock_inq.confirm.return_value.execute.return_value = True
        inst = _make_installer()
        inst._configure_daemon()
        inst.config_mgr.update.assert_called_once_with(DAEMON_CONFIG)

    @patch("ninja_config.tui_installer.inquirer")
    def test_decline_daemon(self, mock_inq):
        mock_inq.confirm.return_value.execute.return_value = False
        inst = _make_installer()
        inst._configure_daemon()
        inst.config_mgr.set.assert_any_call("NINJA_ENABLE_DAEMON", "false")
        assert inst.config.get("NINJA_ENABLE_DAEMON") == "false"


# ---------------------------------------------------------------------------
# _configure_ide
# ---------------------------------------------------------------------------

class TestConfigureIde:
    def test_no_ides_returns_empty(self):
        inst = _make_installer()
        inst.ides = {}
        assert inst._configure_ide() == []

    @patch("ninja_config.tui_installer.inquirer")
    def test_ides_selected(self, mock_inq):
        mock_inq.checkbox.return_value.execute.return_value = ["claude", "vscode"]
        inst = _make_installer()
        inst.ides = {"claude": "/path1", "vscode": "/path2"}
        result = inst._configure_ide()
        assert result == ["claude", "vscode"]

    @patch("ninja_config.tui_installer.inquirer")
    def test_ides_none_selected_returns_empty(self, mock_inq):
        mock_inq.checkbox.return_value.execute.return_value = None
        inst = _make_installer()
        inst.ides = {"claude": "/path1"}
        assert inst._configure_ide() == []


# ---------------------------------------------------------------------------
# _register_ides
# ---------------------------------------------------------------------------

class TestRegisterIdes:
    @patch("ninja_config.tui_installer.register_claude_mcp", return_value=3)
    def test_claude_calls_register(self, mock_reg):
        inst = _make_installer()
        inst._register_ides(["claude"])
        mock_reg.assert_called_once()

    def test_other_ide_prints_warning(self, capsys):
        inst = _make_installer()
        inst._register_ides(["zed"])
        captured = capsys.readouterr()
        assert "zed" in captured.out


# ---------------------------------------------------------------------------
# _verify
# ---------------------------------------------------------------------------

class TestVerify:
    @patch("ninja_config.tui_installer.shutil.which", return_value="/usr/local/bin/cmd")
    def test_all_found(self, mock_which, capsys):
        inst = _make_installer()
        inst._verify()
        out = capsys.readouterr().out
        for cmd in ("ninja-config", "ninja-coder", "ninja-researcher", "ninja-secretary", "ninja-agent"):
            assert cmd in out

    @patch("ninja_config.tui_installer.shutil.which", return_value=None)
    def test_none_found(self, mock_which, capsys):
        inst = _make_installer()
        inst._verify()
        out = capsys.readouterr().out
        assert "not found" in out

    @patch("ninja_config.tui_installer.shutil.which")
    def test_verify_checks_ninja_agent(self, mock_which, capsys):
        mock_which.side_effect = lambda cmd: f"/usr/local/bin/{cmd}" if cmd == "ninja-agent" else None
        inst = _make_installer()
        inst._verify()
        out = capsys.readouterr().out
        assert "ninja-agent" in out
        mock_which.assert_any_call("ninja-agent")


# ---------------------------------------------------------------------------
# _select_modules — agent
# ---------------------------------------------------------------------------

class TestSelectModulesAgent:
    @patch("ninja_config.tui_installer.inquirer")
    def test_full_contains_agent(self, mock_inq):
        mock_inq.select.return_value.execute.return_value = "full"
        inst = _make_installer()
        inst._select_modules()
        assert "agent" in inst.modules

    @patch("ninja_config.tui_installer.inquirer")
    def test_minimal_excludes_agent(self, mock_inq):
        mock_inq.select.return_value.execute.return_value = "minimal"
        inst = _make_installer()
        inst._select_modules()
        assert "agent" not in inst.modules

    @patch("ninja_config.tui_installer.inquirer")
    def test_custom_agent_selection(self, mock_inq):
        mock_inq.select.return_value.execute.return_value = "custom"
        mock_inq.checkbox.return_value.execute.return_value = ["coder", "agent"]
        inst = _make_installer()
        inst._select_modules()
        assert inst.modules == ["coder", "agent"]

    @patch("ninja_config.tui_installer.inquirer")
    def test_custom_choices_include_agent(self, mock_inq):
        captured = []
        def capture_checkbox(**kwargs):
            captured.extend(kwargs.get("choices", []))
            m = MagicMock()
            m.execute.return_value = ["agent"]
            return m
        mock_inq.select.return_value.execute.return_value = "custom"
        mock_inq.checkbox.side_effect = capture_checkbox
        inst = _make_installer()
        inst._select_modules()
        values = [c.value for c in captured if hasattr(c, "value")]
        assert "agent" in values


# ---------------------------------------------------------------------------
# _configure_models — agent
# ---------------------------------------------------------------------------

class TestConfigureModelsAgent:
    @patch("ninja_config.tui_installer.inquirer")
    def test_agent_model_saved(self, mock_inq):
        mock_inq.select.return_value.execute.return_value = "openrouter/anthropic/claude-haiku-4.5"
        inst = _make_installer()
        inst.modules = ["agent"]
        inst._configure_models()
        assert inst.config.get("NINJA_AGENT_MODEL") == "openrouter/anthropic/claude-haiku-4.5"

    @patch("ninja_config.tui_installer.inquirer")
    def test_agent_not_skipped(self, mock_inq):
        mock_inq.select.return_value.execute.return_value = "x"
        inst = _make_installer()
        inst.modules = ["agent"]
        inst._configure_models()
        mock_inq.select.assert_called()


# ---------------------------------------------------------------------------
# run — integration
# ---------------------------------------------------------------------------

class TestRun:
    def _full_installer(self):
        with patch("ninja_config.tui_installer.ConfigManager") as MockCM, \
             patch("ninja_config.tui_installer.detect_tools", return_value={}), \
             patch("ninja_config.tui_installer.detect_ides", return_value={}):
            mock_mgr = MagicMock()
            mock_mgr.list_all.return_value = {}
            MockCM.return_value = mock_mgr
            inst = TUIInstaller()
        return inst

    @patch("ninja_config.tui_installer.shutil.which", return_value="/bin/uv")
    @patch("ninja_config.tui_installer.check_python", return_value=True)
    @patch("ninja_config.tui_installer.check_uv", return_value=True)
    @patch("ninja_config.tui_installer.subprocess")
    @patch("ninja_config.tui_installer.inquirer")
    def test_run_success_returns_0(self, mock_inq, mock_sub, mock_uv, mock_py, mock_which):
        mock_sub.run.return_value = MagicMock(returncode=0)
        mock_inq.select.return_value.execute.return_value = "full"
        mock_inq.confirm.return_value.execute.return_value = True
        mock_inq.checkbox.return_value.execute.return_value = []
        mock_inq.secret.return_value.execute.return_value = ""

        inst = self._full_installer()
        with patch.object(inst, "_configure_coder"), \
             patch.object(inst, "_configure_researcher"), \
             patch.object(inst, "_configure_models"), \
             patch.object(inst, "_configure_daemon"), \
             patch.object(inst, "_configure_ide", return_value=[]), \
             patch.object(inst, "_register_ides"), \
             patch.object(inst, "_verify"), \
             patch.object(inst, "_summary"):
            assert inst.run() == 0

    @patch("ninja_config.tui_installer.check_python", return_value=False)
    def test_run_fails_on_python(self, mock_py):
        inst = self._full_installer()
        assert inst.run() == 1

    @patch("ninja_config.tui_installer.install_uv", return_value=False)
    @patch("ninja_config.tui_installer.check_python", return_value=True)
    @patch("ninja_config.tui_installer.check_uv", return_value=False)
    def test_run_fails_on_uv_install(self, mock_uv, mock_install, mock_py):
        inst = self._full_installer()
        assert inst.run() == 1

    @patch("ninja_config.tui_installer.shutil.which", return_value="/bin/uv")
    @patch("ninja_config.tui_installer.check_python", return_value=True)
    @patch("ninja_config.tui_installer.check_uv", return_value=True)
    @patch("ninja_config.tui_installer.subprocess")
    @patch("ninja_config.tui_installer.inquirer")
    def test_run_fails_on_package_install(self, mock_inq, mock_sub, mock_uv, mock_py, mock_which):
        mock_sub.run.return_value = MagicMock(returncode=1, stderr="fail")
        mock_inq.select.return_value.execute.return_value = "full"

        inst = self._full_installer()
        with patch.object(inst, "_configure_coder"), \
             patch.object(inst, "_configure_researcher"), \
             patch.object(inst, "_configure_models"), \
             patch.object(inst, "_configure_daemon"), \
             patch.object(inst, "_configure_ide", return_value=[]), \
             patch.object(inst, "_register_ides"), \
             patch.object(inst, "_verify"), \
             patch.object(inst, "_summary"):
            assert inst.run() == 1


# ---------------------------------------------------------------------------
# run_tui_installer entry point
# ---------------------------------------------------------------------------

class TestRunTuiInstaller:
    @patch("ninja_config.tui_installer.TUIInstaller")
    def test_delegates_to_installer(self, MockCls):
        MockCls.return_value.run.return_value = 0
        assert run_tui_installer() == 0
        MockCls.return_value.run.assert_called_once()
