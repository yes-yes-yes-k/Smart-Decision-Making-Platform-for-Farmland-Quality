import json

import pytest

from framework.agents.cd_conversation import query_cd
from framework.api.routes import chat as chat_routes
from framework.config import Config
from framework.domain.other_models import heavy_metal_cd
from framework.domain.other_models.cd_parameter_contract import FIELD_DEFINITIONS
from framework.llm.service import llm_service
from framework.models import CdTrial, Conversation, Message, db
from framework.models.thematic_model import SpatialRegionCatalog

from .test_chat_api import _ContextService


@pytest.mark.parametrize("stream", [False, True])
def test_cd_queries_prediction_and_save_at_chat_entry(
    chat_app, auth_header, parcel_context, monkeypatch, stream,
):
    from framework.api.services import farmland_statistics
    from framework.domain.other_models import heavy_metal_cd_db

    monkeypatch.setattr(Config, "FUNCTION_CALLING_ENABLED", True)
    from framework.domain.other_models import cd_flux_v2
    monkeypatch.setattr(cd_flux_v2,'statistics',lambda **kwargs:{'has_data':False,'groups':[]})
    monkeypatch.setattr(chat_routes.chat_request_service, "_context_service", _ContextService(parcel_context))
    monkeypatch.setattr(farmland_statistics, "get_parcel_summary", lambda *args, **kwargs: {
        "metric": {"value": None},
    })
    monkeypatch.setattr(heavy_metal_cd_db, "build_inputs", lambda *args, **kwargs: {
        "status": "no_data", "data": {}, "provenance": {}, "missing_fields": [],
    })
    fields = next(model["input_fields"] for model in heavy_metal_cd.available_models()
                  if model["model_id"] == "crop_cd")
    parameters = dict.fromkeys((field for field in fields if field != "solution"), 1.0)
    units = {field: FIELD_DEFINITIONS[field][1] for field in parameters}

    def fake_llm(*, prompt, tools, default_args, **kwargs):
        question = prompt.split("用户问题：", 1)[1]
        operation = {"查询土壤镉": "soil", "查询镉模型参数": "parameters", "查询镉通量": "flux"}.get(question, "predict")
        inputs = {"parameters": parameters, "parameter_units": units} if question == "试算作物镉" else {}
        payload = tools[0].invoke({"operation": operation, "model_id": "crop_cd", **default_args, **inputs})
        return {"success": True, "content": "Cd 服务结果", "tool_results": {tools[0].name: payload}}

    monkeypatch.setattr(llm_service, "generate_with_tools", fake_llm)
    client = chat_app.test_client()
    conversation_id = client.post("/api/v1/chat/conversations", json={}, headers=auth_header).get_json()["data"]["id"]

    def send(message):
        body = {"message": message, "include_model_results": True, "conversation_id": conversation_id}
        response = client.post("/api/v1/chat/stream" if stream else "/api/v1/chat/", json=body, headers=auth_header)
        assert response.status_code == 200
        if stream:
            events = [json.loads(line[6:]) for line in response.get_data(as_text=True).splitlines()
                      if line.startswith("data: ")]
            assert events[-1]["event"] == "done", events
            data = events[-1]["data"]
        else:
            data = response.get_json()["data"]
        return data

    assert "没有可用" in send("查询土壤镉")["answer"]
    assert "没有可用" in send("查询镉通量")["answer"]
    assert len(send("查询镉模型参数")["cd_conversation"]["parameter_definitions"]) == 14
    assert send("试算作物镉")["cd_conversation"]["missing_fields"] == ["solution"]
    assert "先完成计算" in send("保存这次试算结果")["answer"]
    assert send("同意使用训练集中位数")["cd_conversation"]["status"] == "degraded"
    saved = send("保存这次试算结果")["answer"]
    assert "已保存" in saved
    assert send("保存这次试算结果")["answer"] == saved
    with chat_app.app_context():
        trial = CdTrial.query.one()
        assert trial.payload["result"]["status"] == "degraded"
        assert trial.payload["result"]["input_sources"]["solution"]["source"] == "accepted_training_median"


@pytest.mark.parametrize('stream',[False,True])
def test_flux_trial_multiturn_and_save(chat_app,auth_header,parcel_context,monkeypatch,stream):
    from framework.domain.other_models import cd_flux_v2 as flux
    from framework.agents.cd_flux_conversation import parse_acceptance
    monkeypatch.setattr(Config,'FUNCTION_CALLING_ENABLED',True)
    monkeypatch.setattr(chat_routes.chat_request_service,'_context_service',_ContextService(parcel_context))
    monkeypatch.setattr(flux,'select_inputs',lambda **kwargs:([],{}))
    params=dict(zip(flux.INPUTS+flux.OUTPUTS,[10,5,3,2,1,2,3,4]),initial_cd=600,soil_depth_m=.2)
    def fake_llm(*,prompt,tools,default_args,**kwargs):
        question=prompt.split('用户问题：',1)[1]
        inputs={'year':2024,'parameters':params,'parameter_units':flux.UNITS} if question=='镉通量试算' else {}
        if question=='企业输入改为3':
            inputs={'parameters':{'enterprise_input':3},'parameter_units':{'enterprise_input':'g/ha/a'}}
        if question=='查询镉通量':
            return {'success':True,'content':'查询','tool_results':{tools[0].name:{'status':'no_data','draft':{'calculation_type':'flux'}}}}
        payload=tools[0].invoke({'operation':'flux_predict',**default_args,**inputs})
        return {'success':True,'content':'通量结果','tool_results':{tools[0].name:payload}}
    monkeypatch.setattr(llm_service,'generate_with_tools',fake_llm)
    client=chat_app.test_client()
    cid=client.post('/api/v1/chat/conversations',json={},headers=auth_header).get_json()['data']['id']
    def send(message):
        response=client.post('/api/v1/chat/stream' if stream else '/api/v1/chat/',headers=auth_header,
                             json={'conversation_id':cid,'message':message,'include_model_results':True})
        assert response.status_code==200
        if stream:
            events=[json.loads(line[6:]) for line in response.get_data(as_text=True).splitlines() if line.startswith('data: ')]
            assert events[-1]['event']=='done'
            return events[-1]['data']
        return response.get_json()['data']
    assert send('镉通量试算')['cd_conversation']['end_cd'] is None
    result=send('同意使用通量默认值：bulk_density_g_cm3')['cd_conversation']
    assert result['net_cd']==10 and result['end_cd'] is not None
    saved=send('保存这次试算结果')['answer']
    assert '已保存' in saved and send('保存这次试算结果')['answer']==saved
    assert send('企业输入改为3')['cd_conversation']['net_cd']==11
    send('保存这次试算结果')
    send('查询镉通量')
    assert '先完成计算' in send('保存这次试算结果')['answer']
    with chat_app.app_context():
        assert CdTrial.query.count()==2
        for record in CdTrial.query.all():
            assert record.payload['calculation_type']=='flux'
            assert record.payload['schema_version']==2


def test_late_assistant_response_does_not_replace_newer_draft(
    chat_app, parcel_context, monkeypatch,
):
    service = chat_routes.chat_request_service
    monkeypatch.setattr(service, "_context_service", _ContextService(parcel_context))
    with chat_app.app_context():
        user_id = chat_app.config["TASK9_USER_ID"]
        conversation = Conversation(user_id=user_id)
        db.session.add(conversation)
        db.session.flush()
        for revision in (2, 1):
            db.session.add(Message(conversation_id=conversation.id, role="assistant", content="试算",
                                   analysis_context_snapshot={"cd_draft": {"revision": revision}}))
        db.session.commit()
        prepared = service.prepare(user_id=user_id, body={"conversation_id": conversation.id, "message": "重算"})
        assert prepared.orchestrator_request["_cd_draft"]["revision"] == 2


def test_cd_query_requires_disambiguation_for_shared_region_name_and_model(chat_app):
    with chat_app.app_context():
        db.session.add_all([
            SpatialRegionCatalog(object_type="township", object_id=identifier, display_name="同名镇",
                                 source="test", parent_object_id=parent, enabled=True)
            for identifier, parent in [("T1", "C1"), ("T2", "C2")]
        ])
        db.session.commit()
        result = query_cd("soil", region_name="同名镇")
        assert result["status"] == "needs_analysis_object"
        assert {candidate[1] for candidate in result["candidates"]} == {"T1", "T2"}
        assert query_cd("results", region_type="township", region_id="T1")["status"] == "needs_input"
