# ADR — Independent review at protected decision boundaries

**Date:** 2026-11-04
**Status:** Accepted for research governance, with external reviewer automation pending.

## Context

The old agent guidance instructed agents to attempt the judge for any
non-trivial *recommendation*, including many exploratory conversations.
This imposes interactive latency without strengthening scientific evidence.
The code already uses deterministic PIT, signed-evidence, fixed-OOS and
risk gates. The actual Trader Intelligence readiness path is read-only;
no scientific qualification registry writer currently exists.

## Decision

Run routine conversation, research, testing and previously authorized work
without a judge. Classify state-changing decisions and make their existing
deterministic gates primary. Require selective independent review on
material science/policy changes and protected roster/qualification decisions
at explicit PR or signoff boundaries. Bind reviewer attestation to raw
evidence SHA, policy SHA and source commit. Review is not authorization,
scientific qualification or permission to trade.

Provide a read-only Ed25519 verification CLI that cannot mutate state.
Keep scientific qualification fail-closed until a real independently audited
economic qualification producer and protected writer exist. Avoid adding
a global numerical screening threshold or an always-on LLM dependency.

## Alternatives rejected

- Per-turn independent judge: unnecessary latency and broad triggers.
- Replace all science with three universal `assert` thresholds: loses
  experiment-specific PIT, multiplicity, independence and tail semantics.
- Require LLM review inside signal execution or safety HALT: nondeterministic
  latency and a dangerous availability dependency.
- Add an ungrounded `registry.db`/qualification writer: would create a
  misleading scientific-promoting capability.

## Consequences and trade-offs

- Interactive research can proceed without waiting for a reviewer.
- Protected operations still need a genuine external review and distinct
  authority where applicable. Unavailability blocks only that operation.
- Signed reviews are reusable across identical frozen evidence and commit,
  but trust root/independence must be anchored outside the command.
- Automatic PR review, protected branch enforcement and owner authorization
  remain integration prerequisites rather than claimed completed work.
- Existing frozen research outputs and order/risk services are unaffected.

See [governance contract](../GOVERNANCE-GATES.md).
