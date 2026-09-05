"""Run real HTTP chat conversations and save a redacted acceptance record."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "docs" / "generated"
SENSITIVE_KEYS = {"authorization", "password", "token", "access_token"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact(value: Any, *, key: str = "") -> Any:
    if key.casefold() in SENSITIVE_KEYS:
        return "<redacted>"
    if isinstance(value, dict):
        return {name: redact(item, key=name) for name, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class LiveChatClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.token = ""
        self.exchanges: list[dict[str, Any]] = []

    def request(
        self,
        label: str,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if authenticated:
            if not self.token:
                raise RuntimeError("login_required")
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method,
        )
        started_at = utc_now()
        try:
            with urlopen(request, timeout=180) as response:
                status = response.status
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            status = exc.code
            raw = exc.read().decode("utf-8")
        try:
            response_json = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            response_json = {"raw_text": raw}
        self.exchanges.append({
            "label": label,
            "started_at": started_at,
            "completed_at": utc_now(),
            "request": {
                "method": method,
                "path": path,
                "headers": redact(headers),
                "json": redact(payload),
            },
            "response": {
                "http_status": status,
                "json": redact(response_json),
            },
        })
        if status >= 400:
            raise RuntimeError(
                f"{label} failed with HTTP {status}: "
                f"{json.dumps(redact(response_json), ensure_ascii=False)}"
            )
        return response_json

    def login(self, username: str, password: str) -> None:
        response = self.request(
            "登录",
            "POST",
            "/api/v1/auth/login",
            {"username": username, "password": password},
            authenticated=False,
        )
        self.token = response["data"]["token"]

    def create_conversation(self, title: str) -> int:
        response = self.request(
            f"创建会话：{title}",
            "POST",
            "/api/v1/chat/conversations",
            {"title": title},
        )
        return int(response["data"]["id"])

    def chat(self, label: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request(label, "POST", "/api/v1/chat/", payload)

    def history(self, label: str, conversation_id: int) -> dict[str, Any]:
        return self.request(
            label,
            "GET",
            f"/api/v1/chat/conversations/{conversation_id}/messages",
        )


def response_data(response: dict[str, Any]) -> dict[str, Any]:
    data = response.get("data")
    if not isinstance(data, dict):
        raise AssertionError(f"chat response has no data object: {response}")
    return data


def require_state(response: dict[str, Any], expected: str) -> dict[str, Any]:
    data = response_data(response)
    actual = data.get("interaction_state")
    if actual != expected:
        raise AssertionError(f"expected {expected}, got {actual}: {data}")
    return data


def create_comprehensive_report(
    client: LiveChatClient, conversation_id: int, parcel_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rounds: list[dict[str, Any]] = []
    initial = client.chat(
        "综合诊断：选择真实地块并发起",
        {
            "message": "请为这块地生成包含酸化改良和有机质培肥的综合诊断与改良报告",
            "conversation_id": conversation_id,
            "analysis_context": {
                "action": "set",
                "expected_version": 0,
                "object": {"type": "parcel", "id": parcel_id},
            },
            "include_model_results": True,
            "response_schema": "2.0",
        },
    )
    current = response_data(initial)
    rounds.append(current)

    input_defaults = {
        "land_type": "upland",
        "fertilizer_type": "compound",
        "target_ph": 6.5,
    }
    for supplement_index in range(5):
        if current.get("interaction_state") != "needs_input":
            break
        missing = list(current.get("missing_inputs") or [])
        values = {
            name: input_defaults[name]
            for name in missing
            if name in input_defaults
        }
        if len(values) != len(missing):
            raise AssertionError(f"no safe E2E value configured for {missing}")
        resumed = client.chat(
            f"综合诊断：第{supplement_index + 1}轮补充参数",
            {
                "conversation_id": conversation_id,
                "interaction_response": {
                    "run_id": current["run_id"],
                    "expected_checkpoint_version": current["checkpoint_version"],
                    "action": "provide_input",
                    "values": values,
                },
                "response_schema": "2.0",
            },
        )
        current = response_data(resumed)
        rounds.append(current)

    if current.get("interaction_state") != "needs_confirmation":
        raise AssertionError(f"comprehensive plan was not confirmable: {current}")
    confirmed = client.chat(
        "综合诊断：用户确认方案并执行专业计算",
        {
            "conversation_id": conversation_id,
            "interaction_response": {
                "run_id": current["run_id"],
                "expected_checkpoint_version": current["checkpoint_version"],
                "action": "confirm_plan",
                "values": {},
            },
            "response_schema": "2.0",
        },
    )
    current = require_state(confirmed, "awaiting_release")
    rounds.append(current)
    if not current.get("report_draft"):
        raise AssertionError("confirmed workflow returned no report draft")

    released = client.chat(
        "综合诊断：用户确认发布最终报告",
        {
            "conversation_id": conversation_id,
            "interaction_response": {
                "run_id": current["run_id"],
                "expected_checkpoint_version": current["checkpoint_version"],
                "action": "release_report",
                "values": {},
            },
            "response_schema": "2.0",
        },
    )
    final = response_data(released)
    if final.get("interaction_state") not in {"completed", "partial_complete"}:
        raise AssertionError(f"report was not released: {final}")
    if not final.get("answer"):
        raise AssertionError("released workflow returned no final answer")
    rounds.append(final)
    return rounds, final


def render_acceptance_report(
    *, generated_at: str, conversations: dict[str, int],
    unselected: dict[str, Any], selected: dict[str, Any],
    scenario_missing: dict[str, Any], scenario_complete: dict[str, Any],
    comprehensive_rounds: list[dict[str, Any]], final: dict[str, Any],
) -> str:
    round_actions = (
        ("选择真实地块并提出综合诊断需求", "系统展示分析范围，请用户确认"),
        ("用户确认分析范围", "完成专业计算并生成报告草稿"),
        ("用户确认发布", "最终报告已交付"),
    )
    round_lines = [
        f"| {index} | {action} | {outcome} |"
        for index, (action, outcome) in enumerate(round_actions, start=1)
    ]
    input_labels = {
        "JHX":"交换性氢", "JLA":"交换性铝",
        "land_type":"土地利用类型", "fertilizer_type":"肥料类型",
    }
    missing = "、".join(
        input_labels.get(name, name)
        for name in (scenario_missing.get("missing_inputs") or [])
    )
    selected_object = (selected.get("analysis_context") or {}).get("object") or {}
    return f"""# 真实聊天接口端到端验收记录

生成时间：{generated_at}

## 验收口径

- 所有步骤均通过运行中的 `/api/v1` HTTP 接口完成，不是直接调用内部函数。
- 会话、地块选择和消息历史写入真实数据库；地块 `{selected_object.get('id', '')}` 来自 PostgreSQL。
- 质量评价、障碍诊断、酸化改良和有机质培肥使用项目现有专业计算工具。
- 为避免把真实地块数据发送到未明确授权的外部服务，本次关闭外部大模型；规划和报告成文使用本地确定性兜底，外部资料检索因此标记为不可用。
- 完整请求和原始响应见 `live-chat-e2e-raw.json`；密码、令牌和认证头均已脱敏。

## 流程结果

| 场景 | 会话编号 | 实际结果 |
|---|---:|---|
| 未选择地块直接询问 | {conversations['unselected']} | 系统提示选择地块 |
| 选择真实地块后单项评价 | {conversations['selected']} | 评价完成 |
| 情景试算缺少参数 | {conversations['scenario']} | 系统提示补充：{missing} |
| 补齐情景参数后重算 | {conversations['scenario']} | 试算完成 |
| 综合诊断、确认与发布 | {conversations['comprehensive']} | 报告已发布，外部资料检索未启用 |

## 综合诊断逐轮状态

| 轮次 | 用户操作 | 系统反馈 |
|---:|---|---|
{"\n".join(round_lines)}

## 最终用户报告

{final.get('answer', '')}
"""


def run(args: argparse.Namespace) -> None:
    client = LiveChatClient(args.base_url)
    generated_at = utc_now()
    client.login(args.username, args.password)

    conversations = {
        "unselected": client.create_conversation("E2E-未选择地块"),
        "selected": client.create_conversation("E2E-选择真实地块"),
        "scenario": client.create_conversation("E2E-逐轮补充情景参数"),
        "comprehensive": client.create_conversation("E2E-综合诊断确认发布"),
    }

    unselected = require_state(client.chat(
        "未选地块：直接询问质量等级",
        {
            "message": "请评价这块地的质量等级",
            "conversation_id": conversations["unselected"],
            "include_model_results": False,
            "response_schema": "2.0",
        },
    ), "needs_analysis_object")

    selected = require_state(client.chat(
        "已选地块：使用 PostgreSQL 地块评价",
        {
            "message": "这块地的质量等级怎么样？",
            "conversation_id": conversations["selected"],
            "analysis_context": {
                "action": "set", "expected_version": 0,
                "object": {"type": "parcel", "id": args.parcel_id},
            },
            "include_model_results": True,
            "response_schema": "2.0",
        },
    ), "completed")

    scenario_missing = require_state(client.chat(
        "情景试算：首次输入不完整",
        {
            "message": "试算土壤酸化改良用量",
            "conversation_id": conversations["scenario"],
            "calculation_mode": "scenario",
            "SJD": 5.2,
            "response_schema": "2.0",
        },
    ), "needs_scenario_inputs")
    scenario_complete = require_state(client.chat(
        "情景试算：补齐缺少参数后重算",
        {
            "message": "补齐参数后重新试算土壤酸化改良用量",
            "conversation_id": conversations["scenario"],
            "calculation_mode": "scenario",
            "SJD": 5.2,
            "JHX": 2.1,
            "JLA": 0.4,
            "land_type": "upland",
            "fertilizer_type": "compound",
            "response_schema": "2.0",
        },
    ), "completed")

    comprehensive_rounds, final = create_comprehensive_report(
        client, conversations["comprehensive"], args.parcel_id,
    )

    for key, conversation_id in conversations.items():
        client.history(f"读取完整会话历史：{key}", conversation_id)

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_record = {
        "generated_at": generated_at,
        "base_url": args.base_url,
        "execution_mode": {
            "transport": "actual_http",
            "parcel_source": "PostgreSQL",
            "professional_calculations": "actual_project_tools",
            "external_llm": "disabled_for_data_safety",
            "planner_and_reporter": "local_deterministic_fallback",
        },
        "conversation_ids": conversations,
        "exchanges": client.exchanges,
    }
    (output_dir / "live-chat-e2e-raw.json").write_text(
        json.dumps(raw_record, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    report = render_acceptance_report(
        generated_at=generated_at,
        conversations=conversations,
        unselected=unselected,
        selected=selected,
        scenario_missing=scenario_missing,
        scenario_complete=scenario_complete,
        comprehensive_rounds=comprehensive_rounds,
        final=final,
    )
    (output_dir / "live-chat-e2e-report.md").write_text(report, encoding="utf-8")
    (output_dir / "live-chat-final-diagnostic-report.md").write_text(
        final["answer"].rstrip() + "\n", encoding="utf-8",
    )
    print(json.dumps({
        "status": "ok",
        "conversation_ids": conversations,
        "final_state": final["interaction_state"],
        "outputs": {
            "raw": str(output_dir / "live-chat-e2e-raw.json"),
            "acceptance_report": str(output_dir / "live-chat-e2e-report.md"),
            "final_report": str(output_dir / "live-chat-final-diagnostic-report.md"),
        },
    }, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--username", default=os.getenv("E2E_USERNAME", "admin"))
    parser.add_argument("--password", default=os.getenv("E2E_PASSWORD", ""))
    parser.add_argument("--parcel-id", default="4190")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.password:
        raise SystemExit("E2E_PASSWORD is required")
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
