import os
import random
from collections import defaultdict, deque, Counter
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- BOT TEMEL ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}  # İki admin

def is_admin(update: Update):
    return update.effective_user.id in ADMIN_IDS

# --- EVRİMSEL MOTOR VERİLERİ ---
NUM_RANGE = 37
WINDOW = 100
RECENT_WINDOW = 10
SHORT_WINDOW = 5
PERF_WINDOW = 20
NUM_GUESS = 3
NUM_EXTRA = 3

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

# --- Admin bazlı veriler ---
admins_data = {}
for aid in ADMIN_IDS:
    admins_data[aid] = {
        "prev_input": 0,
        "history": deque(maxlen=WINDOW),
        "transition": defaultdict(lambda: defaultdict(int)),
        "performance": deque(maxlen=PERF_WINDOW),
        "total_rounds": 0,
        "total_wins": 0
    }

# --- START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text("Bot aktif ✅ Tahmin algoritması agresif ve ilk kod mantığında çalışıyor. İki admin kullanabilir.")

# --- ANA MOTOR ---
async def evrimsel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(update):
        return

    admin = admins_data[user_id]
    user_text = update.message.text

    if not user_text.isdigit() or not 0 <= int(user_text) <= 36:
        await update.message.reply_text("Lütfen 0 ile 36 arasında geçerli bir sayı giriniz.")
        return

    user_input = int(user_text)
    prev_input = admin["prev_input"]

    # --- Skor hesaplama ---
    global_counts = Counter([x[1] for x in admin["history"]])
    recent_counts = Counter([x[1] for x in list(admin["history"])[-RECENT_WINDOW:]])
    short_counts = Counter([x[1] for x in list(admin["history"])[-SHORT_WINDOW:]])
    perf_win_rate = sum(admin["performance"])/len(admin["performance"]) if admin["performance"] else 0

    if perf_win_rate < 0.35:
        t_weight, g_weight, r_weight, n_weight, m_weight = 5,3,8,4,6
    elif perf_win_rate < 0.5:
        t_weight, g_weight, r_weight, n_weight, m_weight = 4,3,6,3,4
    else:
        t_weight, g_weight, r_weight, n_weight, m_weight = 3,3,4,2,2

    scores = {}
    for num in range(NUM_RANGE):
        transition_count = admin["transition"][prev_input][num]
        global_count = global_counts[num]
        recent_count = recent_counts[num]
        momentum = short_counts[num] ** 2

        sol1, sag1 = hidden_map[num]
        sol2, sag2 = hidden_map[sol1][0], hidden_map[sag1][1]
        neighbor_trend = recent_counts[sol1] + recent_counts[sag1] + recent_counts[sol2] + recent_counts[sag2]

        scores[num] = (transition_count*t_weight + global_count*g_weight +
                       recent_count*r_weight + neighbor_trend*n_weight + momentum*m_weight)

    sorted_nums = sorted(scores.items(), key=lambda x:-x[1])
    main_guess = [num for num,_ in sorted_nums[:NUM_GUESS]]
    extra_guess = [num for num,_ in sorted_nums[NUM_GUESS:NUM_GUESS+NUM_EXTRA]]

    # Hidden bonus hesaplaması ama mesajda gösterilmiyor
    hidden_bonus = set()
    for num in main_guess + extra_guess:
        sol1, sag1 = hidden_map[num]
        sol2, sag2 = hidden_map[sol1][0], hidden_map[sag1][1]
        hidden_bonus.update([sol1,sag1,sol2,sag2])

    # --- Sonuç ---
    admin["total_rounds"] += 1
    win = user_input in main_guess or user_input in extra_guess or user_input in hidden_bonus
    if win:
        admin["total_wins"] += 1
        admin["performance"].append(1)
        await update.message.reply_text("🎯 Kazandınız!")
    else:
        admin["performance"].append(0)
        await update.message.reply_text("Kaybettik.")

    # --- Sade mesaj ---
    await update.message.reply_text(
        f"Ana: {main_guess}\nEkstra: {extra_guess}\nWin Rate: %{(admin['total_wins']/admin['total_rounds']*100):.2f}"
    )

    # --- History güncelle ---
    if len(admin["history"]) == WINDOW:
        old_prev, old_correct = admin["history"][0]
        admin["transition"][old_prev][old_correct] -= 1

    admin["history"].append((prev_input,user_input))
    admin["transition"][prev_input][user_input] += 1
    admin["prev_input"] = user_input

# --- APP ---
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, evrimsel))

print("Bot çalışıyor... İlk kod mantığı + iki admin + hidden gizli")
app.run_polling()
