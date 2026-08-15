from datetime import datetime

from .sources import query_all
from .state_store import StateStore
from .trust_engine import resolve


class AssetLocationAgent:
    # thin wrapper tying sources + trust engine + persisted state together --
    # this is the object a caller actually talks to
    def __init__(self, state_path: str = "agent_state.json"):
        self.state = StateStore(state_path)

    def query(self, asset_id: str, now: datetime = None):
        # pulls every source's report for this asset, then hands them to the
        # trust engine to detect conflicts and pick a winner
        now = now or datetime.utcnow()  # `now` is overridable so demo.py can replay a fixed timestamp
        reports = query_all(asset_id, now)
        if not reports:
            # nobody has ever heard of this asset -- fail honestly rather than guessing
            return {"asset_id": asset_id, "error": "no data from any source"}
        return resolve(reports, now, self.state)
