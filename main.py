import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from collections import defaultdict, deque, Counter

# --- BOT TEMEL ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}

def is_admin(update: Update):
    return update.effective_user.id in ADMIN_IDS

# --- EVRİMSEL MOTOR ---
NUM_RANGE = 37
WINDOW = 100
RECENT_WINDOW = 10
SHORT_WINDOW = 5
PERF_WINDOW = 20
NUM_GUESS = 2  # Ana tahmin sayısı
NUM_NEIGHBORS = 3  # Her sayının gizli komşu sayısı

hidden_map = {0:(32,26),1:(33,20),2:(25,21),3:(26,35),4:(21,19),
5:(24,10),6:(27,34),7:(28,29),8:(23,30),9:(22,31),
10:(5,23),11:(30,36),12:(35,28),13:(36,27),14:(31,20),
15:(19,32),16:(33,24),17:(34,25),18:(29,22),19:(4,15),
20:(14,1),21:(2,4),22:(18,9),23:(10,8),24:(16,5),
25:(17,2),26:(0,3),27:(13,6),28:(12,7),29:(7,18),
30:(8,11),31:(9,14),32:(15,0),33:(1,16),34:(6,17),
35:(3,12),36:(11,13)}

history = deque(maxlen=WINDOW)
transition = defaultdict(lambda: defaultdict(int))
performance = deque(maxlen=PERF_WINDOW)

total_rounds = 0
total_wins = 0
prev_input = None  # Başlangıçta yok

# --- TELEGRAM HANDLER ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text("Bot aktif ✅ Sadece adminler çalışabilir.")

async def evrimsel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global prev_input, total_rounds, total_wins

    if not is_admin(update):
        return

    user_input_text = update.message.text
    if not user_input_text.isdigit():
        await update.message.reply_text("Sadece sayı giriniz.")
        return
    user_input = int(user_input_text)
    if not 0 <= user_input < NUM_RANGE:
        await update.message.reply_text("Geçerli bir sayı giriniz (0-36).")
        return

    # --- İlk turda prev_input yoksa tahmin üretme ---
    if prev_input is None:
        prev_input = user_input  # İlk sayı başlangıç olarak alınır
        await update.message.reply_text("İlk sayı alındı, bundan sonra tahminler başlatılacak.")
        return

    # --- Skor hesaplama ---
    scores = {}
    global_counts = Counter([x[1] for x in history])
    recent_counts = Counter([x[1] for x in list(history)[-RECENT_WINDOW:]])
    short_counts = Counter([x[1] for x in list(history)[-SHORT_WINDOW:]])

    win_rate = sum(performance)/len(performance) if performance else 0

    if win_rate < 0.35:
        t_weight, g_weight, r_weight, n_weight, m_weight = 5,3,8,4,6
    elif win_rate < 0.5:
        t_weight, g_weight, r_weight, n_weight, m_weight = 4,3,6,3,4
    else:
        t_weight, g_weight, r_weight, n_weight, m_weight = 3,3,4,2,2

    for num in range(NUM_RANGE):
        transition_count = transition[prev_input][num]
        global_count = global_counts[num]
        recent_count = recent_counts[num]
        momentum = short_counts[num]**2

        # Gizli komşular sadece hesaplamada
        sol1, sag1 = hidden_map[num]
        sol2, sag2 = hidden_map[sol1][0], hidden_map[sag1][1]
        neighbor_trend = recent_counts[sol1]+recent_counts[sag1]+recent_counts[sol2]+recent_counts[sag2]

        score = (transition_count*t_weight + global_count*g_weight +
                 recent_count*r_weight + neighbor_trend*n_weight + momentum*m_weight)
        scores[num] = score

    hot_numbers = [num for num,_ in Counter(global_counts).most_common(12)]
    filtered_scores = {k:v for k,v in scores.items() if k in hot_numbers}
    if len(filtered_scores) >= NUM_GUESS:
        scores = filtered_scores

    sorted_nums = sorted(scores.items(), key=lambda x:-x[1])
    main_guess = [num for num,_ in sorted_nums[:NUM_GUESS]]

    # --- Kazanma kontrolü ---
    hidden_bonus = set()
    for num in main_guess:
        s1, s2 = hidden_map[num]
        s3, s4 = hidden_map[s1][0], hidden_map[s2][1]
        hidden_bonus.update([s1,s2,s3,s4])

    win = user_input in main_guess or user_input in hidden_bonus

    # --- Sonuç mesajı ---
    await update.message.reply_text(
        f"Ana Tahmin: {main_guess}\nWin Rate: %{(total_wins/total_rounds*100 if total_rounds else 0):.2f}"
    )
    if win:
        await update.message.reply_text(f"🎯 {user_input} - KAZANDINIZ!")
        total_wins += 1
        performance.append(1)
    else:
        await update.message.reply_text(f"❌ {user_input} - Kaybettiniz.")
        performance.append(0)

    # --- Geçmiş ve transition güncelle ---
    if len(history) == WINDOW:
        old_input, old_correct = history[0]
        transition[old_input][old_correct] -= 1

    history.append((prev_input,user_input))
    transition[prev_input][user_input] += 1
    prev_input = user_input

# --- APP ---
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, evrimsel))

print("Bot çalışıyor...")
app.run_polling()
