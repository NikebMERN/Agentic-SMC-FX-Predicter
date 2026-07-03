# engine/confluence.py
"""Aggregation of valid SMC + ICT signals into one trading decision.

analyze()  - runs every detector over the candle history and returns the
             full market picture.
decide()   - weighted confluence vote across both strategies, blended
             with the freshly trained ML model's probability, producing
             BUY / SELL / NO_TRADE plus structure-based SL/TP and a
             human-readable reasoning trail.

Validity is enforced twice: each detector only emits valid signals
(see smc.py / ict.py), and decide() adds trade-level validity rules -
minimum confluence count, premium/discount alignment vetoes and a
minimum score gap between the two sides.
"""
import numpy as np

from engine import ict, smc
from utils import settings
from utils.compliance import DISCLAIMER
from utils.logger import get_logger

log = get_logger("engine.confluence")

MAX_BARS = 1500          # cap history for analysis performance
SWEEP_RECENT_BARS = 24   # a sweep older than this is spent
STRUCTURE_STALE_BARS = 40
ZONE_BUFFER_ATR = 0.5    # "near a zone" tolerance in ATRs

# Confluence weights (per valid signal)
W_CHOCH = 2.5
W_BOS = 2.0
W_STRUCT_STALE = 1.0
W_SWEEP = 2.0
W_OB_FRESH = 1.5
W_OB_MITIGATED = 0.75
W_FVG_OPEN = 1.0
W_FVG_PARTIAL = 0.5
W_PREMIUM_DISCOUNT = 1.0
W_OTE = 1.0
W_BREAKER = 1.5

MIN_SCORE = 2.5          # winning side must reach this
MIN_GAP = 1.0            # and beat the other side by this
MIN_CONFLUENCES = 2      # distinct valid signals agreeing
EXTREME_PREMIUM = 0.80   # no longs above, no shorts below (1 - x)
MIN_RISK_REWARD = 1.5
MIN_FINAL_CONFIDENCE = 0.55  # blended confidence floor for a trade

STRATEGY_MODES = frozenset({"both", "smc", "ict"})

# Component score weights (must sum to 1.0)
COMPONENT_WEIGHTS = {
    "htf_bias": 0.20,
    "structure": 0.20,
    "liquidity": 0.20,
    "displacement": 0.15,
    "zones": 0.15,
    "session": 0.05,
    "risk_filter": 0.05,
}

ACTION_BUY = "BUY_BIAS"
ACTION_SELL = "SELL_BIAS"
ACTION_NO_TRADE = "NO_TRADE"
ACTION_WAIT = "WAIT_FOR_CONFIRMATION"


def is_trade_action(action: str) -> bool:
    return action in (ACTION_BUY, ACTION_SELL, "BUY", "SELL")


def trade_side_from_action(action: str) -> str | None:
    if action in (ACTION_BUY, "BUY"):
        return "BUY"
    if action in (ACTION_SELL, "SELL"):
        return "SELL"
    return None


def normalize_strategy_mode(raw) -> str:
    """Map API/CLI input to both | smc | ict (default both)."""
    if raw is None or raw == "":
        return "both"
    mode = str(raw).strip().lower().replace("-", "_")
    aliases = {
        "joint": "both",
        "combined": "both",
        "all": "both",
        "smc_only": "smc",
        "ict_only": "ict",
    }
    mode = aliases.get(mode, mode)
    if mode not in STRATEGY_MODES:
        raise ValueError("strategy must be one of: both, smc, ict")
    return mode


def analyze(df, symbol: str, swing_window: int = 3) -> dict:
    """Run all SMC + ICT detectors over the (tail of the) history."""
    df = df.tail(MAX_BARS)
    atr_series = smc.atr(df)
    atr_last = float(atr_series.iloc[-1])
    price = float(df["Close"].iloc[-1])

    swings = smc.find_swings(df, swing_window)
    structure = smc.detect_structure(df, swings, swing_window, atr_series)
    order_blocks = smc.detect_order_blocks(df, structure["events"])
    fvgs = smc.detect_fvg(df, atr_series)
    pools = smc.detect_liquidity_pools(df, swings, tolerance=0.25 * atr_last)
    sweeps = ict.detect_sweeps(
        df, pools, swings, recent_bars=SWEEP_RECENT_BARS, tolerance=0.25 * atr_last
    )
    rng = ict.dealing_range(df, structure["events"])
    pd_info = ict.premium_discount(price, rng)
    ote = ict.ote_zone(rng)
    breakers = ict.detect_breakers(df, order_blocks, sweeps)
    killzone = ict.active_killzone(df.index[-1])

    return {
        "symbol": symbol,
        "bars": len(df),
        "last_time": df.index[-1],
        "price": price,
        "atr": atr_last,
        "df": df,
        "swings": swings,
        "structure": structure,
        "order_blocks": order_blocks,
        "valid_order_blocks": smc.valid_order_blocks(order_blocks),
        "fvgs": fvgs,
        "pools": pools,
        "sweeps": sweeps,
        "dealing_range": rng,
        "premium_discount": pd_info,
        "ote": ote,
        "breakers": breakers,
        "killzone": killzone,
    }


def _collect_votes(analysis: dict, strategy_mode: str = "both") -> list[tuple[str, float, str, str]]:
    """(direction, weight, reason, component) for every valid signal in play now."""
    mode = normalize_strategy_mode(strategy_mode)
    use_smc = mode in ("both", "smc")
    use_ict = mode in ("both", "ict")
    votes: list[tuple[str, float, str, str]] = []
    n = analysis["bars"]
    price = analysis["price"]
    buffer = ZONE_BUFFER_ATR * analysis["atr"]

    # --- HTF bias (ICT context) -----------------------------------------
    htf = analysis.get("htf_bias") or {}
    if htf.get("direction") in ("bullish", "bearish"):
        strength = float(htf.get("strength", 50)) / 100.0 * 2.5
        votes.append((
            htf["direction"], strength,
            htf.get("reason", "Higher timeframe structure bias"),
            "htf_bias",
        ))

    # --- SMC: market structure bias -----------------------------------
    events = analysis["structure"]["events"]
    if use_smc and events:
        ev = events[-1]
        age = n - 1 - ev["pos"]
        weight = W_STRUCT_STALE if age > STRUCTURE_STALE_BARS else (
            W_CHOCH if ev["kind"] == "CHoCH" else W_BOS
        )
        disp = " with displacement" if ev["displacement"] else ""
        votes.append((
            ev["direction"], weight,
            f"SMC structure: {ev['kind']} {ev['direction']}{disp} "
            f"{age} bars ago (close beyond {ev['level']:.5f})",
            "structure",
        ))
        if ev.get("displacement"):
            votes.append((
                ev["direction"], W_CHOCH * 0.6,
                f"SMC displacement confirmed on {ev['kind']}",
                "displacement",
            ))

    # --- ICT: liquidity sweeps (latest two) ---------------------------
    for sweep in analysis["sweeps"][-2:] if use_ict else []:
        side_txt = "buy-side" if sweep["side"] == "buyside" else "sell-side"
        votes.append((
            sweep["bias"], W_SWEEP,
            f"ICT liquidity sweep: {side_txt} liquidity at {sweep['level']:.5f} "
            f"grabbed {sweep['bars_ago']} bars ago and rejected -> {sweep['bias']} signal",
            "liquidity",
        ))

    # --- SMC: valid order blocks price is trading at ------------------
    for ob in analysis["valid_order_blocks"] if use_smc else []:
        if ob["low"] - buffer <= price <= ob["high"] + buffer:
            weight = W_OB_FRESH if ob["status"] == "fresh" else W_OB_MITIGATED
            votes.append((
                ob["direction"], weight,
                f"SMC order block: price at {ob['status']} {ob['direction']} OB "
                f"{ob['low']:.5f}-{ob['high']:.5f} (validated by {ob['event_kind']})",
                "zones",
            ))

    # --- SMC: unfilled FVGs price is inside ---------------------------
    for gap in analysis["fvgs"] if use_smc else []:
        if gap["low"] <= price <= gap["high"]:
            weight = W_FVG_OPEN if gap["status"] == "open" else W_FVG_PARTIAL
            votes.append((
                gap["direction"], weight,
                f"SMC fair value gap: price inside {gap['status']} {gap['direction']} "
                f"FVG {gap['low']:.5f}-{gap['high']:.5f} (displacement-created)",
                "zones",
            ))

    # --- ICT: premium / discount --------------------------------------
    pd_info = analysis["premium_discount"]
    if use_ict and pd_info["zone"] == "discount":
        votes.append((
            "bullish", W_PREMIUM_DISCOUNT,
            f"ICT premium/discount: price in discount ({pd_info['position']:.0%} of dealing range) - longs valid",
            "zones",
        ))
    elif use_ict and pd_info["zone"] == "premium":
        votes.append((
            "bearish", W_PREMIUM_DISCOUNT,
            f"ICT premium/discount: price in premium ({pd_info['position']:.0%} of dealing range) - shorts valid",
            "zones",
        ))

    # --- ICT: OTE retracement ------------------------------------------
    ote = analysis["ote"]
    if use_ict and ict.price_in_zone(price, ote):
        votes.append((
            ote["direction"], W_OTE,
            f"ICT OTE: price inside 61.8-79% retracement "
            f"({ote['low']:.5f}-{ote['high']:.5f}) of the {ote['direction']} leg",
            "zones",
        ))

    # --- ICT: breaker block retest --------------------------------------
    for br in analysis["breakers"] if use_ict else []:
        if br["low"] - buffer <= price <= br["high"] + buffer:
            votes.append((
                br["direction"], W_BREAKER,
                f"ICT breaker block: failed OB flipped {br['direction']}, "
                f"price retesting {br['low']:.5f}-{br['high']:.5f}",
                "displacement",
            ))

    # --- Session timing ------------------------------------------------
    killzone = analysis["killzone"]
    if use_ict and killzone:
        votes.append((
            "neutral", 0.5,
            f"ICT kill zone: {killzone} session active",
            "session",
        ))

    return votes


def _component_scores(votes: list[tuple[str, float, str, str]], direction: str) -> dict[str, int]:
    """Map votes into 0-100 component scores aligned with the winning direction."""
    raw: dict[str, dict[str, float]] = {
        k: {"bullish": 0.0, "bearish": 0.0} for k in COMPONENT_WEIGHTS
    }
    for d, w, _, comp in votes:
        if comp not in raw:
            continue
        if d == "bullish":
            raw[comp]["bullish"] += w
        elif d == "bearish":
            raw[comp]["bearish"] += w

    scores: dict[str, int] = {}
    for comp in COMPONENT_WEIGHTS:
        bull = raw[comp]["bullish"]
        bear = raw[comp]["bearish"]
        total = bull + bear
        if total <= 0:
            scores[comp] = 0
            continue
        aligned = bull if direction == "bullish" else bear
        scores[comp] = int(min(100, max(0, round((aligned / total) * 100))))
    return scores


def _weighted_component_total(scores: dict[str, int]) -> float:
    return sum(scores.get(k, 0) * w for k, w in COMPONENT_WEIGHTS.items())


def _detect_wait_setup(analysis: dict, votes: list, direction: str, vetoes: list[str]) -> bool:
    """True when a setup is forming but not yet tradable."""
    if not vetoes:
        return False
    has_sweep = bool(analysis.get("sweeps"))
    has_structure = bool(analysis["structure"]["events"])
    forming_reasons = (
        "insufficient edge",
        "only 1 valid confluence",
        "only 0 valid confluence",
        "blended confidence",
    )
    veto_text = " ".join(vetoes).lower()
    if any(r in veto_text for r in forming_reasons):
        if has_sweep and not has_structure:
            return True
        if has_sweep or has_structure:
            bull_v = sum(w for d, w, _, _ in votes if d == "bullish")
            bear_v = sum(w for d, w, _, _ in votes if d == "bearish")
            if max(bull_v, bear_v) >= MIN_SCORE * 0.6:
                return True
    if has_sweep and not has_structure:
        return True
    for gap in analysis.get("fvgs", []):
        if gap["status"] in ("open", "partial") and gap["direction"] == direction:
            if analysis["price"] < gap["low"] or analysis["price"] > gap["high"]:
                return True
    return False


def _stop_and_target(analysis: dict, direction: str, decimals: int) -> dict:
    """Structure-based SL/TP: stop beyond protective structure, target at
    the nearest opposing unswept liquidity, minimum RR enforced."""
    price = analysis["price"]
    atr_val = analysis["atr"]
    buffer = 0.25 * atr_val
    swings = analysis["swings"]

    if direction == "bullish":
        protectors = [ob["low"] for ob in analysis["valid_order_blocks"]
                      if ob["direction"] == "bullish" and ob["low"] < price]
        protectors += [s["level"] for s in analysis["sweeps"] if s["side"] == "sellside" and s["level"] < price]
        if not swings.empty:
            lows_below = swings[(swings["kind"] == "low") & (swings["price"] < price)]
            if not lows_below.empty:
                protectors.append(float(lows_below.iloc[-1]["price"]))
        stop = (max(protectors) - buffer) if protectors else price - 1.5 * atr_val
        stop = min(stop, price - 0.5 * atr_val)  # never inside the noise

        targets = sorted(
            [p["level"] for p in analysis["pools"] if p["side"] == "buyside" and not p["swept"] and p["level"] > price]
            + ([float(swings[swings["kind"] == "high"]["price"].max())] if not swings.empty and (swings["kind"] == "high").any() else [])
        )
        targets = [t for t in targets if t > price]
        risk = price - stop
        target = next((t for t in targets if (t - price) / risk >= MIN_RISK_REWARD), None)
        if target is None:
            target = price + 2.0 * risk
    else:
        protectors = [ob["high"] for ob in analysis["valid_order_blocks"]
                      if ob["direction"] == "bearish" and ob["high"] > price]
        protectors += [s["level"] for s in analysis["sweeps"] if s["side"] == "buyside" and s["level"] > price]
        if not swings.empty:
            highs_above = swings[(swings["kind"] == "high") & (swings["price"] > price)]
            if not highs_above.empty:
                protectors.append(float(highs_above.iloc[-1]["price"]))
        stop = (min(protectors) + buffer) if protectors else price + 1.5 * atr_val
        stop = max(stop, price + 0.5 * atr_val)

        targets = sorted(
            [p["level"] for p in analysis["pools"] if p["side"] == "sellside" and not p["swept"] and p["level"] < price]
            + ([float(swings[swings["kind"] == "low"]["price"].min())] if not swings.empty and (swings["kind"] == "low").any() else []),
            reverse=True,
        )
        targets = [t for t in targets if t < price]
        risk = stop - price
        target = next((t for t in targets if (price - t) / risk >= MIN_RISK_REWARD), None)
        if target is None:
            target = price - 2.0 * risk

    risk = abs(price - stop)
    reward = abs(target - price)
    return {
        "entry": round(price, decimals),
        "stop_loss": round(stop, decimals),
        "take_profit": round(target, decimals),
        "risk_reward": round(reward / risk, 2) if risk > 0 else None,
    }


def decide(
    analysis: dict,
    ml_signal: dict | None = None,
    strategy_mode: str = "both",
) -> dict:
    """Aggregate both strategies (and the ML view) into one decision."""
    mode = normalize_strategy_mode(strategy_mode)
    symbol = analysis["symbol"]
    decimals = 3 if symbol.upper().endswith("JPY") else 5
    votes = _collect_votes(analysis, strategy_mode=mode)

    bull_votes = [(w, r) for d, w, r, _ in votes if d == "bullish"]
    bear_votes = [(w, r) for d, w, r, _ in votes if d == "bearish"]
    bull_score = sum(w for w, _ in bull_votes)
    bear_score = sum(w for w, _ in bear_votes)

    direction = "bullish" if bull_score > bear_score else "bearish"
    winner_score, winner_votes = (
        (bull_score, bull_votes) if direction == "bullish" else (bear_score, bear_votes)
    )
    loser_score = min(bull_score, bear_score)
    total = bull_score + bear_score
    reasoning = [r for _, r in (bull_votes if direction == "bullish" else bear_votes)]
    counter = [r for _, r in (bear_votes if direction == "bullish" else bull_votes)]
    component_scores = _component_scores(votes, direction)
    no_trade_reasons: list[str] = []
    vetoes: list[str] = []
    pd_info = analysis["premium_discount"]
    apply_ict_vetoes = mode in ("both", "ict")
    if apply_ict_vetoes and direction == "bullish" and pd_info["zone"] != "discount":
        vetoes.append(
            f"VETO: longs only valid in discount; price is in {pd_info['zone']} "
            f"({pd_info['position']:.0%} of dealing range)"
        )
    if apply_ict_vetoes and direction == "bearish" and pd_info["zone"] != "premium":
        vetoes.append(
            f"VETO: shorts only valid in premium; price is in {pd_info['zone']} "
            f"({pd_info['position']:.0%} of dealing range)"
        )
    if apply_ict_vetoes and direction == "bullish" and pd_info["position"] > EXTREME_PREMIUM:
        vetoes.append(
            f"VETO: buying in extreme premium ({pd_info['position']:.0%} of dealing range) is invalid"
        )
    if apply_ict_vetoes and direction == "bearish" and pd_info["position"] < 1 - EXTREME_PREMIUM:
        vetoes.append(
            f"VETO: selling in extreme discount ({pd_info['position']:.0%} of dealing range) is invalid"
        )
    if winner_score < MIN_SCORE or (winner_score - loser_score) < MIN_GAP:
        vetoes.append(
            f"VETO: insufficient edge (bull {bull_score:.1f} vs bear {bear_score:.1f})"
        )
    if len(winner_votes) < MIN_CONFLUENCES:
        vetoes.append(
            f"VETO: only {len(winner_votes)} valid confluence(s); minimum is {MIN_CONFLUENCES}"
        )

    rule_confidence = float(np.clip(winner_score / total, 0.0, 0.97)) if total > 0 else 0.0

    # --- kill zone modifier (ICT timing) --------------------------------
    killzone = analysis["killzone"]
    if mode in ("both", "ict"):
        if killzone:
            rule_confidence = min(rule_confidence * 1.05, 0.97)
            reasoning.append(f"ICT kill zone: {killzone} session active - timing valid")
        else:
            rule_confidence *= 0.90
            reasoning.append("Outside ICT kill zones - timing weak, confidence reduced")

    # --- blend with the freshly trained ML model -------------------------
    ml_confidence = None
    if ml_signal and ml_signal.get("proba"):
        proba = ml_signal["proba"]
        ml_dir_prob = proba.get("up" if direction == "bullish" else "down", 0.0)
        ml_opp_prob = proba.get("down" if direction == "bullish" else "up", 0.0)
        ml_confidence = float(ml_dir_prob)
        final_confidence = 0.65 * rule_confidence + 0.35 * ml_dir_prob
        reasoning.append(
            f"ML model (trained on latest {symbol} data): "
            f"P(up)={proba.get('up', 0):.2f} P(down)={proba.get('down', 0):.2f} P(flat)={proba.get('flat', 0):.2f}"
        )
        if ml_opp_prob > 0.55 and rule_confidence < 0.70:
            vetoes.append(
                f"VETO: ML model contradicts the rule direction (P(opposite)={ml_opp_prob:.2f})"
            )
    else:
        final_confidence = rule_confidence

    final_confidence = float(np.clip(final_confidence, 0.0, 0.97))
    # Admin-tunable floor (settings table), env-default fallback.
    min_final = settings.get_float("min_final_confidence", MIN_FINAL_CONFIDENCE)
    if total > 0 and final_confidence < min_final:
        vetoes.append(
            f"VETO: blended confidence {final_confidence:.0%} below the "
            f"{min_final:.0%} minimum"
        )

    if vetoes or total == 0:
        risk_score = max(0, 100 - len(vetoes) * 25)
        component_scores["risk_filter"] = risk_score
        if _detect_wait_setup(analysis, votes, direction, vetoes) and total > 0:
            action = ACTION_WAIT
            levels = _stop_and_target(analysis, direction, decimals)
            no_trade_reasons = [v.replace("VETO: ", "") for v in vetoes]
        else:
            action = ACTION_NO_TRADE
            levels = {"entry": None, "stop_loss": None, "take_profit": None, "risk_reward": None}
            no_trade_reasons = [v.replace("VETO: ", "") for v in vetoes]
            if total == 0:
                no_trade_reasons.append("No valid confluence signals detected")
    else:
        action = ACTION_BUY if direction == "bullish" else ACTION_SELL
        levels = _stop_and_target(analysis, direction, decimals)
        component_scores["risk_filter"] = 100

    invalidation_price = levels.get("stop_loss")
    target_liquidity = levels.get("take_profit")

    decision = {
        "symbol": symbol,
        "strategy": mode,
        "action": action,
        "direction": direction if action not in (ACTION_NO_TRADE,) else (
            direction if action == ACTION_WAIT else None
        ),
        "confidence": round(final_confidence, 4),
        "rule_confidence": round(rule_confidence, 4),
        "ml_confidence": round(ml_confidence, 4) if ml_confidence is not None else None,
        "scores": {"bullish": round(bull_score, 2), "bearish": round(bear_score, 2)},
        "component_scores": component_scores,
        "weighted_score": round(_weighted_component_total(component_scores), 2),
        "confluences": len(winner_votes),
        "killzone": killzone,
        "premium_discount": pd_info,
        "reasoning": reasoning,
        "counter_signals": counter,
        "vetoes": vetoes,
        "no_trade_reasons": no_trade_reasons,
        "invalidation_price": invalidation_price,
        "target_liquidity": target_liquidity,
        "disclaimer": DISCLAIMER,
        **levels,
    }
    log.info(
        "%s -> %s (conf %.2f, bull %.1f / bear %.1f, %d confluences, kz=%s)",
        symbol, action, final_confidence, bull_score, bear_score,
        len(winner_votes), killzone,
    )
    return decision
