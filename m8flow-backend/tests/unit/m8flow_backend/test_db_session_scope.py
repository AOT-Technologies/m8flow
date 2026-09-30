"""`db.session` must be one session per app context, not one per access.

Services are written against a stable `db.session` for a whole call (query a
row, commit, then refresh or mutate that row). Background callers -- the NATS
consumer and notification worker, celery jobs, scripts -- hold only an app
context, where a per-access session made every such call fail with
"Instance ... is not persistent within this Session".
"""

from __future__ import annotations

from m8flow_backend.db import current_session


def test_current_session_is_stable_within_an_app_context(app):
    with app.app_context():
        assert current_session() is current_session()


def test_app_context_session_is_not_reused_across_contexts(app):
    with app.app_context():
        first = current_session()
    with app.app_context():
        assert current_session() is not first


def test_app_context_session_is_closed_on_teardown(app):
    from m8flow_bpmn_core.models.user import UserModel

    with app.app_context():
        session = current_session()
        session.query(UserModel).all()  # check out a connection
        assert session.is_active

    # teardown_appcontext rolled it back and closed it: no connection is held.
    assert session.get_transaction() is None


def test_request_session_is_still_request_scoped(app):
    with app.test_request_context("/"):
        assert current_session() is current_session()


def test_a_caller_supplied_session_is_left_open(app, db_session):
    """Routes and tests pin their own session to `g.db_session`; teardown must not close
    a session it did not open."""
    from flask import g

    with app.app_context():
        g.db_session = db_session
        assert current_session() is db_session

    assert db_session.is_active
    from m8flow_bpmn_core.models.user import UserModel

    db_session.query(UserModel).all()  # still usable, not closed out from under us
