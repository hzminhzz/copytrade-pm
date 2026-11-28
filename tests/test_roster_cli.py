"""End-to-end proofs for ``copytrade-pm facts|research|roster|paper|release``.

Every command is driven through the real parser and the real store in a
temporary directory. Signing is exercised with throwaway Ed25519 keys; no
private registry, journal, service or secret is read.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from copytrade_pm import pm_capabilities as capabilities
from copytrade_pm.pm_operations import cli
from copytrade_pm.roster import digest

NOW = 1_800_000_000_000
NOW_ISO = datetime.fromtimestamp(NOW / 1000, UTC).isoformat()
LATER_ISO = (datetime.fromtimestamp(NOW / 1000, UTC) + timedelta(hours=1)).isoformat()
WALLETS = tuple("0x" + f"{index:02x}" * 20 for index in range(1, 6))
CHECKPOINT_POLICY = {
    "name": "cwsa_utc_5m_v3",
    "limits": {
        "max_state_age_ms": 90_000,
        "max_acquisition_ms": 30_000,
        "max_dex_skew_ms": 5_000,
        "publication_grace_ms": 30_000,
    },
    "measurement_sha": digest(["measurement"]),
}
EPOCH = digest(CHECKPOINT_POLICY)
MARKET = "hyperliquid/mainnet:perp:BTC/USD"


def run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, dict]:
    code = cli(argv)
    out = capsys.readouterr().out
    payload = json.loads(out[out.index("{") :]) if "{" in out else {}
    return code, payload


def test_capture_health_requires_apply(monkeypatch, capsys):
    from copytrade_pm import wallet_health_official

    calls = []

    def capture(args):
        calls.append(args)
        return 0

    monkeypatch.setattr(wallet_health_official, "run", capture)
    command = ["facts", "capture-health", "--no-raw-archive"]
    for flags in ([], ["--apply", "--dry-run"]):
        code, response = run(command + flags, capsys)
        assert code == 0
        assert response == {"state": "DRY_RUN", "trading_authorized": False}
    assert calls == []
    assert cli(command + ["--apply"]) == 0
    assert len(calls) == 1
    assert calls[0].no_raw_archive


def register(tmp_path: Path, capsys: pytest.CaptureFixture[str], *, apply: bool = True) -> Path:
    store = tmp_path / "roster.sqlite"
    argv = [
        "roster",
        "register",
        "--store",
        str(store),
        "--account",
        "cft-10k-paper",
        "--seat",
        "seat_1:200:0.45",
        "--seat",
        "seat_2:200:0.45",
        "--policy-epoch",
        EPOCH,
    ]
    code, _ = run(argv + (["--apply"] if apply else []), capsys)
    assert code == 0
    return store


def scorecard_args(
    store: Path, wallet: str, *, k: str = "1", cluster: str, apply: bool = True
) -> list[str]:
    return [
        "roster",
        "scorecard",
        "--store",
        str(store),
        "--wallet",
        wallet,
        "--as-of",
        NOW_ISO,
        "--account-value",
        "10000",
        "--active-days",
        "5",
        "--markout-bps",
        "4",
        "--participation",
        "0.002",
        "--cdar",
        "0.3",
        "--k",
        k,
        "--cluster",
        cluster,
        "--source-sha",
        digest(["source", wallet]),
        "--copyable",
    ] + (["--apply"] if apply else [])


def test_five_domain_groups_are_registered_and_classified():
    validation = capabilities.validate()
    assert validation["status"] == "VERIFIED", validation["errors"]
    leaves = {
        entry["id"]: entry
        for entry in capabilities.inventory()
        # Only the group/verb leaves of the five consolidated groups: nested
        # groups (`release chapter2 ...`) and pre-existing release reads keep
        # their own capability entries.
        if entry["id"].count(".") == 2
        and entry["id"].startswith(
            (
                "operations.facts.",
                "operations.roster.",
                "operations.release.",
                "operations.research.scorecards",
                "operations.paper.mandates",
            )
        )
    }
    assert set(leaves) == {
        "operations.facts.benchmark",
        "operations.facts.capture-health",
        "operations.facts.coverage",
        "operations.facts.migrate",
        "operations.facts.verify",
        "operations.paper.mandates",
        "operations.release.export",
        "operations.release.propose",
        "operations.release.sign",
        "operations.release.verify",
        "operations.research.scorecards",
        "operations.roster.bench",
        "operations.roster.binding",
        "operations.roster.commit",
        "operations.roster.cusum",
        "operations.roster.plan",
        "operations.roster.proposal",
        "operations.roster.register",
        "operations.roster.scorecard",
        "operations.roster.show",
        "operations.roster.veto",
    }
    assert leaves["operations.facts.capture-health"]["classification"] == "LOCAL_MUTATION"
    for cap_id, entry in leaves.items():
        assert entry["available"] is True, cap_id
        assert entry["authority"] not in ("UNKNOWN", ""), cap_id
        if entry["classification"] == "READ_ONLY":
            assert not any(arg.startswith("--apply") for arg in entry["required_arguments"])
        else:
            assert entry["classification"] in {"LOCAL_MUTATION", "PROTECTED_MUTATION"}
    assert leaves["operations.release.sign"]["classification"] == "PROTECTED_MUTATION"
    assert leaves["operations.release.sign"]["owner"] == "copytrade_pm.production_manifest"


def test_capability_interfaces_never_name_a_deleted_console_script(monkeypatch):
    from copytrade_pm import pm_capabilities_catalog as catalog

    root = Path(__file__).resolve().parents[1]
    assert capabilities.validate(root)["status"] == "VERIFIED"
    declared = capabilities._declared_scripts(root)
    for entry in capabilities.inventory(root):
        head = str(entry["interface"] or "").split()
        if head and head[0].startswith("copytrade-pm"):
            assert head[0] in declared, entry["id"]
    # A catalog entry without a real parser route fails closed.
    monkeypatch.setitem(catalog.COMMANDS, "retired worker", catalog.COMMANDS["appliance status"])
    blocked = capabilities.validate(root)
    assert blocked["status"] == "BLOCKED"
    assert "RETIRED_COMMAND_ADVERTISED:retired worker" in blocked["errors"]


def test_roster_register_is_dry_run_by_default(tmp_path, capsys):
    store = register(tmp_path, capsys, apply=False)
    assert not store.exists()


def test_roster_show_reports_flat_and_redacts_addresses(tmp_path, capsys):
    store = register(tmp_path, capsys)
    code, payload = run(
        ["roster", "show", "--store", str(store), "--account", "cft-10k-paper", "--as-of", NOW_ISO],
        capsys,
    )
    assert code == 0
    assert payload["mode"] == "FLAT"
    assert payload["occupied"] == 0
    assert payload["trading_authorized"] is False
    assert all(seat["occupancy"] == "VACANT" for seat in payload["seats"])


def test_roster_commit_requires_apply_and_then_promotes(tmp_path, capsys):
    store = register(tmp_path, capsys)
    for index in range(2):
        code, _ = run(
            scorecard_args(store, WALLETS[index], k=str(index + 1), cluster=f"c{index}"),
            capsys,
        )
        assert code == 0
    bench = []
    for index in range(2):
        card_sha = digest_sha(tmp_path, WALLETS[index], capsys)
        bench += ["--candidate", f"{WALLETS[index]}:{card_sha}:{index + 1}:0.1:c{index}:1.0"]
    code, _ = run(
        ["roster", "bench", "--store", str(store), "--account", "cft-10k-paper"]
        + bench
        + ["--as-of", NOW_ISO, "--apply"],
        capsys,
    )
    assert code == 0

    code, preview = run(
        [
            "roster",
            "commit",
            "--store",
            str(store),
            "--account",
            "cft-10k-paper",
            "--as-of",
            NOW_ISO,
        ],
        capsys,
    )
    assert code == 0 and preview["state"] == "DRY_RUN" and preview["would_change"] is True
    assert not any(
        seat["occupancy"] == "OCCUPIED" for seat in _show(tmp_path, store, capsys)["seats"]
    )

    code, receipt = run(
        [
            "roster",
            "commit",
            "--store",
            str(store),
            "--account",
            "cft-10k-paper",
            "--as-of",
            NOW_ISO,
            "--apply",
        ],
        capsys,
    )
    assert code == 0 and receipt["state"] == "COMMITTED" and receipt["changed"] is True
    shown = _show(tmp_path, store, capsys)
    assert shown["mode"] == "ACTIVE" and shown["occupied"] == 2
    assert all(
        seat["baseline_required"] is True
        for seat in shown["seats"]
        if seat["occupancy"] == "OCCUPIED"
    )
    # Addresses stay redacted, identity is opt-in.
    assert all("wallet:" in seat["wallet"] for seat in shown["seats"] if seat["wallet"])
    code, identified = run(
        [
            "roster",
            "show",
            "--store",
            str(store),
            "--account",
            "cft-10k-paper",
            "--as-of",
            NOW_ISO,
            "--identities",
        ],
        capsys,
    )
    assert code == 0
    assert {seat["wallet"] for seat in identified["seats"] if seat["wallet"]} == set(WALLETS[:2])


def digest_sha(tmp_path: Path, wallet: str, capsys) -> str:
    from copytrade_pm.roster import RosterStore

    store = RosterStore(tmp_path / "roster.sqlite")
    try:
        card = store.latest_scorecard(
            as_of=__import__("copytrade_kernel", fromlist=["KnownAtTs"]).KnownAtTs(NOW)
        )[wallet]
        return card.sha
    finally:
        store.close()


def _show(tmp_path: Path, store: Path, capsys) -> dict:
    code, payload = run(
        ["roster", "show", "--store", str(store), "--account", "cft-10k-paper", "--as-of", NOW_ISO],
        capsys,
    )
    assert code == 0
    return payload


def _write_private_key(path: Path, key: Ed25519PrivateKey) -> Path:
    path.write_bytes(key.private_bytes_raw())
    path.chmod(0o600)
    return path


def _write_public_key(path: Path, key: Ed25519PrivateKey) -> Path:
    path.write_bytes(key.public_key().public_bytes_raw())
    return path


def _approve_selection(
    store_path: Path, account: str, reviewer: Ed25519PrivateKey, observer: Ed25519PrivateKey
) -> None:
    """Append one reviewer-signed policy and observer attestations for the staged body."""
    from copytrade_pm.production_manifest import sign, store_policy
    from copytrade_pm.roster import RosterStore, select_sealed_book

    created_ms = NOW
    with RosterStore(store_path) as roster:
        binding = roster.release_binding(account)
        assert binding is not None
        proposal = roster.proposals(account)[-1]
        metadata = select_sealed_book(
            roster, account, created_ms, require_attestation=False
        ).metadata()
    members = [dict(member) for member in proposal.payload_json["members"]]
    policy = {
        "schema": "production_release_policy_v1",
        "metadata_export_sha256": metadata["export_sha256"],
        "generation": binding.generation,
        "created_at_ms": created_ms,
        "expires_at_ms": binding.expires_at_ms,
        "account_binding": account,
        "risk_policy_sha": binding.risk_policy_sha,
        "rulebook_sha": binding.rulebook_sha,
        "source_mode": binding.source_mode,
        "members": members,
        "source_attestations": [
            sign(
                {
                    "schema": "source_scope_attestation_v1",
                    "source_identity": member["source_identity"],
                    "account_scope": member["account_scope"],
                    "known_at_ms": created_ms - 5_000,
                    "scope_complete": True,
                    "book_complete": True,
                    "source_mode": binding.source_mode,
                },
                observer,
                "source-observer",
            )
            for member in members
        ],
    }
    store_policy(
        store_path,
        account,
        metadata,
        sign(policy, reviewer, "research-release-policy"),
        reviewer.public_key(),
    )


def test_roster_veto_and_cusum_are_dry_run_without_apply(tmp_path, capsys):
    store = register(tmp_path, capsys)
    code, payload = run(
        [
            "roster",
            "cusum",
            "--store",
            str(store),
            "--wallet",
            WALLETS[0],
            "--increment",
            "3",
            "--threshold",
            "3",
            "--epoch",
            EPOCH,
            "--at-ms",
            str(NOW),
        ],
        capsys,
    )
    assert code == 0 and payload["state"] == "DRY_RUN"

    code, receipt = run(
        [
            "roster",
            "cusum",
            "--store",
            str(store),
            "--wallet",
            WALLETS[0],
            "--increment",
            "3",
            "--threshold",
            "3",
            "--epoch",
            EPOCH,
            "--at-ms",
            str(NOW),
            "--apply",
        ],
        capsys,
    )
    assert code == 0 and receipt["state_label"] == "LATCHED" and receipt["retired_latch"] is True

    code, receipt = run(
        [
            "roster",
            "veto",
            "--store",
            str(store),
            "--wallet",
            WALLETS[1],
            "--reason",
            "compromised key",
            "--at-ms",
            str(NOW),
            "--apply",
        ],
        capsys,
    )
    assert code == 0 and receipt["state"] == "VETOED"
    code, revoked = run(
        [
            "roster",
            "veto",
            "--store",
            str(store),
            "--wallet",
            WALLETS[1],
            "--at-ms",
            str(NOW + 1),
            "--revoke",
            "--apply",
        ],
        capsys,
    )
    assert code == 0 and revoked["state"] == "REVOKED"


def test_facts_benchmark_dry_run_plans_only(tmp_path, capsys):
    code, payload = run(["facts", "benchmark", "--wallets", "4", "--days", "2"], capsys)
    assert code == 0 and payload["state"] == "DRY_RUN" and payload["wallets"] == 4


@pytest.mark.parametrize("source_mode", ["SYNTHETIC", "PROSPECTIVE"])
def test_release_propose_sign_verify_end_to_end(tmp_path, capsys, source_mode):
    store = register(tmp_path, capsys)
    binding_path = tmp_path / "binding.json"
    binding = {
        "schema": "roster_release_binding_v1",
        "account_id": "cft-10k-paper",
        "generation": 1,
        "research_commit": "b" * 40,
        "decision_sha": digest(["decision"]),
        "selection_known_at_ms": NOW - 300_000,
        "source_mode": source_mode,
        "risk_policy_sha": digest(["risk"]),
        "rulebook_sha": digest(["rulebook"]),
        "checkpoint_policy": CHECKPOINT_POLICY,
        "checkpoint_scopes": {
            WALLETS[0]: {
                "schema_version": 3,
                "source_id": WALLETS[0],
                "account_sha": digest(["account", WALLETS[0]]),
                "generation": digest(["generation", WALLETS[0]]),
                "selection_sha": digest(["selection", WALLETS[0]]),
                "dexes": ["default"],
            }
        },
        "allowed_markets": {"seat_1": [MARKET]},
        "created_ms": NOW - 1_000,
        "expires_at_ms": NOW + 86_400_000,
    }
    binding_path.write_text(json.dumps(binding))
    code, receipt = run(
        ["roster", "binding", "--store", str(store), "--file", str(binding_path), "--apply"],
        capsys,
    )
    assert code == 0 and receipt["state"] == "RECORDED"

    assert run(scorecard_args(store, WALLETS[0], k="2", cluster="c0"), capsys)[0] == 0
    card_sha = digest_sha(tmp_path, WALLETS[0], capsys)
    code, _ = run(
        [
            "roster",
            "bench",
            "--store",
            str(store),
            "--account",
            "cft-10k-paper",
            "--candidate",
            f"{WALLETS[0]}:{card_sha}:2:0.1:c0:1.0",
            "--as-of",
            NOW_ISO,
            "--apply",
        ],
        capsys,
    )
    assert code == 0
    code, receipt = run(
        [
            "roster",
            "commit",
            "--store",
            str(store),
            "--account",
            "cft-10k-paper",
            "--as-of",
            NOW_ISO,
            "--apply",
        ],
        capsys,
    )
    assert code == 0 and receipt["changed"] is True

    proposal_path = tmp_path / "proposal.json"
    code, proposal = run(
        [
            "release",
            "propose",
            "--store",
            str(store),
            "--account",
            "cft-10k-paper",
            "--as-of",
            NOW_ISO,
            "--out",
            str(proposal_path),
        ],
        capsys,
    )
    assert code == 0 and proposal["state"] == "DRY_RUN" and not proposal_path.exists()

    code, staged = run(
        [
            "release",
            "propose",
            "--store",
            str(store),
            "--account",
            "cft-10k-paper",
            "--as-of",
            NOW_ISO,
            "--out",
            str(proposal_path),
            "--apply",
        ],
        capsys,
    )
    assert code == 0 and staged["state"] == "STAGED" and proposal_path.exists()
    assert oct(proposal_path.stat().st_mode & 0o777) == "0o600"
    assert "signature" not in json.loads(proposal_path.read_text())["payload"]

    paper = ["paper", "mandates", "--store", str(store), "--account", "cft-10k-paper", "--as-of"]
    before = datetime.fromtimestamp((NOW - 1) / 1000, UTC).isoformat()
    code, hidden = run(paper + [before], capsys)
    assert code == 2 and hidden["error_code"] == "ROSTER_PROPOSAL_MISSING"
    code, visible = run(paper + [NOW_ISO], capsys)
    assert code == 0 and visible["proposal_sha"] == staged["proposal_sha"]
    assert visible["order_route"] == "NONE" and visible["trading_authorized"] is False

    signed_path = tmp_path / "release.json"
    reviewer = Ed25519PrivateKey.generate()
    observer = Ed25519PrivateKey.generate()
    reviewer_pub = _write_public_key(tmp_path / "reviewer.pub", reviewer)
    observer_pub = _write_public_key(tmp_path / "observer.pub", observer)
    key = Ed25519PrivateKey.generate()
    key_path = _write_private_key(tmp_path / "release.key", key)
    # A world-readable key would report PRIVATE_KEY_PERMISSIONS the moment it is
    # opened, so this refusal proves the unapproved selection is rejected before
    # the signing key is touched.
    key_path.chmod(0o644)
    unapproved_path = tmp_path / "unapproved.json"
    code, blocked = run(
        [
            "release",
            "sign",
            "--store",
            str(store),
            "--proposal",
            str(proposal_path),
            "--release-signing-key",
            str(key_path),
            "--reviewer-public",
            str(reviewer_pub),
            "--source-observer-public",
            str(observer_pub),
            "--now-ms",
            str(NOW),
            "--out",
            str(unapproved_path),
            "--apply",
        ],
        capsys,
    )
    assert code == 2 and blocked["error_code"] == "SELECTION_ATTESTATION_MISSING"
    assert not unapproved_path.exists()

    # The reviewer-signed policy and independent observer attestations cover the
    # exact staged selection; only then can the offline signature be produced.
    _approve_selection(store, "cft-10k-paper", reviewer, observer)
    key_path.chmod(0o600)

    public_path = tmp_path / "release.pub"
    public_path.write_bytes(key.public_key().public_bytes_raw())

    code, signed = run(
        [
            "release",
            "sign",
            "--store",
            str(store),
            "--proposal",
            str(proposal_path),
            "--release-signing-key",
            str(tmp_path / "absent.key"),
            "--reviewer-public",
            str(reviewer_pub),
            "--source-observer-public",
            str(observer_pub),
            "--now-ms",
            str(NOW),
            "--out",
            str(signed_path),
        ],
        capsys,
    )
    assert code == 0 and signed["state"] == "DRY_RUN" and not signed_path.exists()

    code, signed = run(
        [
            "release",
            "sign",
            "--proposal",
            str(proposal_path),
            "--release-signing-key",
            str(key_path),
            "--reviewer-public",
            str(reviewer_pub),
            "--source-observer-public",
            str(observer_pub),
            "--now-ms",
            str(NOW),
            "--out",
            str(signed_path),
            "--store",
            str(store),
            "--apply",
        ],
        capsys,
    )
    assert code == 0 and signed["state"] == "SIGNED_METADATA_RELEASE"
    assert oct(signed_path.stat().st_mode & 0o777) == "0o600"

    code, verified = run(
        [
            "release",
            "verify",
            "--envelope",
            str(signed_path),
            "--signer-public",
            str(public_path),
        ],
        capsys,
    )
    assert code == 0 and verified["state"] == "VERIFIED"
    assert verified["account_binding"] == "cft-10k-paper" and verified["members"] == 1

    # A signed proposal is recorded, and the payload re-derives its own digests.
    envelope = json.loads(signed_path.read_text())
    payload = envelope["payload"]
    assert payload["definition_sha"] == digest(payload["members"])
    assert payload["source_sha"] == digest(
        {
            key_name: payload[key_name]
            for key_name in (
                "research_commit",
                "decision_sha",
                "inventory_sha",
                "definition_sha",
                "selection_known_at_ms",
            )
        }
    )
    code, listed = run(["roster", "proposal", "--store", str(store)], capsys)
    assert code == 0 and listed["count"] == 1

    # Signing refuses a world-readable key and an existing output path.
    key_path.chmod(0o644)
    code, blocked = run(
        [
            "release",
            "sign",
            "--store",
            str(store),
            "--proposal",
            str(proposal_path),
            "--release-signing-key",
            str(key_path),
            "--reviewer-public",
            str(reviewer_pub),
            "--source-observer-public",
            str(observer_pub),
            "--now-ms",
            str(NOW),
            "--out",
            str(tmp_path / "second.json"),
            "--apply",
        ],
        capsys,
    )
    assert code == 2 and blocked["error_code"] == "PRIVATE_KEY_PERMISSIONS"
    key_path.chmod(0o600)
    code, blocked = run(
        [
            "release",
            "sign",
            "--store",
            str(store),
            "--proposal",
            str(proposal_path),
            "--release-signing-key",
            str(key_path),
            "--reviewer-public",
            str(reviewer_pub),
            "--source-observer-public",
            str(observer_pub),
            "--now-ms",
            str(NOW),
            "--out",
            str(signed_path),
            "--apply",
        ],
        capsys,
    )
    assert code == 2 and blocked["error_code"] == "OUTPUT_REQUIRES_NEW_FILE_IN_PRIVATE_DIRECTORY"


def test_release_propose_refuses_a_missing_binding(tmp_path, capsys):
    store = register(tmp_path, capsys)
    code, blocked = run(
        [
            "release",
            "propose",
            "--store",
            str(store),
            "--account",
            "cft-10k-paper",
            "--as-of",
            NOW_ISO,
        ],
        capsys,
    )
    assert code == 2 and blocked["error_code"] == "RELEASE_BINDING_MISSING"


def test_release_sign_refuses_an_unstaged_body_before_reading_key(tmp_path, capsys):
    store = register(tmp_path, capsys)
    proposal = tmp_path / "unstaged.json"
    proposal.write_text(
        json.dumps(
            {
                "schema": "roster_release_proposal_v1",
                "account_id": "cft-10k-paper",
                "day": "2027-01-15",
                "generation": 1,
                "plan_sha": "1" * 64,
                "book_sha": "2" * 64,
                "binding_sha": "3" * 64,
                "created_ms": NOW,
                "payload": {"schema": "portfolio_release_v2", "source_mode": "SYNTHETIC"},
                "trading_authorized": False,
            }
        )
    )
    output = tmp_path / "release.json"
    code, blocked = run(
        [
            "release",
            "sign",
            "--store",
            str(store),
            "--proposal",
            str(proposal),
            "--release-signing-key",
            str(tmp_path / "absent.key"),
            "--reviewer-public",
            str(tmp_path / "absent-reviewer.pub"),
            "--source-observer-public",
            str(tmp_path / "absent-observer.pub"),
            "--out",
            str(output),
            "--apply",
        ],
        capsys,
    )
    assert code == 2 and blocked["error_code"] == "RELEASE_PROPOSAL_NOT_STAGED"
    assert not output.exists()


def test_paper_and_research_views_read_the_roster(tmp_path, capsys):
    store = register(tmp_path, capsys)
    code, blocked = run(
        ["paper", "mandates", "--store", str(store), "--account", "cft-10k-paper"], capsys
    )
    assert code == 2 and blocked["error_code"] == "ROSTER_PROPOSAL_MISSING"
    code, summary = run(
        ["research", "scorecards", "--store", str(store), "--as-of", NOW_ISO], capsys
    )
    assert code == 0 and summary["scorecards"] == 0 and summary["latched"] == 0
