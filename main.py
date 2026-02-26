import os
import random
from collections import deque
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- AYARLAR ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}

# Avrupa Ruleti Çark Dizilimi
WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 
         5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]

user_states = {}

def get_user_state(uid):
    if uid not in user_states:
        user_states[uid] = {"bakiye": 1000, "history": deque(maxlen=20), "last_bets": []}
    return user_states[uid]

def get_neighbors(n, s=3):
    idx = WHEEL.index(n)
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

def fast_learning_engine(uid):
    """Hızlı Öğrenen Adaptif Motor"""
    state = get_user_state(uid)
    hist = list(state["history"])
    
    if len(hist) < 2: return random.sample(WHEEL, 2)
    
    scores = {num: 0 for num in range(37)}
    
    # --- ÜSTEL AĞIRLIK MANTIĞI ---
    # Son gelen sayı en yüksek (örn: 100 puan), bir önceki 50, bir önceki 25...
    # Bu sayede bot çarkın 'o anki' trendine anında tepki verir.
    for i, n in enumerate(reversed(hist)):
        weight = 100 / (2**i) # Her adımda ağırlık yarıya iner
        if weight < 1: break # Çok eski sayıları artık dikkate alma
        
        # Sayının kendisi ve komşularına (s=2) puan dağıt
        impact_zone = get_neighbors(n, 2)
        for num in impact_zone:
            scores[num] += weight

    # Puanı en yüksek 4 adayı belirle
    sorted_candidates = sorted(scores.items(), key=lambda x: -x[1])[:4]
    top_picks = [x[0] for x in sorted_candidates]
    
    # En iyi adaylardan her seferinde farklı 2'li seçerek statik kalmayı önle
    return random.sample(top_picks, 2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = {"bakiye": 1000, "history": deque(maxlen=20), "last_bets": []}
    await update.message.reply_text("⚡ Hızlı Öğrenen Motor Aktif!\nTrend analizi başlıyor...")

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
                await update.message.reply_text(f"✅ BİNGO! (+360 TL)")
            else:
                await update.message.reply_text(f"❌ PAS (-{cost} TL)")
        
        # Hafıza ve Yeni Analiz
        state["history"].append(res)
        targets = fast_learning_engine(uid)
        
        # Dinamik Risk Kontrolü
        k_sayisi = 3 if state["bakiye"] > 400 else 2
        
        current_bets = set()
        for t in targets:
            current_bets.update(get_neighbors(t, k_sayisi))
        state["last_bets"] = list(current_bets)
        
        # Bilgi Çıktısı
        prob = (len(state["last_bets"]) / 37) * 100
        await update.message.reply_text(
            f"💰 Bakiye: {state['bakiye']} TL\n"
            f"🎯 Odak: {targets}\n"
            f"📈 İhtimal: %{prob:.1f}"
        )
        
    except ValueError:
        await update.message.reply_text("Lütfen 0-36 arası bir sayı girin.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
