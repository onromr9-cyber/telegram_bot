import os
import math
from collections import deque
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- AYARLAR ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}

WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
WHEEL_MAP = {num: i for i, num in enumerate(WHEEL)}

USER_STRATEGY_MAP = {
    0: [6,4,16], 1: [27,23,21], 2: [14,17,8], 3: [5,6,18], 4: [26,7,11], 5: [25,15,35], 
    6: [18,24,15], 7: [21,14,28], 8: [12,32,20], 9: [4,36,22], 10: [26,19,31], 
    11: [29,4,33], 12: [23,32,36], 13: [31,28,16], 14: [25,13,26], 15: [35,6,30], 
    16: [17,20,11], 17: [3,2,11], 18: [19,35,10], 19: [33,29,8], 20: [21,30,10], 
    21: [23,27,28], 22: [27,32,5], 23: [14,15,11], 24: [6,29,30], 25: [28,36,24], 
    26: [10,31,13], 27: [22,20,32], 28: [2,13,16], 29: [4,11,31], 30: [16,3,29], 
    31: [18,13,0], 32: [23,35,27], 33: [19,22,11], 34: [7,31,6], 35: [17,36,5], 36: [12,14,0]
}

user_states = {}

def get_user_state(uid):
    if uid not in user_states:
        user_states[uid] = {
            "bakiye": 0, "history": deque(maxlen=50), "snapshot": [],
            "last_main_bets": [], "last_extra_bets": [], "last_prob_bets": [],
            "last_unit": 0, "is_learning": True, "waiting_for_balance": False
        }
    return user_states[uid]

def get_neighbors(n, s=1):
    idx = WHEEL_MAP[n]
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

def smart_engine_sniper(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    if not hist: return [0, 32, 15], [19, 4], [21]
    
    last_num = hist[-1]
    scores = {num: 0 for num in range(37)}
    jump_avg = 0
    
    if len(hist) >= 3:
        dist1 = (WHEEL_MAP[hist[-1]] - WHEEL_MAP[hist[-2]] + 37) % 37
        dist2 = (WHEEL_MAP[hist[-2]] - WHEEL_MAP[hist[-3]] + 37) % 37
        jump_avg = int(((dist1 + dist2) / 2) * 1.05)

    for i, n in enumerate(reversed(hist[-15:])):
        decay = 100 / (1.15**i)
        p_idx = (WHEEL_MAP[n] + jump_avg) % 37
        for d in [-1, 0, 1]:
            num = WHEEL[(p_idx + d) % 37]
            scores[num] += decay
            
            # --- ESKİ STABİL ÇARPAN (2.2) ---
            if num in USER_STRATEGY_MAP.get(last_num, []): 
                scores[num] *= 2.2  

    sorted_sc = sorted(scores.items(), key=lambda x: -x[1])
    
    main_targets = []
    for cand_num, _ in sorted_sc:
        if len(main_targets) >= 3: break
        if all(abs(WHEEL_MAP[cand_num] - WHEEL_MAP[t]) >= 9 for t in main_targets):
            main_targets.append(cand_num)

    extra_targets = [last_num] 
    for cand_num, _ in sorted_sc:
        if len(extra_targets) >= 2: break
        if cand_num not in main_targets and cand_num != last_num:
            extra_targets.append(cand_num)

    prob_targets = []
    for cand_num, _ in sorted_sc:
        if len(prob_targets) >= 1: break
        if cand_num not in main_targets and cand_num not in extra_targets:
            prob_targets.append(cand_num)
            
    return main_targets, extra_targets, prob_targets

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = get_user_state(uid)
    reply_markup = ReplyKeyboardMarkup([['↩️ GERİ AL', '/reset']], resize_keyboard=True)
    await update.message.reply_text("🎯 SNIPER V7.0 (ESKİ STABİL DÜZEN)\nIsınma: İlk 10 sayıyı girin.", reply_markup=reply_markup)

async def reset_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in user_states: del user_states[uid]
    await start(update, context)

async def undo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_user_state(uid)
    if not state["snapshot"]:
        await update.message.reply_text("⚠️ Geri alınacak hamle yok.")
        return
    last_snap = state["snapshot"].pop()
    state.update(last_snap)
    state["history"] = deque(last_snap["history"], maxlen=50)
    await update.message.reply_text("↩️ Son hamle geri alındı.")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    text = update.message.text.strip().upper()

    if text == '↩️ GERİ AL':
        await undo(update, context)
        return

    if not text.isdigit():
        await update.message.reply_text("⚠️ Lütfen sayı girin!")
        return
    
    val = int(text)

    if state["waiting_for_balance"]:
        state["bakiye"] = val
        state["waiting_for_balance"] = False
        state["is_learning"] = False
        await update.message.reply_text(f"💰 Kasa {val} TL olarak ayarlandı!"); return

    if state["is_learning"]:
        state["history"].append(val)
        if len(state["history"]) < 10:
            await update.message.reply_text(f"📥 Isınma: {len(state['history'])}/10"); return
        else:
            state["waiting_for_balance"] = True
            await update.message.reply_text("✅ Isınma bitti. Kasanızı girin:"); return

    if val < 0 or val > 36:
        await update.message.reply_text("⚠️ 0-36 arası girin!"); return

    snap = {k: (list(v) if isinstance(v, deque) else v) for k, v in state.items() if k != "snapshot"}
    state["snapshot"].append(snap)
    if len(state["snapshot"]) > 10: state["snapshot"].pop(0)

    all_bets = list(set(state["last_main_bets"] + state["last_extra_bets"] + state["last_prob_bets"]))
    if all_bets and state["last_unit"] > 0:
        cost = len(all_bets) * state["last_unit"]
        state["bakiye"] -= cost
        if val in all_bets:
            win = state["last_unit"] * 36
            state["bakiye"] += win
            await update.message.reply_text(f"✅ HİT! (+{win - cost} TL)")
        else:
            await update.message.reply_text(f"❌ PAS ({val}) | -{cost} TL")

    state["history"].append(val)
    main_t, extra_t, prob_t = smart_engine_sniper(uid)

    m_b = set(); [m_b.update(get_neighbors(t, 2)) for t in main_t]
    e_b = set(); [e_b.update(get_neighbors(t, 1)) for t in extra_t]
    p_b = set(); [p_b.update(get_neighbors(t, 1)) for t in prob_t]

    state["last_main_bets"], state["last_extra_bets"], state["last_prob_bets"] = list(m_b), list(e_b), list(p_b)
    
    total_nums = len(set(state["last_main_bets"] + state["last_extra_bets"] + state["last_prob_bets"]))
    if total_nums > 0:
        state["last_unit"] = max(math.floor((state["bakiye"] * 0.15) / total_nums), 1)
    else:
        state["last_unit"] = 0

    await update.message.reply_text(
        f"💰 KASA: {state['bakiye']} TL | 📢 Birim: {state['last_unit']} TL\n"
        f"🎯 MAIN: {main_t}\n"
        f"⚡ EXTRA: {extra_t}\n"
        f"🎲 Toplam: {total_nums} sayı"
    )

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset_bot))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
