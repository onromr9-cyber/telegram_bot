import os
from collections import deque
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}

WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 
         5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
WHEEL_MAP = {num: i for i, num in enumerate(WHEEL)}

# Senin Özel Listen
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
        user_states[uid] = {"bakiye": 0, "history": deque(maxlen=50), "last_main": [], "last_extra": [], "waiting": True}
    return user_states[uid]

def get_neighbors(n, s=2):
    idx = WHEEL_MAP[n]
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

def smart_engine(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    last_num = hist[-1]
    scores = {num: 0 for num in range(37)}

    # Analiz puanlaması
    for i, n in enumerate(reversed(hist[-15:])):
        weight = 100 / (1.1**i)
        for d in [-5, -1, 0, 1, 5]:
            scores[WHEEL[(WHEEL_MAP[n] + d) % 37]] += weight
    
    for s_num in USER_STRATEGY_MAP.get(last_num, []): scores[s_num] *= 1.6

    sorted_sc = sorted(scores.items(), key=lambda x: -x[1])
    
    # ANA (3 Odak)
    main_t = []
    for num, _ in sorted_sc:
        if len(main_t) >= 3: break
        if all(abs(WHEEL_MAP[num] - WHEEL_MAP[t]) >= 8 for t in main_t): main_t.append(num)

    # EKSTRA (1. sayı her zaman TEKRAR, sonraki 3'ü en iyi adaylar)
    extra_t = [last_num] # İlk sayı tekrar
    for num, _ in sorted_sc:
        if len(extra_t) >= 4: break
        if num not in main_t and num not in extra_t: extra_t.append(num)

    return main_t, extra_t

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    
    try:
        text = update.message.text
        if state.get("waiting"):
            state["bakiye"] = int(text); state["waiting"] = False
            await update.message.reply_text("✅ Hazır."); return

        res = int(text)
        win_msg = ""
        if res in state["last_main"]:
            state["bakiye"] += 360; win_msg = "✅ ANA KAZANDI!"
        elif res in state["last_extra"]:
            state["bakiye"] += 360; win_msg = "🔥 EKSTRA KAZANDI!"
        
        if win_msg: await update.message.reply_text(win_msg)
        
        state["history"].append(res)
        main_t, extra_t = smart_engine(uid)
        
        # Bahis Hazırlığı
        m_bets = set(); [m_bets.update(get_neighbors(t, 2)) for t in main_t]
        e_bets = set(); [e_bets.update(get_neighbors(t, 1)) for t in extra_t]
        state["last_main"], state["last_extra"] = list(m_bets), list(e_bets)

        await update.message.reply_text(
            f"💰 {state['bakiye']} TL\n\n"
            f"🎯 ANA (2k): {', '.join(map(str, main_t))}\n"
            f"⚡ EKSTRA (1k): {', '.join(map(str, extra_t))}"
        )
    except Exception: pass

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("Bakiye?")))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
