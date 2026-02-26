import os
import random
from collections import defaultdict, deque, Counter
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- BOT TEMEL ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}

def is_admin(update: Update):
    return update.effective_user.id in ADMIN_IDS

# --- EVRİMSEL MOTOR AYARLARI ---
NUM_RANGE = 37
WINDOW = 100
hidden_map = {
0:(32,26),1:(33,20),2:(25,21),3:(26,35),4:(21,19),
5:(24,10),6:(27,34),7:(28,29),8:(23,30),9:(22,31),
10:(5,23),11:(30,36),12:(35,28),13:(36,27),14:(31,20),
15:(19,32),16:(33,24),17:(34,25),18:(29,22),19:(4,15),
20:(14,1),21:(2,4),22:(18,9),23:(10,8),24:(16,5),
25:(17,2),26:(0,3),27:(13,6),28:(12,7),29:(7,18),
30:(8,11),31:(9,14),32:(15,0),33:(1,16),34:(6,17),
35:(3,12),36:(11,13)
}

# --- Admin Bazlı Veriler ---
admins_data = {}
for aid in ADMIN_IDS:
    admins_data[aid] = {
        "prev_input": 0,  # Başlangıç input
        "history": deque(maxlen=WINDOW),
        "transition": defaultdict(lambda: defaultdict(int)),
        "performance": deque(maxlen=20),
        "total_rounds": 0,
        "total_hits": 0
    }

# --- START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text("Bot aktif ✅ İlk sistem mantığı ile çalışıyor. İki admin kullanabilir.")

# --- ANA MOTOR ---
async def evrimsel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(update):
        return

    admin = admins_data[user_id]
    user_text = update.message.text

    # Rakam ve aralık kontrolü
    if not user_text.isdigit():
        await update.message.reply_text("Lütfen 0 ile 36 arasında geçerli bir sayı giriniz.")
        return

    user_input = int(user_text)
    if not 0 <= user_input <= 36:
        await update.message.reply_text("Lütfen 0 ile 36 arasında geçerli bir sayı giriniz.")
        return

    # Skor hesaplama (basit, ilk bot mantığı)
    global_counts = Counter([x[1] for x in admin["history"]])
    transition = admin["transition"]
    prev = admin["prev_input"]

    scores = {}
    for num in range(NUM_RANGE):
        scores[num] = transition[prev][num] + global_counts[num]

    # Sıralı tahmin
    sorted_nums = sorted(scores.items(), key=lambda x:-x[1])
    main_guess = [num for num,_ in sorted_nums[:3]]
    extra_guess = [num for num,_ in sorted_nums[3:6]]

    # Hidden bonus
    hidden_bonus = set()
    for num in main_guess + extra_guess:
        sol1, sag1 = hidden_map[num]
        sol2, sag2 = hidden_map[sol1][0], hidden_map[sag1][1]
        hidden_bonus.update([sol1, sag1, sol2, sag2])

    # Sonuç ve istatistik
    total_rounds = admin["total_rounds"]
    total_hits = admin["total_hits"]
    hit = user_input in main_guess or user_input in extra_guess or user_input in hidden_bonus

    if hit:
        admin["total_hits"] += 1
        admin["performance"].append(1)
        await update.message.reply_text("🎯 Kazandınız!")
    else:
        admin["performance"].append(0)
        await update.message.reply_text("Kaybettik.")

    admin["total_rounds"] += 1

    await update.message.reply_text(
        f"Ana: {main_guess}\nEkstra: {extra_guess}\nHidden: {sorted(list(hidden_bonus))}\n"
        f"Win Rate: %{(admin['total_hits']/admin['total_rounds']*100):.2f}"
    )

    # History ve transition güncelle
    if len(admin["history"]) == WINDOW:
        old_prev, old_correct = admin["history"][0]
        admin["transition"][old_prev][old_correct] -= 1

    admin["history"].append((prev,user_input))
    admin["transition"][prev][user_input] += 1
    admin["prev_input"] = user_input

# --- APP ---
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, evrimsel))

print("Bot çalışıyor... İlk sistem mantığı")
app.run_polling()
