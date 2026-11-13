"""#347 / ANOS-13: reuse preflight over the existing immutable research cache.

Tests exercise ``ImmutableCache``, ``assess_reuse``, ``pm_operations.cli``,
``pm_capabilities``, ``pm_cwsa_chapter2_gate``, and
``pm_cwsa_chapter2_projection`` directly. No network, broker, wallet_store or
private data is used.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from copytrade_pm import (
    pm_capabilities as capabilities,
    pm_cwsa_chapter2_gate as gate,
    pm_cwsa_chapter2_projection as projection,
    pm_operations,
)
from copytrade_pm.pm_offline_cache import ImmutableCache
from copytrade_pm.pm_offline_job import REPORT
from copytrade_pm.pm_offline_job_catalog import (
    COVERAGE_RECEIPT_SCHEMA,
    assess_reuse,
    list_reports,
)

START = "2026-10-20T00:00:00+00:00"
MID = "2026-10-20T12:00:00+00:00"
END = "2026-10-21T00:00:00+00:00"
KNOWN_BEFORE = "2026-10-19T00:00:00+00:00"
KNOWN_AFTER = "2026-10-22T00:00:00+00:00"
AS_OF = "2026-10-25T00:00:00+00:00"
COHORT = "reservoir-5w"
WALLETS = ["0xaaa", "0xbbb"]
DEXES = ["main", "xyz"]
POLICY = "PER_FILL_ELIGIBILITY"
COST = "HL_TAKER_4_5BPS"
FORBIDDEN_AUTHORITY = (
    "fresh_account_balance",
    "fresh_quote",
    "halt_clearance",
    "copy_mandate",
    "paper_financial_proof",
    "trading_authorization",
)


def sha(label: str) -> str:
    return sha256(label.encode()).hexdigest()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def snapshot(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def artifact_binding(
    *,
    cohort: str = COHORT,
    wallets: list[str] = WALLETS,
    dexes: list[str] = DEXES,
    utc_start: str = START,
    utc_end: str = END,
    as_of: str = AS_OF,
    job: str = "job-1",
    input_: str = "input-1",
    source: str = "source-1",
    market: str = "market-1",
    software: str = "software-1",
    cost_assumption: str | dict = COST,
    policy: str = POLICY,
    report_schema: str = REPORT,
) -> str:
    scope = {
        "cohort": cohort,
        "wallets": sorted(set(wallets)),
        "dexes": sorted(set(dexes)),
        "utc_start": utc_start,
        "utc_end": utc_end,
        "as_of": as_of,
        "job_sha256": sha(job),
        "input_sha256": sha(input_),
        "source_sha256": sha(source),
        "market_sha256": sha(market),
        "software_sha256": sha(software),
        "cost_assumption": cost_assumption,
        "policy": policy,
        "report_schema": report_schema,
    }
    return sha256(canonical_bytes(scope)).hexdigest()


def publish_report(
    root: Path,
    *,
    job: str = "job-1",
    input_: str = "input-1",
    source: str = "source-1",
    market: str = "market-1",
    software: str = "software-1",
    cohort: str = COHORT,
    wallets: list[str] = WALLETS,
    dexes: list[str] = DEXES,
    utc_start: str = START,
    utc_end: str = END,
    as_of: str = AS_OF,
    cost_assumption: str | dict = COST,
    status: str = "COMPLETE_HISTORICAL_ORACLE_SCREEN_ONLY",
    clock_basis: str = "HISTORICAL_ORACLE",
    selection_known_at: str | None = KNOWN_BEFORE,
    policy: str = POLICY,
    study: str = "study-1",
    legacy_unbound: bool = False,
    legacy_key: bool = False,
    supersedes: list[str] | None = None,
    depends_on_cache_keys: list[str] | None = None,
) -> str:
    deps = {
        "job": sha(job),
        "input": sha(input_),
        "market": sha(market),
        "software": sha(software),
    }
    doc: dict = {
        "schema": REPORT,
        "job_id": study,
        "job_sha256": deps["job"],
        "job_kind": "HISTORICAL_ORACLE_NATIVE",
        "clock_basis": clock_basis,
        "policy": policy,
        "status": status,
        "financial_status": "BLOCKED_MISSING_ATOMIC_BOOK_ASOF_NAV_AND_REAL_FIRST_KNOWN",
        "financial_certified_real": False,
        "scientifically_qualified": False,
        "authorized_for_trading": False,
        "deployed": False,
        "blockers": ["NO_INDEPENDENT_FIRST_KNOWN"],
        "engineering_path_verified": True,
    }
    if not legacy_unbound:
        doc.update(
            {
                "cohort": cohort,
                "wallets": sorted(set(wallets)),
                "dexes": sorted(set(dexes)),
                "utc_start": utc_start,
                "utc_end": utc_end,
                "as_of": as_of,
                "source_sha256": sha(source),
                "cost_assumption": cost_assumption,
                "selection_known_at": selection_known_at,
            }
        )
    if supersedes is not None:
        doc["supersedes"] = supersedes
    if depends_on_cache_keys is not None:
        doc["depends_on_cache_keys"] = depends_on_cache_keys
    if not (legacy_unbound or legacy_key):
        deps["source"] = sha(source)
        deps["scope"] = artifact_binding(
            cohort=cohort,
            wallets=wallets,
            dexes=dexes,
            utc_start=utc_start,
            utc_end=utc_end,
            as_of=as_of,
            job=job,
            input_=input_,
            source=source,
            market=market,
            software=software,
            cost_assumption=cost_assumption,
            policy=policy,
            report_schema=REPORT,
        )
    return ImmutableCache(root, min_free_bytes=0).publish(
        "job_report", deps, version=REPORT, content=canonical_bytes(doc)
    )["key"]


def publish_coverage_receipt(
    root: Path,
    *,
    wallet: str,
    dex: str,
    utc_start: str = START,
    utc_end: str = END,
    known_at: str = START,
    input_: str = "input-1",
    source: str = "source-1",
    collected: bool = True,
    blocked: bool = False,
    source_verified: bool = True,
    empty_verified: bool = False,
    row_count: int = 12,
) -> str:
    payload = {
        "schema": COVERAGE_RECEIPT_SCHEMA,
        "wallet": wallet,
        "dex": dex,
        "utc_start": utc_start,
        "utc_end": utc_end,
        "known_at": known_at,
        "input_sha256": sha(input_),
        "source_sha256": sha(source),
        "collected": collected,
        "blocked": blocked,
        "source_verified": source_verified,
        "empty_verified": empty_verified,
        "row_count": row_count,
    }
    scope_digest = sha256(canonical_bytes(payload)).hexdigest()
    deps = {"input": sha(input_), "source": sha(source), "span": scope_digest}
    return ImmutableCache(root, min_free_bytes=0).publish(
        "coverage_receipt",
        deps,
        version=COVERAGE_RECEIPT_SCHEMA,
        content=canonical_bytes(payload),
    )["key"]


def publish_full_coverage(
    root: Path,
    *,
    wallets: list[str] = WALLETS,
    dexes: list[str] = DEXES,
    utc_start: str = START,
    utc_end: str = END,
    known_at: str = START,
    input_: str = "input-1",
    source: str = "source-1",
    collected: bool = True,
    blocked: bool = False,
    source_verified: bool = True,
    empty_verified: bool = False,
    row_count: int = 12,
) -> list[str]:
    return [
        publish_coverage_receipt(
            root,
            wallet=w,
            dex=d,
            utc_start=utc_start,
            utc_end=utc_end,
            known_at=known_at,
            input_=input_,
            source=source,
            collected=collected,
            blocked=blocked,
            source_verified=source_verified,
            empty_verified=empty_verified,
            row_count=row_count,
        )
        for w in wallets
        for d in dexes
    ]


def request(root: Path | None = None, *, receipts: list[str] | None = None, **override) -> dict:
    cov = (
        receipts
        if receipts is not None
        else (publish_full_coverage(root) if root is not None else [])
    )
    base = {
        "cohort": COHORT,
        "wallets": list(WALLETS),
        "dexes": list(DEXES),
        "utc_start": START,
        "utc_end": END,
        "as_of": AS_OF,
        "selection_known_at": KNOWN_BEFORE,
        "job_sha256": sha("job-1"),
        "input_sha256": sha("input-1"),
        "source_sha256": sha("source-1"),
        "market_sha256": sha("market-1"),
        "software_sha256": sha("software-1"),
        "cost_assumption": COST,
        "report_schema": REPORT,
        "policy": POLICY,
        "coverage_receipts": cov,
    }
    base.update(override)
    return base


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "cache"
    ImmutableCache(path, min_free_bytes=0)
    return path


def test_verified_hit_binds_scope_and_grants_no_authority(root: Path) -> None:
    key = publish_report(root)
    cov = publish_full_coverage(root)
    before = snapshot(root)
    out = assess_reuse(root, request(receipts=cov))
    assert out["state"] == "VERIFIED_CACHE_HIT"
    assert out["reusable"] is True and out["acquisition_needed"] is False
    assert out["cache_key"] == key and out["report"]["cache_key"] == key
    assert out["report"]["input_binding_sha256"] == sha("input-1")
    assert out["report"]["market_binding_sha256"] == sha("market-1")
    assert out["report"]["source_sha256"] == sha("source-1")
    assert out["report"]["cohort"] == COHORT
    assert out["report"]["cost_assumption"] == COST
    assert out["coverage_basis"] == "SHA_VERIFIED_IMMUTABLE_COVERAGE_RECEIPTS"
    assert out["coverage_summary"]["verified_data_receipts"] == 4
    assert out["pit"]["status"] == "SELECTION_KNOWN_BEFORE_WINDOW"
    assert out["pit"]["prospective_first_known_event_inferred"] is False
    assert out["pit"]["executable_follower_pnl"] is False
    assert all(out["authority"][name] is False for name in FORBIDDEN_AUTHORITY)
    assert out["scientifically_qualified"] is False and out["trading_authorized"] is False
    assert snapshot(root) == before


@pytest.mark.parametrize(
    "override",
    [
        {"cohort": "other-cohort"},
        {"wallets": ["0xaaa"]},
        {"dexes": ["main"]},
        {"utc_start": MID},
        {"utc_end": MID},
        {"as_of": "2026-10-26T00:00:00+00:00"},
        {"source_sha256": sha("source-2")},
        {"market_sha256": sha("market-2")},
        {"software_sha256": sha("software-2")},
        {"cost_assumption": {"maker_bps": 1.0, "taker_bps": 3.5}},
        {"policy": "OTHER_POLICY"},
        {"report_schema": "pm_offline_research_job_report_v2"},
    ],
)
def test_every_bound_dimension_invalidates_when_changed(root: Path, override: dict) -> None:
    publish_report(root)
    cov = publish_full_coverage(root)
    base = assess_reuse(root, request(receipts=cov))
    assert base["state"] == "VERIFIED_CACHE_HIT"
    receipts = (
        publish_full_coverage(root, source="source-2") if "source_sha256" in override else cov
    )
    out = assess_reuse(root, request(receipts=receipts, **override))
    assert out["state"] == "INVALIDATED_BINDING_CHANGED"
    assert out["reusable"] is False and out["acquisition_needed"] is True
    assert out["request_binding_sha256"] != base["request_binding_sha256"]
    if "source_sha256" in override:
        assert assess_reuse(root, request(receipts=cov, **override))["state"] == (
            "INCOMPLETE_WALLET_DEX_SCOPE"
        )


def test_unbound_legacy_report_and_legacy_key_mismatch_never_hit(root: Path) -> None:
    legacy_key = publish_report(root, legacy_unbound=True)
    cov = publish_full_coverage(root)
    out = assess_reuse(root, request(receipts=cov))
    assert out["state"] == "INVALIDATED_BINDING_CHANGED"
    assert out["reusable"] is False and out["cache_key"] == legacy_key
    assert set(out["mismatch_fields"]) >= {
        "as_of",
        "cohort",
        "cost_assumption",
        "dexes",
        "source_sha256",
        "utc_end",
        "utc_start",
        "wallets",
    }
    # Even a legacy-keyed report carrying a different policy or cohort is checked field-by-field.
    other_root = root.parent / "other_cache"
    cov2 = publish_full_coverage(other_root)
    publish_report(other_root, policy="DIFFERENT_POLICY", legacy_key=True)
    out2 = assess_reuse(other_root, request(receipts=cov2))
    assert out2["state"] == "INVALIDATED_BINDING_CHANGED"
    assert "policy" in out2["mismatch_fields"]


@pytest.mark.parametrize(
    "bad",
    [
        {"cohort": ""},
        {"wallets": []},
        {"wallets": ["0xAaA", "0xbbb"]},  # unnormalized mixed hex rejected
        {"wallets": ["0Xaaa", "0xbbb"]},
        {"dexes": []},
        {"utc_start": "2026-10-20T00:00:00"},  # naive clock
        {"as_of": "2026-10-20T06:00:00+00:00"},  # as-of before window end
        {"utc_end": START},  # empty window
        {"input_sha256": "not-a-sha"},
        {"source_sha256": "not-a-sha"},
        {"cost_assumption": ""},
        {"purpose": "SOMETHING_ELSE"},
        {"require_pit": "yes"},
        {"coverage_receipts": ["not-a-sha"]},
    ],
)
def test_malformed_or_unnormalized_request_fails_before_cache_access(root: Path, bad: dict) -> None:
    publish_report(root)
    cov = publish_full_coverage(root)
    with pytest.raises(ValueError):
        assess_reuse(root, request(receipts=cov, **bad))


def test_verified_empty_vs_unverified_empty_vs_uncollected(root: Path) -> None:
    verified_empty = publish_full_coverage(
        root, row_count=0, source_verified=True, empty_verified=True
    )
    out_empty = assess_reuse(root, request(receipts=verified_empty))
    assert out_empty["state"] == "VERIFIED_EMPTY"
    assert out_empty["acquisition_needed"] is False and out_empty["reusable"] is False
    assert out_empty["report"] is None

    # row_count=0 without empty_verified/source_verified must never count as VERIFIED_EMPTY!
    for bad_empty in (
        {"row_count": 0, "source_verified": False, "empty_verified": True},
        {"row_count": 0, "source_verified": True, "empty_verified": False},
        {"row_count": 0, "collected": False, "source_verified": True, "empty_verified": True},
        {"row_count": 0, "blocked": True, "source_verified": True, "empty_verified": True},
        {"row_count": 10, "source_verified": False},
    ):
        receipts = publish_full_coverage(root, **bad_empty)
        out = assess_reuse(root, request(receipts=receipts))
        assert out["state"] == "UNCOLLECTED_OR_BLOCKED_PERIOD"
        assert out["reusable"] is False and out["acquisition_needed"] is True

    # Contradictory receipt (positive rows claiming empty_verified=True) fails closed as CORRUPT.
    impossible = publish_full_coverage(root, row_count=5, source_verified=True, empty_verified=True)
    assert assess_reuse(root, request(receipts=impossible))["state"] == "CORRUPT_RECEIPT"

    # Empty list of receipts means uncollected.
    assert assess_reuse(root, request(receipts=[]))["state"] == "UNCOLLECTED_OR_BLOCKED_PERIOD"


def test_incomplete_wallet_dex_or_pit_coverage_blocks_reuse(root: Path) -> None:
    publish_report(root)
    full = publish_full_coverage(root)
    assert assess_reuse(root, request(receipts=full))["state"] == "VERIFIED_CACHE_HIT"

    # Drop one (wallet, dex) pair (partial DEX coverage must not count for whole scope)
    dropped = full[:-1]
    # Half period for one wallet
    half = [
        publish_coverage_receipt(root, wallet=w, dex=d, utc_end=MID if w == "0xaaa" else END)
        for w in WALLETS
        for d in DEXES
    ]
    # Wrong input_sha256 on xyz
    foreign_input = [
        publish_coverage_receipt(
            root, wallet=w, dex=d, input_="other-input" if d == "xyz" else "input-1"
        )
        for w in WALLETS
        for d in DEXES
    ]
    # Wrong source_sha256 on xyz
    foreign_source = [
        publish_coverage_receipt(
            root, wallet=w, dex=d, source="other-source" if d == "xyz" else "source-1"
        )
        for w in WALLETS
        for d in DEXES
    ]
    # Learned after as_of cutoff
    late_known = [
        publish_coverage_receipt(
            root, wallet=w, dex=d, known_at=KNOWN_AFTER if d == "xyz" else START
        )
        for w in WALLETS
        for d in DEXES
    ]
    for bad_receipts in (dropped, half, foreign_input, foreign_source, late_known):
        out = assess_reuse(root, request(receipts=bad_receipts, as_of="2026-10-21T12:00:00+00:00"))
        assert out["state"] == "INCOMPLETE_WALLET_DEX_SCOPE"
        assert out["reusable"] is False and out["acquisition_needed"] is True


def test_corrupt_report_or_coverage_receipt_is_isolated(root: Path) -> None:
    key = publish_report(root)
    other = publish_report(root, job="job-2", study="study-2")
    cov = publish_full_coverage(root)
    # Tamper requested job_report payload.
    payload = root / "job_report" / key[:2] / f"{key}.data"
    payload.write_bytes(payload.read_bytes() + b"\n")
    out = assess_reuse(root, request(receipts=cov))
    assert out["state"] == "CORRUPT_RECEIPT" and out["reusable"] is False

    # Other clean report unaffected, while list_reports keeps failing closed on job_report corruption.
    good = publish_report(root, job="job-1", software="software-3")
    assert (
        assess_reuse(root, request(receipts=cov, software_sha256=sha("software-3")))["state"]
        == "VERIFIED_CACHE_HIT"
    )
    assert good != key and other != key
    with pytest.raises(ValueError):
        list_reports(root)

    # Now isolate a tampered coverage receipt from a clean request using good coverage receipts.
    cov_tamper = publish_coverage_receipt(root, wallet="0xaaa", dex="main", row_count=99)
    cov_path = root / "coverage_receipt" / cov_tamper[:2] / f"{cov_tamper}.data"
    cov_path.write_bytes(b"{corrupt")
    tampered_list = [cov_tamper, *cov[1:]]
    assert (
        assess_reuse(root, request(receipts=tampered_list, software_sha256=sha("software-3")))[
            "state"
        ]
        == "CORRUPT_RECEIPT"
    )
    # An uncited corrupt coverage receipt on disk never poisons a verified clean request.
    assert (
        assess_reuse(root, request(receipts=cov, software_sha256=sha("software-3")))["state"]
        == "VERIFIED_CACHE_HIT"
    )


@pytest.mark.parametrize("damage", ["manifest_garbage", "manifest_oversized", "orphan_payload"])
def test_damage_at_requested_report_key_is_corrupt_not_miss(root: Path, damage: str) -> None:
    key = publish_report(root)
    cov = publish_full_coverage(root)
    folder = root / "job_report" / key[:2]
    manifest, payload = folder / f"{key}.manifest.json", folder / f"{key}.data"
    if damage == "manifest_garbage":
        manifest.write_bytes(b"{not json")
    elif damage == "manifest_oversized":
        manifest.write_bytes(b" " * (64 * 1024 + 1))
    else:
        manifest.unlink()
    assert payload.exists()
    out = assess_reuse(root, request(receipts=cov))
    assert out["state"] == "CORRUPT_RECEIPT" and out["reusable"] is False


def test_pit_flags_require_pit_block_and_dishonest_prospective_claim(root: Path) -> None:
    cov = publish_full_coverage(root)
    publish_report(root, selection_known_at=KNOWN_AFTER)
    for known in (KNOWN_AFTER, None):
        out = assess_reuse(root, request(receipts=cov, selection_known_at=known))
        assert out["state"] == "VERIFIED_CACHE_HIT"
        assert out["pit"]["status"] == "EX_POST_FIXED_COHORT_NOT_PIT"
        assert out["reusable_as"] == "EX_POST_RESEARCH_EVIDENCE_ONLY"
        assert out["pit"]["prospective_first_known_event_inferred"] is False
        assert out["pit"]["executable_follower_pnl"] is False
        blocked = assess_reuse(
            root, request(receipts=cov, selection_known_at=known, require_pit=True)
        )
        assert blocked["state"] == "BLOCKED_EX_POST_COHORT_NOT_PIT"
        assert blocked["reusable"] is False and blocked["acquisition_needed"] is True

    # Boundary: selection_known_at == utc_start is NOT ex-post.
    assert (
        assess_reuse(root, request(receipts=cov, selection_known_at=START))["reusable_as"]
        == "RESEARCH_EVIDENCE_ONLY"
    )

    # Falsifier: a report claiming PROSPECTIVE_FIRST_KNOWN for an ex-post window fails closed.
    bad_root = root.parent / "bad_pit_cache"
    cov_bad = publish_full_coverage(bad_root)
    publish_report(bad_root, clock_basis="PROSPECTIVE_FIRST_KNOWN", selection_known_at=KNOWN_AFTER)
    assert (
        assess_reuse(bad_root, request(receipts=cov_bad, selection_known_at=KNOWN_AFTER))["state"]
        == "CORRUPT_RECEIPT"
    )


def test_trial_history_retention_and_explicit_supersedes_dependents(root: Path) -> None:
    # Real repo research statuses preserved alongside explicit supersedes & depends_on_cache_keys.
    old = publish_report(root, input_="input-v1", status="PARTIAL_ENGINEERING_FIXTURE_BLOCKED")
    mid = publish_report(
        root, input_="input-v2", status="COMPLETE_ENGINEERING_FIXTURE", supersedes=[old]
    )
    current = publish_report(root, supersedes=[old, mid])
    downstream = publish_report(
        root,
        job="job-downstream",
        input_="input-1",
        depends_on_cache_keys=[mid],
        study="study-downstream",
    )
    unrelated = publish_report(
        root,
        job="job-third",
        input_="input-unrelated",
        market="market-unrelated",
        source="source-unrelated",
        study="s3",
    )
    cov = publish_full_coverage(root)
    before = snapshot(root)
    out = assess_reuse(root, request(receipts=cov))
    assert out["state"] == "VERIFIED_CACHE_HIT" and out["cache_key"] == current
    history = {p["cache_key"]: (p["research_status"], p["relation"]) for p in out["prior_reports"]}
    assert history == {
        old: ("PARTIAL_ENGINEERING_FIXTURE_BLOCKED", "SUPERSEDED"),
        mid: ("COMPLETE_ENGINEERING_FIXTURE", "SUPERSEDED"),
    }
    refresh = {d["cache_key"]: d["reason"] for d in out["dependent_results_needing_refresh"]}
    assert refresh == {downstream: "DEPENDS_ON_SUPERSEDED_OR_STALE_REPORT"}
    assert unrelated not in refresh
    assert snapshot(root) == before


def test_changed_input_exposes_dependents_without_mutation(root: Path) -> None:
    old = publish_report(root, input_="input-OLD", study="study-old")
    dependent = publish_report(root, job="job-other", input_="input-OLD", study="study-dep")
    unrelated = publish_report(
        root,
        job="job-third",
        input_="input-UNRELATED",
        market="m3",
        source="s3",
        study="s3",
    )
    cov = publish_full_coverage(root)
    before = snapshot(root)
    out = assess_reuse(root, request(receipts=cov))
    assert out["state"] == "INVALIDATED_BINDING_CHANGED"
    assert out["reusable"] is False and out["acquisition_needed"] is True
    assert [p["cache_key"] for p in out["prior_reports"]] == [old]
    assert {"input", "scope"} <= set(out["prior_reports"][0]["changed_dependencies"])
    refresh = {d["cache_key"] for d in out["dependent_results_needing_refresh"]}
    assert dependent in refresh and old not in refresh and unrelated not in refresh
    assert snapshot(root) == before


@pytest.mark.parametrize(
    "purpose",
    [
        "ACCOUNT_BALANCE",
        "QUOTE",
        "HALT_CLEARANCE",
        "COPY_MANDATE",
        "PAPER_FINANCIAL_PROOF",
        "TRADING_AUTHORIZATION",
    ],
)
def test_reusable_read_evidence_cannot_serve_fresh_or_authoritative_purposes(
    root: Path, purpose: str
) -> None:
    publish_report(root)
    cov = publish_full_coverage(root)
    assert assess_reuse(root, request(receipts=cov))["state"] == "VERIFIED_CACHE_HIT"
    out = assess_reuse(root, request(receipts=cov, purpose=purpose))
    assert out["state"] == "REFUSED_NOT_REUSABLE_FOR_PURPOSE"
    assert out["reusable"] is False and out["acquisition_needed"] is None
    assert all(out["authority"][name] is False for name in FORBIDDEN_AUTHORITY)


def test_adjacent_spans_mid_window_gap_and_blocked_overlap(root: Path) -> None:
    publish_report(root)
    split_mixed = []
    for w in WALLETS:
        for d in DEXES:
            split_mixed.append(publish_coverage_receipt(root, wallet=w, dex=d, utc_end=MID))
            split_mixed.append(
                publish_coverage_receipt(
                    root,
                    wallet=w,
                    dex=d,
                    utc_start=MID,
                    row_count=0,
                    source_verified=True,
                    empty_verified=True,
                )
            )
    assert assess_reuse(root, request(receipts=split_mixed))["state"] == "VERIFIED_CACHE_HIT"

    gap = [
        c
        for w in WALLETS
        for d in DEXES
        for c in (
            publish_coverage_receipt(root, wallet=w, dex=d, utc_end="2026-10-20T06:00:00+00:00"),
            publish_coverage_receipt(root, wallet=w, dex=d, utc_start="2026-10-20T07:00:00+00:00"),
        )
    ]
    assert assess_reuse(root, request(receipts=gap))["state"] == "INCOMPLETE_WALLET_DEX_SCOPE"

    full = publish_full_coverage(root)
    overlap = full + [
        publish_coverage_receipt(root, wallet="0xaaa", dex="main", utc_start=MID, blocked=True)
    ]
    assert assess_reuse(root, request(receipts=overlap))["state"] == "UNCOLLECTED_OR_BLOCKED_PERIOD"


def test_unrelated_malformed_entries_history_truncation_and_public_list(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from copytrade_pm import pm_offline_job_catalog as owner

    key = publish_report(root)
    cov = publish_full_coverage(root)
    assert "policy" not in list_reports(root)["reports"][0]

    stale = publish_report(root, input_="input-OLD")
    folder = root / "job_report" / stale[:2]
    manifest = folder / f"{stale}.manifest.json"
    doc = json.loads(manifest.read_text())
    doc["dependencies"]["input"] = ["unhashable"]
    manifest.write_bytes(json.dumps(doc).encode())
    (root / "job_report" / "zz-stray").mkdir()
    (root / "job_report" / "zz-stray").chmod(0o755)
    out = assess_reuse(root, request(receipts=cov))
    assert out["state"] == "VERIFIED_CACHE_HIT" and out["cache_key"] == key
    assert out["history_scan_complete"] is False

    trunc_root = root.parent / "trunc_cache"
    cov_trunc = publish_full_coverage(trunc_root)
    monkeypatch.setattr(owner, "HISTORY_LIMIT", 2)
    for n in range(4):
        publish_report(trunc_root, input_=f"input-old-{n}")
    trunc_out = assess_reuse(trunc_root, request(receipts=cov_trunc))
    assert len(trunc_out["prior_reports"]) == 2 and trunc_out["prior_reports_truncated"] is True


def test_cli_research_preflight_and_capability_discovery(
    root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    val = capabilities.validate(Path(__file__).resolve().parents[1])
    assert val["status"] == "VERIFIED" and val["errors"] == []

    assert pm_operations.cli(["capabilities", "show", "research.preflight", "--json"]) == 0
    cap_doc = json.loads(capsys.readouterr().out)
    assert cap_doc["classification"] == "READ_ONLY"
    assert cap_doc["runtime_required_arguments"] == ["--cache-root PATH", "--request PATH"]

    # Missing required runtime arguments return UNKNOWN + exit 2.
    assert pm_operations.cli(["research", "preflight"]) == 2
    assert (
        json.loads(capsys.readouterr().out)["error_code"] == "EXPLICIT_RESEARCH_CACHE_ROOT_REQUIRED"
    )
    assert pm_operations.cli(["research", "preflight", "--cache-root", str(root)]) == 2
    assert (
        json.loads(capsys.readouterr().out)["error_code"]
        == "EXPLICIT_PREFLIGHT_REQUEST_PATH_REQUIRED"
    )

    cov = publish_full_coverage(root)
    publish_report(root)
    req_file = tmp_path / "req.json"
    req_file.write_text(json.dumps(request(receipts=cov)))
    before = snapshot(root)

    # Verified hit returns exit 0 and grants zero authority.
    assert (
        pm_operations.cli(
            ["research", "preflight", "--cache-root", str(root), "--request", str(req_file)]
        )
        == 0
    )
    hit = json.loads(capsys.readouterr().out)
    assert hit["status"] == "VERIFIED" and hit["data"]["reusable"] is True
    assert hit["data"]["trading_authorized"] is False

    # Trading authorization purpose or --require-pit on ex-post cohort fails closed (exit 2).
    assert (
        pm_operations.cli(
            [
                "research",
                "preflight",
                "--cache-root",
                str(root),
                "--request",
                str(req_file),
                "--purpose",
                "TRADING_AUTHORIZATION",
            ]
        )
        == 2
    )
    refused = json.loads(capsys.readouterr().out)
    assert (
        refused["status"] == "BLOCKED"
        and refused["error_code"] == "REFUSED_NOT_REUSABLE_FOR_PURPOSE"
    )

    req_ex_post = tmp_path / "req_ex_post.json"
    req_ex_post.write_text(json.dumps(request(receipts=cov, selection_known_at=KNOWN_AFTER)))
    assert (
        pm_operations.cli(
            [
                "research",
                "preflight",
                "--cache-root",
                str(root),
                "--request",
                str(req_ex_post),
                "--require-pit",
            ]
        )
        == 2
    )
    pit_blocked = json.loads(capsys.readouterr().out)
    assert (
        pit_blocked["status"] == "BLOCKED"
        and pit_blocked["error_code"] == "BLOCKED_EX_POST_COHORT_NOT_PIT"
    )

    # Symlink request JSON fails closed.
    bad_link = tmp_path / "symlink_req.json"
    bad_link.symlink_to(req_file)
    assert (
        pm_operations.cli(
            ["research", "preflight", "--cache-root", str(root), "--request", str(bad_link)]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED"
    assert snapshot(root) == before


def test_reusable_research_never_bypasses_chapter2_gates_or_projection(root: Path) -> None:
    publish_report(root)
    cov = publish_full_coverage(root)
    reuse = assess_reuse(root, request(receipts=cov))
    assert reuse["state"] == "VERIFIED_CACHE_HIT" and reuse["reusable"] is True

    # Falsifier 1: runtime financial admission still requires signed independent paper effects.
    fin = gate.assess_financial_runtime(
        service_active=True,
        signed_portfolios=set(),
        finance_scans={},
        source_changes={"A": 100},
        journal_cursors={"A": 100},
        latest_source_checkpoint_ms=100,
        modeled_effects={"A": 0},
    )
    assert fin.state != "PASS"
    decision = gate.decide(
        "premerge", [gate.GateCheck("research_reuse_preflight", "PASS", "OK"), fin]
    )
    assert decision["verdict"] != "PASS"

    # Falsifier 2: portfolio roster admission rejects partial rosters even with reusable research.
    roster = gate.assess_portfolio_roster({"A": {"W083"}})
    assert roster.state == "FAIL"

    # Falsifier 3: projection never marks financial_status VERIFIED or trading_authorized True without
    # independent verified_finance and qualified_k.
    source_summary = {
        "source_count": len(gate.EXPECTED_WALLETS),
        "latest_kinds": {member: "BASELINE" for member in gate.EXPECTED_WALLETS},
        "head_sha256": sha("head"),
        "latest_checkpoint_ms": 1_000,
    }
    proj = projection.project(
        source=source_summary,
        papers={},
        verified_finance=set(),
        qualified_k=set(),
        release_sha="0" * 40,
        epoch="2026-11-12",
    )
    assert proj["trading_authorized"] is False and proj["scientifically_qualified"] is False
    assert all(
        row["financial_admission"] == "BLOCKED_EVIDENCE" and row["trading_authorized"] is False
        for row in proj["portfolios"].values()
    )
