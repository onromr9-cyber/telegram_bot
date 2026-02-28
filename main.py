import os
import random
from collections import deque
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}

WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 
         5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]

WHEEL_MAP = {num: i for i, num in enumerate(WHEEL)}
user_states = {}

def get_user_state(uid):
    if uid not in user_states:
        user_states[uid] = {
            "bakiye": 0, "history": deque(maxlen=40), 
            "last_bets": [], "loss_streak": 0, "waiting_for_balance": True
        }
    return user_states[uid]

def get_neighbors(n, s=2):
    idx = WHEEL_MAP[n]
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

def smart_engine(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    
    # Öğrenme modunun aktifleşmesi için en az 10 tur veri lazım
    if len(hist) < 10:
        return [hist[-1] if hist else 0, 10, 20]

    # --- ÖĞRENME ANALİZİ (SON 10 TUR) ---
    last_10 = hist[-10:]
    indices = [WHEEL_MAP[n] for n in last_10]
    
    # 1. Dağılım Kontrolü: Toplar birbirine yakın mı düşüyor? (Kümelenme Analizi)
    cluster_score = sum(1 for i in range(len(indices)-1) if abs(indices[i] - indices[i+1]) <= 5)
    
    # 2. Bölge Yoğunluğu (Voisins, Tiers, Orphelins tespiti)
    regions = {"V": [22,18,29,7,28,12,35,3,26,0,32,15,19,4,21,2,25], "T": [27,13,36,11,30,8,23,10,5,24,16,33], "O": [1,20,14,31,9,17,34,6]}
    reg_hits = {k: sum(1 for n in last_10 if n in v) for k, v in regions.items()}
    hot_region = max(reg_hits, key=reg_hits.get)
    cold_region = min(reg_hits, key=reg_hits.get)

    targets = []

    # --- KARAR MEKANİZMASI ---
    if cluster_score >= 4:
        # ÖĞRENME SONUCU: Masa "Sıcak Bölge" eğiliminde.
        # En çok puan alan sayıları ve son sayının etrafını al.
        scores = {num: 0 for num in range(37)}
        for i, n in enumerate(reversed(last_10)):
            w = 100 / (1.1**i)
            idx = WHEEL_MAP[n]
            for d in [-2, -1, 0, 1, 2]: scores[WHEEL[(idx+d)%37]] += w
        
        sorted_sc = sorted(scores.items(), key=lambda x: -x[1])
        targets = [sorted_sc[0][0], hist[-1], sorted_sc[1][0]]
        decision_msg = "🧠 ÖĞRENME: Kümelenme tespit edildi, sıcak bölge takibi aktif."
    else:
        # ÖĞRENME SONUCU: Masa dağınık. Kaçan bölgelere "Pusu" kur.
        # En az gelen bölgeden (cold_region) ve çarkın zıt uçlarından seç.
        targets.append(random.choice(regions[cold_region]))
        targets.append(WHEEL[(WHEEL_MAP[hist[-1]] + 18) % 37]) # Çarkın tam karşısı
        targets.append(random.choice(regions["O"] if hot_region != "O" else regions["T"]))
        decision_msg = "🧠 ÖĞRENME: Dağınık seyir tespit edildi, pusu stratejisi aktif."

    return targets[:3], decision_msg

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = {"bakiye": 0, "history": deque(maxlen=40), "last_bets": [], "loss_streak": 0, "waiting_for_balance": True}
    await update.message.reply_text("🎰 Bot Hazır. Öğrenme modu son 10 turu izler.\nLütfen başlangıç bakiyenizi girin:")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    
    try:
        text = update.message.text
        if state.get("waiting_for_balance"):
            state["bakiye"] = int(text); state["waiting_for_balance"] = False
            await update.message.reply_text(f"✅ Bakiye {state['bakiye']} TL. İlk sayıyı girin."); return

        res = int(text)
        if not (0 <= res <= 36): raise ValueError
        
        if state["last_bets"]:
            cost = len(state["last_bets"]) * 10
            state["bakiye"] -= cost
            if res in state["last_bets"]:
                state["bakiye"] += 360; state["loss_streak"] = 0
                msg = f"✅ KAZANDINIZ! (+{360-cost} TL)"
            else:
                state["loss_streak"] += 1
                msg = f"❌ KAYBETTİNİZ ({res})"
            await update.message.reply_text(msg)
        
        state["history"].append(res)
        targets, d_msg = smart_engine(uid)
        
        current_bets = set()
        for t in targets: current_bets.update(get_neighbors(t, 2))
        state["last_bets"] = list(current_bets)
        
        await update.message.reply_text(
            f"{d_msg}\n"
            f"💰 Bakiye: {state['bakiye']} TL\n"
            f"🎯 Odaklar: {targets}\n"
            f"🎲 Bahis: {len(state['last_bets'])} sayı"
        )
    except ValueError:
        await update.message.reply_text("0-36 arası sayı girin.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
