# bot.py
"""Telegram bot: pick a pair, run full pipeline, per-user delivery via /link."""
import asyncio

from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup  # type: ignore
from telegram.error import Conflict  # type: ignore
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes  # type: ignore

from services.user_access import decrement_quota, increment_quota, can_use_predictions, DEFAULT_SIGNALS_QUOTA
from engine.data import normalize_symbol
from engine.pipeline import predict_symbol, format_result_text
from services.prediction_record import record_prediction_from_result
from services.telegram_link import get_user_by_chat, get_or_register_telegram_user, redeem_link_code, unlink_user
from services.user_feedback_service import submit_feedback
from utils.compliance import DISCLAIMER
from utils.config import TELEGRAM_BOT_TOKEN
from utils.logger import get_logger
from utils import settings as runtime_settings
from utils.settings import get_supported_pairs

log = get_logger("bot")


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
    await update.message.reply_text(
        "SmartFlow AI — SMC/ICT signal engine.\n\n"
        + welcome
        + f"\n\n{DISCLAIMER}\n\n"
        "Commands: /predict EURUSD, /pairs, /feedback, /link CODE, /unlink",
        reply_markup=_pair_keyboard(),
    )


async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /link 123456\nGet a code from POST /telegram/link-code (authenticated).")
        return
    code = context.args[0].strip().zfill(6) if context.args[0].strip().isdigit() else context.args[0].strip()
    chat_id = str(update.effective_chat.id)
    result = redeem_link_code(chat_id, code)
    if result.get("error"):
        await update.message.reply_text(f"Link failed: {result['error']}")
    else:
        await update.message.reply_text(
            "Account linked. Predictions share the same free-trial quota as the web app."
        )


async def unlink_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    user = get_user_by_chat(chat_id)
    if not user:
        await update.message.reply_text("No linked account.")
        return
    unlink_user(user.id)
    await update.message.reply_text("Telegram unlinked.")


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
        pending = [r for r in reviews if r.get("feedback_required")]
        if not pending:
            await update.message.reply_text("No predictions awaiting feedback right now.")
            return
        lines = ["Predictions awaiting your feedback (use /feedback ID SUCCESSFUL|FAILED|DID_NOT_TAKE):"]
        for r in pending[:5]:
            lines.append(f"  #{r['id']} {r['symbol']} {r['predicted_action']}")
        await update.message.reply_text("\n".join(lines))
        return

    try:
        review_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Usage: /feedback <review_id> SUCCESSFUL|FAILED|DID_NOT_TAKE")
        return
    fb = context.args[1].upper()
    ok, msg, _ = await asyncio.to_thread(submit_feedback, user.id, review_id, fb)
    await update.message.reply_text(msg if ok else f"Could not save feedback: {msg}")


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
        "3. Training the model on this data\n"
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
        if user_id and quota_msg:
            text += f"\n\n({quota_msg})"
        if review:
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
        await query.edit_message_text(text)

    async def send_result(text):
        try:
            await query.edit_message_text(text, parse_mode="Markdown")
        except Exception:
            await query.edit_message_text(text)

    await _run_prediction(symbol, send_status, send_result, user.id)


async def predict_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: /predict EURUSD", reply_markup=_pair_keyboard()
        )
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
        status_msg = await update.message.reply_text(text)

    async def send_result(text):
        try:
            if status_msg:
                await status_msg.edit_text(text, parse_mode="Markdown")
            else:
                await update.message.reply_text(text, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(text)

    await _run_prediction(
        context.args[0], send_status, send_result, user.id
    )


async def pairs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Supported pairs:", reply_markup=_pair_keyboard())


async def _clear_webhook_for_polling(bot: Bot) -> bool:
    """Drop any webhook so long-polling (getUpdates) is allowed."""
    deleted = await bot.delete_webhook(drop_pending_updates=True)
    if deleted:
        log.info("Removed active Telegram webhook — switching to long polling.")
    return bool(deleted)


async def _post_init(application):
    await _clear_webhook_for_polling(application.bot)


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(context.error, Conflict):
        log.warning(
            "Telegram polling conflict (%s) — clearing webhook again.",
            context.error,
        )
        await _clear_webhook_for_polling(context.application.bot)
        return
    log.exception("Telegram bot handler error", exc_info=context.error)


def build_application():
    application = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(_post_init)
        .build()
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("predict", predict_command))
    application.add_handler(CommandHandler("pairs", pairs_command))
    application.add_handler(CommandHandler("link", link_command))
    application.add_handler(CommandHandler("unlink", unlink_command))
    application.add_handler(CommandHandler("feedback", feedback_command))
    application.add_handler(CallbackQueryHandler(handle_pair_selection, pattern=r"^predict:"))
    application.add_error_handler(_on_error)
    return application


def _prepare_event_loop(in_thread: bool) -> asyncio.AbstractEventLoop:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop


async def _bootstrap_polling():
    """Delete webhook before Application.run_polling (belt-and-suspenders)."""
    bot = Bot(TELEGRAM_BOT_TOKEN)
    try:
        await _clear_webhook_for_polling(bot)
    finally:
        await bot.shutdown()


def run_bot(in_thread: bool = False):
    if not TELEGRAM_BOT_TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN not set - bot disabled.")
        return

    loop = _prepare_event_loop(in_thread)
    loop.run_until_complete(_bootstrap_polling())

    application = build_application()
    log.info("Telegram bot polling started.")
    if in_thread:
        application.run_polling(
            stop_signals=None,
            drop_pending_updates=True,
            close_loop=False,
        )
    else:
        application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    run_bot()
