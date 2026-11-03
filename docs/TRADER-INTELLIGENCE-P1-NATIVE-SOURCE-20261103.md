# Native Hyperliquid P1 read-only source snapshot — 2026-11-03

**Engineering acquisition:** VERIFIED. **Scientific qualification:** NOT_QUALIFIED. No orders, broker credentials, production Telegram, source collector changes, or new subscriptions.

## Real P1 source capture

The first one-shot source generation `/home/quant/.local/share/copytrade/reports/gTI_20261103_0806_P1` partially captured the official DEX catalog and the three parent/subaccount discoveries, but halted on **HTTP 422**, because the `allDexsClearinghouseState` message is a **WebSocket subscription** and not an HTTP `/info` method. **The partial original generation is preserved unchanged.**

The corrected, verified generation is:

`/home/quant/.local/share/copytrade/reports/gTI_20261103_REST_P1_v2/`

- Private immutable 0700 generation, 0600 `snapshot.json` and raw response files.
- Snapshot SHA256: `962e36822f9adba63995cee50ca6910b935f6ba7058d679a197369cca2d4d19b`.
- Three parent wallets: S035-ENA, S051-BTC, S053-HYPE. Zero subaccounts returned for these three **at this discovery time**, not proof that no subaccount ever existed.
- Official `perpDexs` list contained **11 DEX entries**; `clearinghouseState` requested and checked per-DEX for **11/11** on each parent, followed by a current `spotClearinghouseState` reply on each. **40 bounded read-only official REST requests** total.
- Parsed current nonzero perp positions: S035-ENA **2**, S051-BTC **2**, S053-HYPE **6**. A position count does not mean a directional entry or a compatible follower position.
- Each DEX/spot reply is retained with original bytes, SHA256 and conservative individual local requested/received clocks, verified against the official DEX catalog by the existing `pm_e4_prospective._account_state` parser. The acquisition did **not** contact the HyperX fill endpoint.
- Private alias/address locator files and all raw account identities/economic values remain outside Git.

## Contract and limitations

The read-only adapter is `src/copytrade_pm/trader_intelligence_source_capture.py`. Example for a **new unique** private generation (not an invitation to overwrite already captured outputs):

```bash
uv run --group dev python -m copytrade_pm.trader_intelligence_source_capture \
  --private-source-files /home/quant/dev/copytrade-pm/data/wallet_fills_90d \
  --generation /home/quant/.local/share/copytrade/reports/gTI_UNIQUE_NEW_GENERATION \
  --aliases S035-ENA,S051-BTC,S053-HYPE
```

Hyperliquid's REST `/info` supports per-DEX `clearinghouseState`, whereas `allDexsClearinghouseState` is documented for WebSocket. A set of 11 sequential DEX replies **cannot claim an atomic complete account book**. Spot/vault balances, collateral transfers, portfolio denominator, positions between replies, funding cash flows, wallet owner dependencies, prospective continuity, actual follower order/fill/slippage and Propr account market rules are not reconciled by the snapshot. No model may silently use the displayed per-DEX equity as verified full-wallet equity. Source capture is a *new, dated, partial evidence generation*, not a repair to PM-01's frozen historical 36-wallet replay nor an independently observed historical first-known clock.

**Falsification context:** The P1 [live hypothetical-outcome audit](TRADER-INTELLIGENCE-P1-EXPLORATORY-AUDIT-20261103.md) reports insufficient/unverified 1h economic evidence and Holm-adjusted exploratory p=1.0 across all three wallets. The positive HYPE midpoint incremental R is not statistically qualified. The proposed [future study](TRADER-INTELLIGENCE-PROSPECTIVE-STUDY-20261103.md) still needs a registered PIT roster, independent full-book/equity and 300-second executable follower/control economic producer plus genuinely out-of-sample testing. **C/X at 0R remains the only supported grade.**
