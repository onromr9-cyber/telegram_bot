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
    hist = list(state["history"])
    
    # Eğer veri azsa rastgele başla
    if len(hist) < 3: 
        return random.sample(WHEEL, 2)
    
    # --- DEĞİŞİKLİK BURADA: Sadece son 10 sayıya bak ---
    recent_hist = hist[-10:] 
    scores = {num: 0 for num in range(37)}
    
    for i, h in enumerate(recent_hist):
        # Yeni gelen sayılara daha fazla puan ver (Zaman ağırlıklı)
        weight = i + 1 
        for delta in [-1, 0, 1]:
            # Çark üzerindeki komşuyu bul
            idx = WHEEL.index(h)
            n = WHEEL[(idx + delta) % 37]
            scores[n] += (5 * weight)

    # En yüksek puanlı ilk 5 adayı belirle
    sorted_scores = sorted(scores.items(), key=lambda x: -x[1])
    top_5 = [num for num, score in sorted_scores[:5]]
    
    # --- DEĞİŞİKLİK BURADA: En iyi 5 arasından her seferinde farklı 2'li seç ---
    return random.sample(top_5, 2)

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

