import os
import random
from collections import deque
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- AYARLAR ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}

WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 
         5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]

user_states = {}

def get_user_state(uid):
    if uid not in user_states:
        user_states[uid] = {
            "bakiye": 1000, 
            "history": deque(maxlen=25), 
            "last_bets": [],
            "loss_streak": 0  # Kaybetme serisini takip eder
        }
    return user_states[uid]

def get_neighbors(n, s=3):
    idx = WHEEL.index(n)
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

def smart_engine(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    
    if len(hist) < 2: return random.sample(WHEEL, 2)
    
    scores = {num: 0 for num in range(37)}
    
    # Trendi ve yoğunluğu analiz et
    for i, n in enumerate(reversed(hist)):
        weight = 100 / (1.5**i) # Daha dengeli bir sönümlenme
        if weight < 5: break
        
        # Kaybetme serisi arttıkça etki alanını genişlet (Dinamik Etki)
        impact_range = 2 if state["loss_streak"] < 3 else 3
        
        impact_zone = get_neighbors(n, impact_range)
        for num in impact_zone:
            scores[num] += weight

    sorted_candidates = sorted(scores.items(), key=lambda x: -x[1])[:5]
    top_picks = [x[0] for x in sorted_candidates]
    
    # Kaybetme serisi varsa daha güvenli (3 hedef), yoksa odaklı (2 hedef)
    target_count = 3 if state["loss_streak"] >= 4 else 2
    return random.sample(top_picks, target_count)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = {"bakiye": 1000, "history": deque(maxlen=25), "last_bets": [], "loss_streak": 0}
    await update.message.reply_text("🛡️ Savunma Destekli Motor Aktif!\nKaybetme serilerinde alan otomatik genişler.")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    
    try:
        res = int(update.message.text)
        if not (0 <= res <= 36): raise ValueError
        
        # --- KAZANÇ / KAYIP VE SERİ TAKİBİ ---
        if state["last_bets"]:
            cost = len(state["last_bets"]) * 10
            state["bakiye"] -= cost
            if res in state["last_bets"]:
                state["bakiye"] += 360
                state["loss_streak"] = 0 # Seri sıfırlandı
                await update.message.reply_text(f"✅ TEBRİKLER! (+360 TL)")
            else:
                state["loss_streak"] += 1 # Seri arttı
                await update.message.reply_text(f"❌ PAS ({res}) - Seri: {state['loss_streak']}")
        
        state["history"].append(res)
        targets = smart_engine(uid)
        
        # --- DİNAMİK KOMŞU SAYISI ---
        # Kaybettikçe alanı genişleten mekanizma
        k_sayisi = 3
        if state["loss_streak"] >= 5: k_sayisi = 4 # Çok kayıpta alanı devasa yap
        if state["bakiye"] < 200: k_sayisi = 2    # Bakiye biterken hayatta kalma modu
        
        current_bets = set()
        for t in targets:
            current_bets.update(get_neighbors(t, k_sayisi))
        state["last_bets"] = list(current_bets)
        
        prob = (len(state["last_bets"]) / 37) * 100
        await update.message.reply_text(
            f"💰 Bakiye: {state['bakiye']} TL\n"
            f"🎯 Hedefler: {targets}\n"
            f"🎲 Kapsama: %{prob:.1f}"
        )
        
    except ValueError:
        await update.message.reply_text("0-36 arası sayı girin.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
