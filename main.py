import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from collections import defaultdict, deque, Counter
import random

# --- BOT TEMEL ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}  # 2 adminli

def is_admin(update: Update):
    return update.effective_user.id in ADMIN_IDS

# --- EVRİMSEL MOTOR VERİLERİ ---
NUM_RANGE = 37
WINDOW = 100
PERF_WINDOW = 20
NUM_GUESS = 2  # Ana sayı sayısı

# Gizli komşular haritası
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
prev_input = None  # İlk input yok, bot kendi tahmini ile başlar

# --- HELPER: Gizli 3 soldan + 3 sağdan + ana sayı = 7 sayı ---
def get_hidden_set(main_number):
    sol1, sag1 = hidden_map[main_number]
    sol2, _ = hidden_map[sol1]
    _, sag2 = hidden_map[sag1]
    sol3, _ = hidden_map[sol2]
    _, sag3 = hidden_map[sag2]
    return {sol3, sol2, sol1, main_number, sag1, sag2, sag3}

# --- TELEGRAM HANDLER ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text("Bot aktif ✅ 2 adminli sistem hazır.")

async def evrimsel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    global prev_input, total_rounds, total_wins

    user_input_text = update.message.text
    if not user_input_text.isdigit():
        await update.message.reply_text("Sadece sayı giriniz.")
        return
    user_input = int(user_input_text)

    # --- Eğer önce tahmin yapılmamışsa ilk turu başlat ---
    if prev_input is None:
        prev_input = random.randint(0, NUM_RANGE-1)

    # --- Tahmin motoru (basit rastgele + transition geçmişi) ---
    # Toplam NUM_RANGE arasından geçici skor hesapla
    scores = {num: transition.get(prev_input, {}).get(num,0) + random.randint(0,5) for num in range(NUM_RANGE)}
    sorted_scores = sorted(scores.items(), key=lambda x:-x[1])
    main_guess = [num for num,_ in sorted_scores[:NUM_GUESS]]

    # --- Gizli setleri hazırla ---
    hidden_set = set()
    for num in main_guess:
        hidden_set.update(get_hidden_set(num))  # Ana sayı + soldan 3 + sağdan 3

    # --- Kullanıcı kontrol ---
    if user_input in hidden_set:
        result_text = "🎯 KAZANDINIZ!"
        total_wins += 1
        performance.append(1)
    else:
        result_text = "Kaybettiniz."
        performance.append(0)
    total_rounds += 1

    # --- Sonuç mesajı ---
    await update.message.reply_text(f"Ana tahminler: {main_guess}\n{result_text}\nWin Rate: %{(total_wins/total_rounds*100):.2f}")

    # --- Transition güncelle ---
    if prev_input is not None:
        transition[prev_input][user_input] += 1
        history.append((prev_input, user_input))

    prev_input = user_input  # Bir sonraki tur için baz

# --- APP ---
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, evrimsel))

print("Bot çalışıyor...")
app.run_polling()
