from datetime import timedelta

from .trust_engine import SourceReport

# stubbed source data -- swap query_source's body for a real HTTP call and
# nothing else in the agent needs to change. time offsets are minutes
# before `now`; each asset has a list of reports so the same source can
# answer differently across repeated queries
_DATA = {
    "wms": {
        "FORKLIFT-07": [("Bay 12", "in_use", 10), ("Bay 9", "in_use", 2)],
        "PALLET-JACK-02": [("Loading Dock", "idle", 5)],
        "SCISSOR-LIFT-03": [("Bay 2", "idle", 8)],
    },
    "field_tech": {
        "FORKLIFT-07": [("Bay 12", "in_use", 60), ("Bay 9", "in_use", 25)],
        "PALLET-JACK-02": [("Loading Dock", "idle", 90)],
    },
    "manual": {
        "FORKLIFT-07": [("Bay 4", "idle", 180), ("Bay 4", "idle", 20)],
        "PALLET-JACK-02": [("Storage C", "idle", 200)],
        "SCISSOR-LIFT-03": [("Bay 2", "idle", 45)],
    },
}

_call_counters = {"wms": {}, "field_tech": {}, "manual": {}}

ALL_SOURCES = ["wms", "field_tech", "manual"]


def query_source(source: str, asset_id: str, now):
    # returns None if this source has never reported on the asset -- a real
    # gap, not something to fake an answer for
    entries = _DATA.get(source, {}).get(asset_id)
    if not entries:
        return None
    idx = _call_counters[source].get(asset_id, 0)
    if idx >= len(entries):
        idx = len(entries) - 1  # keep returning the last known report once scripted data runs out
    location, status, minutes_ago = entries[idx]
    _call_counters[source][asset_id] = idx + 1
    return SourceReport(
        source=source,
        asset_id=asset_id,
        location=location,
        status=status,
        timestamp=now - timedelta(minutes=minutes_ago),
    )


def query_all(asset_id: str, now):
    # queries every source and drops the ones with no data instead of
    # treating a gap as a conflicting answer
    reports = []
    for source in ALL_SOURCES:
        r = query_source(source, asset_id, now)
        if r is not None:
            reports.append(r)
    return reports
