from datetime import datetime

from agent import AssetLocationAgent

# fixed instead of datetime.now() so every run produces identical,
# reproducible output -- the "10 minutes ago" in sources.py always means
# the same wall-clock time
NOW = datetime(2026, 8, 13, 15, 0, 0)

# query 1 & 2: manual disagrees and loses, twice, on two different assets.
# query 3: manual disagrees a third time on the SAME asset as query 1, but
# is now heavily discounted despite a fresher timestamp.
# query 4: no conflict, and field_tech has no data at all -- a sanity check
# that a missing source is handled as "no data", not as a wrong answer.
QUERIES = [
    "FORKLIFT-07",
    "PALLET-JACK-02",
    "FORKLIFT-07",
    "SCISSOR-LIFT-03",
]


def main():
    # fresh state file per demo run so the walkthrough always starts from
    # the same priors, separate from agent_state.json used elsewhere
    agent = AssetLocationAgent(state_path="demo_state.json")

    for i, asset_id in enumerate(QUERIES, start=1):
        print(f"\n===== Query {i}: {asset_id} =====")
        result = agent.query(asset_id, now=NOW)
        print(result["explanation"])
        print(f"-> Resolved: {result['resolved_location']} / {result['resolved_status']}")

    # proof that reliability actually moved over the course of the demo
    print("\n===== Final learned reliability per source =====")
    for source, entry in agent.state.snapshot().items():
        print(
            f"  {source:<11} reliability={entry['reliability']:.2f} "
            f"({entry['n_agreed']}/{entry['n_conflicts']} conflicts agreed)"
        )


if __name__ == "__main__":
    main()
