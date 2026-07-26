# bot.py
"""Telegram bot: pick a pair, run full pipeline, per-user delivery via /link."""
import asyncio
import math

from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup  # type: ignore
from telegram.error import Conflict, NetworkError, RetryAfter, TimedOut  # type: ignore
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes  # type: ignore

from services.user_access import decrement_quota, increment_quota, can_use_predictions, DEFAULT_SIGNALS_QUOTA
from engine.data import normalize_symbol
from engine.risk_calc import calculate_lot_from_market
from engine.pipeline import predict_symbol, format_result_text
from services.prediction_record import record_prediction_from_result
from services.telegram_link import get_user_by_chat, get_or_register_telegram_user, redeem_link_code, unlink_user
from services.user_feedback_service import submit_feedback
from utils.compliance import DISCLAIMER
from utils.config import TELEGRAM_BOT_TOKEN
from utils.logger import get_logger
from utils import settings as runtime_settings
from utils.settings import get_supported_pairs
from utils.telegram_http import build_httpx_request, build_httpx_request_for_updates

log = get_logger("bot")

_SEND_RETRIES = 3


async def _send_with_retry(coro_factory, *, label: str = "message"):
    """Retry Telegram sends on transient network/timeouts."""
    last_exc = None
    for attempt in range(_SEND_RETRIES):
        try:
            return await coro_factory()
        except RetryAfter as exc:
            wait = float(exc.retry_after) + 1.0
            log.warning("Telegram rate limit on %s — waiting %.0fs", label, wait)
            await asyncio.sleep(wait)
            last_exc = exc
        except (TimedOut, NetworkError) as exc:
            last_exc = exc
            if attempt + 1 >= _SEND_RETRIES:
                break
            delay = 2 ** attempt
            log.warning("Telegram %s timeout (attempt %d/%d): %s", label, attempt + 1, _SEND_RETRIES, exc)
            await asyncio.sleep(delay)
    log.warning("Telegram could not deliver %s after %d attempts: %s", label, _SEND_RETRIES, last_exc)
    return None


async def safe_reply(message, text: str, **kwargs):
    return await _send_with_retry(lambda: message.reply_text(text, **kwargs), label="reply")


async def safe_edit(message, text: str, **kwargs):
    return await _send_with_retry(lambda: message.edit_text(text, **kwargs), label="edit")


def _pair_keyboard() -> InlineKeyboardMarkup:
    rows, row = [], []
    for pair in get_supported_pairs():
        row.append(InlineKeyboardButton(pair, callback_data=f"predict:{pair}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def _check_kill_switch(symbol: str) -> tuple[bool, str]:
    enabled = runtime_settings.get("predictions_enabled", "true")
    if str(enabled).strip().lower() in {"0", "false", "no", "off"}:
        return False, "Predictions are temporarily disabled by the administrator."
    disabled_raw = runtime_settings.get("disabled_pairs", "") or ""
    disabled = {p.strip().upper() for p in disabled_raw.split(",") if p.strip()}
    if symbol.upper() in disabled:
        return False, f"Predictions are disabled for {symbol.upper()}."
    return True, ""


def _check_user_access(user_id: int) -> tuple[bool, str]:
    from services.user_access import get_user
    user = get_user(user_id)
    return can_use_predictions(user)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    tg = update.effective_user
    user = await asyncio.to_thread(
        get_or_register_telegram_user,
        chat_id,
        tg.username if tg else None,
        tg.first_name if tg else None,
    )
    status = getattr(user, "status", "active")
    if status == "banned" or not user.is_active:
        welcome = "Your account is suspended. Contact support."
    else:
        welcome = (
            f"Welcome, {user.username}!\n"
            f"Free trial quota: {user.signals_remaining}/{DEFAULT_SIGNALS_QUOTA} "
            f"(shared with the web app when linked)\n\n"
            "Pick a pair below or use /predict EURUSD.\n"
            "After 2 hours you'll be asked for feedback on each prediction."
        )
    text = (
        "SmartFlow AI — SMC/ICT signal engine.\n\n"
        + welcome
        + f"\n\n{DISCLAIMER}\n\n"
        "Commands: /predict EURUSD, /pairs, /feedback, /link CODE, /unlink"
    )
    sent = await safe_reply(update.message, text, reply_markup=_pair_keyboard())
    if sent is None:
        log.error("Could not deliver /start welcome to chat %s (Telegram API unreachable)", chat_id)


async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await safe_reply(
            update.message,
            "Usage: /link 123456\nGet a code from POST /telegram/link-code (authenticated).",
        )
        return
    code = context.args[0].strip().zfill(6) if context.args[0].strip().isdigit() else context.args[0].strip()
    chat_id = str(update.effective_chat.id)
    result = redeem_link_code(chat_id, code)
    if result.get("error"):
        await safe_reply(update.message, f"Link failed: {result['error']}")
    else:
        await safe_reply(
            update.message,
            "Account linked. Predictions share the same free-trial quota as the web app.",
        )


async def unlink_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    user = get_user_by_chat(chat_id)
    if not user:
        await safe_reply(update.message, "No linked account.")
        return
    unlink_user(user.id)
    await safe_reply(update.message, "Telegram unlinked.")


async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /feedback <review_id> SUCCESSFUL|FAILED|DID_NOT_TAKE"""
    chat_id = str(update.effective_chat.id)
    user = get_user_by_chat(chat_id)
    if not user:
        tg = update.effective_user
        user = await asyncio.to_thread(
            get_or_register_telegram_user,
            chat_id,
            tg.username if tg else None,
            tg.first_name if tg else None,
        )
    if len(context.args) < 2:
        from services.prediction_review import list_reviews
        reviews = await asyncio.to_thread(
            lambda: list_reviews(user_id=user.id, limit=10)
        )
        pending = [r for r in reviews if r.get("can_record_outcome")]
        if not pending:
            await safe_reply(update.message, "No predictions waiting for outcome feedback.")
            return
        lines = ["Rate your trade: /feedback ID SUCCESSFUL|FAILED|DID_NOT_TAKE"]
        for r in pending[:5]:
            lines.append(f"  #{r['id']} {r['symbol']} {r['predicted_action']}")
        await safe_reply(update.message, "\n".join(lines))
        return

    try:
        review_id = int(context.args[0])
    except ValueError:
        await safe_reply(update.message, "Usage: /feedback <review_id> SUCCESSFUL|FAILED|DID_NOT_TAKE")
        return
    fb = context.args[1].upper()
    ok, msg, _ = await asyncio.to_thread(submit_feedback, user.id, review_id, fb)
    await safe_reply(update.message, msg if ok else f"Could not save feedback: {msg}")


async def _run_prediction(symbol: str, send_status, send_result, user_id: int | None = None):
    try:
        symbol = normalize_symbol(symbol)
    except ValueError as exc:
        await send_result(f"Error: {exc}")
        return

    ks_ok, ks_msg = await asyncio.to_thread(_check_kill_switch, symbol)
    if not ks_ok:
        await send_result(ks_msg)
        return

    quota_msg = ""
    if user_id:
        ok, quota_msg = await asyncio.to_thread(_check_user_access, user_id)
        if not ok:
            await send_result(quota_msg)
            return
        ok, quota_msg = await asyncio.to_thread(decrement_quota, user_id)
        if not ok:
            await send_result(quota_msg)
            return

    await send_status(
        f"Analyzing {symbol}...\n"
        "1. Pulling the latest candles\n"
        "2. Detecting valid SMC/ICT signals\n"
        "3. Running meta-model quality gate\n"
        "4. Aggregating the decision\n\n"
        "This takes a moment."
    )
    try:
        result = await asyncio.to_thread(predict_symbol, symbol)
        review = await asyncio.to_thread(
            record_prediction_from_result,
            user_id=user_id,
            result=result,
            horizon="intraday",
            source="telegram",
        )
        text = format_result_text(result, markdown=True)
        action = (result.get("decision") or {}).get("action", "")
        if action == "WAIT_FOR_CONFIRMATION":
            text += (
                "\n\n_We'll notify you here and in the web app when this setup confirms "
                "so you can enter the trade._"
            )
        if user_id and quota_msg:
            text += f"\n\n({quota_msg})"
        if review and action not in ("NO_TRADE", "WAIT_FOR_CONFIRMATION"):
            text += f"\n\nFeedback due in ~2 hours (review #{review.id}). Use /feedback when ready."
        text += f"\n\n{DISCLAIMER}"
        await send_result(text)
    except Exception as exc:
        if user_id:
            await asyncio.to_thread(increment_quota, user_id)
        log.exception("Bot prediction failed for %s", symbol)
        await send_result(f"Prediction failed for {symbol}: {exc}")


async def handle_pair_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    symbol = query.data.split(":", 1)[-1]
    tg = query.from_user
    user = await asyncio.to_thread(
        get_or_register_telegram_user,
        str(query.message.chat_id),
        tg.username if tg else None,
        tg.first_name if tg else None,
    )

    async def send_status(text):
        if await safe_edit(query.message, text) is None:
            await safe_reply(query.message, text)

    async def send_result(text):
        try:
            if await safe_edit(query.message, text, parse_mode="Markdown") is None:
                await safe_reply(query.message, text, parse_mode="Markdown")
        except Exception:
            await safe_reply(query.message, text)

    await _run_prediction(symbol, send_status, send_result, user.id)


async def predict_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await safe_reply(update.message, "Usage: /predict EURUSD", reply_markup=_pair_keyboard())
        return
    tg = update.effective_user
    user = await asyncio.to_thread(
        get_or_register_telegram_user,
        str(update.effective_chat.id),
        tg.username if tg else None,
        tg.first_name if tg else None,
    )
    status_msg = None

    async def send_status(text):
        nonlocal status_msg
        status_msg = await safe_reply(update.message, text)

    async def send_result(text):
        try:
            if status_msg:
                if await safe_edit(status_msg, text, parse_mode="Markdown") is None:
                    await safe_reply(update.message, text, parse_mode="Markdown")
            else:
                await safe_reply(update.message, text, parse_mode="Markdown")
        except Exception:
            await safe_reply(update.message, text)

    await _run_prediction(context.args[0], send_status, send_result, user.id)


async def pairs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(update.message, "Supported pairs:", reply_markup=_pair_keyboard())


def parse_lot_command_args(args) -> tuple[str, float, float]:
    if len(args) != 3:
        raise ValueError("Usage: /lot EURUSD 1000 1%")
    symbol_raw, balance_raw, risk_raw = args
    symbol = normalize_symbol(symbol_raw)
    supported = {normalize_symbol(pair) for pair in get_supported_pairs()}
    supported.add("XAUUSD")
    if symbol not in supported:
        raise ValueError(f"Unsupported symbol: {symbol}")
    try:
        balance = float(str(balance_raw).replace(",", "").strip())
        risk_pct = float(str(risk_raw).strip().removesuffix("%"))
    except ValueError as exc:
        raise ValueError("Balance and risk must be numbers, for example /lot EURUSD 1000 1%") from exc
    if not math.isfinite(balance) or balance <= 0:
        raise ValueError("Balance must be a positive number")
    if not math.isfinite(risk_pct) or not 0 < risk_pct <= 10:
        raise ValueError("Risk percentage must be greater than 0% and no more than 10%")
    return symbol, balance, risk_pct


async def lot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        symbol, balance, risk_pct = parse_lot_command_args(context.args)
        result = await asyncio.to_thread(
            calculate_lot_from_market, symbol, balance, risk_pct
        )
    except (ValueError, TypeError) as exc:
        await safe_reply(update.message, f"Lot calculation failed: {exc}")
        return
    except Exception as exc:
        log.exception("Telegram lot calculation failed for %s", context.args[:1])
        await safe_reply(update.message, "Lot calculation is temporarily unavailable. Please try again.")
        return
    await safe_reply(
        update.message,
        f"Risk sizing - {result['symbol']}\n\n"
        f"Balance: ${result['balance']:.2f}\n"
        f"Risk: {result['risk_pct']:.2f}% (${result['requested_risk_amount']:.2f})\n"
        f"Entry: {result['entry']}\n"
        f"Stop Loss: {result['stop_loss']} ({result['sl_pips']} pips, {result['stop_method']})\n"
        f"Pip value: ${result['pip_value_per_lot_usd']:.2f}/lot\n"
        f"Recommended lot size: {result['lot_size']:.2f}\n"
        f"Position size: {result['position_size']:.2f} units\n"
        f"Data source: {result['data_source']}"
    )


async def _clear_webhook_for_polling(bot: Bot) -> bool:
    """Drop any webhook so long-polling (getUpdates) is allowed."""
    from utils.telegram_http import is_telegram_network_error

    try:
        deleted = await bot.delete_webhook(drop_pending_updates=True)
        if deleted:
            log.info("Removed active Telegram webhook — switching to long polling.")
        return bool(deleted)
    except Exception as exc:
        if is_telegram_network_error(exc):
            log.warning("Could not clear Telegram webhook (network): %s", exc)
        else:
            log.warning("Could not clear Telegram webhook: %s", exc)
        return False


async def _post_init(application):
    await _clear_webhook_for_polling(application.bot)


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = context.error
    if isinstance(err, Conflict):
        log.warning("Telegram polling conflict (%s) — clearing webhook again.", err)
        await _clear_webhook_for_polling(context.application.bot)
        return
    if isinstance(err, (TimedOut, NetworkError)):
        log.warning("Telegram network error (transient): %s", err)
        return
    log.exception("Telegram bot handler error", exc_info=err)


def build_application():
    request = build_httpx_request()
    updates_request = build_httpx_request_for_updates()
    application = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .request(request)
        .get_updates_request(updates_request)
        .post_init(_post_init)
        .build()
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("predict", predict_command))
    application.add_handler(CommandHandler("pairs", pairs_command))
    application.add_handler(CommandHandler("link", link_command))
    application.add_handler(CommandHandler("unlink", unlink_command))
    application.add_handler(CommandHandler("feedback", feedback_command))
    application.add_handler(CommandHandler("lot", lot_command))
    application.add_handler(CallbackQueryHandler(handle_pair_selection, pattern=r"^predict:"))
    application.add_error_handler(_on_error)
    return application


def _prepare_event_loop(in_thread: bool) -> asyncio.AbstractEventLoop:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop


async def _bootstrap_polling():
    """Delete webhook before Application.run_polling (belt-and-suspenders)."""
    request = build_httpx_request()
    bot = Bot(TELEGRAM_BOT_TOKEN, request=request)
    try:
        await _clear_webhook_for_polling(bot)
    finally:
        await bot.shutdown()


def run_bot(in_thread: bool = False) -> bool:
    """Start polling. Returns True if polling ran; False if network unavailable."""
    if not TELEGRAM_BOT_TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN not set - bot disabled.")
        return False

    from utils.telegram_http import is_telegram_network_error, telegram_api_reachable

    if not telegram_api_reachable():
        log.warning(
            "Telegram API unreachable — skipping bot start. "
            "Use TELEGRAM_PROXY_URL if blocked, or TELEGRAM_BOT_ENABLED=false to disable."
        )
        return False

    loop = _prepare_event_loop(in_thread)
    try:
        loop.run_until_complete(_bootstrap_polling())
    except Exception as exc:
        if is_telegram_network_error(exc):
            log.warning("Telegram bootstrap failed (network): %s", exc)
            return False
        raise

    application = build_application()
    log.info("Telegram bot polling started.")
    try:
        if in_thread:
            application.run_polling(
                stop_signals=None,
                drop_pending_updates=True,
                close_loop=False,
            )
        else:
            application.run_polling(drop_pending_updates=True)
        return True
    except Exception as exc:
        if is_telegram_network_error(exc):
            log.warning("Telegram polling stopped (network): %s", exc)
            return False
        raise


if __name__ == "__main__":
    run_bot()
