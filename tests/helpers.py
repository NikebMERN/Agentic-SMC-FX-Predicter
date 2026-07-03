# tests/helpers.py
import uuid


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def register_and_login(client, admin_token, *, username, email, password, quota=100):
    suffix = uuid.uuid4().hex[:8]
    username = f"{username}_{suffix}"
    local, domain = email.split("@", 1)
    email = f"{local}_{suffix}@{domain}"

    reg = client.post("/register", json={"username": username, "email": email, "password": password})
    assert reg.status_code == 201, reg.get_json()
    uid = reg.get_json()["user_id"]
    appr = client.post(
        f"/admin/api/users/{uid}/approve",
        headers=auth(admin_token),
        json={"signals_remaining": quota},
    )
    assert appr.status_code == 200, appr.get_json()
    login = client.post("/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.get_json()
    body = login.get_json()
    body["email"] = email
    body["username"] = username
    disc = client.post("/me/accept-disclosure", headers=auth(body["token"]))
    assert disc.status_code == 200, disc.get_json()
    return body
