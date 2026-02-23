import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

TOKEN = "8613047337:AAES_dc6-VGy1YXveIuaNFCrb3ObsotMQ2w"
AUTHORIZED_USER_ID = 5813833511

numbers = []
WINDOW_SIZE = 100

def analyze(data):
    if not data:
        return "Henüz veri yok."

    window = data[-WINDOW_SIZE:]

    freq = {}
    for n in window:
        freq[n] = freq.get(n, 0) + 1

    sorted_freq = sorted(freq.items(), key=lambda x: x[1], reverse=True)

    strongest = [str(x[0]) for x in sorted_freq[:3]]

    aggressive = []
    for n in range(37):
        if n not in freq:
            aggressive.append(str(n))
        if len(aggressive) == 3:
            break

    neighbors = []
    for s in strongest:
        num = int(s)
        left = (num - 1) % 37
        right = (num + 1) % 37
        neighbors.append(f"{num} → {left} {right}")

    response = f"""
Toplam Veri: {len(data)}
Window: {len(window)}

En Güçlü: {' '.join(strongest)}
Agresif: {' '.join(aggressive)}

Komşular:
{chr(10).join(neighbors)}
"""
    return response


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != AUTHORIZED_USER_ID:
        return
    await update.message.reply_text("Sistem aktif. Sayı gönderebilirsin.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != AUTHORIZED_USER_ID:
        return

    try:
        num = int(update.message.text)
        if 0 <= num <= 36:
            numbers.append(num)
            result = analyze(numbers)
            await update.message.reply_text(result)
        else:
            await update.message.reply_text("0-36 arası sayı gir.")
    except:
        await update.message.reply_text("Geçerli bir sayı gönder.")


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.run_polling()