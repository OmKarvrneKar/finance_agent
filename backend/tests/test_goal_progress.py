"""Tests for deterministic savings-goal progress analytics."""
from datetime import datetime, timedelta, date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database.db import Base, get_db, SavingsGoal, SavingsGoalContribution
from app.services import goal_progress


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


def _user_id():
    db = TestingSessionLocal()
    try:
        from app.database.db import User
        return db.query(User).order_by(User.id.asc()).first().id
    finally:
        db.close()


def _seed_goal(target="10000", current=None, target_date=None, name="Emergency Fund", user_id=None):
    """Insert a goal directly so current_amount can be set without the API."""
    db = TestingSessionLocal()
    try:
        uid = user_id or _user_id()
        goal = SavingsGoal(
            user_id=uid,
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


def _seed_contributions(goal_id, amounts, months_ago_list=None, user_id=None):
    """Append ledger rows dated in the past to build real contribution history."""
    db = TestingSessionLocal()
    try:
        uid = user_id or _user_id()
        if months_ago_list is None:
            months_ago_list = list(range(len(amounts), 0, -1))
        for amount, months_ago in zip(amounts, months_ago_list):
            db.add(SavingsGoalContribution(
                goal_id=goal_id,
                user_id=uid,
                amount=Decimal(amount),
                contributed_at=datetime.utcnow() - timedelta(days=int(months_ago * 30.4375)),
            ))
        db.commit()
    finally:
        db.close()


def _progress(goal_id, auth):
    res = auth.get(f"/api/goals/{goal_id}/progress", headers=auth)
    return res


def _get(client, goal_id, auth):
    res = client.get(f"/api/goals/{goal_id}/progress", headers=auth)
    assert res.status_code == 200
    return res.json()


class TestProgressBasics:
    def test_zero_progress(self, client, user_a_auth):
        goal_id = _seed_goal(target="10000", current="0")
        data = _get(client, goal_id, user_a_auth)
        assert data["current_amount"] == "0.00"
        assert data["remaining_amount"] == "10000.00"
        assert data["progress_percent"] == 0

    def test_partial_progress(self, client, user_a_auth):
        goal_id = _seed_goal(target="10000", current="2500")
        data = _get(client, goal_id, user_a_auth)
        assert data["progress_percent"] == 25.0
        assert data["remaining_amount"] == "7500.00"

    def test_progress_percentage_precision(self, client, user_a_auth):
        goal_id = _seed_goal(target="3000", current="1000")
        data = _get(client, goal_id, user_a_auth)
        # 33.333... -> 33.33
        assert data["progress_percent"] == 33.33

    def test_completed_at_100_percent(self, client, user_a_auth):
        goal_id = _seed_goal(target="10000", current="10000")
        data = _get(client, goal_id, user_a_auth)
        assert data["progress_percent"] == 100.0
        assert data["remaining_amount"] == "0.00"
        assert data["projection_status"] == "completed"
        assert data["projected_months_remaining"] == 0

    def test_over_target_clamps_progress_and_shows_negative_remaining(self, client, user_a_auth):
        goal_id = _seed_goal(target="10000", current="12000")
        data = _get(client, goal_id, user_a_auth)
        assert data["progress_percent"] == 100.0
        assert data["remaining_amount"] == "-2000.00"
        assert data["projection_status"] == "completed"

    def test_remaining_amount(self, client, user_a_auth):
        goal_id = _seed_goal(target="50000", current="17500.50")
        data = _get(client, goal_id, user_a_auth)
        assert data["remaining_amount"] == "32499.50"

    def test_echoes_goal_identity_and_amounts(self, client, user_a_auth):
        goal_id = _seed_goal(target="8000", current="2000", name="Laptop", target_date=date(2027, 6, 1))
        data = _get(client, goal_id, user_a_auth)
        assert data["goal_id"] == goal_id
        assert data["goal_name"] == "Laptop"
        assert data["target_amount"] == "8000.00"
        assert data["current_amount"] == "2000.00"
        assert data["target_date"] == "2027-06-01"

    def test_null_target_date_serialised_as_null(self, client, user_a_auth):
        goal_id = _seed_goal(target="8000", current="2000", target_date=None)
        data = _get(client, goal_id, user_a_auth)
        assert data["target_date"] is None


class TestContributionRate:
    def test_insufficient_data_without_history(self, client, user_a_auth):
        goal_id = _seed_goal(target="10000", current="3000")
        data = _get(client, goal_id, user_a_auth)
        assert data["projection_status"] == "insufficient_data"
        assert data["monthly_contribution_rate"] is None
        assert data["projected_completion_date"] is None
        assert data["contribution_count"] == 0

    def test_insufficient_data_with_single_contribution(self, client, user_a_auth):
        goal_id = _seed_goal(target="10000", current="3000")
        _seed_contributions(goal_id, ["3000"], months_ago_list=[6])
        data = _get(client, goal_id, user_a_auth)
        assert data["contribution_count"] == 1
        assert data["projection_status"] == "insufficient_data"
        assert data["monthly_contribution_rate"] is None
        assert data["projected_completion_date"] is None

    def test_insufficient_data_when_window_too_short(self, client, user_a_auth):
        goal_id = _seed_goal(target="10000", current="2000")
        # Two deposits but both inside the last month: window < 1 month.
        _seed_contributions(goal_id, ["1000", "1000"], months_ago_list=[0.2, 0.05])
        data = _get(client, goal_id, user_a_auth)
        assert data["contribution_count"] == 2
        assert data["projection_status"] == "insufficient_data"
        assert data["monthly_contribution_rate"] is None

    def test_sufficient_history_computes_rate(self, client, user_a_auth):
        goal_id = _seed_goal(target="10000", current="3000")
        # 1000/month over 3 months
        _seed_contributions(goal_id, ["1000", "1000", "1000"], months_ago_list=[3, 2, 1])
        data = _get(client, goal_id, user_a_auth)
        assert data["contribution_count"] == 3
        assert data["monthly_contribution_rate"] is not None
        # 3000 contributed over a 3-month window -> ~1000/month
        assert float(data["monthly_contribution_rate"]) == pytest.approx(1000.0, rel=0.05)
        assert data["projection_status"] in ("no_target_date", "on_track", "behind")

    def test_average_monthly_contribution_is_mean_of_deposits(self, client, user_a_auth):
        goal_id = _seed_goal(target="20000", current="5000")
        _seed_contributions(goal_id, ["1000", "2000", "2000"], months_ago_list=[3, 2, 1])
        data = _get(client, goal_id, user_a_auth)
        # mean of 1000, 2000, 2000 = 1666.67
        assert data["average_monthly_contribution"] == "1666.67"

    def test_zero_contribution_no_progress(self, client, user_a_auth):
        goal_id = _seed_goal(target="10000", current="0")
        # Non-positive deposits in the ledger.
        _seed_contributions(goal_id, ["0", "0"], months_ago_list=[3, 2])
        data = _get(client, goal_id, user_a_auth)
        assert data["projection_status"] == "no_progress"
        assert data["projected_completion_date"] is None
        assert data["monthly_contribution_rate"] is not None
        assert float(data["monthly_contribution_rate"]) == 0.0

    def test_negative_contribution_rate_reports_no_progress(self, client, user_a_auth):
        goal_id = _seed_goal(target="10000", current="0")
        # Over-contributed then withdrawn: ledger nets negative.
        _seed_contributions(goal_id, ["-500", "-500"], months_ago_list=[3, 2])
        data = _get(client, goal_id, user_a_auth)
        assert data["projection_status"] == "no_progress"
        assert data["projected_completion_date"] is None
        assert float(data["monthly_contribution_rate"]) < 0

    def test_zero_rate_does_not_divide_by_zero(self, client, user_a_auth):
        goal_id = _seed_goal(target="10000", current="0")
        _seed_contributions(goal_id, ["0", "0"], months_ago_list=[4, 3])
        data = _get(client, goal_id, user_a_auth)
        # Must not raise ZeroDivisionError and must not invent a completion date.
        assert data["projected_completion_date"] is None


class TestProjection:
    def test_projection_computed_from_rate(self, client, user_a_auth):
        goal_id = _seed_goal(target="10000", current="3000")
        _seed_contributions(goal_id, ["1000", "1000", "1000"], months_ago_list=[3, 2, 1])
        data = _get(client, goal_id, user_a_auth)
        assert data["projection_status"] == "no_target_date"
        assert data["projected_months_remaining"] is not None
        assert data["projected_months_remaining"] > 0
        # remaining 7000 at ~1000/month -> roughly 7 months
        assert data["projected_months_remaining"] == pytest.approx(7, abs=1)
        assert data["projected_completion_date"] is not None

    def test_projection_months_rounds_up(self, client, user_a_auth):
        goal_id = _seed_goal(target="10000", current="9500")
        _seed_contributions(goal_id, ["4750", "4750"], months_ago_list=[2, 1])
        data = _get(client, goal_id, user_a_auth)
        # remaining 500 at ~4750/month -> a fraction of a month, must round up to 1
        assert data["projected_months_remaining"] == 1

    def test_faster_rate_projects_sooner(self, client, user_a_auth):
        slow_id = _seed_goal(target="12000", current="6000", name="Slow")
        fast_id = _seed_goal(target="12000", current="6000", name="Fast")
        _seed_contributions(slow_id, ["1000", "1000", "1000"], months_ago_list=[6, 5, 4])
        _seed_contributions(fast_id, ["3000", "3000", "3000"], months_ago_list=[6, 5, 4])
        slow = _get(client, slow_id, user_a_auth)
        fast = _get(client, fast_id, user_a_auth)
        assert fast["projected_months_remaining"] < slow["projected_months_remaining"]
        assert fast["projected_completion_date"] < slow["projected_completion_date"]

    def test_completed_goal_needs_no_projection(self, client, user_a_auth):
        goal_id = _seed_goal(target="5000", current="5000")
        _seed_contributions(goal_id, ["5000"], months_ago_list=[2])
        data = _get(client, goal_id, user_a_auth)
        assert data["projection_status"] == "completed"
        assert data["projected_completion_date"] is None
        assert data["projected_months_remaining"] == 0


class TestTargetDate:
    def test_on_track_when_projection_beats_deadline(self, client, user_a_auth):
        far_future = date.today() + timedelta(days=365 * 3)
        goal_id = _seed_goal(target="10000", current="3000", target_date=far_future)
        _seed_contributions(goal_id, ["1000", "1000", "1000"], months_ago_list=[3, 2, 1])
        data = _get(client, goal_id, user_a_auth)
        assert data["projection_status"] == "on_track"
        assert data["projected_completion_date"] <= far_future.isoformat()

    def test_behind_when_projection_misses_deadline(self, client, user_a_auth):
        # Deadline inside a month, but funding pace needs several months.
        soon = date.today() + timedelta(days=20)
        goal_id = _seed_goal(target="50000", current="1000", target_date=soon)
        _seed_contributions(goal_id, ["500", "500"], months_ago_list=[4, 3])
        data = _get(client, goal_id, user_a_auth)
        assert data["projection_status"] == "behind"
        # The honest projection is still reported, not clipped to the deadline.
        assert data["target_date"] == soon.isoformat()
        assert data["projected_completion_date"] > soon.isoformat()

    def test_no_target_date_reports_no_target_date(self, client, user_a_auth):
        goal_id = _seed_goal(target="10000", current="3000", target_date=None)
        _seed_contributions(goal_id, ["1000", "1000", "1000"], months_ago_list=[3, 2, 1])
        data = _get(client, goal_id, user_a_auth)
        assert data["target_date"] is None
        assert data["projection_status"] == "no_target_date"
        assert data["projected_completion_date"] is not None

    def test_target_date_never_shrinks_projection(self, client, user_a_auth):
        """A tight deadline must not make the projection look achievable."""
        tight = date.today() + timedelta(days=10)
        goal_id = _seed_goal(target="100000", current="1000", target_date=tight)
        _seed_contributions(goal_id, ["500", "500"], months_ago_list=[6, 5])
        data = _get(client, goal_id, user_a_auth)
        assert data["projection_status"] == "behind"
        assert data["projected_months_remaining"] > 1
        assert data["projected_completion_date"] > tight.isoformat()


class TestDecimalPrecision:
    def test_money_values_are_two_dp_strings(self, client, user_a_auth):
        goal_id = _seed_goal(target="10000.555", current="3333.333")
        data = _get(client, goal_id, user_a_auth)
        assert data["target_amount"] == "10000.56"
        assert data["current_amount"] == "3333.33"
        assert data["remaining_amount"] == "6667.23"

    def test_no_float_drift_on_repeated_decimal_amounts(self, client, user_a_auth):
        goal_id = _seed_goal(target="1000", current="0")
        for _ in range(10):
            client.post(f"/api/goals/{goal_id}/contribute", json={"amount": "0.10"}, headers=user_a_auth)
        data = _get(client, goal_id, user_a_auth)
        assert data["current_amount"] == "1.00"

    def test_large_amounts_keep_precision(self, client, user_a_auth):
        goal_id = _seed_goal(target="99999999.99", current="12345678.89")
        data = _get(client, goal_id, user_a_auth)
        assert data["target_amount"] == "99999999.99"
        assert data["current_amount"] == "12345678.89"
        assert data["remaining_amount"] == "87654321.10"


class TestUserIsolation:
    def test_cannot_read_another_users_goal_progress(self, client, user_a_auth, user_b_auth):
        goal_id = _seed_goal(target="10000", current="2000")
        res = client.get(f"/api/goals/{goal_id}/progress", headers=user_b_auth)
        assert res.status_code == 404

    def test_list_excludes_other_users_goals(self, client, user_a_auth, user_b_auth):
        a_goal = _seed_goal(target="10000", current="2000", name="A Goal")
        res = client.get("/api/goals/progress", headers=user_b_auth)
        assert res.status_code == 200
        assert res.json()["total"] == 0
        assert res.json()["goals"] == []

    def test_list_only_returns_owned_goals(self, client, user_a_auth, user_b_auth):
        a_goal = _seed_goal(target="10000", current="2000", name="A Goal")
        res = client.get("/api/goals/progress", headers=user_a_auth)
        assert res.status_code == 200
        assert res.json()["total"] == 1
        assert res.json()["goals"][0]["goal_id"] == a_goal

    def test_contributions_are_user_scoped_in_rate(self, client, user_a_auth, user_b_auth):
        """Another user's ledger rows must not inflate this goal's rate."""
        a_id = _seed_goal(target="10000", current="1000", name="Shared")

        # Rows belonging to a *different* user, targeting the same goal id.
        db = TestingSessionLocal()
        try:
            from app.database.db import User
            b_id = db.query(User).order_by(User.id.desc()).first().id
            for months_ago in (3, 2):
                db.add(SavingsGoalContribution(
                    goal_id=a_id, user_id=b_id, amount=Decimal("9999"),
                    contributed_at=datetime.utcnow() - timedelta(days=int(months_ago * 30.4375)),
                ))
            db.commit()
        finally:
            db.close()

        data = _get(client, a_id, user_a_auth)
        # Only the owner-scoped rows are counted.
        assert data["contribution_count"] == 0
        assert data["projection_status"] == "insufficient_data"


class TestAuthentication:
    def test_progress_requires_auth(self, client, user_a_auth):
        # Seed via an authenticated call so the goal exists.
        res = client.post("/api/goals", json={"name": "Fund", "target_amount": "10000"}, headers=user_a_auth)
        goal_id = res.json()["id"]

        # Login also sets an HttpOnly cookie, so drop cookies as well as the
        # Authorization header to make this a genuinely anonymous request.
        client.cookies.clear()
        assert client.get(f"/api/goals/{goal_id}/progress").status_code == 401

    def test_progress_list_requires_auth(self, client, user_a_auth):
        client.cookies.clear()
        assert client.get("/api/goals/progress").status_code == 401

    def test_unknown_goal_id_returns_404(self, client, user_a_auth):
        assert client.get("/api/goals/99999/progress", headers=user_a_auth).status_code == 404


class TestMultipleGoals:
    def test_multiple_goals_each_get_own_progress(self, client, user_a_auth):
        a = _seed_goal(target="10000", current="2500", name="A")
        b = _seed_goal(target="20000", current="5000", name="B")
        c = _seed_goal(target="3000", current="3000", name="C")
        res = client.get("/api/goals/progress", headers=user_a_auth)
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 3
        by_id = {g["goal_id"]: g for g in body["goals"]}
        assert by_id[a]["progress_percent"] == 25.0
        assert by_id[b]["progress_percent"] == 25.0
        assert by_id[c]["projection_status"] == "completed"

    def test_empty_list_when_no_goals(self, client, user_a_auth):
        res = client.get("/api/goals/progress", headers=user_a_auth)
        assert res.status_code == 200
        assert res.json() == {"goals": [], "total": 0}


class TestReadOnlyGuarantee:
    def test_progress_call_does_not_mutate_goal(self, client, user_a_auth):
        goal_id = _seed_goal(target="10000", current="3000")
        _seed_contributions(goal_id, ["1000", "1000", "1000"], months_ago_list=[3, 2, 1])
        db = TestingSessionLocal()
        try:
            before = db.query(SavingsGoal).filter(SavingsGoal.id == goal_id).first()
            snapshot = (before.target_amount, before.current_amount, before.status, before.updated_at)
        finally:
            db.close()

        _get(client, goal_id, user_a_auth)
        _get(client, goal_id, user_a_auth)

        db = TestingSessionLocal()
        try:
            after = db.query(SavingsGoal).filter(SavingsGoal.id == goal_id).first()
            assert (after.target_amount, after.current_amount, after.status, after.updated_at) == snapshot
        finally:
            db.close()

    def test_projection_does_not_complete_the_goal(self, client, user_a_auth):
        """A projection is advice, never a state change."""
        goal_id = _seed_goal(target="50000", current="1000")
        _seed_contributions(goal_id, ["500", "500"], months_ago_list=[4, 3])
        _get(client, goal_id, user_a_auth)
        db = TestingSessionLocal()
        try:
            goal = db.query(SavingsGoal).filter(SavingsGoal.id == goal_id).first()
            assert goal.status == "active"
            assert goal.current_amount == Decimal("1000")
        finally:
            db.close()


class TestContributeRecordsHistory:
    def test_contribution_endpoint_records_ledger_row(self, client, user_a_auth):
        res = client.post("/api/goals", json={"name": "Fund", "target_amount": "10000"}, headers=user_a_auth)
        goal_id = res.json()["id"]
        client.post(f"/api/goals/{goal_id}/contribute", json={"amount": "1000"}, headers=user_a_auth)
        client.post(f"/api/goals/{goal_id}/contribute", json={"amount": "1000"}, headers=user_a_auth)

        db = TestingSessionLocal()
        try:
            rows = db.query(SavingsGoalContribution).filter(
                SavingsGoalContribution.goal_id == goal_id
            ).all()
            assert len(rows) == 2
            assert sum((Decimal(str(r.amount)) for r in rows), Decimal("0")) == Decimal("2000")
        finally:
            db.close()

    def test_aggregate_and_ledger_stay_consistent(self, client, user_a_auth):
        res = client.post("/api/goals", json={"name": "Fund", "target_amount": "10000"}, headers=user_a_auth)
        goal_id = res.json()["id"]
        for amount in ("1500.25", "2000.75", "500.00"):
            client.post(f"/api/goals/{goal_id}/contribute", json={"amount": amount}, headers=user_a_auth)

        detail = _get(client, goal_id, user_a_auth)
        # 1500.25 + 2000.75 + 500.00 = 4001.00
        assert detail["current_amount"] == "4001.00"
        assert detail["contribution_count"] == 3

    def test_decimal_contributions_sum_exactly(self, client, user_a_auth):
        res = client.post("/api/goals", json={"name": "Pence", "target_amount": "1000"}, headers=user_a_auth)
        goal_id = res.json()["id"]
        for _ in range(4):
            client.post(f"/api/goals/{goal_id}/contribute", json={"amount": "0.25"}, headers=user_a_auth)
        detail = _get(client, goal_id, user_a_auth)
        assert detail["current_amount"] == "1.00"
        assert detail["contribution_count"] == 4


class TestServiceUnit:
    def test_compute_is_pure(self):
        """Same inputs -> same outputs, with no session involved."""
        goal = SavingsGoal(
            id=1, user_id=1, name="G", target_amount=Decimal("1000"),
            current_amount=Decimal("250"), status="active",
        )
        contributions = [
            SavingsGoalContribution(goal_id=1, user_id=1, amount=Decimal("100"), contributed_at=datetime.utcnow() - timedelta(days=60)),
            SavingsGoalContribution(goal_id=1, user_id=1, amount=Decimal("150"), contributed_at=datetime.utcnow() - timedelta(days=30)),
        ]
        first = goal_progress.compute_goal_progress(goal, contributions)
        second = goal_progress.compute_goal_progress(goal, contributions)
        assert first == second
        # inputs untouched
        assert goal.target_amount == Decimal("1000")
        assert goal.current_amount == Decimal("250")

    def test_add_months_clamps_to_month_end(self):
        # 31 Jan + 1 month must land on 28/29 Feb, not crash.
        result = goal_progress._add_months(date(2026, 1, 31), 1)
        assert result.month == 2
        assert result.day == 28

    def test_add_months_rolls_over_year(self):
        result = goal_progress._add_months(date(2026, 11, 15), 3)
        assert (result.year, result.month, result.day) == (2027, 2, 15)

    def test_months_between_zero_for_same_day(self):
        today = date.today()
        assert goal_progress._months_between(today, today) == Decimal("0")

    def test_no_contributions_never_sets_a_date(self):
        goal = SavingsGoal(
            id=2, user_id=1, name="G", target_amount=Decimal("1000"),
            current_amount=Decimal("0"), status="active",
        )
        result = goal_progress.compute_goal_progress(goal, [])
        assert result["projected_completion_date"] is None
        assert result["monthly_contribution_rate"] is None
        assert result["projection_status"] == "insufficient_data"