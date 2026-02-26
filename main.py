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
            "history": deque(maxlen=30), 
            "last_bets": [],
            "loss_streak": 0
        }
    return user_states[uid]

def get_neighbors(n, s=3):
    idx = WHEEL.index(n)
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

def smart_engine(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    
    if len(hist) < 3: return random.sample(WHEEL, 2)
    
    scores = {num: 0 for num in range(37)}
    
    # 1. RADİKAL TREND TAKİBİ: Son 2 sayıya devasa ağırlık ver (Yön değişimini yakalar)
    last_two = hist[-2:]
    for i, n in enumerate(last_two):
        idx = WHEEL.index(n)
        for d in [-2, -1, 0, 1, 2]: # Etki alanını geniş tut
            scores[WHEEL[(idx + d) % 37]] += (150 * (i + 1))

    # 2. BÖLGESEL HAFIZA: Son 15 sayıya orta ağırlık ver (İstikrar sağlar)
    for n in hist[-15:]:
        idx = WHEEL.index(n)
        for d in [-1, 0, 1]:
            scores[WHEEL[(idx + d) % 37]] += 20

    # Puanları sırala
    sorted_candidates = sorted(scores.items(), key=lambda x: -x[1])[:6]
    top_picks = [x[0] for x in sorted_candidates]
    
    # --- STRATEJİ DEĞİŞİMİ ---
    # Eğer bot kaybediyorsa, en yüksek puanlı 3 farklı bölgeyi seç (Dağınık oyun)
    if state["loss_streak"] >= 3:
        # Puan sıralamasında birbirine uzak olanları seçmeye çalışır
        return [top_picks[0], top_picks[2], top_picks[4]]
    
    # Kazandığında veya stabil gittiğinde en güçlü 2 bölgeye odaklan
    return [top_picks[0], top_picks[1]]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = {"bakiye": 1000, "history": deque(maxlen=30), "last_bets": [], "loss_streak": 0}
    await update.message.reply_text("🎯 Kararlı Hibrit Motor Aktif!\nTrend değişimlerini daha hızlı yakalar.")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    
    try:
        res = int(update.message.text)
        if not (0 <= res <= 36): raise ValueError
        
        # Sonuç Değerlendirme
        if state["last_bets"]:
            cost = len(state["last_bets"]) * 10
            state["bakiye"] -= cost
            if res in state["last_bets"]:
                state["bakiye"] += 360
                state["loss_streak"] = 0
                await update.message.reply_text(f"✅ BİLDİK! (+360 TL)")
            else:
                state["loss_streak"] += 1
                await update.message.reply_text(f"❌ KAÇTI ({res}) | Seri: {state['loss_streak']}")
        
        state["history"].append(res)
        targets = smart_engine(uid)
        
        # Komşu sayısını seri durumuna göre esnet
        # Çok kaybederse kapsama alanını genişletir
        k_sayisi = 3
        if state["loss_streak"] >= 5: k_sayisi = 4 
        
        current_bets = set()
        for t in targets:
            current_bets.update(get_neighbors(t, k_sayisi))
        state["last_bets"] = list(current_bets)
        
        prob = (len(state["last_bets"]) / 37) * 100
        await update.message.reply_text(
            f"💰 Bakiye: {state['bakiye']} TL\n"
            f"🎯 Tahminler: {targets}\n"
            f"🎲 Kapsama: %{prob:.1f}"
        )
        
    except ValueError:
        await update.message.reply_text("0-36 arası sayı girin.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
