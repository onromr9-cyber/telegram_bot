import os
import random
from collections import Counter, deque
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- AYARLAR ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}

# Gerçek Avrupa Ruleti Çark Dizilimi
WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 
         5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]

user_states = {}

def get_user_state(uid):
    if uid not in user_states:
        user_states[uid] = {"bakiye": 1000, "history": deque(maxlen=30), "last_bets": []}
    return user_states[uid]

def get_neighbors(n, s=3):
    idx = WHEEL.index(n)
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

def smart_engine(uid):
    """Hibrit Analiz Motoru: Trend + Yoğunluk"""
    state = get_user_state(uid)
    hist = list(state["history"])
    
    if len(hist) < 3: return random.sample(WHEEL, 2)
    
    # 1. BÖLGE ANALİZİ: Çarkı 4 ana bölgeye ayırıp hangisi 'sıcak' bakıyoruz
    # (Voisins, Orphelins, Tiers, Zero)
    scores = {num: 0 for num in range(37)}
    
    # Son 15 sayıya puan ver (Yeni sayılar daha kıymetli)
    for i, n in enumerate(hist[-15:]):
        weight = i + 1
        neighbors = get_neighbors(n, 2) # Sayının etrafındaki etki alanı
        for nb in neighbors:
            scores[nb] += weight

    # 2. EN SICAK NOKTALARI SEÇ
    # Puanı en yüksek olan ilk 5 sayıyı al
    hot_ones = sorted(scores.items(), key=lambda x: -x[1])[:5]
    candidates = [x[0] for x in hot_ones]
    
    # 3. ÇEŞİTLİLİK: Takılı kalmamak için en iyi 5 adaydan 2'sini seç
    return random.sample(candidates, 2)

# --- BOT İŞLEMLERİ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = {"bakiye": 1000, "history": deque(maxlen=30), "last_bets": []}
    await update.message.reply_text("🎲 Yeni Nesil Analiz Motoru Aktif!\nBakiye: 1000 TL")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    
    try:
        res = int(update.message.text)
        if not (0 <= res <= 36): raise ValueError
        
        # Kazanç Kontrol
        if state["last_bets"]:
            cost = len(state["last_bets"]) * 10
            state["bakiye"] -= cost
            if res in state["last_bets"]:
                state["bakiye"] += 360
                await update.message.reply_text(f"✅ KAZANDIN! (+360 TL)")
            else:
                await update.message.reply_text(f"❌ KAYIP! (-{cost} TL)")
        
        # Yeni Analiz
        state["history"].append(res)
        targets = smart_engine(uid)
        
        # Dinamik Komşu Belirleme (Bakiye koruma)
        k_sayisi = 3 if state["bakiye"] > 300 else 2
        bets = set()
        for t in targets:
            bets.update(get_neighbors(t, k_sayisi))
        state["last_bets"] = list(bets)
        
        # İhtimal Göstergesi
        prob = (len(state["last_bets"]) / 37) * 100
        await update.message.reply_text(
            f"💰 Bakiye: {state['bakiye']} TL\n"
            f"🎯 Tahmin: {targets}\n"
            f"🎲 İhtimal: %{prob:.1f}"
        )
        
    except ValueError:
        await update.message.reply_text("0-36 arası bir sayı gir.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
