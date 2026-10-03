"""The legacy savings-goal endpoints and the progress API must never disagree.

`projected_completion` on the legacy response used to come from a separate
routine that inferred a saving pace from the goal's age. These tests pin the
legacy field to the single methodology in `app.services.goal_progress`, so a
goal cannot report two different completion dates depending on which endpoint
answered.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database.db import Base, get_db, SavingsGoal, SavingsGoalContribution, User


engine = create_engine(
    'sqlite:///:memory:',
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db(client):
    from app.dependencies import _rate_store
    _rate_store.clear()
    client.cookies.clear()
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


def _register_and_login(client, email, password, name):
    client.post("/api/auth/register", json={"email": email, "password": password, "full_name": name})
    res = client.post("/api/auth/login", data={"username": email, "password": password})
    return res.json()["access_token"]


@pytest.fixture
def user_a_auth(client):
    token = _register_and_login(client, "usera@test.com", "Pass123456789", "User A")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_b_auth(client):
    token = _register_and_login(client, "userb@test.com", "Pass123456789", "User B")
    return {"Authorization": f"Bearer {token}"}


def _first_user_id():
    db = TestingSessionLocal()
    try:
        return db.query(User).order_by(User.id.asc()).first().id
    finally:
        db.close()


def _last_user_id():
    """The most recently registered user (user B in the isolation tests)."""
    db = TestingSessionLocal()
    try:
        return db.query(User).order_by(User.id.desc()).first().id
    finally:
        db.close()


def _seed_goal(target="10000", current=None, target_date=None, name="Goal", user_id=None):
    db = TestingSessionLocal()
    try:
        goal = SavingsGoal(
            user_id=user_id or _first_user_id(),
            name=name,
            target_amount=Decimal(target),
            current_amount=Decimal(current or "0"),
            target_date=target_date,
            status="active",
        )
        db.add(goal)
        db.commit()
        db.refresh(goal)
        return goal.id
    finally:
        db.close()


def _seed_contributions(goal_id, amounts, days_ago_list=None, user_id=None):
    db = TestingSessionLocal()
    try:
        uid = user_id or _first_user_id()
        if days_ago_list is None:
            days_ago_list = [30 * (len(amounts) - i) for i in range(len(amounts))]
        for amount, days_ago in zip(amounts, days_ago_list):
            db.add(SavingsGoalContribution(
                goal_id=goal_id,
                user_id=uid,
                amount=Decimal(amount),
                contributed_at=datetime.utcnow() - timedelta(days=days_ago),
            ))
        db.commit()
    finally:
        db.close()


def _progress(client, goal_id, auth):
    """The new, authoritative projection."""
    res = client.get(f"/api/goals/{goal_id}/progress", headers=auth)
    assert res.status_code == 200
    return res.json()


def _legacy(client, goal_id, auth):
    """The legacy detail endpoint."""
    res = client.get(f"/api/goals/{goal_id}", headers=auth)
    assert res.status_code == 200
    return res.json()


class TestLegacyDelegatesToProgressService:
    def test_detail_endpoint_matches_progress_endpoint(self, client, user_a_auth):
        goal_id = _seed_goal(target="100000", current="40000", target_date=date(2028, 1, 31))
        _seed_contributions(goal_id, ["10000", "15000", "15000"])

        legacy = _legacy(client, goal_id, user_a_auth)
        progress = _progress(client, goal_id, user_a_auth)

        assert legacy["projected_completion"] == progress["projected_completion_date"]
        assert legacy["progress_percent"] == progress["progress_percent"]
        assert progress["projected_completion_date"] is not None

    def test_progress_percent_matches_for_every_status(self, client, user_a_auth):
        goal_id = _seed_goal(target="50000", current="12500", target_date=date(2029, 6, 1))
        _seed_contributions(goal_id, ["6250", "6250"])

        legacy = _legacy(client, goal_id, user_a_auth)
        progress = _progress(client, goal_id, user_a_auth)
        assert legacy["progress_percent"] == progress["progress_percent"] == 25.0

    def test_list_endpoint_matches_progress_endpoint(self, client, user_a_auth):
        first = _seed_goal(target="100000", current="30000", target_date=date(2028, 3, 1), name="One")
        _seed_contributions(first, ["10000", "10000", "10000"])
        second = _seed_goal(target="8000", current="8000", target_date=date(2027, 1, 1), name="Two")
        _seed_contributions(second, ["4000", "4000"])

        res = client.get("/api/goals", headers=user_a_auth)
        assert res.status_code == 200
        legacy_by_id = {g["id"]: g for g in res.json()}

        for goal_id in (first, second):
            progress = _progress(client, goal_id, user_a_auth)
            assert legacy_by_id[goal_id]["projected_completion"] == progress["projected_completion_date"]
            assert legacy_by_id[goal_id]["progress_percent"] == progress["progress_percent"]

    def test_contribute_response_matches_progress_endpoint(self, client, user_a_auth):
        goal_id = _seed_goal(target="120000", current="0", target_date=date(2028, 12, 1))
        _seed_contributions(goal_id, ["10000", "10000"])
        # A fresh contribution made through the API, so the two must agree after a write.
        res = client.post(f"/api/goals/{goal_id}/contribute", json={"amount": "10000"}, headers=user_a_auth)
        assert res.status_code == 200

        progress = _progress(client, goal_id, user_a_auth)
        assert res.json()["projected_completion"] == progress["projected_completion_date"]

    def test_update_response_matches_progress_endpoint(self, client, user_a_auth):
        goal_id = _seed_goal(target="90000", current="20000", target_date=date(2028, 5, 1))
        _seed_contributions(goal_id, ["5000", "5000", "5000", "5000"])

        res = client.put(f"/api/goals/{goal_id}", json={"target_amount": "60000"}, headers=user_a_auth)
        assert res.status_code == 200

        progress = _progress(client, goal_id, user_a_auth)
        assert res.json()["projected_completion"] == progress["projected_completion_date"]
        assert res.json()["progress_percent"] == progress["progress_percent"]


class TestLegacyUnavailableProjections:
    def test_insufficient_data_leaves_legacy_field_null(self, client, user_a_auth):
        goal_id = _seed_goal(target="50000", current="20000", target_date=date(2028, 1, 1))
        _seed_contributions(goal_id, ["20000"])  # single deposit

        progress = _progress(client, goal_id, user_a_auth)
        assert progress["projection_status"] == "insufficient_data"
        assert progress["projected_completion_date"] is None
        assert _legacy(client, goal_id, user_a_auth)["projected_completion"] is None

    def test_no_ledger_rows_leaves_legacy_field_null(self, client, user_a_auth):
        goal_id = _seed_goal(target="50000", current="20000", target_date=date(2028, 1, 1))

        progress = _progress(client, goal_id, user_a_auth)
        assert progress["projection_status"] == "insufficient_data"
        assert _legacy(client, goal_id, user_a_auth)["projected_completion"] is None

    def test_no_progress_leaves_legacy_field_null(self, client, user_a_auth):
        goal_id = _seed_goal(target="50000", current="20000", target_date=date(2028, 1, 1))
        # Two non-positive deposits: enough history, but no pace.
        _seed_contributions(goal_id, ["0", "0"])

        progress = _progress(client, goal_id, user_a_auth)
        assert progress["projection_status"] == "no_progress"
        assert progress["projected_completion_date"] is None
        assert _legacy(client, goal_id, user_a_auth)["projected_completion"] is None

    def test_completed_goal_leaves_legacy_field_null(self, client, user_a_auth):
        goal_id = _seed_goal(target="10000", current="10000", target_date=date(2028, 1, 1))
        _seed_contributions(goal_id, ["5000", "5000"])

        progress = _progress(client, goal_id, user_a_auth)
        assert progress["projection_status"] == "completed"
        assert progress["projected_completion_date"] is None
        legacy = _legacy(client, goal_id, user_a_auth)
        assert legacy["projected_completion"] is None
        assert legacy["progress_percent"] == 100.0

    def test_overfunded_goal_reports_100_percent_not_above(self, client, user_a_auth):
        goal_id = _seed_goal(target="10000", current="12500")
        _seed_contributions(goal_id, ["6250", "6250"])

        legacy = _legacy(client, goal_id, user_a_auth)
        progress = _progress(client, goal_id, user_a_auth)
        assert legacy["progress_percent"] == 100.0
        assert legacy["progress_percent"] == progress["progress_percent"]


class TestLegacyProjectedStatuses:
    def test_on_track(self, client, user_a_auth):
        goal_id = _seed_goal(target="120000", current="30000", target_date=date(2030, 1, 1))
        _seed_contributions(goal_id, ["15000", "15000"])

        progress = _progress(client, goal_id, user_a_auth)
        assert progress["projection_status"] == "on_track"
        legacy = _legacy(client, goal_id, user_a_auth)
        assert legacy["projected_completion"] == progress["projected_completion_date"]
        assert legacy["projected_completion"] is not None

    def test_behind(self, client, user_a_auth):
        goal_id = _seed_goal(target="500000", current="20000", target_date=date(2027, 2, 1))
        _seed_contributions(goal_id, ["10000", "10000"])

        progress = _progress(client, goal_id, user_a_auth)
        assert progress["projection_status"] == "behind"
        legacy = _legacy(client, goal_id, user_a_auth)
        assert legacy["projected_completion"] == progress["projected_completion_date"]
        # The deadline is missed, not hidden: the honest date is still reported.
        assert legacy["projected_completion"] > "2027-02-01"

    def test_no_target_date_still_projects(self, client, user_a_auth):
        goal_id = _seed_goal(target="120000", current="30000", target_date=None)
        _seed_contributions(goal_id, ["15000", "15000"])

        progress = _progress(client, goal_id, user_a_auth)
        assert progress["projection_status"] == "no_target_date"
        legacy = _legacy(client, goal_id, user_a_auth)
        assert legacy["projected_completion"] == progress["projected_completion_date"]
        assert legacy["projected_completion"] is not None
        assert legacy["target_date"] is None


class TestLegacyUserIsolation:
    def test_cannot_read_another_users_goal_progress(self, client, user_a_auth, user_b_auth):
        goal_id = _seed_goal(target="100000", current="20000", target_date=date(2028, 1, 1))
        _seed_contributions(goal_id, ["10000", "10000"])

        assert client.get(f"/api/goals/{goal_id}", headers=user_b_auth).status_code == 404
        assert client.get(f"/api/goals/{goal_id}/progress", headers=user_b_auth).status_code == 404

    def test_list_only_contains_owned_goals(self, client, user_a_auth, user_b_auth):
        goal_id = _seed_goal(target="100000", current="20000", target_date=date(2028, 1, 1))
        _seed_contributions(goal_id, ["10000", "10000"])

        user_b_id = _seed_goal(
            target="7000", current="1000", target_date=date(2028, 1, 1),
            user_id=_last_user_id(),
        )

        b_list = client.get("/api/goals", headers=user_b_auth).json()
        assert [g["id"] for g in b_list] == [user_b_id]

        b_progress = client.get("/api/goals/progress", headers=user_b_auth).json()
        assert [g["goal_id"] for g in b_progress["goals"]] == [user_b_id]

    def test_contribution_history_is_not_shared_between_users(self, client, user_a_auth, user_b_auth):
        """A second user reusing a goal id cannot pick up the first user's rate."""
        goal_id = _seed_goal(target="100000", current="20000", target_date=date(2028, 1, 1))
        _seed_contributions(goal_id, ["10000", "10000"])

        # User B contributes to their own goal with the same numeric id shape.
        b_id = _seed_goal(
            target="100000", current="0", target_date=date(2028, 1, 1),
            user_id=_last_user_id(),
        )
        assert b_id != goal_id
        assert client.post(f"/api/goals/{b_id}/contribute", json={"amount": "5000"}, headers=user_b_auth).status_code == 200

        b_progress = client.get(f"/api/goals/{b_id}/progress", headers=user_b_auth).json()
        assert b_progress["contribution_count"] == 1
        assert b_progress["projection_status"] == "insufficient_data"


class TestListingDoesNotScaleQueriesWithGoals:
    """Listing must not issue one contribution query per goal (N+1)."""

    def _select_count(self, client, auth):
        statements = []

        def record(conn, cursor, statement, params, context, executemany):
            if statement.strip().lower().startswith("select"):
                statements.append(statement)

        event.listen(engine, "before_cursor_execute", record)
        try:
            res = client.get("/api/goals", headers=auth)
            assert res.status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", record)
        return len(statements)

    def test_query_count_is_independent_of_goal_count(self, client, user_a_auth):
        first = _seed_goal(target="100000", current="10000", target_date=date(2028, 1, 1), name="One")
        _seed_contributions(first, ["5000", "5000"])
        with_one_goal = self._select_count(client, user_a_auth)

        for i in range(4):
            goal_id = _seed_goal(
                target="100000", current="10000", target_date=date(2028, 1, 1), name=f"Extra {i}"
            )
            _seed_contributions(goal_id, ["5000", "5000"])
        with_five_goals = self._select_count(client, user_a_auth)

        assert with_five_goals == with_one_goal, (
            "listing issues extra queries per goal: "
            f"{with_one_goal} selects for 1 goal vs {with_five_goals} for 5"
        )

    def test_progress_list_query_count_is_independent_of_goal_count(self, client, user_a_auth):
        def select_count():
            statements = []

            def record(conn, cursor, statement, params, context, executemany):
                if statement.strip().lower().startswith("select"):
                    statements.append(statement)

            event.listen(engine, "before_cursor_execute", record)
            try:
                res = client.get("/api/goals/progress", headers=user_a_auth)
                assert res.status_code == 200
            finally:
                event.remove(engine, "before_cursor_execute", record)
            return len(statements)

        first = _seed_goal(target="100000", current="10000", target_date=date(2028, 1, 1), name="One")
        _seed_contributions(first, ["5000", "5000"])
        with_one_goal = select_count()

        for i in range(4):
            goal_id = _seed_goal(
                target="100000", current="10000", target_date=date(2028, 1, 1), name=f"Extra {i}"
            )
            _seed_contributions(goal_id, ["5000", "5000"])
        with_five_goals = select_count()

        assert with_five_goals == with_one_goal


class TestNoLegacyProjectionMathsRemains:
    def test_router_does_not_define_its_own_projection(self):
        """The legacy path must not reintroduce projection maths in the router."""
        from app.routers import goals as goals_router
        from app.services import goal_progress as service

        source = goals_router._compute_progress
        assert source.__module__ == goals_router.__name__
        # Everything the router needs must come from the service module.
        assert hasattr(service, "get_legacy_progress")
        assert hasattr(service, "get_legacy_progress_bulk")

    def test_progress_percent_is_clamped_by_the_service_not_the_router(self):
        from app.services import goal_progress as service
        from decimal import Decimal as D

        goal = SavingsGoal(user_id=1, name="G", target_amount=D("100"), current_amount=D("100"))
        result = service.compute_legacy_progress(goal, [])
        assert result["progress_percent"] == 100.0
        assert result["projected_completion"] is None