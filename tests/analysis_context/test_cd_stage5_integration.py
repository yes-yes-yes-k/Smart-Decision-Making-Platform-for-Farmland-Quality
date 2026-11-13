"""Stage 5 rehearsals use real PostgreSQL flux data and local chat records."""
import csv
import io
import json
import os

import pytest
from sqlalchemy import text

from test_cd_flux_v2 import csv_data, pg, row

from framework.api.routes import chat as chat_routes
from framework.api.routes.cd_flux import cd_flux_bp
from framework.config import Config
from framework.domain.other_models import cd_flux_v2 as flux
from framework.domain.other_models import heavy_metal_cd_visualization as viz
from framework.llm.service import llm_service
from framework.models import ParcelInfo, db

from .test_chat_api import _ContextService


COMPARE = "请比较当前地块 2023 年与 2024 年的自有镉净通量。"
QUERY = "请查询当前地块 2024 年的自有镉净通量统计。"
TRIAL = "请用当前地块 2024 年自有镉通量的已记录参数做一次试算。"
MODIFY = "企业输入改为 3 g/ha/a，重新试算镉通量。"
OLD_QUERY = "请查询 2024 年梅花镇的作物镉预测统计。"


@pytest.fixture
def scenario(chat_app, auth_header, parcel_context, pg, tmp_path, monkeypatch):
    chat_app.config["CD_CHAT_ARTIFACT_ROOT"] = tmp_path / "attachments"
    chat_app.register_blueprint(cd_flux_bp, url_prefix="/api/v1/cd-flux")
    monkeypatch.setattr(Config, "FUNCTION_CALLING_ENABLED", True)
    monkeypatch.setattr(chat_routes.chat_request_service, "_context_service", _ContextService(parcel_context))
    with chat_app.app_context():
        xmin, ymin, xmax, ymax = viz.load_template()["bounds"]
        db.session.add(ParcelInfo(parcel_id="P001", centroid_lon=(xmin + xmax) / 2, centroid_lat=(ymin + ymax) / 2))
        db.session.commit()
    client = chat_app.test_client()
    prefix = "/api/v1/cd-flux/v2"
    rows = [{**row(year, "native"), "parcel_id": "P001", "enterprise_input": enterprise}
            for year, enterprise in [(2023, 0), (2024, 2)]]
    upload = client.post(prefix + "/inputs/import", headers=auth_header,
                         data={"file": (io.BytesIO(csv_data(rows)), "synthetic-flux.csv")})
    assert upload.status_code == 200
    assert upload.get_json()["data"]["imported"] == 2
    calculated = client.post(prefix + "/calculate", headers=auth_header, json={"source": "native"})
    assert calculated.status_code == 200
    assert calculated.get_json()["data"]["calculated"] == 2
    cid = client.post("/api/v1/chat/conversations", json={}, headers=auth_header).get_json()["data"]["id"]
    return client, auth_header, cid, pg


def send(scenario, question, *, stream):
    client, headers, cid, _ = scenario
    endpoint = "/api/v1/chat/stream" if stream else "/api/v1/chat/"
    response = client.post(endpoint, headers=headers,
                           json={"conversation_id": cid, "message": question, "include_model_results": True})
    assert response.status_code == 200
    if stream:
        events = [json.loads(line[6:]) for line in response.get_data(as_text=True).splitlines()
                  if line.startswith("data: ")]
        assert events[-1]["event"] == "done"
        return events[-1]["data"]
    return response.get_json()["data"]


def assert_comparison(result):
    assert result["status"] == "ok", result.get("status")
    values = {entry["coverage"]["year"]: entry["groups"][0]["statistics"]["均值"] for entry in result["years"]}
    assert values == {2023: 8, 2024: 10}


@pytest.mark.parametrize("stream", [False, True])
def test_import_calculate_chat_and_attachments(scenario, monkeypatch, stream):
    def deterministic_model(*, prompt, tools, default_args, **kwargs):
        question = prompt.split("用户问题：", 1)[1]
        query = {"operation": "flux_compare", "years": [2023, 2024]} if question == COMPARE else {
            "operation": "flux", "year": 2024,
        }
        payload = tools[0].invoke({**query, "source": "native", "field": "net_cd", **default_args})
        return {"success": True, "content": "Cd 通量", "tool_results": {tools[0].name: payload}}

    monkeypatch.setattr(llm_service, "generate_with_tools", deterministic_model)
    assert_comparison(send(scenario, COMPARE, stream=stream)["cd_conversation"])
    result = send(scenario, QUERY, stream=stream)["cd_conversation"]
    assert result["groups"][0]["statistics"]["均值"] == 10
    assert result["calculation_version"] == flux.VERSION
    chart_response = send(scenario, "画成图", stream=stream)
    assert "cd_artifacts" in chart_response, chart_response.get("cd_conversation", {}).get("reason")
    charts = chart_response["cd_artifacts"]
    exported = send(scenario, "下载刚才的数据", stream=stream)["cd_artifacts"]
    assert charts["scope"]["year"] == exported["scope"]["year"] == 2024
    assert charts["metadata"]["records"] == 1
    client, headers, _, connection = scenario
    for item in charts["attachments"]:
        image = client.get(item["url"], headers=headers)
        assert image.mimetype == "image/jpeg" and image.data.startswith(b"\xff\xd8")
        image.close()
    csv_file = client.get(exported["attachments"][0]["url"], headers=headers)
    entries = list(csv.DictReader(io.StringIO(csv_file.data.decode("utf-8-sig"))))
    assert len(entries) == 1
    assert entries[0]["accounting_year"] == "2024"
    assert float(entries[0]["net_cd_g_ha_a"]) == 10
    assert entries[0]["calculation_version"] == flux.VERSION
    csv_file.close()
    assert connection.execute(text("SELECT count(*) FROM cd_flux_output_v2")).scalar_one() == 2


@pytest.mark.skipif(os.getenv("CD_LIVE_LLM") != "1", reason="explicit live-provider rehearsal")
@pytest.mark.parametrize("stream", [False, True])
def test_live_provider_cd_conversation(scenario, stream):
    assert llm_service.is_available(), "Configured model client unavailable"
    assert_comparison(send(scenario, COMPARE, stream=stream)["cd_conversation"])
    trial = send(scenario, TRIAL, stream=stream)["cd_conversation"]
    assert trial.get("net_cd") == 10, trial.get("status")
    modified = send(scenario, MODIFY, stream=stream)["cd_conversation"]
    assert modified.get("net_cd") == 11, modified.get("status")
    previous_prediction = send(scenario, OLD_QUERY, stream=stream)["cd_conversation"]
    assert previous_prediction["status"] == "unsupported_year"
    assert scenario[3].execute(text("SELECT count(*) FROM cd_flux_output_v2")).scalar_one() == 2
