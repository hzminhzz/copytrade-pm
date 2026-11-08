# Grafana Phase 3 acceptance controller — source implementation and scope

## Fidelity to approved #180 and #190

The controlling design seam remains the approved **Operational Read Model** (`DashboardReader`/bounded HTTP projection); Grafana remains presentation-only. This acceptance controller is an additive read-only release decision helper, not a second read model, financial authority, or deployment system. It neither changes T+300s entry semantics nor starts Guardian, Vike, Grafana or broker services. Phase 2 PR #195 and its independent audit #204 remain separate unmerged source branches; this change is based on #204.

The verifier's mandatory gates map to #190: five dashboards and manual visual review; owner SSO/Viewer query isolation; independent non-owner Tailscale peer; canonical financial source provenance; causal execution clocks; browser-independent alert fault/recovery; restart/plugin/concurrency; measured resource and latency; protected Guardian journal noninterference; pinned installed release and tested rollback. Each gate is distinct. Missing evidence is UNKNOWN, explicit negative evidence is FAIL, and any non-PASS blocks eligibility. No test result can silently qualify finance, a live release, or trading.

## Interface

`python -m copytrade_pm.dashboard.grafana_acceptance --receipt <file.json> --candidate <40-char-git-sha> --bundle-sha256 <64-char-expected-source-hash>`

Input `grafana_acceptance_evidence_v1` contains the exact candidate SHA, independently approved source bundle hash, and a `gates` map. Each gate supplies status, candidate, bundle hash and `sha256:<64-hex>` evidence reference. Unknown/mismatched candidate or malformed evidence cannot pass. Exit 0 indicates **eligibility for a separately authorized cutover**, not installation or trading authority. Exit 2 indicates HOLD or REJECT. The CLI never reads protected journals or performs network or runtime mutation.

**Trust limit:** the JSON input and its hash references are not signed or independently authenticated. A caller controlling the receipt can forge PASS values. This controller is therefore a *decision consistency check*, not cryptographic independent proof. The operator/reviewer must authenticate receipts and issuers out of band. It must not be wired as an unattended production promotion gate until independently verified receipts and installed-runtime attestation are implemented.

## Current acceptance disposition

**HOLD.** The previous isolated staging verified the existing five route/three viewport checks and owner Viewer HTTP/network isolation. It did not prove an independent non-owner Tailscale identity, authentic financial and broker evidence, complete alert fault/recovery, performance budget, protected journal continuity, or installed rollback. Those missing mandatory gates remain UNKNOWN. The controller must not reinterpret them as PASS or waive them to close #190.

## Deployment boundary

This work does not merge Phase 2, replace Marimo, change HTTPS 8443, install Grafana, or close #184–#190. Phase 3 cannot honestly be marked complete without external identity and protected owner evidence. Keep #191 cutover and #192 retirement blocked until the exact #180 acceptance contract is satisfied and a separate authorized release/rollback operation is verified.
