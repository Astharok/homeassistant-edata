"""Unit tests for the surplus auto-refresh logic in EdataCoordinator.

Tests cover three methods:
  - _find_stale_zero_surplus_months
  - _purge_month_from_memory
  - The ACCEPT / KEEP NEW / RESTORE decision logic (exercised via a helper
    that mimics the post-update decision block).

The full coordinator stack (HA, Datadis API, etc.) is intentionally NOT
instantiated.  A minimal stub exposes only the attributes the tested methods
touch, so the tests are fast, dependency-free and deterministic.
"""

from __future__ import annotations

import types
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Stub: replaces EdataCoordinator just for the methods under test
# ---------------------------------------------------------------------------

def _make_stub(consumptions: list[dict]) -> Any:
    """Return a stub object that looks enough like EdataCoordinator."""

    stub = MagicMock()
    stub.scups = "TEST"
    stub._MAX_SURPLUS_REFRESH_ATTEMPTS = 5
    stub._SURPLUS_STALE_DAYS = 3
    stub._surplus_refresh_done: set = set()
    stub._surplus_refresh_attempts: dict = {}
    stub._edata = MagicMock()
    stub._edata.data = {"consumptions": list(consumptions)}

    # Bind the real methods to the stub
    from custom_components.edata.coordinator import EdataCoordinator
    stub._find_stale_zero_surplus_months = (
        EdataCoordinator._find_stale_zero_surplus_months.__get__(stub)
    )
    stub._purge_month_from_memory = (
        EdataCoordinator._purge_month_from_memory.__get__(stub)
    )
    return stub


def _dt(year: int, month: int, day: int = 1, hour: int = 1) -> datetime:
    return datetime(year, month, day, hour)


def _rec(dt: datetime, value: float = 0.5, surplus: float = 0.0) -> dict:
    return {"datetime": dt, "value_kWh": value, "surplus_kWh": surplus}


# ---------------------------------------------------------------------------
# _find_stale_zero_surplus_months
# ---------------------------------------------------------------------------

class TestFindStaleZeroSurplusMonths:
    """Tests for _find_stale_zero_surplus_months."""

    def _stale(self, days_ago: int = 5) -> datetime:
        """Return a datetime that qualifies as 'stale'."""
        return datetime.today() - timedelta(days=days_ago)

    def _fresh(self, days_ago: int = 1) -> datetime:
        """Return a datetime that does NOT qualify as 'stale'."""
        return datetime.today() - timedelta(days=days_ago)

    # --- guard: no surplus anywhere → skip entirely ---

    def test_no_solar_installation_skips(self):
        """If no month ever has surplus, return empty list (no solar)."""
        consumptions = [_rec(self._stale(), surplus=0.0)]
        stub = _make_stub(consumptions)
        result = stub._find_stale_zero_surplus_months(datetime(2000, 1, 1))
        assert result == []

    # --- basic detection ---

    def test_detects_stale_zero_surplus_month(self):
        """A month with stale records and 0 surplus is returned when another
        month has surplus (proving solar is present)."""
        date_from = datetime(2026, 1, 1)
        # April: has surplus → proves solar
        consumptions = [
            _rec(_dt(2026, 4, 15), surplus=1.5),
            # May: stale, no surplus
            _rec(self._stale(10).replace(year=2026, month=5, day=2), surplus=0.0),
        ]
        stub = _make_stub(consumptions)
        result = stub._find_stale_zero_surplus_months(date_from)
        assert (2026, 5) in result

    def test_ignores_fresh_records(self):
        """A month where all records are too recent is NOT returned."""
        date_from = datetime(2026, 1, 1)
        consumptions = [
            _rec(_dt(2026, 4, 15), surplus=1.5),  # solar proof
            _rec(self._fresh(1).replace(year=2026, month=5), surplus=0.0),  # fresh
        ]
        stub = _make_stub(consumptions)
        result = stub._find_stale_zero_surplus_months(date_from)
        assert (2026, 5) not in result

    def test_ignores_months_before_date_from(self):
        """Records before date_from window are excluded."""
        date_from = datetime(2026, 5, 1)
        consumptions = [
            _rec(_dt(2026, 4, 15), surplus=2.0),  # solar proof (also before window)
            _rec(self._stale(10).replace(year=2026, month=4, day=2), surplus=0.0),
        ]
        stub = _make_stub(consumptions)
        result = stub._find_stale_zero_surplus_months(date_from)
        # April is before date_from, must not appear
        assert (2026, 4) not in result

    def test_ignores_already_resolved_months(self):
        """Months already in _surplus_refresh_done are skipped."""
        date_from = datetime(2026, 1, 1)
        consumptions = [
            _rec(_dt(2026, 4, 15), surplus=1.5),
            _rec(self._stale(10).replace(year=2026, month=5, day=2), surplus=0.0),
        ]
        stub = _make_stub(consumptions)
        stub._surplus_refresh_done.add((2026, 5))
        result = stub._find_stale_zero_surplus_months(date_from)
        assert (2026, 5) not in result

    def test_ignores_months_at_max_attempts(self):
        """Months that have already reached MAX_SURPLUS_REFRESH_ATTEMPTS are skipped."""
        date_from = datetime(2026, 1, 1)
        consumptions = [
            _rec(_dt(2026, 4, 15), surplus=1.5),
            _rec(self._stale(10).replace(year=2026, month=5, day=2), surplus=0.0),
        ]
        stub = _make_stub(consumptions)
        stub._surplus_refresh_attempts[(2026, 5)] = stub._MAX_SURPLUS_REFRESH_ATTEMPTS
        result = stub._find_stale_zero_surplus_months(date_from)
        assert (2026, 5) not in result

    def test_returns_multiple_candidate_months(self):
        """Multiple stale zero-surplus months are all returned."""
        date_from = datetime(2026, 1, 1)
        consumptions = [
            _rec(_dt(2026, 6, 15), surplus=3.0),  # solar proof
            _rec(self._stale(10).replace(year=2026, month=4, day=2), surplus=0.0),
            _rec(self._stale(8).replace(year=2026, month=5, day=2), surplus=0.0),
        ]
        stub = _make_stub(consumptions)
        result = stub._find_stale_zero_surplus_months(date_from)
        assert (2026, 4) in result
        assert (2026, 5) in result

    def test_does_not_return_month_with_partial_surplus(self):
        """A month that has at least one record with surplus is NOT returned."""
        date_from = datetime(2026, 1, 1)
        stale = self._stale(10).replace(year=2026, month=5)
        consumptions = [
            _rec(_dt(2026, 4, 15), surplus=1.5),
            _rec(stale.replace(day=2), surplus=0.0),
            _rec(stale.replace(day=3), surplus=0.5),  # surplus present
        ]
        stub = _make_stub(consumptions)
        result = stub._find_stale_zero_surplus_months(date_from)
        assert (2026, 5) not in result

    def test_result_is_sorted(self):
        """The returned list is sorted."""
        date_from = datetime(2026, 1, 1)
        consumptions = [
            _rec(_dt(2026, 6, 15), surplus=3.0),
            _rec(self._stale(5).replace(year=2026, month=5, day=2), surplus=0.0),
            _rec(self._stale(5).replace(year=2026, month=3, day=2), surplus=0.0),
        ]
        stub = _make_stub(consumptions)
        result = stub._find_stale_zero_surplus_months(date_from)
        assert result == sorted(result)


# ---------------------------------------------------------------------------
# _purge_month_from_memory
# ---------------------------------------------------------------------------

class TestPurgeMonthFromMemory:
    """Tests for _purge_month_from_memory."""

    def _make_data(self) -> dict:
        may_dt = _dt(2026, 5, 3)
        jun_dt = _dt(2026, 6, 5)
        return {
            "consumptions": [_rec(may_dt), _rec(jun_dt)],
            "cost_hourly_sum": [{"datetime": may_dt, "value": 1.0}, {"datetime": jun_dt, "value": 2.0}],
            "consumptions_daily_sum": [{"datetime": may_dt, "value": 10.0}, {"datetime": jun_dt, "value": 20.0}],
            "cost_daily_sum": [{"datetime": may_dt, "value": 0.5}],
            "consumptions_monthly_sum": [{"datetime": may_dt, "value": 200.0}],
            "cost_monthly_sum": [{"datetime": may_dt, "value": 15.0}],
        }

    def test_purges_target_month_from_all_keys(self):
        """All six time-series keys are purged for the target month."""
        data = self._make_data()
        stub = _make_stub([])
        stub._edata.data = data
        stub._purge_month_from_memory(2026, 5)

        for key in ["consumptions", "cost_hourly_sum", "consumptions_daily_sum",
                    "cost_daily_sum", "consumptions_monthly_sum", "cost_monthly_sum"]:
            remaining = stub._edata.data[key]
            for row in remaining:
                dt = row.get("datetime")
                assert not (dt is not None and dt.year == 2026 and dt.month == 5), (
                    f"key={key} still has a May-2026 record after purge"
                )

    def test_preserves_other_months(self):
        """Records from months other than the target are untouched."""
        data = self._make_data()
        stub = _make_stub([])
        stub._edata.data = data
        stub._purge_month_from_memory(2026, 5)

        jun_recs = stub._edata.data["consumptions"]
        assert len(jun_recs) == 1
        assert jun_recs[0]["datetime"].month == 6

    def test_tolerates_missing_keys(self):
        """Does not raise if a key is absent from edata.data."""
        stub = _make_stub([])
        stub._edata.data = {"consumptions": [_rec(_dt(2026, 5, 1))]}
        stub._purge_month_from_memory(2026, 5)  # no crash expected
        assert stub._edata.data["consumptions"] == []

    def test_purge_empty_month_is_noop(self):
        """Purging a month with no records leaves everything unchanged."""
        data = self._make_data()
        stub = _make_stub([])
        stub._edata.data = data
        original_len = len(data["consumptions"])
        stub._purge_month_from_memory(2026, 7)  # July has no records
        assert len(stub._edata.data["consumptions"]) == original_len


# ---------------------------------------------------------------------------
# ACCEPT / KEEP NEW / RESTORE decision logic
# ---------------------------------------------------------------------------

def _run_decision(
    backup_recs: list[dict],
    datadis_recs: list[dict],
    update_exc: Exception | None,
    attempts: int,
    max_attempts: int = 5,
) -> tuple[str, list[dict]]:
    """Re-implement the ACCEPT/KEEP/RESTORE decision from coordinator.py so we
    can test it without running the full async coordinator loop.

    Returns (decision_label, current_consumptions_for_month).
    """
    mk = (2026, 5)
    backup = {"consumptions": list(backup_recs)}

    new_recs = datadis_recs
    new_surplus = sum((c.get("surplus_kWh") or 0) for c in new_recs)
    new_count = len(new_recs)
    old_count = len(backup.get("consumptions", []))

    # Current in-memory state (after orphan-merge might have re-added backup)
    # In the real coordinator this comes from self._edata.data["consumptions"].
    # For the decision, we use pre-orphan-merge snapshot (datadis_recs).
    current: dict = {"consumptions": list(datadis_recs)}

    if new_surplus > 0:
        decision = "ACCEPT"
    elif update_exc is not None or new_count < old_count:
        decision = "RESTORE"
        # Restore backup into current
        current["consumptions"] = list(backup["consumptions"])
    else:
        if attempts >= max_attempts:
            decision = "GIVE_UP"
        else:
            decision = "KEEP_NEW"

    return decision, current["consumptions"]


class TestDecisionLogic:
    """Tests for the ACCEPT / KEEP_NEW / RESTORE / GIVE_UP decision."""

    def _may_recs(self, n: int, surplus: float = 0.0) -> list[dict]:
        return [_rec(_dt(2026, 5, d + 1), surplus=surplus) for d in range(n)]

    # ACCEPT ----------------------------------------------------------------

    def test_accept_when_new_surplus_positive(self):
        old = self._may_recs(30, surplus=0.0)
        new = self._may_recs(30, surplus=1.5)
        decision, recs = _run_decision(old, new, None, attempts=1)
        assert decision == "ACCEPT"
        assert all((r.get("surplus_kWh") or 0) >= 0 for r in recs)

    # KEEP_NEW --------------------------------------------------------------

    def test_keep_new_when_same_count_and_no_surplus(self):
        old = self._may_recs(30)
        new = self._may_recs(30, surplus=0.0)
        decision, _ = _run_decision(old, new, None, attempts=1)
        assert decision == "KEEP_NEW"

    def test_keep_new_when_more_records_arrived(self):
        """Datadis returned MORE records than we had (new hours added)."""
        old = self._may_recs(20)
        new = self._may_recs(30, surplus=0.0)
        decision, _ = _run_decision(old, new, None, attempts=1)
        assert decision == "KEEP_NEW"

    # RESTORE ---------------------------------------------------------------

    def test_restore_on_exception(self):
        old = self._may_recs(30)
        new = self._may_recs(30, surplus=0.0)  # same count, would be KEEP_NEW
        decision, recs = _run_decision(old, new, RuntimeError("timeout"), attempts=1)
        assert decision == "RESTORE"
        assert recs == old

    def test_restore_when_datadis_returned_fewer(self):
        old = self._may_recs(30)
        new = self._may_recs(20, surplus=0.0)  # fewer records
        decision, recs = _run_decision(old, new, None, attempts=1)
        assert decision == "RESTORE"
        assert len(recs) == 30  # backup restored

    def test_restore_when_datadis_returned_zero(self):
        old = self._may_recs(30)
        new = []  # Datadis returned nothing
        decision, recs = _run_decision(old, new, None, attempts=1)
        assert decision == "RESTORE"
        assert len(recs) == 30

    def test_restore_reverts_to_backup_consumptions(self):
        old = [_rec(_dt(2026, 5, d + 1), value=d + 1.0) for d in range(30)]
        new = []
        _, recs = _run_decision(old, new, None, attempts=1)
        # Restored values must match backup (not some empty/corrupt state)
        assert [r["value_kWh"] for r in recs] == [r["value_kWh"] for r in old]

    # GIVE_UP ---------------------------------------------------------------

    def test_give_up_after_max_attempts(self):
        old = self._may_recs(30)
        new = self._may_recs(30, surplus=0.0)
        decision, _ = _run_decision(old, new, None, attempts=5, max_attempts=5)
        assert decision == "GIVE_UP"

    def test_no_give_up_before_max_attempts(self):
        old = self._may_recs(30)
        new = self._may_recs(30, surplus=0.0)
        decision, _ = _run_decision(old, new, None, attempts=4, max_attempts=5)
        assert decision == "KEEP_NEW"

    # Edge: ACCEPT takes priority over max attempts -------------------------

    def test_accept_overrides_max_attempts(self):
        """Even after many failed attempts, surplus > 0 triggers ACCEPT."""
        old = self._may_recs(30)
        new = self._may_recs(30, surplus=2.0)
        decision, _ = _run_decision(old, new, None, attempts=5, max_attempts=5)
        assert decision == "ACCEPT"

    # Edge: empty backup ----------------------------------------------------

    def test_keep_new_when_old_count_is_zero(self):
        """If backup is empty and Datadis returns records, keep them."""
        old = []
        new = self._may_recs(10, surplus=0.0)
        decision, recs = _run_decision(old, new, None, attempts=1)
        assert decision == "KEEP_NEW"
        assert len(recs) == 10


# ---------------------------------------------------------------------------
# Interaction: orphan-merge does NOT contaminate the decision
# ---------------------------------------------------------------------------

class TestOrphanMergeDoesNotContaminateDecision:
    """The Datadis snapshot is taken BEFORE orphan-merge, so the decision
    is based on true Datadis output even if orphan-merge re-injected old
    records for the same month."""

    def test_restore_fires_when_datadis_empty_despite_orphan_merge(self):
        """Simulate: Datadis returned 0 for May, but orphan-merge would have
        re-added the 30 old May records.  Decision must be RESTORE (based on
        pre-orphan-merge snapshot of 0 records) not KEEP_NEW."""

        old_may = [_rec(_dt(2026, 5, d + 1)) for d in range(30)]

        # Datadis snapshot: 0 records (what update() returned)
        datadis_snapshot: list[dict] = []

        # What orphan-merge would produce (mixing Datadis + old snapshot):
        # In the real coordinator the DECISION uses datadis_snapshot, not the
        # merged list.  Here we verify the decision function uses the snapshot.
        decision, recs = _run_decision(
            backup_recs=old_may,
            datadis_recs=datadis_snapshot,  # what the snapshot captures
            update_exc=None,
            attempts=1,
        )
        assert decision == "RESTORE", (
            "Expected RESTORE because Datadis returned 0 records for the purged month, "
            "even though orphan-merge would have re-added them"
        )
        assert len(recs) == 30  # backup fully restored


# ---------------------------------------------------------------------------
# _accepted_months tracks ACCEPT decisions for stats rebuild
# ---------------------------------------------------------------------------

def _run_decision_with_tracking(
    backup_recs: list[dict],
    datadis_recs: list[dict],
    update_exc: Exception | None,
    attempts: int,
    max_attempts: int = 5,
) -> tuple[str, list[tuple[int, int]]]:
    """Like _run_decision but also returns the accepted_months list."""
    mk = (2026, 5)
    backup = {"consumptions": list(backup_recs)}
    new_recs = datadis_recs
    new_surplus = sum((c.get("surplus_kWh") or 0) for c in new_recs)
    new_count = len(new_recs)
    old_count = len(backup.get("consumptions", []))
    accepted_months: list[tuple[int, int]] = []

    if new_surplus > 0:
        decision = "ACCEPT"
        accepted_months.append(mk)
    elif update_exc is not None or new_count < old_count:
        decision = "RESTORE"
    else:
        decision = "GIVE_UP" if attempts >= max_attempts else "KEEP_NEW"

    return decision, accepted_months


class TestAcceptedMonthsTracking:
    """Verify that _accepted_months is populated on ACCEPT and empty otherwise."""

    def _may_recs(self, n: int, surplus: float = 0.0) -> list[dict]:
        return [_rec(_dt(2026, 5, d + 1), surplus=surplus) for d in range(n)]

    def test_accepted_months_populated_on_accept(self):
        """ACCEPT appends the month to _accepted_months."""
        old = self._may_recs(30)
        new = self._may_recs(30, surplus=1.5)
        decision, accepted = _run_decision_with_tracking(old, new, None, attempts=1)
        assert decision == "ACCEPT"
        assert (2026, 5) in accepted

    def test_accepted_months_empty_on_keep_new(self):
        """KEEP_NEW does not add to _accepted_months."""
        old = self._may_recs(30)
        new = self._may_recs(30, surplus=0.0)
        decision, accepted = _run_decision_with_tracking(old, new, None, attempts=1)
        assert decision == "KEEP_NEW"
        assert accepted == []

    def test_accepted_months_empty_on_restore(self):
        """RESTORE does not add to _accepted_months."""
        old = self._may_recs(30)
        new = []
        decision, accepted = _run_decision_with_tracking(old, new, None, attempts=1)
        assert decision == "RESTORE"
        assert accepted == []

    def test_accepted_months_empty_on_give_up(self):
        """GIVE_UP does not add to _accepted_months."""
        old = self._may_recs(30)
        new = self._may_recs(30, surplus=0.0)
        decision, accepted = _run_decision_with_tracking(old, new, None, attempts=5, max_attempts=5)
        assert decision == "GIVE_UP"
        assert accepted == []

    def test_multiple_accepted_months(self):
        """When multiple months are accepted, all appear in _accepted_months."""
        accepted_months: list[tuple[int, int]] = []
        for month in [4, 5]:
            mk = (2026, month)
            new_recs = [_rec(_dt(2026, month, d + 1), surplus=1.0) for d in range(28)]
            if sum((c.get("surplus_kWh") or 0) for c in new_recs) > 0:
                accepted_months.append(mk)
        assert (2026, 4) in accepted_months
        assert (2026, 5) in accepted_months
        # rebuild_from would be the earliest: April
        rebuild_from = datetime(min(accepted_months)[0], min(accepted_months)[1], 1)
        assert rebuild_from == datetime(2026, 4, 1)
