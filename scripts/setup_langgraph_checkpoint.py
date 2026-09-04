from framework.agents.workflows.comprehensive.checkpointing import (
    PostgresCheckpointerRuntime,
)
from framework.config import Config


def main() -> int:
    runtime = PostgresCheckpointerRuntime(
        Config.LANGGRAPH_CHECKPOINT_URI,
        auto_setup=True,
    )
    try:
        runtime.start()
    finally:
        runtime.close()
    print("LangGraph checkpoint schema is ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
