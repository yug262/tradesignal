"""Market Open Confirmation Agent — Phase 2 of the trading pipeline.

Runs at 9:20 AM IST (5 minutes after NSE market open).
Takes Agent 1's pre-market signals (pending_confirmation) and validates them
against LIVE market-open data.

Pipeline:
  1. Query DB for today's signals where status = 'pending_confirmation'
  2. For each signal with BUY/SELL (skip NO_TRADE/HOLD):
     a. Fetch LIVE stock data (current price, volume, open, high/low)
     b. Compare opening data with Agent 1's predictions
     c. Send to Gemini for confirmation analysis
     d. Update signal: confirmation_status, confirmation_data, revised prices
  3. Return summary of all confirmations
"""

import time
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

import db_models
from database import SessionLocal
from agent.data_collector import fetch_stock_data_for_symbols
from agent.gemini_confirmer import confirm_signal


IST = timezone(timedelta(hours=5, minutes=30))


def _market_date_str() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def _now_ms() -> int:
    return int(time.time() * 1000)


def run_market_open_confirmation(db: Session = None) -> dict:
    """
    Execute the Market Open Confirmation pipeline.

    Fetches all pending_confirmation signals for today, gets live market data,
    and uses Gemini to confirm/revise/invalidate each one.

    Returns a summary dict with confirmation results.
    """
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    try:
        market_date = _market_date_str()
        run_id = f"confirm-{market_date}-{uuid.uuid4().hex[:8]}"
        started_at = _now_ms()

        print(f"\n{'='*60}")
        print(f"[AGENT 2] MARKET OPEN CONFIRMATION -- Run ID: {run_id}")
        print(f"   Market Date: {market_date}")
        print(f"   Time: {datetime.now(IST).strftime('%H:%M:%S IST')}")
        print(f"   NSE opened at 09:15 — checking live data now")
        print(f"{'='*60}")

        # -- Step 1: Get today's pending signals ----------------------------
        pending_signals = (
            db.query(db_models.DBTradeSignal)
            .filter(db_models.DBTradeSignal.market_date == market_date)
            .filter(db_models.DBTradeSignal.confirmation_status == "pending")
            .all()
        )

        if not pending_signals:
            print("\n[WARN] No pending signals found for today. Nothing to confirm.")
            return {
                "run_id": run_id,
                "market_date": market_date,
                "confirmed_at": _now_ms(),
                "total_checked": 0,
                "summary": {"confirmed": 0, "revised": 0, "invalidated": 0, "skipped": 0},
                "results": [],
                "duration_ms": _now_ms() - started_at,
            }

        # Filter: only confirm BUY/SELL signals, auto-skip HOLD/NO_TRADE
        tradable_signals = [s for s in pending_signals if s.signal_type in ("BUY", "SELL")]
        skip_signals = [s for s in pending_signals if s.signal_type not in ("BUY", "SELL")]

        print(f"\n[STEP 1] Found {len(pending_signals)} pending signals")
        print(f"   Tradable (BUY/SELL): {len(tradable_signals)}")
        print(f"   Auto-skip (HOLD/NO_TRADE): {len(skip_signals)}")

        # Auto-skip non-tradable signals
        for sig in skip_signals:
            sig.confirmation_status = "invalidated"
            sig.confirmed_at = _now_ms()
            sig.confirmation_data = {
                "decision": "INVALIDATED",
                "reasoning": {"final_recommendation": f"Auto-skipped: original signal was {sig.signal_type}"},
                "_source": "auto_skip",
            }

        if not tradable_signals:
            db.commit()
            print("\n[DONE] No BUY/SELL signals to confirm.")
            return {
                "run_id": run_id,
                "market_date": market_date,
                "confirmed_at": _now_ms(),
                "total_checked": len(pending_signals),
                "summary": {"confirmed": 0, "revised": 0, "invalidated": len(skip_signals), "skipped": 0},
                "results": [],
                "duration_ms": _now_ms() - started_at,
            }

        # -- Step 2: Fetch LIVE stock data for all symbols ------------------
        symbols = list(set(s.symbol for s in tradable_signals))
        print(f"\n[STEP 2] Fetching LIVE market data for {len(symbols)} symbols...")
        live_data_map = fetch_stock_data_for_symbols(symbols)
        print(f"   [OK] Got live data for {len(live_data_map)} symbols")

        # -- Step 3: Run confirmation for each signal -----------------------
        print(f"\n[STEP 3] Running Gemini confirmation analysis...")
        results = []
        summary = {"confirmed": 0, "revised": 0, "invalidated": 0, "skipped": 0}

        for sig in tradable_signals:
            live_data = live_data_map.get(sig.symbol)
            if not live_data:
                print(f"   [SKIP] {sig.symbol}: No live data available")
                sig.confirmation_status = "confirmed"  # Default to confirmed if no data
                sig.confirmed_at = _now_ms()
                sig.confirmation_data = {
                    "decision": "CONFIRMED",
                    "reasoning": {"final_recommendation": "No live data — keeping original signal"},
                    "_source": "no_data_fallback",
                }
                summary["skipped"] += 1
                continue

            print(f"\n   -- Confirming {sig.symbol} ({sig.signal_type} {sig.trade_mode}) --")

            # Get Agent 1's stock snapshot for comparison
            prev_snapshot = sig.stock_snapshot if isinstance(sig.stock_snapshot, dict) else {}

            # Log the key comparison
            prev_close = prev_snapshot.get("last_close") or live_data.get("last_close") or 0
            open_price = live_data.get("today_open") or 0
            volume = live_data.get("current_volume") or 0
            gap_pct = 0
            if prev_close and prev_close > 0 and open_price:
                gap_pct = round(((open_price - prev_close) / prev_close) * 100, 2)

            print(f"      Prev Close: Rs.{prev_close}")
            print(f"      Open Price: Rs.{open_price}  (Gap: {gap_pct}%)")
            print(f"      Volume: {volume}")
            print(f"      Entry was: Rs.{sig.entry_price} | SL: Rs.{sig.stop_loss} | Target: Rs.{sig.target_price}")

            # Build original signal dict for Gemini
            original_signal_dict = {
                "signal_type": sig.signal_type,
                "trade_mode": sig.trade_mode,
                "entry_price": sig.entry_price,
                "stop_loss": sig.stop_loss,
                "target_price": sig.target_price,
                "confidence": sig.confidence,
                "risk_reward": sig.risk_reward,
                "reasoning": sig.reasoning,
            }

            # Call Gemini
            print(f"      [GEMINI] Confirming {sig.symbol}...")
            confirmation = confirm_signal(
                symbol=sig.symbol,
                original_signal=original_signal_dict,
                live_stock_data=live_data,
                prev_stock_data=prev_snapshot,
                market_date=market_date,
            )

            decision = confirmation.get("decision", "CONFIRMED").upper()
            print(f"      [RESULT] {decision}")
            print(f"         Impact remaining: {confirmation.get('impact_remaining', 'N/A')}")
            print(f"         Gap type: {confirmation.get('gap_type', 'N/A')}")
            print(f"         Volume: {confirmation.get('volume_assessment', 'N/A')}")

            # -- Update the signal in DB ------------------------------------
            sig.confirmation_status = decision.lower()
            sig.confirmed_at = _now_ms()
            sig.confirmation_data = confirmation

            if decision == "CONFIRMED":
                sig.status = "confirmed"
                # Optionally update confidence from Gemini
                revised_conf = confirmation.get("revised_confidence")
                if revised_conf is not None:
                    sig.confidence = revised_conf
                summary["confirmed"] += 1

            elif decision == "REVISED":
                sig.status = "revised"
                # We no longer overwrite the main signal columns so Agent 1 page stays unchanged.
                # All revised values are already in the 'confirmation' dict and saved in sig.confirmation_data.
                
                print(f"         Revised: Entry Rs.{confirmation.get('revised_entry')} | SL Rs.{confirmation.get('revised_stop_loss')} | Target Rs.{confirmation.get('revised_target')}")
                summary["revised"] += 1

            elif decision == "INVALIDATED":
                sig.status = "invalidated"
                summary["invalidated"] += 1
            else:
                sig.status = "confirmed"
                summary["confirmed"] += 1

            results.append({
                "symbol": sig.symbol,
                "original_signal": sig.signal_type,
                "decision": decision,
                "impact_remaining": confirmation.get("impact_remaining"),
                "gap_type": confirmation.get("gap_type"),
                "volume_assessment": confirmation.get("volume_assessment"),
                "revised_entry": sig.entry_price,
                "revised_sl": sig.stop_loss,
                "revised_target": sig.target_price,
                "revised_confidence": sig.confidence,
                "reasoning": confirmation.get("reasoning", {}),
            })

        db.commit()

        duration = _now_ms() - started_at
        print(f"\n{'='*60}")
        print(f"[DONE] Market Open Confirmation complete!")
        print(f"   Checked: {len(tradable_signals)} signals")
        print(f"   CONFIRMED: {summary['confirmed']} | REVISED: {summary['revised']} | INVALIDATED: {summary['invalidated']} | SKIPPED: {summary['skipped']}")
        print(f"   Duration: {duration}ms")
        print(f"{'='*60}\n")

        return {
            "run_id": run_id,
            "market_date": market_date,
            "confirmed_at": _now_ms(),
            "total_checked": len(tradable_signals),
            "summary": summary,
            "results": results,
            "duration_ms": duration,
        }

    finally:
        if own_session:
            db.close()
