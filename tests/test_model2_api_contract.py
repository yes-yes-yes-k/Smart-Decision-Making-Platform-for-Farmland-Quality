"""验证模型2真实计算在 HTTP 接口中的参数与错误契约。"""

from flask_jwt_extended import create_access_token


def _client_with_token():
    from framework.api.app import create_app
    from framework.models.user import User, db

    app = create_app("sqlite")
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        user = User.query.filter_by(username="model2-api-tester").first()
        if user is None:
            user = User(username="model2-api-tester", password="x")
            db.session.add(user)
            db.session.commit()
        token = create_access_token(identity=str(user.id))
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def test_models_run_forwards_type5_parameters_to_model2():
    client, headers = _client_with_token()

    response = client.post(
        "/api/v1/models/run",
        json={
            "model_id": "improvement-potential-assessment",
            "question_type": 5,
            "parcel_code": "A0001",
        },
        headers=headers,
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["data"]["analysis"]["quality_grade"] == "10等"


def test_models_run_forwards_county_potential_parameters_to_model2():
    client, headers = _client_with_token()

    response = client.post(
        "/api/v1/models/run",
        json={
            "model_id": "improvement-potential-assessment",
            "question_type": 6,
            "xqmc_code": 8,
            "scenario": 1,
        },
        headers=headers,
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["data"]["analysis"]["county_code"] == 8
    assert payload["data"]["analysis"]["scenario"] == 1


def test_models_run_forwards_parcel_potential_parameters_to_model2():
    client, headers = _client_with_token()

    response = client.post(
        "/api/v1/models/run",
        json={
            "model_id": "improvement-potential-assessment",
            "question_type": 6,
            "parcel_code": "A0001",
        },
        headers=headers,
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["data"]["analysis"]["parcel_code"] == "A0001"


def test_models_run_returns_deployment_error_for_missing_csv_path():
    client, headers = _client_with_token()

    response = client.post(
        "/api/v1/models/run",
        json={
            "model_id": "improvement-potential-assessment",
            "question_type": 5,
            "parcel_code": "A0001",
            "csv_path": "D:/does-not-exist/model2.csv",
        },
        headers=headers,
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "DEPLOYMENT_ERROR"


def test_chat_exposes_model2_missing_parcel_code_error():
    client, headers = _client_with_token()

    response = client.post(
        "/api/v1/chat/",
        json={"message": "我的田耕地质量等级是多少"},
        headers=headers,
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["status"] == "error"
    assert payload["data"]["model_results"]["status"] == "error"
    assert payload["data"]["model_results"]["data"]["error"]["code"] == "MISSING_PARCEL_CODE"
