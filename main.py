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
        user_states[uid] = {
            "bakiye": 1000, 
            "history": deque(maxlen=40), 
            "last_bets": [], 
            "loss_streak": 0,
            "level": 2 # Hedef sayı seviyesi
        }
    return user_states[uid]

def get_neighbors(n, s=3):
    idx = WHEEL.index(n)
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

def smart_engine(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    
    # Seviyeyi belirle (Senin önerin üzerine geliştirildi)
    # Kaybettikçe seviye artar, kazandıkça kademeli düşer
    if state["loss_streak"] == 0:
        state["level"] = max(2, state["level"] - 1) # Kademeli düşüş
    else:
        # Her 3 kayıpta bir hedef sayısını artır
        state["level"] = min(5, 2 + (state["loss_streak"] // 3))

    target_count = state["level"]
    
    scores = {num: 0 for num in range(37)}
    for i, n in enumerate(reversed(hist[-12:])):
        weight = 100 / (1.15**i)
        idx = WHEEL.index(n)
        for d in [-2, -1, 0, 1, 2]:
            scores[WHEEL[(idx + d) % 37]] += weight

    sorted_candidates = sorted(scores.items(), key=lambda x: -x[1])
    
    # Son kazanan bölgeyi koruma altına al (Eğer varsa)
    targets = []
    if hist:
        targets.append(hist[-1]) # Son gelen sayıyı her zaman hedef al
        
    for cand in sorted_candidates:
        if len(targets) >= target_count: break
        if cand[0] not in targets:
            # Çark üzerinde çok yakın olanları ele (Dağılım sağla)
            if all(abs(WHEEL.index(cand[0]) - WHEEL.index(t)) > 2 for t in targets):
                targets.append(cand[0])

    # Eğer hala eksikse doldur
    for cand in sorted_candidates:
        if len(targets) >= target_count: break
        if cand[0] not in targets:
            targets.append(cand[0])
            
    return targets

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = {"bakiye": 1000, "history": deque(maxlen=40), "last_bets": [], "loss_streak": 0, "level": 2}
    await update.message.reply_text("⚖️ Denge Modu Aktif!\nKazanç sonrası kademeli geçiş ve sıcak bölge koruması devrede.")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    
    try:
        res = int(update.message.text)
        if not (0 <= res <= 36): raise ValueError
        
        # Sonuç ve Bakiye
        if state["last_bets"]:
            cost = len(state["last_bets"]) * 10
            state["bakiye"] -= cost
            if res in state["last_bets"]:
                state["bakiye"] += 360
                state["loss_streak"] = 0
                msg_res = f"✅ KAZANDIK! (+{360-cost} TL)"
            else:
                state["loss_streak"] += 1
                msg_res = f"❌ PAS ({res})"
            await update.message.reply_text(msg_res)
        
        state["history"].append(res)
        targets = smart_engine(uid)
        
        # Komşu sayısı: Seviyeye göre optimize
        # Çok sayı oynandığında komşuyu daralt (2), az sayı varken genişlet (3)
        k_sayisi = 2 if len(targets) >= 4 else 3
        
        current_bets = set()
        for t in targets:
            current_bets.update(get_neighbors(t, k_sayisi))
        state["last_bets"] = list(current_bets)
        
        prob = (len(state["last_bets"]) / 37) * 100
        await update.message.reply_text(
            f"💰 Bakiye: {state['bakiye']} TL\n"
            f"📊 Seviye: {len(targets)} Hedef\n"
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
