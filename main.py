import os
import random
from collections import deque
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}

WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 
         5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]

user_states = {}

def get_user_state(uid):
    if uid not in user_states:
        user_states[uid] = {"bakiye": 1000, "history": deque(maxlen=40), "last_bets": [], "loss_streak": 0}
    return user_states[uid]

def get_neighbors(n, s=3):
    idx = WHEEL.index(n)
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

def dynamic_engine(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    streak = state["loss_streak"]
    
    if len(hist) < 3: return random.sample(WHEEL, 2)
    
    scores = {num: 0 for num in range(37)}
    for i, n in enumerate(reversed(hist[-10:])):
        weight = 100 / (1.2**i)
        idx = WHEEL.index(n)
        for d in [-2, -1, 0, 1, 2]:
            scores[WHEEL[(idx + d) % 37]] += weight

    sorted_candidates = sorted(scores.items(), key=lambda x: -x[1])
    
    # --- SENİN ÖNERİN: KAYIP ARTTIKÇA SAYI SAYISINI ARTIR ---
    if streak < 4:
        target_count = 2
    elif streak < 7:
        target_count = 3
    elif streak < 10:
        target_count = 4
    else:
        target_count = 5
        
    # En yüksek puanlı sayıları seç ama birbirine çok yakın olmamalarına dikkat et
    targets = [sorted_candidates[0][0]]
    for cand in sorted_candidates[1:]:
        if len(targets) >= target_count: break
        # Seçilen diğer hedeflere çok yakın değilse listeye ekle (Masanın farklı yerlerine dağıt)
        if all(abs(WHEEL.index(cand[0]) - WHEEL.index(t)) > 3 for t in targets):
            targets.append(cand[0])
            
    # Eğer filtreleme yüzünden sayı eksik kalırsa en yüksek puanlıları doldur
    if len(targets) < target_count:
        for cand in sorted_candidates:
            if cand[0] not in targets:
                targets.append(cand[0])
                if len(targets) == target_count: break
                
    return targets

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = {"bakiye": 1000, "history": deque(maxlen=40), "last_bets": [], "loss_streak": 0}
    await update.message.reply_text("💡 Senin Stratejin Devrede!\nKaybettikçe hedef sayısı artar, komşular daralır.")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    
    try:
        res = int(update.message.text)
        if not (0 <= res <= 36): raise ValueError
        
        if state["last_bets"]:
            cost = len(state["last_bets"]) * 10
            state["bakiye"] -= cost
            if res in state["last_bets"]:
                state["bakiye"] += 360
                state["loss_streak"] = 0
                await update.message.reply_text(f"✅ BİLDİK! Strateji sıfırlandı.")
            else:
                state["loss_streak"] += 1
                await update.message.reply_text(f"❌ PAS ({res}) | Seri: {state['loss_streak']}")
        
        state["history"].append(res)
        targets = dynamic_engine(uid)
        
        # --- SENİN ÖNERİN: KOMŞULARI DARALT ---
        k_sayisi = 3 if state["loss_streak"] < 4 else 2
        
        current_bets = set()
        for t in targets:
            current_bets.update(get_neighbors(t, k_sayisi))
        state["last_bets"] = list(current_bets)
        
        prob = (len(state["last_bets"]) / 37) * 100
        await update.message.reply_text(
            f"💰 Bakiye: {state['bakiye']} TL\n"
            f"🎯 Hedef Sayı Sayısı: {len(targets)}\n"
            f"📍 Odaklar: {targets}\n"
            f"🎲 Kapsama: %{prob:.1f}"
        )
        
    except ValueError:
        await update.message.reply_text("0-36 arası sayı girin.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
