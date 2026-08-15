import os
import tempfile
from datetime import datetime, timedelta

from agent.state_store import StateStore
from agent.trust_engine import SourceReport, resolve


def make_report(source, location, status, minutes_ago, now):
    return SourceReport(source, "TEST-ASSET", location, status, now - timedelta(minutes=minutes_ago))


def test_no_conflict_when_sources_agree():
    now = datetime(2026, 1, 1, 12, 0, 0)
    with tempfile.TemporaryDirectory() as d:
        state = StateStore(os.path.join(d, "state.json"))
        reports = [
            make_report("wms", "Bay 1", "idle", 5, now),
            make_report("field_tech", "Bay 1", "idle", 10, now),
        ]
        result = resolve(reports, now, state)
        assert result["conflict_detected"] is False
        assert result["resolved_location"] == "Bay 1"


def test_conflict_resolved_by_higher_trust():
    now = datetime(2026, 1, 1, 12, 0, 0)
    with tempfile.TemporaryDirectory() as d:
        state = StateStore(os.path.join(d, "state.json"))
        reports = [
            make_report("wms", "Bay 1", "idle", 2, now),
            make_report("manual", "Bay 9", "idle", 300, now),
        ]
        result = resolve(reports, now, state)
        assert result["conflict_detected"] is True
        assert result["resolved_location"] == "Bay 1"


def test_reliability_drops_after_losing_a_conflict():
    now = datetime(2026, 1, 1, 12, 0, 0)
    with tempfile.TemporaryDirectory() as d:
        state = StateStore(os.path.join(d, "state.json"))
        before = state.get_reliability("manual")
        reports = [
            make_report("wms", "Bay 1", "idle", 2, now),
            make_report("field_tech", "Bay 1", "idle", 5, now),
            make_report("manual", "Bay 9", "idle", 300, now),
        ]
        resolve(reports, now, state)
        after = state.get_reliability("manual")
        assert after < before


def test_low_reliability_can_outweigh_a_fresher_timestamp():
    now = datetime(2026, 1, 1, 12, 0, 0)
    with tempfile.TemporaryDirectory() as d:
        state = StateStore(os.path.join(d, "state.json"))
        for _ in range(3):
            state.update_reliability("manual", agreed=False)

        reports = [
            make_report("field_tech", "Bay 1", "idle", 30, now),
            make_report("manual", "Bay 9", "idle", 5, now),
        ]
        result = resolve(reports, now, state)
        assert result["resolved_location"] == "Bay 1"


def test_state_persists_across_store_instances():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "state.json")
        state1 = StateStore(path)
        state1.update_reliability("manual", agreed=False)
        reliability_after_write = state1.get_reliability("manual")

        state2 = StateStore(path)
        assert state2.get_reliability("manual") == reliability_after_write


def test_missing_source_does_not_count_as_conflict():
    now = datetime(2026, 1, 1, 12, 0, 0)
    with tempfile.TemporaryDirectory() as d:
        state = StateStore(os.path.join(d, "state.json"))
        reports = [make_report("wms", "Bay 1", "idle", 2, now)]
        result = resolve(reports, now, state)
        assert result["conflict_detected"] is False
