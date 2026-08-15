# Asset Location Reconciliation Agent

An agent that answers "where is asset X?" by querying multiple sources that
sometimes disagree, deciding which one to trust, and explaining why — with
that trust adjusting over time as sources prove reliable or unreliable.

Built for the LEC AI build assessment.

## The problem this solves

Three systems can report on where a forklift is: a warehouse management
system (WMS), a field technician's last-known-position log, and a manual
paper check-in sheet that gets transcribed. They don't always agree. Naively
trusting the most recent timestamp, or always trusting the "official"
system, both fail in practice — a system can lag, and a fresh manual entry
can still be a typo. This agent scores every report on two signals and
tracks a per-source reliability score that updates every time a conflict is
resolved, so it gets better at knowing which sources to trust as it goes.

## How the decision is made

For every report, the agent computes:

```
trust_score = 0.4 × recency_score + 0.6 × learned_reliability
```

- **`recency_score`** — exponential decay, half-life 60 minutes. A report
  from 2 minutes ago scores ~0.98; from 3 hours ago, ~0.13.
- **`learned_reliability`** — starts at a documented prior per source type
  (WMS 0.75, field tech 0.65, manual sheet 0.55 — structured/audited systems
  are assumed more reliable than handwritten logs, until evidence says
  otherwise) and is updated by an EWMA (α=0.35) every time that source is
  involved in a resolved conflict: it moves toward 1.0 if it agreed with the
  resolution, toward 0.0 if it didn't.

When sources disagree, they're grouped by (location, status); the group
with the highest combined trust score wins, and the agent explains its
reasoning per source (see sample output below).

**Why not just let an LLM decide?** The brief specifically warns against
falling back to a default or guessing. An LLM judging "which of these three
conflicting reports is right" from a prompt is effectively a fancy guess —
it isn't grounded in anything auditable. So the decision is a small,
deterministic, unit-tested function instead, and the explanation it prints
is built directly from the same numbers that drove the decision.

## Why this holds state

`agent/state_store.py` persists learned reliability to a JSON file. That's
what lets a source's track record from *one* query affect a *different*,
later query — including for a completely different asset. That's the part
of the brief I spent the most time on, because "notice a source is
unreliable and adjust future confidence" only means something if the
adjustment survives past a single function call.

## Demo walkthrough

`demo.py` runs four scripted queries against stubbed sources
(`agent/sources.py`) designed to show this end-to-end:

1. **Query 1** (`FORKLIFT-07`) — `manual` disagrees with `wms`/`field_tech`
   and loses. Its reliability drops from 0.55 → 0.36.
2. **Query 2** (`PALLET-JACK-02`) — `manual` disagrees again (different
   asset, reinforcing the pattern). Reliability drops further, to 0.15.
3. **Query 3** (`FORKLIFT-07` again) — `manual`'s report is actually
   **fresher** than `field_tech`'s (20 min old vs 25 min old — recency 0.79
   vs 0.75), but it still loses, because its learned reliability (0.23 at
   that point) drags its trust score down to 0.46 against field_tech's
   0.81. This is the requirement in the brief made concrete: past
   reliability overriding raw recency in a later decision.
4. **Query 4** (`SCISSOR-LIFT-03`) — no conflict: `field_tech` has no data
   for this asset at all (handled as "no data," not as a wrong answer), and
   the two sources that do respond agree.

```
$ python demo.py

===== Query 1: FORKLIFT-07 =====
Conflict detected. Resolved to location='Bay 12', status='in_use'.
  [TRUSTED ] wms         reported 'Bay 12' | recency=0.89 learned_reliability=0.75 -> trust_score=0.81
  [TRUSTED ] field_tech  reported 'Bay 12' | recency=0.50 learned_reliability=0.65 -> trust_score=0.59
  [REJECTED] manual      reported 'Bay 4'  | recency=0.12 learned_reliability=0.55 -> trust_score=0.38
-> Resolved: Bay 12 / in_use

===== Query 3: FORKLIFT-07 =====
Conflict detected. Resolved to location='Bay 9', status='in_use'.
  [TRUSTED ] wms         reported 'Bay 9' | recency=0.98 learned_reliability=0.89 -> trust_score=0.93
  [TRUSTED ] field_tech  reported 'Bay 9' | recency=0.75 learned_reliability=0.85 -> trust_score=0.81
  [REJECTED] manual      reported 'Bay 4' | recency=0.79 learned_reliability=0.23 -> trust_score=0.46
-> Resolved: Bay 9 / in_use

===== Final learned reliability per source =====
  wms         reliability=0.93 (3/3 conflicts agreed)
  field_tech  reliability=0.90 (3/3 conflicts agreed)
  manual      reliability=0.15 (0/3 conflicts agreed)
```

(Full output, all four queries, is in `demo_output.txt`.)

## Running it

```bash
pip install -r requirements.txt   # only needed for pytest
python demo.py                    # deterministic run
python -m pytest tests/ -v        # 6 unit tests
```

No dependencies are required for the agent itself — it's stdlib-only.
`pytest` is only needed for the test suite.

## Assumptions and limitations (honest version)

- **Sources are stubbed**, not real APIs — `agent/sources.py` returns
  scripted data. Swapping in real HTTP calls only touches that one file;
  nothing else in the agent needs to change.
- **The reliability update uses the resolution itself as pseudo-ground-truth**
  (a source is "correct" if it agreed with the winning group). This is a
  reasonable proxy with only 2-3 sources but isn't real ground truth. In
  production I'd reconcile against a periodic audit (e.g. RFID gate scans)
  and use *that* to update reliability instead, which would make the
  learning signal much stronger.
- **The prior weights (0.4 recency / 0.6 reliability, EWMA α=0.35, 60-min
  half-life) are reasonable starting points, not tuned against real data.**
  With historical data I'd fit these instead of hand-picking them.
- **No handling yet for a source going stale identically across all
  reports** (e.g. WMS goes down and returns the same cached answer every
  query) — right now that would look like consistent agreement rather than
  a broken source. Worth adding a staleness/variance check.
- **Single-process state file, not concurrency-safe.** Fine for this demo;
  would move to a real datastore with proper locking for concurrent queries
  in production.

## What I'd do with more time

- Replace the pseudo-ground-truth reliability update with real audit data
  where available, and fall back to it only when audits aren't.
- Add a confidence interval/uncertainty output, not just a point answer —
  "Bay 9, 87% confident" is more useful to a downstream system than a bare
  location string.
- Detect the "all sources are stale together" failure mode described above.

## Project structure

```
lec-asset-agent/
├── agent/
│   ├── trust_engine.py   # scoring + conflict detection + resolution (core logic)
│   ├── state_store.py    # persisted learned reliability
│   ├── sources.py        # stubbed data sources
│   └── agent.py          # orchestrator
├── tests/
│   └── test_trust_engine.py
├── demo.py
└── requirements.txt
```
