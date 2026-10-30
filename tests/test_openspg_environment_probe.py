from scripts.probe_openspg_environment import evaluate_probe


def _checks(**overrides):
    checks = {
        "docker_cli": {"available": True, "version": "Docker 1"},
        "docker_compose": {"available": True, "version": "Compose 1"},
        "python_modules": {"kag": True, "knext": True},
        "openspg_server_configured": True,
        "model_provider_configured": True,
    }
    checks.update(overrides)
    return checks


def test_openspg_probe_is_ready_only_when_all_external_requirements_exist():
    ready, blockers = evaluate_probe(_checks())

    assert ready is True
    assert blockers == []


def test_openspg_probe_reports_reproducible_missing_dependencies():
    ready, blockers = evaluate_probe(_checks(
        docker_cli={"available": False, "version": None},
        python_modules={"kag": False, "knext": False},
        openspg_server_configured=False,
    ))

    assert ready is False
    assert blockers == [
        "docker_cli_missing",
        "kag_module_missing",
        "knext_module_missing",
        "openspg_server_not_configured",
    ]
