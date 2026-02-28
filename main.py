import os
from collections import deque
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}

WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 
         5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
WHEEL_MAP = {num: i for i, num in enumerate(WHEEL)}

SECTORS = {
    "Voisins": [22, 18, 29, 7, 28, 12, 35, 3, 26, 0, 32, 15, 19, 4, 21, 2, 25],
    "Orphelins": [1, 20, 14, 31, 9, 17, 34, 6],
    "Tiers": [27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33]
}

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
            "last_main_bets": [], "last_extra_bets": [], "last_prob_bets": [],
            "is_learning": True, "waiting_for_balance": False
        }
    return user_states[uid]

def get_neighbors(n, s=2):
    idx = WHEEL_MAP[n]
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

def smart_engine_v5(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    last_num = hist[-1]
    
    scores = {num: 0 for num in range(37)}
    jump_avg = 0
    if len(hist) >= 3:
        dist1 = (WHEEL_MAP[hist[-1]] - WHEEL_MAP[hist[-2]] + 37) % 37
        dist2 = (WHEEL_MAP[hist[-2]] - WHEEL_MAP[hist[-3]] + 37) % 37
        jump_avg = int(((dist1 + dist2) / 2) * 1.1)

    for i, n in enumerate(reversed(hist[-15:])):
        decay = 100 / (1.1**i)
        p_idx = (WHEEL_MAP[n] + jump_avg) % 37
        for d in [-2, 0, 2]:
            num = WHEEL[(p_idx + d) % 37]
            scores[num] += decay
            if num in USER_STRATEGY_MAP.get(last_num, []): scores[num] *= 2.0

    sorted_sc = sorted(scores.items(), key=lambda x: -x[1])
    
    main_targets = []
    for cand_num, _ in sorted_sc:
        if len(main_targets) >= 3: break
        if all(abs(WHEEL_MAP[cand_num] - WHEEL_MAP[t]) >= 7 for t in main_targets):
            main_targets.append(cand_num)

    extra_targets = [last_num] # Kural: İlk sayı son gelenin tekrarı
    for cand_num, _ in sorted_sc:
        if len(extra_targets) >= 3: break 
        if cand_num not in main_targets and cand_num not in extra_targets:
            extra_targets.append(cand_num)

    sector_counts = {"Voisins": 0, "Orphelins": 0, "Tiers": 0}
    for n in hist[-10:]:
        for sector, nums in SECTORS.items():
            if n in nums: sector_counts[sector] += 1
    
    hot_sector = max(sector_counts, key=sector_counts.get)
    
    prob_targets = []
    for cand_num, _ in sorted_sc:
        if len(prob_targets) >= 2: break
        if cand_num in SECTORS[hot_sector] and cand_num not in main_targets and cand_num not in extra_targets:
            prob_targets.append(cand_num)
            
    return main_targets, extra_targets, prob_targets, hot_sector

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = get_user_state(uid)
    await update.message.reply_text("⚖️ AI HYBRID V5 - KAZANÇ TAKİBİ AKTİF\nIsınma: İlk 10 sayıyı girin.", 
                                   reply_markup=ReplyKeyboardMarkup([['/reset']], resize_keyboard=True))

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in user_states: del user_states[uid]
    await start(update, context)

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    text = update.message.text.strip()
    if not text.isdigit(): return
    val = int(text)

    if state["waiting_for_balance"]:
        state["bakiye"] = val
        state["waiting_for_balance"] = False
        await update.message.reply_text(f"💰 Başlangıç Kasası: {val} TL. Bol şans!"); return

    if state["is_learning"]:
        state["history"].append(val)
        if len(state["history"]) < 10:
            await update.message.reply_text(f"📥 Veri: {len(state['history'])}/10"); return
        else:
            state["is_learning"] = False; state["waiting_for_balance"] = True
            await update.message.reply_text("✅ Isınma Bitti. Bakiyenizi girin:"); return

    # Bahis Sonuçlandırma ve Kazanç Ekranı
    all_bets = list(set(state["last_main_bets"] + state["last_extra_bets"] + state["last_prob_bets"]))
    if all_bets:
        bet_cost = len(all_bets) * 10
        state["bakiye"] -= bet_cost
        
        if val in all_bets:
            win_amount = 360
            net_profit = win_amount - bet_cost
            state["bakiye"] += win_amount
            result_msg = f"✅ KAZANDI!\n💵 Bahis: {bet_cost} TL\n💰 Net Kazanç: +{net_profit} TL"
        else:
            result_msg = f"❌ KAYIP ({val})\n💵 Bahis: {bet_cost} TL"
        
        await update.message.reply_text(result_msg)

    state["history"].append(val)
    main_t, extra_t, prob_t, hot_zone = smart_engine_v5(uid)

    m_b = set(); [m_b.update(get_neighbors(t, 2)) for t in main_t]
    e_b = set(); [e_b.update(get_neighbors(t, 2)) for t in extra_t]
    p_b = set(); [p_b.update(get_neighbors(t, 2)) for t in prob_t]

    state["last_main_bets"], state["last_extra_bets"], state["last_prob_bets"] = list(m_b), list(e_b), list(p_b)
    total_nums = len(set(state["last_main_bets"] + state["last_extra_bets"] + state["last_prob_bets"]))

    await update.message.reply_text(
        f"💰 GÜNCEL KASA: {state['bakiye']} TL\n"
        f"📝 Bir sonraki el maliyeti: {total_nums * 10} TL\n\n"
        f"🎯 MAIN: {main_t}\n"
        f"⚡ EXTRA: {extra_t}\n"
        f"🔥 OLASILIK ({hot_zone}): {prob_t}\n\n"
        f"🎲 Toplam: {total_nums} sayı"
    )

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
