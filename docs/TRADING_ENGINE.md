# Trading engine explanation

The engine is deterministic and rule-first. Market structure, institutional
location, liquidity and risk must agree before ML is consulted.

SMC evaluates BOS, CHoCH, MSS, order/breaker/mitigation blocks, equal
highs/lows, sweeps, FVGs and premium/discount. ICT evaluates sessions, kill
zones, OTE, liquidity engineering and institutional entries. Top-down analysis
aligns higher-timeframe bias with execution structure.

Patterns such as engulfing, doji, hammer, stars, head-and-shoulders, triangles,
wedges and channels are supporting evidence only. They cannot overcome missing
structure, poor location or invalid risk.

The confluence resolver removes contradictory direction evidence. Insufficient
quality produces `NO_TRADE`; a valid setup lacking its trigger produces
`WAIT_FOR_CONFIRMATION`. Confirmed direction then receives entry refinement,
structure/volatility stop placement, liquidity/structure targets, RR and
risk-based sizing. Any invalid stop, target, spread or minimum RR returns a
non-trade decision.

Historical scenario tests cover fake BOS, trend synchronization, institutional
priority, pattern weighting, scoring and risk calculations.
