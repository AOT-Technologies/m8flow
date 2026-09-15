import pytest

from m8flow_backend.auth.tenant_context import clear_tenant_context


@pytest.fixture(autouse=True)
def _unit_testing_env(monkeypatch):
    """Pin disposable unit-testing env for every test.

    Auth/settings helpers (``KeycloakSettings.from_env``, session secrets) fail
    closed outside unit-testing. Tests that do not use ``db_engine`` still need
    this pin — otherwise an empty shell env raises before the assertion runs.
    Individual tests may override via their own ``monkeypatch.setenv``.
    """
    monkeypatch.setenv("M8FLOW_BACKEND_ENV", "unit_testing")
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_ENV", "unit_testing")
    monkeypatch.setenv("FLASK_SESSION_SECRET_KEY", "unit-test-secret-key-32bytes-min")


@pytest.fixture(autouse=True)
def _reset_tenant_context_between_tests():
    clear_tenant_context()
    yield
    clear_tenant_context()


# --- Connexion test-client compatibility shim -----------------------------
# create_app() now returns a Connexion FlaskApp (ASGI). Its test client is a
# Starlette TestClient (httpx), whose request/response surface differs from the
# Flask test client the suite was written against. Rather than rewrite ~100 call
# sites across 11 files, this shim presents the small slice of the Flask
# test-client API the tests use (get_json(), headers.getlist(), query_string=,
# set_cookie()) on top of the ASGI client. It changes ergonomics only —
# Connexion's routing/validation still runs at the ASGI layer for every call.
class _HeadersShim:
    def __init__(self, headers):
        self._h = headers

    def getlist(self, key):
        return self._h.get_list(key)

    def get(self, key, default=None):
        return self._h.get(key, default)

    def __getitem__(self, key):
        return self._h[key]

    def __contains__(self, key):
        return key in self._h

    def __getattr__(self, name):
        return getattr(self._h, name)


class _ResponseShim:
    def __init__(self, response):
        self._r = response

    @property
    def status_code(self):
        return self._r.status_code

    def get_json(self, silent=False):
        try:
            return self._r.json()
        except Exception:
            if silent:
                return None
            raise

    @property
    def json(self):
        return self._r.json()

    @property
    def text(self):
        return self._r.text

    @property
    def mimetype(self):
        content_type = self._r.headers.get("content-type", "")
        return content_type.split(";", 1)[0].strip() or None

    @property
    def data(self):
        return self._r.content

    @property
    def headers(self):
        return _HeadersShim(self._r.headers)

    def __getattr__(self, name):
        return getattr(self._r, name)


class _ClientShim:
    def __init__(self, test_client):
        self._c = test_client

    def _request(self, method, url, *, query_string=None, data=None, content_type=None, **kwargs):
        # Translate the Flask test-client kwargs the suite uses onto httpx's.
        if query_string is not None:
            kwargs["params"] = query_string
        if data is not None:
            kwargs["content"] = data
        if content_type is not None:
            headers = dict(kwargs.get("headers") or {})
            headers.setdefault("Content-Type", content_type)
            kwargs["headers"] = headers
        return _ResponseShim(getattr(self._c, method)(url, **kwargs))

    def get(self, url, **kwargs):
        return self._request("get", url, **kwargs)

    def post(self, url, **kwargs):
        return self._request("post", url, **kwargs)

    def put(self, url, **kwargs):
        return self._request("put", url, **kwargs)

    def patch(self, url, **kwargs):
        return self._request("patch", url, **kwargs)

    def delete(self, url, **kwargs):
        return self._request("delete", url, **kwargs)

    def options(self, url, **kwargs):
        return self._request("options", url, **kwargs)

    def set_cookie(self, key, value="", **_ignored):
        # Flask's test client persists cookies across requests; the Starlette
        # client does the same via its httpx cookie jar. path/domain are
        # irrelevant to in-process test dispatch, so they're ignored.
        self._c.cookies.set(key, value)

    def delete_cookie(self, key, **_ignored):
        self._c.cookies.delete(key)


@pytest.fixture
def db_engine(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("M8FLOW_BACKEND_DATABASE_URI", f"sqlite:///{db_path}")
    monkeypatch.setenv("M8FLOW_BACKEND_ENV", "unit_testing")
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_ENV", "unit_testing")
    monkeypatch.setenv("FLASK_SESSION_SECRET_KEY", "unit-test-secret-key-32bytes-min")
    monkeypatch.setenv("M8FLOW_CREATE_ALL_SCHEMA", "1")
    from m8flow_backend.db import create_all, get_engine, reset_engine

    reset_engine()
    engine = get_engine()
    create_all(engine)
    yield engine
    reset_engine()


@pytest.fixture
def db_session(db_engine):
    from m8flow_backend.db import get_session_factory

    session = get_session_factory()()
    try:
        yield session
        session.commit()
    finally:
        session.close()


@pytest.fixture
def connexion_app(db_engine):
    from m8flow_backend.app import create_app

    application = create_app()
    application.app.config["TESTING"] = True
    return application


@pytest.fixture
def app(connexion_app):
    # The underlying Flask app: tests use it directly for app.test_request_context,
    # app.config, app.url_map, app.extensions, and Flask-level app.test_client().
    return connexion_app.app


@pytest.fixture
def client(connexion_app):
    # Connexion's ASGI test client reaches both the api.yml operations and the
    # plain-Flask v1/root routes (fall-through). follow_redirects=False matches
    # the Flask test client the suite expects (login tests assert 302s).
    return _ClientShim(connexion_app.test_client(follow_redirects=False))
