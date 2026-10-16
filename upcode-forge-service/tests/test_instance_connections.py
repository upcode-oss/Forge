import json
from contextlib import ExitStack
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import instance_link
from app.instance_link import PREFIX, create_link_router
from app.models import Base, InstanceConnection

PATH = f"/api/v1{PREFIX}"
ADMIN = {"X-Test-Admin": "1"}


def database_dependency(engine):
    def get_db():
        with Session(engine) as db:
            yield db

    return get_db


@pytest.fixture
def instances(tmp_path, monkeypatch):
    """Two independent databases and keys, with real HTTP handlers in both directions."""
    clients, engines, calls = {}, {}, []
    failures = {"url": None, "lose_pair_response": False}
    real_client = httpx.Client
    with ExitStack() as stack:
        for product in ("forge", "sprint"):
            engine = create_engine(
                f"sqlite:///{tmp_path / product}.db", connect_args={"check_same_thread": False}
            )
            engines[product] = engine
            Base.metadata.create_all(engine)
            cipher = Fernet(Fernet.generate_key())

            def admin(request: Request):
                if request.headers.get("x-test-admin") != "1":
                    raise HTTPException(403, "Administrator access required")

            def authenticate(db, username, password, request):
                if username != "admin" or password != "remote-admin-password":
                    raise HTTPException(401, "Invalid credentials")

            app = FastAPI()
            app.include_router(
                create_link_router(
                    product=product,
                    model=InstanceConnection,
                    get_db=database_dependency(engine),
                    admin=admin,
                    authenticate=authenticate,
                    identity=lambda db, product=product: {
                        "name": f"Test {product}",
                        "url": f"https://{product}.test",
                    },
                    encrypt=lambda value, cipher=cipher: cipher.encrypt(value.encode()).decode(),
                    decrypt=lambda value, cipher=cipher: cipher.decrypt(value.encode()).decode(),
                ),
                prefix="/api/v1",
            )
            clients[product] = stack.enter_context(TestClient(app))
            stack.callback(engine.dispose)

        def transport(request):
            calls.append((request.method, str(request.url)))
            if request.url.host == failures["url"]:
                raise httpx.ConnectError("sensitive infrastructure detail", request=request)
            product = request.url.host.split(".")[0]
            response = clients[product].request(
                request.method,
                request.url.raw_path.decode(),
                headers=request.headers,
                content=request.content,
            )
            if request.url.path.endswith("/pair") and failures["lose_pair_response"]:
                raise httpx.ReadTimeout("Response lost after remote commit", request=request)
            return httpx.Response(response.status_code, content=response.content)

        monkeypatch.setattr(
            instance_link.httpx,
            "Client",
            lambda **kwargs: real_client(transport=httpx.MockTransport(transport), **kwargs),
        )
        yield clients, engines, calls, failures


def connect(clients, source, **overrides):
    target = "sprint" if source == "forge" else "forge"
    return clients[source].post(
        PATH,
        headers=ADMIN,
        json={
            "url": f"https://{target}.test",
            "username": "admin",
            "password": "remote-admin-password",
            **overrides,
        },
    )


@pytest.mark.parametrize("source", ["forge", "sprint"])
def test_pair_check_and_disconnect_from_either_side(instances, source):
    clients, engines, calls, _ = instances
    target = "sprint" if source == "forge" else "forge"
    response = connect(clients, source)
    assert response.status_code == 200, response.text
    connection_id = response.json()["connection_id"]
    for product in clients:
        result = clients[product].get(PATH, headers=ADMIN)
        assert result.json()["connection_id"] == connection_id
        assert result.json()["state"] == "connected"
        assert "secret" not in result.text and "password" not in result.text
        assert clients[product].get(PATH).status_code == 403
        assert clients[product].get(PATH + "/peer").status_code == 401
        with Session(engines[product]) as db:
            row = db.get(InstanceConnection, 1)
            assert row.secret_encrypted.startswith("gAAAA")
            assert "remote-admin-password" not in row.secret_encrypted
    calls.clear()
    assert clients[target].post(PATH + "/test", headers=ADMIN).status_code == 200
    assert calls == [
        ("GET", f"https://{source}.test{PATH}/check"),
        ("GET", f"https://{target}.test{PATH}/peer"),
    ]
    assert clients[target].delete(PATH, headers=ADMIN).status_code == 200
    for client in clients.values():
        assert client.get(PATH, headers=ADMIN).json() is None
        assert client.post(PATH + "/test", headers=ADMIN).status_code == 404


def test_wrong_credentials_can_be_retried(instances):
    clients, _, _, _ = instances
    response = connect(clients, "forge", password="incorrect-password")
    assert response.status_code == 400
    assert "incorrect-password" not in response.text
    assert clients["sprint"].get(PATH, headers=ADMIN).json() is None
    assert clients["forge"].get(PATH, headers=ADMIN).json()["state"] == "pending"
    assert connect(clients, "forge").status_code == 200


def test_equivalent_origins_are_normalized(instances):
    clients, _, _, _ = instances
    response = connect(clients, "forge", url="  https://SPRINT.test:443/  ")
    assert response.status_code == 200, response.text
    assert response.json()["url"] == "https://sprint.test"
    assert instance_link.origin("http://[::1]:8080/") == "http://[::1]:8080"


def test_callback_failure_never_links_remote_and_retry_works(instances):
    clients, _, _, failures = instances
    failures["url"] = "forge.test"
    assert connect(clients, "forge").status_code == 502
    assert clients["sprint"].get(PATH, headers=ADMIN).json() is None
    failures["url"] = None
    assert connect(clients, "forge").status_code == 200


@pytest.mark.parametrize("recover", ["test", "retry"])
def test_lost_response_recovers_same_connection(instances, recover):
    clients, _, _, failures = instances
    failures["lose_pair_response"] = True
    assert connect(clients, "forge").status_code == 502
    pending = clients["forge"].get(PATH, headers=ADMIN).json()
    remote = clients["sprint"].get(PATH, headers=ADMIN).json()
    assert pending["state"] == "pending" and remote["state"] == "connected"
    failures["lose_pair_response"] = False
    response = (
        clients["forge"].post(PATH + "/test", headers=ADMIN)
        if recover == "test"
        else connect(clients, "forge")
    )
    assert response.status_code == 200, response.text
    assert response.json()["connection_id"] == remote["connection_id"]
    assert response.json()["state"] == "connected"


def test_existing_connection_cannot_be_replaced(instances):
    clients, _, _, _ = instances
    assert connect(clients, "forge").status_code == 200
    before = clients["sprint"].get(PATH, headers=ADMIN).json()
    assert connect(clients, "sprint").status_code == 409
    response = clients["sprint"].post(
        PATH + "/pair",
        json={
            "identity": {"product": "forge", "name": "Other", "url": "https://other.test"},
            "connection_id": str(uuid4()),
            "secret": "x" * 64,
            "username": "admin",
            "password": "remote-admin-password",
        },
    )
    assert response.status_code == 409
    assert clients["sprint"].get(PATH, headers=ADMIN).json() == before


def test_check_detects_broken_return_path_and_force_remove(instances):
    clients, _, _, failures = instances
    assert connect(clients, "forge").status_code == 200
    failures["url"] = "forge.test"
    assert clients["forge"].post(PATH + "/test", headers=ADMIN).status_code == 502
    failures["url"] = "sprint.test"
    assert clients["forge"].delete(PATH, headers=ADMIN).status_code == 502
    assert clients["forge"].get(PATH, headers=ADMIN).json() is not None
    assert clients["forge"].delete(PATH + "?force=true", headers=ADMIN).status_code == 200
    assert clients["forge"].get(PATH, headers=ADMIN).json() is None
    assert clients["sprint"].get(PATH, headers=ADMIN).json() is not None


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://user:password@sprint.test",
        "https://sprint.test/api",
        "https://sprint.test?x=1",
        "https://sprint.test/#x",
        "https://sprint.test:invalid",
        "https://sprint.test:0",
        "https://sprint.test\\@other.test",
        "https://sprint.test\n",
    ],
)
def test_invalid_urls(instances, url):
    clients, _, calls, _ = instances
    # Leading/trailing whitespace is normalized, embedded control characters are rejected.
    if url.endswith("\n"):
        url = "https://sprint.\ntest"
    assert connect(clients, "forge", url=url).status_code == 422
    assert calls == []


def test_self_connection_and_same_product_rejected(instances):
    clients, _, _, _ = instances
    assert connect(clients, "forge", url="https://forge.test").status_code == 400
    response = clients["forge"].post(
        PATH + "/pair",
        json={
            "identity": {"product": "forge", "name": "Forge", "url": "https://other.test"},
            "connection_id": str(uuid4()),
            "secret": "x" * 64,
            "username": "admin",
            "password": "remote-admin-password",
        },
    )
    assert response.status_code == 400


def test_link_key_cannot_administer_or_revoke_another_connection(instances):
    clients, engines, _, _ = instances
    assert connect(clients, "forge").status_code == 200
    headers = {"Authorization": "Bearer wrong-key", "X-Instance-Connection": str(uuid4())}
    for method, suffix in [("GET", "/peer"), ("GET", "/check"), ("DELETE", "/peer")]:
        assert clients["sprint"].request(method, PATH + suffix, headers=headers).status_code == 401
    for method, suffix in [("GET", ""), ("POST", "/test"), ("DELETE", "?force=true")]:
        assert clients["sprint"].request(method, PATH + suffix, headers=headers).status_code == 403
    with Session(engines["sprint"]) as db:
        assert db.scalar(select(InstanceConnection)) is not None


def test_forge_admin_permissions_and_remote_credential_permissions(admin):
    assert admin.get(PATH).status_code == 200
    assert admin.get(PATH).json() is None
    assert (
        admin.post(
            "/api/v1/users",
            json={
                "username": "reader",
                "email": "reader@example.com",
                "display_name": "Reader",
                "password": "reader-password-123",
            },
        ).status_code
        == 201
    )
    response = admin.post(
        PATH + "/pair",
        json={
            "identity": {"product": "sprint", "name": "Sprint", "url": "https://sprint.test"},
            "connection_id": str(uuid4()),
            "secret": "x" * 64,
            "username": "reader",
            "password": "reader-password-123",
        },
    )
    assert response.status_code == 403
    admin.post("/api/v1/auth/login", json={"username": "reader", "password": "reader-password-123"})
    assert admin.get(PATH).status_code == 403
    assert admin.delete(PATH + "?force=true").status_code == 403


def test_peer_client_rejects_redirects_and_malformed_responses(monkeypatch):
    real_client = httpx.Client
    for response in [
        httpx.Response(302, headers={"Location": "https://elsewhere.test"}),
        httpx.Response(200, text="not JSON"),
        httpx.Response(200, content=b"x" * 65537),
    ]:

        def transport(request, response=response):
            assert "cookie" not in request.headers
            return response

        monkeypatch.setattr(
            instance_link.httpx,
            "Client",
            lambda **kwargs: real_client(
                transport=httpx.MockTransport(transport),
                **kwargs,
            ),
        )
        with pytest.raises(HTTPException) as error:
            instance_link.request_peer(
                "https://sprint.test",
                "POST",
                "/pair",
                payload={
                    "password": "never-include-me",
                },
            )
        assert error.value.status_code == 502
        assert "never-include-me" not in json.dumps(error.value.detail)
