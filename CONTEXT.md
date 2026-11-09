# Copytrade domain glossary

Canonical domain meanings. This glossary does not specify implementation or storage.

## Source observation

- **Selected account**: The exact authorized-for-observation source account and perp-market scope; parent and subaccounts are independent selections unless explicitly included.
- **Official position book**: A complete exchange-reported set of positions within one selected account's declared perp scope. It is not equivalent to fills or whole-wallet NAV.
- **Raw source evidence**: The original externally observed message and its provenance. It must not be reconstructed from a normalized representation.
- **Economic position state**: The economic meaning of a valid complete position book; numerically equivalent quantities represent the same exposure even when their raw encodings differ.
- **Evidence identity**: The provenance-bound identity of an actual received message, which can differ between observations even when their economic positions are equal.
- **Position transition**: A demonstrable change in economic exposure within an unchanged, complete selected-account scope, observed with unbroken prospective continuity.
- **First-known time**: When this system first received an observation locally. It is not interchangeable with the exchange event time or the later decision time.
- **Continuity gap**: A break in the ability to prove complete prospective observation. A reconnect baseline can restore a starting reference but is not a new entry signal.
- **Scope generation**: The validity interval for one declared selected-account and market scope. A materially changed scope begins a new generation and cannot inherit past prospective continuity.
- **Observer generation**: The identity and version of the overall observation configuration and its subscriptions, which is not itself proof that any individual selected account changed economic scope.
- **Selected-perp completeness**: Complete, authentic official positions and DEX coverage for one explicitly selected account's perpetual market scope; not the same as all-wallet collateral or related subaccount finance.
- **Whole-wallet financial completeness**: Evidence sufficient to characterize broader leader financial balances and collateral across relevant account types; not a universal requirement for fixed-k mirroring.

## Follower research and authority

- **Desired source exposure**: The selected account's verified economic position vector; not an instruction or proof of follower holdings.
- **Paper intent**: A proposed simulated action derived from verified source evidence and the paper policy; it is not a real order or permit.
- **Terminal modeled attempt**: A completed decision to make at most one modeled entry attempt for a given eligible paper intent; later exit protection remains a separate responsibility.
- **Protective reduction**: An attempted decrease of independently verified follower risk, distinct from admitting new exposure, with unresolved effects remaining financially accountable.
- **Modeled follower inventory**: Outstanding positions and unresolved exposure in the research/shadow financial account. Missing source/market data does not imply flat inventory.
- **Unresolved exposure**: An open, incomplete or uncertain financial effect that must remain accounted for until independently reconciled; it is not erased when an intent becomes terminal.
- **Durable receipt**: An observation or effect whose persistence can be verified after a process interruption; a successful delivery acknowledgement is not itself proof that a financial effect occurred.
- **Wire contract**: The versioned meaning and identity of a record exchanged between independent authorities; historical signed representations retain their original meaning.
- **Validated evidence**: A well-formed observation under its declared contract, distinct from complete/prospective evidence and distinct from permission to act.
- **Transition identity**: The unique provenance-bound occurrence of a state change, which may differ between events that reach the same economic state.
- **Consumer cursor**: One consumer's durable position in a verified evidence stream, separate from the producer's cursor and other consumers' acknowledgements.
- **Durable HALT**: A latched financial risk restriction that cannot disappear through a transient diagnostic update. Any reset requires its own authorized, auditable transition.
- **Operational readiness**: The current evidence of source, market, transport, worker and account-data availability; it does not override a financial risk latch or scientific verdict.
- **Capability-scoped admission**: A decision about one specifically requested operation using only its applicable evidence and authority prerequisites; read-only observation does not imply permission to trade.
- **Evidence availability**: Whether required evidence is valid, complete, fresh, supported and currently accessible; availability does not imply positive scientific or financial authorization.
- **Wallet eligibility**: The current deterministic evidence that a wallet meets configured participation requirements, distinct from evidence that its strategy is economically profitable.
- **Financial authority**: The system that owns financial state transitions and risk admission for its context; PM-03/04 own simulated research finance, while Guardian independently owns protected production finance.
- **Scientific qualification**: A separately evidenced result of a specified prospective economic evaluation; not synonymous with valid input, passing engineering tests or a paper run.
- **Agent diagnostic evaluation**: A controlled assessment of whether a research agent correctly interprets available evidence and abstains when it cannot; it is not a test of executable follower profitability.
- **Quarantined observation**: Received evidence that cannot support current prospective continuity until its affected scope and cause are resolved; quarantine is not proof of a position close or a financial HALT.
- **Intentional semantic correction**: A declared, independently justified change to previously incorrect future behavior; not permission to rewrite earlier signed historical records.
- **Trading authorization**: Permission from the protected execution authority, not created by research selection, source observation, an AI evaluation or Pydantic validation.
