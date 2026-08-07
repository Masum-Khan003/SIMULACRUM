"""
Verifies the CI workflow file itself (§22) -- structural sanity checks
against real assumptions this project depends on (Redis service
present, correct install command, import-order check present), so the
workflow file can't silently drift from what the project actually
needs without a test catching it.
"""
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")


@pytest.fixture
def workflow():
    path = Path(__file__).parent.parent.parent / ".github" / "workflows" / "ci.yml"
    with open(path) as f:
        return yaml.safe_load(f)


def test_workflow_has_redis_service(workflow):
    services = workflow["jobs"]["test"].get("services", {})
    assert "redis" in services, "CI must provision a real Redis service (test_redis_session_store.py needs it)"


def test_workflow_sets_redis_url_env(workflow):
    env = workflow["jobs"]["test"].get("env", {})
    assert "SIMULACRUM_REDIS_URL" in env, (
        "CI must set SIMULACRUM_REDIS_URL -- Settings has no default (§00b), tests will fail without it"
    )


def test_workflow_runs_import_order_check(workflow):
    steps = workflow["jobs"]["test"]["steps"]
    step_commands = [s.get("run", "") for s in steps]
    assert any("check_import_order.py" in cmd for cmd in step_commands), (
        "CI must run the import-order check (finding 003) as a dedicated step"
    )


def test_workflow_runs_pytest(workflow):
    steps = workflow["jobs"]["test"]["steps"]
    step_commands = [s.get("run", "") for s in steps]
    assert any("pytest" in cmd for cmd in step_commands)


def test_workflow_does_not_install_ml_extra_in_main_step(workflow):
    """
    Verifies the fast, lightweight CI path stays lightweight -- the
    core install step should NOT pull in [ml] (torch), matching this
    project's own repeatedly-verified fresh-venv-without-ml property.
    """
    steps = workflow["jobs"]["test"]["steps"]
    install_steps = [s for s in steps if "Install" in s.get("name", "")]
    assert len(install_steps) > 0
    for step in install_steps:
        assert "[ml]" not in step.get("run", ""), (
            "Main CI install step should stay lightweight (no torch) -- matches "
            "this project's verified fresh-venv-without-ml property"
        )
