import os
import random
from collections import Counter, deque
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- AYARLAR VE ADMINLER ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}

# Avrupa Ruleti Çark Dizilimi (Senin hidden_map yerine dinamik index kullanıyoruz)
WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 
         5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]

# Çok kullanıcılı veri deposu
user_states = {}

def get_user_state(uid):
    if uid not in user_states:
        user_states[uid] = {
            "bakiye": 1000,
            "history": deque(maxlen=50),
            "last_bets": set(),
            "targets": []
        }
    return user_states[uid]

def is_admin(uid):
    return uid in ADMIN_IDS

def get_neighbors(n, s=3):
    """Senin hidden_map'inin dinamik ve hatasız versiyonu"""
    idx = WHEEL.index(n)
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

def generate_main_guess(uid):
    state = get_user_state(uid)
    if not state["history"]: return random.sample(WHEEL, 2)
    
    # Senin puanlama (scoring) mantığını daha agresif hale getirdik
    scores = {num: 1 for num in range(37)}
    for h in state["history"]:
        for delta in [-1, 0, 1]: # Sayının kendisi ve yanındakilere odaklan
            n = (WHEEL[(WHEEL.index(h) + delta) % 37])
            scores[n] += 5 # Ağırlığı artırdık
            
    sorted_scores = sorted(scores.items(), key=lambda x: -x[1])
    return [num for num, _ in sorted_scores[:2]]

# --- TELEGRAM HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid): return
    
    user_states[uid] = {"bakiye": 1000, "history": deque(maxlen=50), "last_bets": set(), "targets": []}
    await update.message.reply_text("✅ Sistem Hazır.\nBakiyen: 1000 TL\nSayı girerek başla.")

async def handle_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid): return
    
    state = get_user_state(uid)
    text = update.message.text

    if not text.isdigit():
        await update.message.reply_text("Sadece sayı gir!")
        return

    res = int(text)
    if not (0 <= res <= 36): return

    # 1. Önceki Tahmin Sonucu (Senin 'Kazandım/Kaybettim' mantığın)
    if state["last_bets"]:
        cost = len(state["last_bets"]) * 10
        state["bakiye"] -= cost
        if res in state["last_bets"]:
            state["bakiye"] += 360
            await update.message.reply_text(f"✅ KAZANDIM! (+360 TL)")
        else:
            await update.message.reply_text(f"❌ KAYBETTİM! (-{cost} TL)")

    # 2. Yeni Tahmin Üret
    state["history"].append(res)
    state["targets"] = generate_main_guess(uid)
    
    # Kapsama Alanı (Senin 3 komşu mantığın)
    k_sayisi = 3 if state["bakiye"] > 300 else 2 # Risk adaptif mod
    state["last_bets"] = set()
    for t in state["targets"]:
        state["last_bets"].update(get_neighbors(t, k_sayisi))

    # 3. Bilgilendirme
    oran = (len(state["last_bets"]) / 37) * 100
    msg = (f"💰 Bakiye: {state['bakiye']}\n"
           f"🎯 Hedefler: {state['targets']}\n"
           f"🎲 Olasılık: %{oran:.1f}")
    await update.message.reply_text(msg)

# --- APP ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_game))
    print("Bot Railway üzerinde aktif!")
    app.run_polling()
