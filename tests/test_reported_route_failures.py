from db.models import ModelVersion
from db.session import SessionLocal
from tests.helpers import auth, register_and_login
from admin_panel import _model_display_name


def test_model_version_sequence():
    assert _model_display_name(1) == "Model 1.0"
    assert _model_display_name(10) == "Model 1.9"
    assert _model_display_name(11) == "Model 2.0"


def test_reported_user_routes_do_not_return_internal_error(client, admin_token):
    user = register_and_login(
        client, admin_token, username="routeuser",
        email="routeuser@test.local", password="SecurePass123!",
    )
    for path in ("/my/history", "/my/reviews"):
        response = client.get(path, headers=auth(user["token"]))
        assert response.status_code == 200, (path, response.get_json())


def test_reported_admin_routes_do_not_return_internal_error(client, admin_token):
    for path in (
        "/admin/api/models", "/admin/api/models/versions",
        "/admin/api/ml/model-versions", "/admin/api/ml/training-runs",
        "/admin/api/ml/backtests", "/admin/api/ml/monitoring",
        "/admin/api/training-records",
    ):
        response = client.get(path, headers=auth(admin_token))
        assert response.status_code == 200, (path, response.get_json())


def test_model_semantic_name_and_edit(client, admin_token):
    db = SessionLocal()
    try:
        row = ModelVersion(symbol="EURUSD", interval="60min", path="", status="CANDIDATE")
        db.add(row)
        db.commit()
        version_id = row.id
    finally:
        db.close()
    listed = client.get("/admin/api/models/versions", headers=auth(admin_token))
    item = next(row for row in listed.get_json()["versions"] if row["id"] == version_id)
    assert item["name"].startswith("Model ")
    renamed = client.patch(
        f"/admin/api/models/versions/{version_id}/name",
        headers=auth(admin_token), json={"name": "Model 2.0 Institutional"},
    )
    assert renamed.status_code == 200
    assert renamed.get_json()["name"] == "Model 2.0 Institutional"
