import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import random
from collections import deque

# --- BOT TEMEL ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}  # 2 admin

def is_admin(update: Update):
    return update.effective_user.id in ADMIN_IDS

# --- HIDDEN MAP ---
hidden_map = {0:(32,26),1:(33,20),2:(25,21),3:(26,35),4:(21,19),
5:(24,10),6:(27,34),7:(28,29),8:(23,30),9:(22,31),
10:(5,23),11:(30,36),12:(35,28),13:(36,27),14:(31,20),
15:(19,32),16:(33,24),17:(34,25),18:(29,22),19:(4,15),
20:(14,1),21:(2,4),22:(18,9),23:(10,8),24:(16,5),
25:(17,2),26:(0,3),27:(13,6),28:(12,7),29:(7,18),
30:(8,11),31:(9,14),32:(15,0),33:(1,16),34:(6,17),
35:(3,12),36:(11,13)}

# --- GLOBAL ---
prev_guess = None
history = deque(maxlen=50)  # geçmiş kullanıcı girdileri
current_hidden_set = set()
current_main_guess = []

# --- HELPER ---
def get_hidden_set(main_number):
    sol1, sag1 = hidden_map[main_number]
    sol2, _ = hidden_map[sol1]
    _, sag2 = hidden_map[sag1]
    sol3, _ = hidden_map[sol2]
    _, sag3 = hidden_map[sag2]
    return {sol3, sol2, sol1, main_number, sag1, sag2, sag3}

def generate_main_guess():
    # geçmişe göre ağırlıklı tahmin
    scores = {num:1 for num in range(37)}
    for h in history:
        for delta in [-1,0,1]:
            n = (h + delta) % 37
            scores[n] += 3
    sorted_scores = sorted(scores.items(), key=lambda x:-x[1])
    return [num for num,_ in sorted_scores[:2]]

# --- START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text("Bot aktif ✅ 2 adminli sistem hazır. Tahminler başlıyor...")

# --- TAHMİN ---
async def evrimsel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global prev_guess, history, current_hidden_set, current_main_guess
    if not is_admin(update):
        return

    user_input_text = update.message.text
    if not user_input_text.isdigit():
        await update.message.reply_text("Sadece sayı giriniz.")
        return
    user_input = int(user_input_text)

    # --- Kullanıcının önceki tahmini kontrol et ---
    if current_hidden_set:
        if user_input in current_hidden_set:
            await update.message.reply_text("Kazandım")
        else:
            await update.message.reply_text("Kaybettim")
        history.append(user_input)

    # --- Yeni tahmin üret ---
    current_main_guess = generate_main_guess()
    current_hidden_set = set()
    for num in current_main_guess:
        current_hidden_set.update(get_hidden_set(num))

    # --- Ana sayıları göster ---
    await update.message.reply_text(f"Ana sayılar: {current_main_guess}")

# --- APP ---
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, evrimsel))

print("Bot çalışıyor...")
app.run_polling()
