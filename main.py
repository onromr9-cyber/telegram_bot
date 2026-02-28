import os
from collections import deque
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}

# Avrupa Ruleti Çark Dizilimi
WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 
         5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
WHEEL_MAP = {num: i for i, num in enumerate(WHEEL)}

# --- SENİN ÖZEL STRATEJİK REFERANS LİSTEN ---
USER_STRATEGY_MAP = {
    0: [6,4,16], 1: [27,23,21], 2: [14,17,8], 3: [5,6,18], 4: [26,7,11], 5: [25,15,35], 
    6: [22,24,12], 7: [21,14,28], 8: [12,32,20], 9: [4,36,22], 10: [26,19,31], 
    11: [29,4,33], 12: [23,32,36], 13: [31,28,16], 14: [25,13,26], 15: [35,6,30], 
    16: [17,20,11], 17: [3,2,1], 18: [19,35,10], 19: [33,29,8], 20: [21,30,10], 
    21: [23,27,28], 22: [27,32,5], 23: [14,15,3], 24: [6,29,30], 25: [28,36,24], 
    26: [10,31,13], 27: [18,20,32], 28: [2,13,16], 29: [4,11,31], 30: [16,3,29], 
    31: [18,13,1], 32: [23,35,9], 33: [19,22,11], 34: [7,31,6], 35: [17,36,5], 36: [12,14,4]
}

user_states = {}

def get_user_state(uid):
    if uid not in user_states:
        user_states[uid] = {
            "bakiye": 0, "history": deque(maxlen=50), 
            "last_main_bets": [], "last_extra_bets": [],
            "loss_streak": 0, "waiting_for_balance": True,
            "predicted_history": deque(maxlen=2)
        }
    return user_states[uid]

def get_neighbors(n, s=2):
    idx = WHEEL_MAP[n]
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

def smart_engine(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    loss_streak = state.get("loss_streak", 0)
    
    if len(hist) < 5:
        return [0, 10, 20], [5, 15, 25, 35], "🌱 Analiz Hazırlanıyor..."

    last_num = hist[-1]
    scores = {num: 0 for num in range(37)}

    # 1. Gecikme ve Momentum Hesabı
    jump_avg = 0
    if len(hist) >= 3:
        dist1 = (WHEEL_MAP[hist[-1]] - WHEEL_MAP[hist[-2]] + 37) % 37
        dist2 = (WHEEL_MAP[hist[-2]] - WHEEL_MAP[hist[-3]] + 37) % 37
        jump_avg = int(((dist1 + dist2) / 2) * 1.2)

    # 2. Puanlama
    suggested_by_user = USER_STRATEGY_MAP.get(last_num, [])
    for i, n in enumerate(reversed(hist[-15:])):
        weight = 100 / (1.1**i)
        predicted_idx = (WHEEL_MAP[n] + jump_avg) % 37
        for d in [-5, -2, -1, 0, 1, 2, 5]:
            num = WHEEL[(predicted_idx + d) % 37]
            scores[num] += weight
            if num in suggested_by_user: scores[num] *= 1.6

    # 3. Ana ve Ekstra Hedef Seçimi
    sorted_sc = sorted(scores.items(), key=lambda x: -x[1])
    main_targets = []
    extra_targets = []

    # Ana 3 Tahmin (Üçgen Açı)
    for cand_num, score in sorted_sc:
        if len(main_targets) >= 3: break
        if all(abs(WHEEL_MAP[cand_num] - WHEEL_MAP[t]) >= 9 for t in main_targets):
            main_targets.append(cand_num)

    # Ekstra 4 Tahmin (1 Komşulu olacaklar)
    for cand_num, score in sorted_sc:
        if len(extra_targets) >= 4: break
        if cand_num not in main_targets and all(abs(WHEEL_MAP[cand_num] - WHEEL_MAP[t]) >= 5 for t in (main_targets + extra_targets)):
            extra_targets.append(cand_num)

    state["predicted_history"].append(main_targets)
    return main_targets, extra_targets, "🚀 Çift Katmanlı Analiz Aktif!"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = get_user_state(uid)
    await update.message.reply_text("⚖️ ÇİFT KATMANLI HİBRİT SİSTEM\n1. Ana Tahminler (2 Komşu)\n2. Ekstra Tahminler (1 Komşu)\n\nBakiyenizi girin:")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    
    try:
        text = update.message.text
        if state.get("waiting_for_balance"):
            state["bakiye"] = int(text); state["waiting_for_balance"] = False
            await update.message.reply_text(f"💰 Kasa: {state['bakiye']} TL."); return

        res = int(text)
        total_bets = state["last_main_bets"] + state["last_extra_bets"]
        
        if total_bets:
            cost = len(total_bets) * 10
            state["bakiye"] -= cost
            if res in state["last_main_bets"]:
                state["bakiye"] += 360; state["loss_streak"] = 0
                await update.message.reply_text(f"✅ ANA TAHMİN KAZANDI! (+{360-cost} TL)")
            elif res in state["last_extra_bets"]:
                state["bakiye"] += 360; state["loss_streak"] = 0
                await update.message.reply_text(f"🔥 EKSTRA TAHMİN KAZANDI! (+{360-cost} TL)")
            else:
                state["loss_streak"] += 1
                await update.message.reply_text(f"❌ KAYIP ({res})")
        
        state["history"].append(res)
        main_t, extra_t, d_msg = smart_engine(uid)
        
        # Bahisleri Hazırla
        main_bets = set()
        for t in main_t: main_bets.update(get_neighbors(t, 2))
        state["last_main_bets"] = list(main_bets)

        extra_bets = set()
        for t in extra_t: extra_bets.update(get_neighbors(t, 1))
        state["last_extra_bets"] = list(extra_bets)

        await update.message.reply_text(
            f"{d_msg}\n"
            f"💰 Kasa: {state['bakiye']} TL\n\n"
            f"🎯 ANA ODAKLAR (2 Komşu): {main_t}\n"
            f"⚡ EKSTRA ODAKLAR (1 Komşu): {extra_t}\n\n"
            f"🎲 Toplam Bahis: {len(state['last_main_bets']) + len(state['last_extra_bets'])} sayı"
        )
    except ValueError: pass

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
