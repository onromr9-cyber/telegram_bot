import os
import random
from collections import defaultdict, deque, Counter
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- BOT TEMEL ---
TOKEN = os.getenv("BOT_TOKEN")

# 2 admin desteği
ADMIN_IDS = {5813833511, 1278793650}

def is_admin(update: Update):
    return update.effective_user.id in ADMIN_IDS

# --- EVRİMSEL MOTOR AYARLARI ---
NUM_RANGE = 37
WINDOW = 100
RECENT_WINDOW = 10
SHORT_WINDOW = 5
PERF_WINDOW = 20
NUM_MAIN = 3
NUM_SUPPORT = 3

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
        "prev_input": None,
        "history": deque(maxlen=WINDOW),
        "transition": defaultdict(lambda: defaultdict(int)),
        "performance": deque(maxlen=PERF_WINDOW),
        "total_rounds": 0,
        "total_main_hits": 0,
        "total_support_hits": 0
    }

# --- START KOMUTU ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text("Bot aktif ✅ Pro Mode ile hazır. İki admin aynı anda kullanabilir.")

# --- SKOR HESAPLAMA ---
def calculate_scores(admin_dict):
    scores = {}
    history = admin_dict["history"]
    transition = admin_dict["transition"]
    prev_input = admin_dict["prev_input"]
    performance = admin_dict["performance"]

    global_counts = Counter([x[1] for x in history])
    recent_counts = Counter([x[1] for x in list(history)[-RECENT_WINDOW:]])
    short_counts = Counter([x[1] for x in list(history)[-SHORT_WINDOW:]])

    win_rate = (sum(performance)/len(performance)) if performance else 0

    # Adaptif ağırlık
    if win_rate < 0.35:
        t_weight, g_weight, r_weight, n_weight, m_weight = 5, 3, 8, 4, 6
    elif win_rate < 0.5:
        t_weight, g_weight, r_weight, n_weight, m_weight = 4, 3, 6, 3, 4
    else:
        t_weight, g_weight, r_weight, n_weight, m_weight = 3, 3, 4, 2, 2

    for num in range(NUM_RANGE):
        transition_count = transition[prev_input][num]
        global_count = global_counts[num]
        recent_count = recent_counts[num]
        momentum = short_counts[num] ** 2

        sol1, sag1 = hidden_map[num]
        sol2, sag2 = hidden_map[sol1][0], hidden_map[sag1][1]

        neighbor_trend = (
            recent_counts[sol1] +
            recent_counts[sag1] +
            recent_counts[sol2] +
            recent_counts[sag2]
        )

        score = (
            transition_count * t_weight +
            global_count * g_weight +
            recent_count * r_weight +
            neighbor_trend * n_weight +
            momentum * m_weight
        )

        scores[num] = score

    # Hot filter
    hot_numbers = [num for num,_ in global_counts.most_common(12)]
    filtered_scores = {k:v for k,v in scores.items() if k in hot_numbers}
    return filtered_scores if len(filtered_scores) >= 6 else scores

# --- ANA MOTOR ---
async def evrimsel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(update):
        return

    admin_dict = admins_data[user_id]

    user_input_text = update.message.text
    if not user_input_text.isdigit():
        await update.message.reply_text("Sadece 0-36 arası sayı giriniz.")
        return

    user_input = int(user_input_text)
    if not 0 <= user_input < NUM_RANGE:
        await update.message.reply_text("0-36 arası sayı giriniz.")
        return

    # İlk veri
    if admin_dict["prev_input"] is None:
        admin_dict["prev_input"] = user_input
        await update.message.reply_text("Başlangıç verisi alındı. Öğrenme başlıyor...")
        return

    # Skor hesapla ve sıralı tahmin
    scores = calculate_scores(admin_dict)
    sorted_nums = sorted(scores.items(), key=lambda x: -x[1])

    main_guess = [num for num,_ in sorted_nums[:NUM_MAIN]]
    support_guess = [num for num,_ in sorted_nums[NUM_MAIN:NUM_MAIN+NUM_SUPPORT]]

    hidden_bonus = set()
    for num in main_guess + support_guess:
        sol1, sag1 = hidden_map[num]
        sol2, sag2 = hidden_map[sol1][0], hidden_map[sag1][1]
        hidden_bonus.update([sol1, sag1, sol2, sag2])

    # Sonuçlar
    total_rounds = admin_dict["total_rounds"]
    total_main_hits = admin_dict["total_main_hits"]
    total_support_hits = admin_dict["total_support_hits"]

    main_hit = user_input in main_guess
    support_hit = user_input in support_guess

    if main_hit:
        admin_dict["total_main_hits"] += 1
    if support_hit:
        admin_dict["total_support_hits"] += 1

    admin_dict["performance"].append(1 if main_hit else 0)
    admin_dict["total_rounds"] += 1

    await update.message.reply_text(
        f"Main: {main_guess}\nSupport: {support_guess}\nHidden Coverage: {sorted(list(hidden_bonus))}\n"
        f"Main WR: %{(admin_dict['total_main_hits']/admin_dict['total_rounds']*100):.2f} | "
        f"Support WR: %{(admin_dict['total_support_hits']/admin_dict['total_rounds']*100):.2f}"
    )

    # Win / Lose mesaj
    if main_hit or support_hit or user_input in hidden_bonus:
        await update.message.reply_text("🎯 Kazandınız!")
    else:
        await update.message.reply_text("Kaybettik.")

    # History ve transition güncelle
    if len(admin_dict["history"]) == WINDOW:
        old_prev, old_correct = admin_dict["history"][0]
        admin_dict["transition"][old_prev][old_correct] -= 1

    admin_dict["history"].append((admin_dict["prev_input"], user_input))
    admin_dict["transition"][admin_dict["prev_input"]][user_input] += 1
    admin_dict["prev_input"] = user_input

# --- APP BAŞLAT ---
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, evrimsel))

print("Bot çalışıyor... Pro Mode")
app.run_polling()
