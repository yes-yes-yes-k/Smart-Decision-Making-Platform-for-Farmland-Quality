from framework.agents.workflows.comprehensive.checkpointing import (
    normalize_postgres_uri,
    workflow_thread_config,
)
from framework.config import Config


def test_comprehensive_workflow_defaults_off():
    assert Config.COMPREHENSIVE_WORKFLOW_MODE == "off"


def test_psycopg2_sqlalchemy_uri_is_normalized_for_psycopg3():
    uri = "postgresql+psycopg2://u:p@db:5432/app"
    assert normalize_postgres_uri(uri) == "postgresql://u:p@db:5432/app"


def test_workflow_thread_config_is_run_scoped():
    assert workflow_thread_config(12, "run-7") == {
        "configurable": {
            "thread_id": "chat:12:comprehensive:run-7",
        }
    }


def test_workflow_thread_config_requires_conversation_and_run_id():
    import pytest

    with pytest.raises(ValueError, match="conversation_id and run_id are required"):
        workflow_thread_config(0, "run-7")
    with pytest.raises(ValueError, match="conversation_id and run_id are required"):
        workflow_thread_config(12, " ")


def test_checkpointer_runtime_reuses_saver_and_closes_once(monkeypatch):
    from framework.agents.workflows.comprehensive import checkpointing

    class FakeSaver:
        def __init__(self):
            self.setup_calls = 0

        def setup(self):
            self.setup_calls += 1

    class FakeContextManager:
        def __init__(self):
            self.saver = FakeSaver()
            self.enter_calls = 0
            self.exit_calls = 0

        def __enter__(self):
            self.enter_calls += 1
            return self.saver

        def __exit__(self, exc_type, exc_value, traceback):
            self.exit_calls += 1

    context_manager = FakeContextManager()

    class FakePostgresSaver:
        @staticmethod
        def from_conn_string(uri):
            assert uri == "postgresql://u:p@db:5432/app"
            return context_manager

    monkeypatch.setattr(checkpointing, "PostgresSaver", FakePostgresSaver)
    runtime = checkpointing.PostgresCheckpointerRuntime(
        "postgresql+psycopg2://u:p@db:5432/app"
    )

    assert runtime.start() is context_manager.saver
    assert runtime.start() is context_manager.saver
    assert context_manager.enter_calls == 1
    assert context_manager.saver.setup_calls == 0

    runtime.close()
    runtime.close()
    assert context_manager.exit_calls == 1


def test_checkpointer_runtime_closes_and_resets_when_setup_fails(monkeypatch):
    from framework.agents.workflows.comprehensive import checkpointing
    import pytest

    class FakeSaver:
        def setup(self):
            raise RuntimeError("setup failed")

    class FakeContextManager:
        def __init__(self):
            self.saver = FakeSaver()
            self.enter_calls = 0
            self.exit_calls = 0

        def __enter__(self):
            self.enter_calls += 1
            return self.saver

        def __exit__(self, exc_type, exc_value, traceback):
            self.exit_calls += 1

    context_manager = FakeContextManager()

    class FakePostgresSaver:
        @staticmethod
        def from_conn_string(uri):
            return context_manager

    monkeypatch.setattr(checkpointing, "PostgresSaver", FakePostgresSaver)
    runtime = checkpointing.PostgresCheckpointerRuntime(
        "postgresql://u:p@db:5432/app", auto_setup=True
    )

    with pytest.raises(RuntimeError, match="setup failed"):
        runtime.start()

    assert context_manager.enter_calls == 1
    assert context_manager.exit_calls == 1
    assert runtime._context_manager is None
    assert runtime._saver is None


def test_enabled_app_initializes_checkpointer_and_allows_repeated_close(monkeypatch):
    from flask import Flask
    from framework.agents.workflows.comprehensive import checkpointing
    from framework.api.app import init_comprehensive_checkpointer

    class FakeSaver:
        pass

    class FakeContextManager:
        def __init__(self):
            self.saver = FakeSaver()
            self.exit_calls = 0

        def __enter__(self):
            return self.saver

        def __exit__(self, exc_type, exc_value, traceback):
            self.exit_calls += 1

    context_manager = FakeContextManager()

    class FakePostgresSaver:
        @staticmethod
        def from_conn_string(uri):
            assert uri == "postgresql://u:p@db:5432/app"
            return context_manager

    monkeypatch.setattr(checkpointing, "PostgresSaver", FakePostgresSaver)
    app = Flask(__name__)
    app.config.update(
        COMPREHENSIVE_WORKFLOW_MODE="enabled",
        LANGGRAPH_CHECKPOINT_URI="postgresql://u:p@db:5432/app",
        LANGGRAPH_CHECKPOINT_AUTO_SETUP=False,
    )

    init_comprehensive_checkpointer(app)

    runtime = app.extensions["comprehensive_checkpointer_runtime"]
    assert app.extensions["comprehensive_checkpointer"] is context_manager.saver
    runtime.close()
    runtime.close()
    assert context_manager.exit_calls == 1


def test_off_and_shadow_modes_do_not_connect_checkpointer(monkeypatch):
    from flask import Flask
    import framework.api.app as app_module

    def fail_if_constructed(*args, **kwargs):
        raise AssertionError("checkpointer must remain disconnected")

    monkeypatch.setattr(
        app_module, "PostgresCheckpointerRuntime", fail_if_constructed
    )
    for mode in ("off", "shadow"):
        app = Flask(__name__)
        app.config.update(COMPREHENSIVE_WORKFLOW_MODE=mode)
        app_module.init_comprehensive_checkpointer(app)
        assert "comprehensive_checkpointer_runtime" not in app.extensions
