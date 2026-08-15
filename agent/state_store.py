import json
from pathlib import Path

from .trust_engine import SOURCE_TYPE_PRIORS, EWMA_ALPHA


class StateStore:
    # backed by a plain JSON file so reliability learned in one query is
    # still there for the next one -- swap this for a real DB later, nothing
    # else in the agent needs to know
    def __init__(self, path: str = "agent_state.json"):
        self.path = Path(path)
        # load whatever was learned last run, if anything, so state survives
        # across separate `python demo.py` invocations, not just within one
        self._state = self._load()

    def _load(self) -> dict:
        # no file yet means no history -- every source starts at its prior
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {}

    def save(self):
        # rewritten in full each time rather than appended -- the state is
        # tiny (one entry per source) so this is simplest and always correct
        self.path.write_text(json.dumps(self._state, indent=2))

    def _entry(self, source: str) -> dict:
        # first time we see a source, seed it with its prior instead of 0.5 flat.
        # setdefault means later calls just return the existing entry unchanged
        return self._state.setdefault(
            source,
            {"reliability": SOURCE_TYPE_PRIORS.get(source, 0.5), "n_conflicts": 0, "n_agreed": 0},
        )

    def get_reliability(self, source: str) -> float:
        # what the trust engine reads before scoring a report
        return self._entry(source)["reliability"]

    def update_reliability(self, source: str, agreed: bool):
        # EWMA nudge toward 1.0 if the source agreed with the resolved
        # answer, toward 0.0 if it didn't -- recent behaviour matters more
        # than old behaviour, but nothing swings on a single data point.
        # also keeps a raw agreed/total tally purely for the demo's summary line
        entry = self._entry(source)
        target = 1.0 if agreed else 0.0
        entry["reliability"] = entry["reliability"] + EWMA_ALPHA * (target - entry["reliability"])
        entry["n_conflicts"] += 1
        entry["n_agreed"] += 1 if agreed else 0
        self.save()

    def snapshot(self) -> dict:
        # deep copy so callers (e.g. demo.py's summary printout) can't
        # accidentally mutate live state through the dict they get back
        return json.loads(json.dumps(self._state))
