import os
from pathlib import Path
import pandas as pd
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup  # type: ignore
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes  # type: ignore
from predict.predict_direction import predict_market_direction  # type: ignore
from dotenv import load_dotenv  # type: ignore

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATA_DIR = Path("data")


# Decide trading action based on confidence
def decide_action(confidence_scores):
    if not confidence_scores:
        return "Don't Enter"

    top_label, top_prob = max(confidence_scores.items(), key=lambda x: x[1])
    label = top_label.lower()

    if label in ["strong uptrend", "buy"]:
        return "Buy"
    elif label in ["strong downtrend", "sell"]:
        return "Sell"
    else:
        return "Don't Enter"


# ✅ Calculate TP and SL based on last close using pips
def calculate_tp_sl(csv_file_path, action, sl_pips=10, risk_reward_ratio=2):
    """
    Calculate TP and SL using pip values with a risk-to-reward ratio.
    Default: SL = 10 pips, RRR = 2 (so TP = 20 pips).
    """
    df = pd.read_csv(csv_file_path)

    if df.empty or "Close" not in df.columns:
        return None, None

    last_close = df["Close"].iloc[-1]

    # Pip size detection (JPY pairs use 0.01, others use 0.0001)
    pip_size = 0.01 if "JPY" in csv_file_path.upper() else 0.0001

    # Compute pip distances
    tp_pips = sl_pips * risk_reward_ratio

    if action == "Buy":
        sl = last_close - (sl_pips * pip_size)
        tp = last_close + (tp_pips * pip_size)
    elif action == "Sell":
        sl = last_close + (sl_pips * pip_size)
        tp = last_close - (tp_pips * pip_size)
    else:
        return None, None

    return round(tp, 5), round(sl, 5)

    """
    Calculate TP and SL using pip values.
    Default: TP = 20 pips, SL = 10 pips.
    """
    df = pd.read_csv(csv_file_path)

    if df.empty or "Close" not in df.columns:
        return None, None

    last_close = df["Close"].iloc[-1]

    # Determine pip size (JPY pairs use 0.01, others use 0.0001)
    pip_size = 0.01 if "JPY" in csv_file_path.upper() else 0.0001

    if action == "Buy":
        sl = last_close - (sl_pips * pip_size)
        tp = last_close + (tp_pips * pip_size)
    elif action == "Sell":
        sl = last_close + (sl_pips * pip_size)
        tp = last_close - (tp_pips * pip_size)
    else:
        return None, None

    return round(tp, 5), round(sl, 5)


# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    files = list(DATA_DIR.glob("*.csv"))
    if not files:
        await update.message.reply_text("❌ No CSV files found.")
        return

    keyboard = [[InlineKeyboardButton(f.name, callback_data=f.name)] for f in files]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📂 Select a file to analyze:", reply_markup=reply_markup)


# File selection handler
async def handle_file_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected_filename = query.data
    selected_file = DATA_DIR / selected_filename

    try:
        results = predict_market_direction(str(selected_file))

        if not results or not isinstance(results[0], tuple):
            await query.edit_message_text("⚠️ Unexpected result from prediction function.")
            return

        prediction, confidence = results[-1]  # Take the most recent prediction (last row)

        summary = [f"📊 *Prediction*: {prediction}"]

        if confidence:
            summary.append("\n📈 *Confidence Scores:*")
            for label, prob in confidence.items():
                summary.append(f"  - {label}: {prob * 100:.2f}%")

            action = decide_action(confidence)
            summary.append(f"\n🚦 *Final Action*: {action}")

            tp, sl = calculate_tp_sl(str(selected_file), action)
            if tp is not None and sl is not None:
                summary.append(f"🎯 *Take Profit*: {tp}")
                summary.append(f"🛡️ *Stop Loss*: {sl}")
                summary.append("\n🔗 [View Site](https://shimmering-crumble-d20c92.netlify.app/)")
            else:
                summary.append("⚠️ Could not calculate TP/SL.")
        else:
            summary.append("⚠️ No confidence data available.")

        await query.edit_message_text("\n".join(summary), parse_mode="Markdown")

    except Exception as e:
        await query.edit_message_text(f"❌ Error processing file:\n{str(e)}")


# Run bot
def run_bot():
    if not TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not found in .env file.")
        return

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_file_selection))

    print("✅ Telegram bot is running...")
    app.run_polling()


if __name__ == "__main__":
    run_bot()
