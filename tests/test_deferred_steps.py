"""Tests for all 11 deferred steps implemented in feature/deferred-steps-cleanup."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# Ensure pace/ is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "pace"))


# ===========================================================================
# Item 4 (updater.py) — URL fix, update_available event, update_status.yaml
# ===========================================================================

def test_upgrade_tutorial_url_is_real(tmp_path):
    """_UPGRADE_TUTORIAL must not contain the placeholder 'example.com'."""
    import updater
    assert "example.com" not in updater._UPGRADE_TUTORIAL
    assert updater._UPGRADE_TUTORIAL.startswith("https://")


def test_write_update_status_creates_file(tmp_path, monkeypatch):
    import updater
    monkeypatch.setattr(updater, "_PACE_DIR", tmp_path)
    monkeypatch.setattr(updater, "_UPDATE_STATUS_FILE", tmp_path / "update_status.yaml")

    updater._write_update_status("v3.0.0", "2.0.0", [])
    data = json.loads((tmp_path / "update_status.yaml").read_text())
    assert data["update_available"] is True
    assert data["new_version"] == "v3.0.0"
    assert data["current_version"] == "v2.0.0"
    assert "customization_note" in data


def test_write_update_status_with_customizations(tmp_path, monkeypatch):
    import updater
    monkeypatch.setattr(updater, "_PACE_DIR", tmp_path)
    monkeypatch.setattr(updater, "_UPDATE_STATUS_FILE", tmp_path / "update_status.yaml")

    updater._write_update_status("v3.0.0", "2.0.0", ["pace/forger.py", "pace/config.py", "pace/extra.py", "pace/more.py"])
    data = json.loads((tmp_path / "update_status.yaml").read_text())
    assert "..." in data["customization_note"]   # truncated list gets "..."


def test_clear_update_status_removes_file(tmp_path, monkeypatch):
    import updater
    status_file = tmp_path / "update_status.yaml"
    status_file.write_text("{}")
    monkeypatch.setattr(updater, "_UPDATE_STATUS_FILE", status_file)

    updater._clear_update_status()
    assert not status_file.exists()


def test_clear_update_status_noop_when_absent(tmp_path, monkeypatch):
    import updater
    monkeypatch.setattr(updater, "_UPDATE_STATUS_FILE", tmp_path / "no_such_file.yaml")
    updater._clear_update_status()  # must not raise


def test_fire_update_available_event_calls_alert_engine(monkeypatch):
    import updater
    mock_engine = MagicMock()
    mock_cfg = MagicMock()

    # The function imports load_config and AlertEngine inside itself via
    # `from config import load_config` / `from alert_engine import AlertEngine`,
    # so we patch the source modules, not updater.
    with patch("config.load_config", return_value=mock_cfg), \
         patch("alert_engine.AlertEngine", return_value=mock_engine):
        updater._fire_update_available_event("v3.0.0", "2.0.0", [])

    mock_engine.fire.assert_called_once_with(
        "update_available",
        {
            "new_version": "v3.0.0",
            "current_version": "v2.0.0",
            "customization_note": "Auto-update is disabled in config.",
        },
    )


def test_fire_update_available_event_non_fatal_on_exception(monkeypatch):
    """Event fire failure must never propagate."""
    import updater
    with patch("config.load_config", side_effect=RuntimeError("cfg error")):
        updater._fire_update_available_event("v3.0.0", "2.0.0", [])  # must not raise


def test_check_and_warn_fires_event_when_cannot_auto_update(tmp_path, monkeypatch):
    import updater
    monkeypatch.setattr(updater, "_PACE_DIR", tmp_path)
    monkeypatch.setattr(updater, "_UPDATE_STATUS_FILE", tmp_path / "update_status.yaml")
    monkeypatch.setattr(updater, "_current_version", lambda: "2.0.0")
    monkeypatch.setattr(updater, "_read_cache", lambda: None)
    monkeypatch.setattr(updater, "_fetch_latest_release", lambda channel="stable": {"tag_name": "v3.0.0"})
    monkeypatch.setattr(updater, "detect_customizations", lambda installed_tag=None: ["pace/foo.py"])
    monkeypatch.setattr(updater, "apply_update", lambda tag: False)

    fired_events = []

    def _mock_fire(ev, payload):
        fired_events.append((ev, payload))

    mock_engine = MagicMock()
    mock_engine.fire.side_effect = _mock_fire

    with patch("config.load_config", return_value=MagicMock()), \
         patch("alert_engine.AlertEngine", return_value=mock_engine):
        updater.check_and_warn(auto_update=True, suppress_warning=True)

    assert any(ev == "update_available" for ev, _ in fired_events)
    assert (tmp_path / "update_status.yaml").exists()


# ===========================================================================
# Item 8 (config_tester.py) — ci_generator cross-wire suggestion
# ===========================================================================

def test_validate_cron_suggests_ci_generator_check(tmp_path):
    from config_tester import _validate_cron, ConfigTestResult

    r = ConfigTestResult()
    _validate_cron({"cron": {"pace_pipeline": "0 9 * * 1-5"}}, r)

    assert any("ci_generator.py --check" in s for s in r.suggestions)


def test_validate_cron_no_suggestion_when_invalid_expression(tmp_path):
    from config_tester import _validate_cron, ConfigTestResult

    r = ConfigTestResult()
    _validate_cron({"cron": {"pace_pipeline": "not-a-cron"}}, r)

    assert not any("ci_generator.py" in s for s in r.suggestions)
    assert any("cron" in e for e in r.errors)


def test_validate_cron_no_suggestion_when_cron_absent():
    from config_tester import _validate_cron, ConfigTestResult

    r = ConfigTestResult()
    _validate_cron({}, r)

    assert not any("ci_generator.py" in s for s in r.suggestions)
    assert any("cron" in s for s in r.suggestions)   # the "not configured" suggestion


# ===========================================================================
# Item 1 step 6 (preflight.py) — branch protection check
# ===========================================================================

def test_check_branch_protection_skips_without_token(monkeypatch):
    """No GITHUB_TOKEN → function returns silently without making any HTTP calls."""
    import preflight
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    with patch("urllib.request.urlopen") as mock_urlopen:
        preflight._check_branch_protection()
    mock_urlopen.assert_not_called()


def test_check_branch_protection_skips_without_repo(monkeypatch):
    import preflight
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    with patch("urllib.request.urlopen") as mock_urlopen:
        preflight._check_branch_protection()
    mock_urlopen.assert_not_called()


def test_check_branch_protection_warns_on_404(monkeypatch, capsys):
    import preflight
    import urllib.error
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REPOSITORY", "org/repo")

    # First call (repo info) returns default_branch; second call (protection) returns 404
    call_count = [0]

    def _fake_urlopen(req, timeout=10):
        call_count[0] += 1
        if call_count[0] == 1:
            resp = MagicMock()
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            resp.read.return_value = json.dumps({"default_branch": "main"}).encode()
            return resp
        raise urllib.error.HTTPError(url="", code=404, msg="Not Found", hdrs=None, fp=None)

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
        preflight._check_branch_protection()

    captured = capsys.readouterr()
    assert "no protection rules" in captured.out.lower() or "WARNING" in captured.out


def test_check_branch_protection_non_fatal_on_exception(monkeypatch):
    import preflight
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REPOSITORY", "org/repo")

    with patch("urllib.request.urlopen", side_effect=RuntimeError("network down")):
        preflight._check_branch_protection()  # must not raise


# ===========================================================================
# Item 2 step 3 (prime.py) — plan_diff parameter
# ===========================================================================

def test_run_prime_accepts_plan_diff_param():
    """run_prime must accept a plan_diff keyword argument without error."""
    import agents.prime as prime_mod
    import inspect
    sig = inspect.signature(prime_mod.run_prime)
    assert "plan_diff" in sig.parameters


def test_run_prime_plan_diff_included_in_message(monkeypatch):
    """When plan_diff is provided, it should appear in the LLM user message."""
    import agents.prime as prime_mod

    captured_messages = {}

    def _fake_complete(system, user, max_tokens=2048):
        captured_messages["user"] = user
        return (
            "```yaml\n"
            "day: 5\n"
            "agent: PRIME\n"
            "story: \"test story\"\n"
            "given: \"state\"\n"
            "when: \"action\"\n"
            "then: \"outcome\"\n"
            "acceptance:\n"
            "  - \"AC1\"\n"
            "out_of_scope:\n"
            "  - \"nothing\"\n"
            "```"
        )

    mock_adapter = MagicMock()
    mock_adapter.complete.side_effect = _fake_complete
    mock_cfg = MagicMock()
    mock_cfg.product_name = "Test"
    mock_cfg.product_description = "Desc"

    with patch("agents.prime.load_config", return_value=mock_cfg), \
         patch("agents.prime.get_analysis_adapter", return_value=mock_adapter), \
         patch("agents.prime._load_context", return_value=""), \
         patch("agents.prime._load_deferred_scope", return_value=""):
        prime_mod.run_prime(
            day=5,
            target="implement feature",
            recent_gates=[],
            plan_diff="stories_added:\n  - story-6: new feature",
        )

    assert "Sprint Re-plan Diff" in captured_messages["user"]
    assert "stories_added" in captured_messages["user"]


def test_run_prime_no_plan_diff_backward_compatible(monkeypatch):
    """run_prime with no plan_diff must work as before."""
    import agents.prime as prime_mod

    def _fake_complete(system, user, max_tokens=2048):
        assert "Sprint Re-plan Diff" not in user
        return (
            "```yaml\n"
            "day: 1\n"
            "agent: PRIME\n"
            "story: \"story\"\n"
            "given: \"g\"\n"
            "when: \"w\"\n"
            "then: \"t\"\n"
            "acceptance:\n  - \"AC1\"\n"
            "out_of_scope:\n  - \"none\"\n"
            "```"
        )

    mock_adapter = MagicMock()
    mock_adapter.complete.side_effect = _fake_complete
    mock_cfg = MagicMock()
    mock_cfg.product_name = "P"
    mock_cfg.product_description = "D"

    with patch("agents.prime.load_config", return_value=mock_cfg), \
         patch("agents.prime.get_analysis_adapter", return_value=mock_adapter), \
         patch("agents.prime._load_context", return_value=""), \
         patch("agents.prime._load_deferred_scope", return_value=""):
        prime_mod.run_prime(day=1, target="t", recent_gates=[])


# ===========================================================================
# Item 2 step 5 (scribe.py) — planning report
# ===========================================================================

def test_write_scribe_report_creates_yaml(tmp_path, monkeypatch):
    import agents.scribe as scribe_mod
    monkeypatch.setattr(scribe_mod, "REPO_ROOT", tmp_path)

    scribe_mod._write_scribe_report(
        docs_written={"product.md", "engineering.md"},
        files_read=["README.md", "pace/plan.yaml"],
        iterations=7,
    )

    report_path = tmp_path / ".pace" / "scribe_report.yaml"
    assert report_path.exists()
    data = yaml.safe_load(report_path.read_text())
    assert set(data["documents_written"]) == {"engineering.md", "product.md"}
    assert data["tool_iterations"] == 7
    assert "README.md" in data["source_files_read"]
    assert set(data["missing_docs"]) == {"security.md", "devops.md"}


def test_write_scribe_report_non_fatal_on_write_error(tmp_path, monkeypatch):
    import agents.scribe as scribe_mod
    # Make .pace/ a file instead of a directory to force a write error
    pace_dir = tmp_path / ".pace"
    pace_dir.write_text("not a directory")
    monkeypatch.setattr(scribe_mod, "REPO_ROOT", tmp_path)
    scribe_mod._write_scribe_report({"product.md"}, [], 1)  # must not raise


def test_run_scribe_tracks_files_read_and_writes_report(tmp_path, monkeypatch):
    """run_scribe must track read_file calls and produce scribe_report.yaml."""
    import agents.scribe as scribe_mod
    from llm.base import ChatResponse, ToolCall

    monkeypatch.setattr(scribe_mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(scribe_mod, "CONTEXT_DIR", tmp_path / ".pace" / "context")

    # Simulate: one read_file call, then four write_doc calls, then end_turn
    responses = [
        ChatResponse(
            stop_reason="tool_use",
            text=None,
            tool_calls=[ToolCall(id="r1", name="read_file", input={"path": "README.md"})],
        ),
        ChatResponse(
            stop_reason="tool_use",
            text=None,
            tool_calls=[
                ToolCall(id="w1", name="write_doc", input={"name": "product.md", "content": "# Product"}),
                ToolCall(id="w2", name="write_doc", input={"name": "engineering.md", "content": "# Eng"}),
                ToolCall(id="w3", name="write_doc", input={"name": "security.md", "content": "# Sec"}),
                ToolCall(id="w4", name="write_doc", input={"name": "devops.md", "content": "# DevOps"}),
            ],
        ),
        ChatResponse(stop_reason="end_turn", text="Done", tool_calls=[]),
    ]
    resp_iter = iter(responses)

    mock_adapter = MagicMock()
    mock_adapter.chat.side_effect = lambda **kw: next(resp_iter)
    mock_cfg = MagicMock()
    mock_cfg.product_name = "P"
    mock_cfg.product_description = "D"
    mock_cfg.docs_dir = None

    with patch("agents.scribe.load_config", return_value=mock_cfg), \
         patch("agents.scribe.get_llm_adapter", return_value=mock_adapter):
        scribe_mod.run_scribe()

    report_path = tmp_path / ".pace" / "scribe_report.yaml"
    assert report_path.exists()
    data = yaml.safe_load(report_path.read_text())
    assert "README.md" in data["source_files_read"]
    assert len(data["documents_written"]) == 4
    assert data["tool_iterations"] >= 2


# ===========================================================================
# Item 1 step 5 (orchestrator.py) — staging CI gate → release PR
# ===========================================================================

def test_try_open_staging_pr_skips_without_commit(monkeypatch):
    """No commit_sha → PR must not be opened."""
    import orchestrator
    mock_ba = MagicMock()
    with patch("orchestrator.load_config") as mock_cfg, \
         patch("orchestrator.subprocess.run") as mock_run:
        mock_cfg.return_value.active_release = MagicMock(name="v2.0")
        orchestrator._try_open_staging_pr(1, "story", "", {"conclusion": "success"})
    mock_ba.create_pull_request.assert_not_called()


def test_try_open_staging_pr_skips_when_ci_failed(monkeypatch):
    import orchestrator
    mock_ba = MagicMock()
    with patch("orchestrator.load_config") as mock_cfg:
        mock_cfg.return_value.active_release = MagicMock(name="v2.0")
        orchestrator._try_open_staging_pr(1, "story", "abc123", {"conclusion": "failure"})
    mock_ba.create_pull_request.assert_not_called()


def test_try_open_staging_pr_skips_without_release_config(monkeypatch):
    import orchestrator
    mock_ba = MagicMock()
    with patch("orchestrator.load_config") as mock_cfg:
        mock_cfg.return_value.active_release = None
        orchestrator._try_open_staging_pr(1, "story", "abc123", {"conclusion": "success"})
    mock_ba.create_pull_request.assert_not_called()


def test_try_open_staging_pr_opens_pr_on_success(tmp_path, monkeypatch):
    import orchestrator

    mock_ba = MagicMock()
    mock_ba.create_pull_request.return_value = "https://github.com/org/repo/pull/42"

    mock_release = MagicMock()
    mock_release.name = "v2.0"

    mock_run_result = MagicMock()
    mock_run_result.returncode = 0
    mock_run_result.stdout = "sprint/v2.0/1\n"

    with patch("orchestrator.load_config") as mock_cfg, \
         patch("orchestrator.subprocess.run", return_value=mock_run_result), \
         patch("branching.get_branching_adapter", return_value=mock_ba):
        mock_cfg.return_value.active_release = mock_release
        orchestrator._try_open_staging_pr(3, "As a user I can login", "abc123", {"conclusion": "success"})

    mock_ba.create_pull_request.assert_called_once()
    call_kwargs = mock_ba.create_pull_request.call_args
    assert call_kwargs.kwargs["base"] == "release/v2.0"
    assert "Day 3" in call_kwargs.kwargs["title"]


def test_try_open_staging_pr_non_fatal_on_exception(monkeypatch):
    import orchestrator

    with patch("orchestrator.load_config", side_effect=RuntimeError("cfg error")):
        orchestrator._try_open_staging_pr(1, "story", "abc123", {"conclusion": "success"})  # must not raise


# ===========================================================================
# Item 4 step 7 (reporter.py) — version update summary in job summary
# ===========================================================================

def test_load_update_status_returns_none_when_absent(tmp_path, monkeypatch):
    import reporter
    monkeypatch.setattr(reporter, "PACE_DIR", tmp_path)
    assert reporter._load_update_status() is None


def test_load_update_status_parses_json(tmp_path, monkeypatch):
    import reporter
    monkeypatch.setattr(reporter, "PACE_DIR", tmp_path)
    status = {"update_available": True, "new_version": "v3.0.0", "current_version": "v2.0.0", "customization_note": "note"}
    (tmp_path / "update_status.yaml").write_text(json.dumps(status))

    result = reporter._load_update_status()
    assert result["new_version"] == "v3.0.0"


def test_write_job_summary_includes_update_section(tmp_path, monkeypatch):
    import reporter

    monkeypatch.setattr(reporter, "PACE_DIR", tmp_path)
    monkeypatch.setattr(reporter, "PLAN_FILE", tmp_path / "plan.yaml")
    monkeypatch.setattr(reporter, "PROGRESS_FILE", tmp_path / "PROGRESS.md")

    # Write a minimal plan.yaml
    (tmp_path / "plan.yaml").write_text(
        yaml.dump({"days": [{"day": 1, "target": "do X"}], "start_date": "2026-03-17"})
    )

    # Write update_status.yaml
    (tmp_path / "update_status.yaml").write_text(json.dumps({
        "update_available": True,
        "new_version": "v3.0.0",
        "current_version": "v2.0.0",
        "customization_note": "some files customized",
    }))

    mock_cfg = MagicMock()
    mock_cfg.product_name = "TestProd"
    mock_cfg.reporter_timezone = "UTC"
    mock_cfg.sprint_duration_days = 1
    mock_cfg.alerts = []
    mock_cfg.notifications = None

    captured_summary = {}

    def _fake_write_job_summary(md):
        captured_summary["md"] = md

    mock_ci = MagicMock()
    mock_ci.write_job_summary.side_effect = _fake_write_job_summary

    with patch("reporter.load_config", return_value=mock_cfg), \
         patch("reporter.load_open_backlog", return_value=[]):
        reporter.write_job_summary(1, "SHIP", None, None, ci=mock_ci)

    assert "PACE Update Available" in captured_summary["md"]
    assert "v3.0.0" in captured_summary["md"]
    assert "some files customized" in captured_summary["md"]


def test_write_job_summary_no_update_section_when_status_absent(tmp_path, monkeypatch):
    import reporter

    monkeypatch.setattr(reporter, "PACE_DIR", tmp_path)
    monkeypatch.setattr(reporter, "PLAN_FILE", tmp_path / "plan.yaml")
    monkeypatch.setattr(reporter, "PROGRESS_FILE", tmp_path / "PROGRESS.md")
    (tmp_path / "plan.yaml").write_text(
        yaml.dump({"days": [{"day": 1, "target": "do X"}], "start_date": "2026-03-17"})
    )

    mock_cfg = MagicMock()
    mock_cfg.product_name = "TestProd"
    mock_cfg.reporter_timezone = "UTC"
    mock_cfg.sprint_duration_days = 1
    mock_cfg.alerts = []
    mock_cfg.notifications = None

    captured_summary = {}

    def _fake_write(md):
        captured_summary["md"] = md

    mock_ci = MagicMock()
    mock_ci.write_job_summary.side_effect = _fake_write

    with patch("reporter.load_config", return_value=mock_cfg), \
         patch("reporter.load_open_backlog", return_value=[]):
        reporter.write_job_summary(1, "SHIP", None, None, ci=mock_ci)

    assert "PACE Update Available" not in captured_summary.get("md", "")


# ===========================================================================
# Item 3 step 6 (anthropic_adapter.py) — per-call retry on token limit
# ===========================================================================

def test_compact_user_message_truncates():
    from llm.anthropic_adapter import _compact_user_message
    long_msg = "x" * 1000
    result = _compact_user_message(long_msg)
    assert len(result) < len(long_msg) + 200   # compacted + notice
    assert "truncated" in result.lower()


def test_compact_user_message_min_length():
    from llm.anthropic_adapter import _compact_user_message
    short_msg = "hi"
    result = _compact_user_message(short_msg)
    assert len(result) >= len(short_msg)  # notice appended


def test_anthropic_adapter_complete_retries_on_context_length():
    """complete() must retry with a compacted message on BadRequestError with 'prompt is too long'."""
    import anthropic
    from llm.anthropic_adapter import AnthropicAdapter

    call_count = [0]

    def _fake_stream(**kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise anthropic.BadRequestError(
                message="prompt is too long",
                response=MagicMock(status_code=400),
                body={"error": {"type": "invalid_request_error", "message": "prompt is too long"}},
            )
        # Second call succeeds — return a context-manager mock
        final = MagicMock()
        final.model = "claude-sonnet-4-6"
        final.usage.input_tokens = 100
        final.usage.output_tokens = 50
        final.content = [MagicMock(text="ok response")]
        stream_cm = MagicMock()
        stream_cm.__enter__ = MagicMock(return_value=stream_cm)
        stream_cm.__exit__ = MagicMock(return_value=False)
        stream_cm.text_stream = []
        stream_cm.get_final_message.return_value = final
        return stream_cm

    adapter = AnthropicAdapter.__new__(AnthropicAdapter)
    adapter._model = "claude-sonnet-4-6"
    adapter._client = MagicMock()
    adapter._client.messages.stream.side_effect = _fake_stream

    with patch("llm.anthropic_adapter.spend_tracker"):
        result = adapter.complete("system", "user " * 500, max_tokens=256)

    assert result == "ok response"
    assert call_count[0] == 2


def test_anthropic_adapter_complete_does_not_retry_other_errors():
    """Non-context-length BadRequestErrors must be re-raised immediately."""
    import anthropic
    from llm.anthropic_adapter import AnthropicAdapter

    def _fake_stream(**kwargs):
        raise anthropic.BadRequestError(
            message="invalid model",
            response=MagicMock(status_code=400),
            body={"error": {"type": "invalid_request_error", "message": "invalid model"}},
        )

    adapter = AnthropicAdapter.__new__(AnthropicAdapter)
    adapter._model = "claude-sonnet-4-6"
    adapter._client = MagicMock()
    adapter._client.messages.stream.side_effect = _fake_stream

    with pytest.raises(anthropic.BadRequestError):
        adapter.complete("system", "user")
