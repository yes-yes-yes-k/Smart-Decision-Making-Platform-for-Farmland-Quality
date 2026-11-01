"""CLI wrapper for the packaged analysis-context migration implementation."""

from framework.migrations.analysis_context import *  # noqa: F401,F403
from framework.migrations.analysis_context import _dialect_ddl_type, main


if __name__ == "__main__":
    raise SystemExit(main())
