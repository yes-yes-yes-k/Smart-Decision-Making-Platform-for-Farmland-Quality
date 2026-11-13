import json

import pytest
from flask_jwt_extended import create_access_token

from framework.api.routes import chat as chat_routes
from framework.api.routes.cd_flux import cd_flux_bp
from framework.api.routes.heavy_metal_cd import heavy_metal_cd_bp
from framework.api.services import cd_chat_artifacts as artifacts
from framework.config import Config
from framework.domain.other_models import cd_flux_v2, heavy_metal_cd_visualization as viz
from framework.llm.service import llm_service
from framework.models import Conversation, Message, db

from .test_chat_api import _ContextService


@pytest.mark.parametrize("stream", [False, True])
def test_export_followup_history_and_authorization(chat_app, auth_header, parcel_context, tmp_path, monkeypatch, stream):
    chat_app.config["CD_CHAT_ARTIFACT_ROOT"] = tmp_path / "private"
    chat_app.register_blueprint(cd_flux_bp, url_prefix="/api/v1/cd-flux")
    chat_app.register_blueprint(heavy_metal_cd_bp, url_prefix="/api/v1/heavy-metal-cd")
    monkeypatch.setattr(viz, "VISUALIZATION_ROOT", tmp_path / "legacy")
    monkeypatch.setattr(Config, "FUNCTION_CALLING_ENABLED", True)
    monkeypatch.setattr(chat_routes.chat_request_service, "_context_service", _ContextService(parcel_context))
    monkeypatch.setattr(cd_flux_v2, "statistics", lambda **kwargs: {"has_data":True,"groups":[]})
    calls = []

    def query_rows(**scope):
        calls.append(scope)
        return {"rows":[{"source":"native","accounting_year":2024,"parcel_id":scope["parcel_id"],
                         "sample_id":"=1+2","output":{"net_cd":10}}]}

    monkeypatch.setattr(cd_flux_v2, "results", query_rows)

    def fake_llm(*, tools, default_args, **kwargs):
        result = tools[0].invoke({"operation":"flux","source":"native","year":2024,**default_args})
        return {"success":True,"content":"通量结果","tool_results":{tools[0].name:result}}

    monkeypatch.setattr(llm_service, "generate_with_tools", fake_llm)
    client = chat_app.test_client()
    cid = client.post("/api/v1/chat/conversations",json={},headers=auth_header).get_json()["data"]["id"]

    def send(message):
        path = "/api/v1/chat/stream" if stream else "/api/v1/chat/"
        response = client.post(path,json={"conversation_id":cid,"message":message},headers=auth_header)
        assert response.status_code == 200
        if stream:
            return [json.loads(line[6:])["data"] for line in response.get_data(as_text=True).splitlines()
                    if line.startswith("data: ") and json.loads(line[6:]).get("event") == "done"][-1]
        return response.get_json()["data"]

    send("查询2024年自有镉通量")
    first = send("下载刚才的数据")["cd_artifacts"]
    assert first == send("导出CSV")["cd_artifacts"]
    assert len(calls) == 1 and calls[0]["year"] == 2024 and calls[0]["source"] == "native"
    file = first["attachments"][0]
    url = file["url"]
    aid = file["artifact_id"]
    response = client.get(url,headers=auth_header)
    assert response.status_code == 200 and "'=1+2" in response.get_data(as_text=True)
    assert response.headers["Cache-Control"] == "private, no-store"
    response.close()
    assert client.get(url).status_code == 401
    with chat_app.app_context():
        other = {"Authorization":"Bearer " + create_access_token(identity="999")}
    assert client.get(url,headers=other).status_code == 404
    assert client.get(url.replace("/csv","/raster"),headers=auth_header).status_code == 404
    assert client.get(url.replace(aid,"invalid"),headers=auth_header).status_code == 404
    listing = f"/api/v1/chat/conversations/{cid}/attachments"
    assert client.get(listing,headers=other).status_code == 404
    assert client.get(listing,headers=auth_header).get_json()["data"] == [first]
    for legacy in (f"/api/v1/cd-flux/artifacts/{aid}/map",
                   f"/api/v1/heavy-metal-cd/visualization/artifacts/{aid}/map"):
        assert client.get(legacy,headers=auth_header).status_code == 404
    history = client.get(f"/api/v1/chat/conversations/{cid}/messages",headers=auth_header).get_json()["data"]
    assert history[-1]["cd_artifacts"] == first
    assert client.delete(f"/api/v1/chat/conversations/{cid}",headers=auth_header).status_code == 200
    assert client.get(url,headers=auth_header).status_code == 404
    assert not list((tmp_path / "private").rglob("manifest.json"))


def _query_record(chat_app, tmp_path):
    chat_app.config["CD_CHAT_ARTIFACT_ROOT"] = tmp_path / "private"
    uid = chat_app.config["TASK9_USER_ID"]
    conversation = Conversation(user_id=uid)
    db.session.add(conversation)
    db.session.flush()
    message = Message(conversation_id=conversation.id,role="user",content="Cd查询")
    db.session.add(message)
    db.session.commit()
    return uid, conversation.id, message.id


def test_prediction_chart_tiff_truncation_and_atomic_retry(chat_app,tmp_path,monkeypatch):
    from rasterio import Affine
    points = [("P1",1.,1.,.16),("P2",2.,2.,.22),("P3",2.5,1.5,.30),("P4",3.,2.,.19)]
    monkeypatch.setattr(artifacts,"_prediction_points",lambda scope:points)
    monkeypatch.setattr(artifacts,"MAX_POINTS",3)
    crs = viz.load_template()["crs"]
    monkeypatch.setattr(viz,"load_template",lambda:{"width":4,"height":4,"transform":Affine(1,0,0,0,-1,4),
                                                   "bounds":(0,0,4,4),"crs":crs,"nodata":None})
    monkeypatch.setattr(viz,"_region_boundary",lambda *args:None)
    scope = {"category":"prediction","model_id":"crop_cd","source":"all","period":"未知"}
    with chat_app.app_context():
        ids = _query_record(chat_app,tmp_path)
        render = viz._render_histogram
        with monkeypatch.context() as patch:
            def fail(*args, **kwargs):
                raise OSError("render failure")
            patch.setattr(viz,"_render_histogram",fail)
            with pytest.raises(OSError):
                artifacts.generate(*ids,scope,raster=True)
        assert not list((tmp_path / "private").rglob("*.jpg"))
        assert viz._render_histogram is render
        result = artifacts.generate(*ids,scope,raster=True)
        assert {a["kind"] for a in result["attachments"]} == {"map","histogram","raster"}
        assert result["metadata"]["truncated"] and result["metadata"]["used_points"] == 3
        assert result["metadata"]["interpolation_effective"] is None
        assert result == artifacts.generate(*ids,scope,raster=True)
        for item in result["attachments"]:
            path, mime = artifacts.download(*ids[:2],item["artifact_id"],item["kind"])
            assert path.stat().st_size > 0 and mime == item["mime_type"]
        with monkeypatch.context() as patch:
            patch.setattr(artifacts,"_prediction_points",lambda scope:[("outside",100.,100.,.2)])
            with pytest.raises(viz.CdVisualizationError,match="no_data_in_template"):
                artifacts.generate(*ids,scope,interpolation="nearest")


def test_legacy_unowned_and_cross_user_access(chat_app,auth_header,tmp_path,monkeypatch):
    chat_app.register_blueprint(heavy_metal_cd_bp,url_prefix="/api/v1/heavy-metal-cd")
    monkeypatch.setattr(viz,"VISUALIZATION_ROOT",tmp_path)
    for key,owner in (("a",None),("b","999"),("c",str(chat_app.config["TASK9_USER_ID"]))):
        path = tmp_path / "crop_cd" / (key * 32)
        path.mkdir(parents=True)
        (path / "meta.json").write_text(json.dumps({"artifact_id":key*32,"owner_id":owner}))
        (path / "map.jpg").write_bytes(b"jpeg")
    client = chat_app.test_client()
    prefix = "/api/v1/heavy-metal-cd/visualization/artifacts"
    assert client.get(prefix,headers=auth_header).get_json()["data"]["count"] == 1
    assert client.get(f"{prefix}/{'a'*32}/map",headers=auth_header).status_code == 404
    assert client.get(f"{prefix}/{'b'*32}/map",headers=auth_header).status_code == 404
    response = client.get(f"{prefix}/{'c'*32}/map",headers=auth_header)
    assert response.status_code == 200
    response.close()


def test_csv_limit_and_flux_chart_option(chat_app,tmp_path,monkeypatch):
    scope = {"category":"flux","field":"net_cd","year":2024,"source":"native"}
    record = {"source":"native","accounting_year":2024,"parcel_id":"p","sample_id":"s","output":{}}
    monkeypatch.setattr(artifacts,"MAX_ROWS",1)
    monkeypatch.setattr(artifacts,"_flux_rows",lambda scope:iter([record,record]))
    with chat_app.app_context():
        ids = _query_record(chat_app,tmp_path)
        with pytest.raises(artifacts.ArtifactError,match="too_many_rows"):
            artifacts.generate(*ids,scope,export=True)
        with pytest.raises(artifacts.ArtifactError,match="unsupported_flux_chart_option"):
            artifacts.generate(*ids,scope,interpolation="nearest")
        assert artifacts.list_owned(*ids[:2]) == []


def test_flux_chart_followup_and_missing_dependency(chat_app,tmp_path,monkeypatch):
    from rasterio import Affine
    from framework.agents.cd_artifact_conversation import answer_attachment
    from framework.models import ParcelInfo

    scope = {"category":"flux","field":"net_cd","year":2024,"source":"native"}
    monkeypatch.setattr(artifacts,"_flux_rows",lambda scope:iter([
        {"parcel_id":f"P{i}","accounting_year":2024,"output":{"net_cd":value}}
        for i,value in enumerate((-8., 5., 10.))
    ]))
    crs = viz.load_template()["crs"]
    monkeypatch.setattr(viz,"load_template",lambda:{"width":4,"height":4,"transform":Affine(1,0,0,0,-1,4),
                                                   "bounds":(0,0,4,4),"crs":crs})
    with chat_app.app_context():
        uid,cid,revision = _query_record(chat_app,tmp_path)
        for i,(lon,lat) in enumerate(((1.,1.),(2.,2.),(2.5,1.5))):
            db.session.add(ParcelInfo(parcel_id=f"P{i}",centroid_lon=lon,centroid_lat=lat))
        db.session.commit()
        request = {"user_id":uid,"conversation_id":cid,"_cd_artifact_context":{"scope":scope,"revision":revision}}
        with monkeypatch.context() as patch:
            def missing(*args, **kwargs):
                raise ImportError("optional plotting dependency")
            patch.setattr(artifacts,"_charts",missing)
            result = answer_attachment(request,"画成图")
            assert result["model_results"]["models"]["cd_conversation"]["reason"] == "missing_render_dependency"
        assert artifacts.list_owned(uid,cid) == []
        result = answer_attachment(request,"画成图")["model_results"]["models"]["cd_conversation"]
        assert result["metadata"]["used_points"] == 3
        assert result["scope"]["year"] == 2024
        assert result["metadata"]["interpolated"] is False
        aid = result["attachments"][0]["artifact_id"]
        path,_ = artifacts.download(uid,cid,aid,"map")
        assert path.read_bytes().startswith(b"\xff\xd8")
        with pytest.raises(artifacts.ArtifactError):
            artifacts.download(uid,cid,"../"+aid,"map")
