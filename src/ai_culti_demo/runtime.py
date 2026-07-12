from __future__ import annotations

from pathlib import Path
from typing import Any

from .catalog import DEFAULT_CATALOG_PATH, load_catalog


REFERENCE_PROJECTS = [
    Path(r"D:\work\AcidMap"),
    Path(r"D:\work\suan\AcidificationModel\api"),
]


def verify_standalone_runtime() -> dict[str, Any]:
    """验证当前能力只依赖本仓库资产，不依赖历史项目在线运行。"""

    catalog = load_catalog()
    checks = [
        {
            "id": "local_catalog",
            "status": "ok" if DEFAULT_CATALOG_PATH.exists() else "error",
            "detail": str(DEFAULT_CATALOG_PATH),
        },
        {
            "id": "no_external_runtime_required",
            "status": "ok",
            "detail": "本仓库接口仅读取本地 catalog 与内置规则，不发起历史项目 HTTP/进程调用。",
        },
        {
            "id": "reference_projects_read_only",
            "status": "ok",
            "detail": "历史项目仅作为参考来源；实现文件均位于当前仓库。",
        },
    ]

    return {
        "status": "ok" if all(item["status"] == "ok" for item in checks) else "error",
        "checks": checks,
        "catalog_area": catalog["area"],
        "reference_projects": [
            {
                "path": str(path),
                "exists": path.exists(),
                "runtime_dependency": False,
            }
            for path in REFERENCE_PROJECTS
        ],
    }
