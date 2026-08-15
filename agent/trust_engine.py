from dataclasses import dataclass
from datetime import datetime
from math import pow as _pow

# a report loses half its recency weight every 60 minutes
RECENCY_HALF_LIFE_MINUTES = 60.0
RECENCY_WEIGHT = 0.4
RELIABILITY_WEIGHT = 1.0 - RECENCY_WEIGHT
# how fast learned reliability moves toward 0/1 after each conflict
EWMA_ALPHA = 0.35

# starting reliability before we've observed anything, based on how
# structured/audited each source type is (WMS most, manual sheet least)
SOURCE_TYPE_PRIORS = {
    "wms": 0.75,
    "field_tech": 0.65,
    "manual": 0.55,
}


# what a single source says about a single asset at query time
@dataclass
class SourceReport:
    source: str
    asset_id: str
    location: str
    status: str
    timestamp: datetime


# a SourceReport plus the numbers that went into deciding whether to trust it
@dataclass
class ScoredReport:
    report: SourceReport
    recency_score: float
    reliability_score: float
    trust_score: float


def recency_score(report_ts: datetime, now: datetime) -> float:
    # exponential decay -- a fresh report scores near 1.0, an old one decays toward 0
    age_minutes = max((now - report_ts).total_seconds() / 60.0, 0.0)
    return _pow(0.5, age_minutes / RECENCY_HALF_LIFE_MINUTES)


def score_report(report: SourceReport, now: datetime, reliability: float) -> ScoredReport:
    # the actual trust formula: 40% how fresh it is, 60% how often this source
    # has been right before
    r = recency_score(report.timestamp, now)
    trust = RECENCY_WEIGHT * r + RELIABILITY_WEIGHT * reliability
    return ScoredReport(report=report, recency_score=r, reliability_score=reliability, trust_score=trust)


def resolve(reports: list[SourceReport], now: datetime, state):
    # the main entry point: takes every source's report for one asset and
    # returns a single resolved answer plus the reasoning behind it
    if not reports:
        return None

    # look up each source's current learned reliability and score every report
    scored = [score_report(r, now, state.get_reliability(r.source)) for r in reports]

    # group reports that agree on the same (location, status) -- more than
    # one group means the sources are in conflict
    groups: dict[tuple, list[ScoredReport]] = {}
    for s in scored:
        key = (s.report.location, s.report.status)
        groups.setdefault(key, []).append(s)

    conflict = len(groups) > 1

    if not conflict:
        winning_key = next(iter(groups))
    else:
        # the winning answer is whichever group has the highest combined
        # trust score, not just whichever has the most sources
        winning_key = max(groups, key=lambda k: sum(s.trust_score for s in groups[k]))

    winners = groups[winning_key]
    # everything in a losing group, flattened into one list
    losers = [s for key, members in groups.items() if key != winning_key for s in members]

    # only update reliability when there was actually something to agree or
    # disagree on -- no conflict means no evidence either way
    if conflict:
        for s in winners:
            state.update_reliability(s.report.source, agreed=True)
        for s in losers:
            state.update_reliability(s.report.source, agreed=False)

    explanation = build_explanation(winning_key, winners, losers, conflict)

    return {
        "asset_id": reports[0].asset_id,
        "resolved_location": winning_key[0],
        "resolved_status": winning_key[1],
        "conflict_detected": conflict,
        "winners": winners,
        "losers": losers,
        "explanation": explanation,
    }


def build_explanation(winning_key, winners, losers, conflict) -> str:
    # turns the resolution into a human-readable audit trail -- this is the
    # string demo.py prints, so every number a person sees traces back to
    # an actual score computed above, nothing is summarized away
    if not conflict:
        sources = ", ".join(s.report.source for s in winners)
        return (
            f"No conflict: {sources} agree on location='{winning_key[0]}', "
            f"status='{winning_key[1]}'."
        )

    lines = [f"Conflict detected. Resolved to location='{winning_key[0]}', status='{winning_key[1]}'."]
    # highest trust first, so the reader sees the winning case before the rejected ones
    for s in sorted(winners + losers, key=lambda s: -s.trust_score):
        verdict = "TRUSTED " if s in winners else "REJECTED"
        lines.append(
            f"  [{verdict}] {s.report.source:<11} reported '{s.report.location}' "
            f"| recency={s.recency_score:.2f} learned_reliability={s.reliability_score:.2f} "
            f"-> trust_score={s.trust_score:.2f}"
        )
    return "\n".join(lines)
