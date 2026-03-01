import os
import math
import collections
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
            "bakiye": 0, "ath_bakiye": 0, "history": deque(maxlen=60), 
            "hit_history": deque(maxlen=5), "is_locked": False, "snapshot": [],
            "last_main_bets": [], "last_extra_bets": [], "last_prob_bets": [],
            "last_unit": 0, "waiting_for_balance": False, "balance_set": False
        }
    return user_states[uid]

def get_neighbors(n, s=1):
    idx = WHEEL_MAP[n]
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

def smart_engine_hybrid(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    if not hist: return [0], [32], [15]
    
    last_num = hist[-1]
    scores = {num: 0 for num in range(37)}
    
    jump_avg = 0
    if len(hist) >= 3:
        dists = [(WHEEL_MAP[hist[i]] - WHEEL_MAP[hist[i-1]] + 37) % 37 for i in range(-1, -3, -1)]
        jump_avg = int(sum(dists) / len(dists))

    for i, n in enumerate(reversed(hist[-15:])):
        decay = 100 / (1.15**i)
        p_idx = (WHEEL_MAP[n] + jump_avg) % 37
        for d in [-1, 0, 1]:
            num = WHEEL[(p_idx + d) % 37]
            scores[num] += decay
            if num in USER_STRATEGY_MAP.get(last_num, []):
                scores[num] *= 2.8

    sorted_sc = sorted(scores.items(), key=lambda x: -x[1])
    
    main_t = []
    for cand_num, _ in sorted_sc:
        if len(main_t) >= 3: break
        if all(abs(WHEEL_MAP[cand_num] - WHEEL_MAP[t]) >= 7 for t in main_t):
            main_t.append(cand_num)
    
    # EXTRA: Tekrar Kuralı (Son 10 sayıdaki taze tekrar)
    counts = collections.Counter(hist[-10:])
    repeats = [num for num, count in counts.items() if count > 1]
    extra_t = []
    if repeats: extra_t.append(repeats[-1])
    
    for cand_num, _ in sorted_sc:
        if len(extra_t) >= 2: break
        if cand_num not in main_t and cand_num not in extra_t:
            extra_t.append(cand_num)

    prob_t = []
    for cand_num, _ in reversed(sorted_sc):
        if len(prob_t) >= 1: break
        if cand_num not in main_t and cand_num not in extra_t:
            prob_t.append(cand_num)
            
    return main_t, extra_t, prob_t

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = get_user_state(uid)
    reply_markup = ReplyKeyboardMarkup([['↩️ GERİ AL', '/reset']], resize_keyboard=True)
    await update.message.reply_text("🛡️ GUARDIAN V7.4 AKTİF\n10 sayı girerek ısınmayı başlatın.", reply_markup=reply_markup)

async def reset_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in user_states: del user_states[uid]
    await start(update, context)

async def undo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_user_state(uid)
    if not state["snapshot"]:
        await update.message.reply_text("⚠️ Geri alınacak işlem yok."); return
    last_snap = state["snapshot"].pop()
    state.update(last_snap)
    state["history"] = deque(last_snap["history"], maxlen=60)
    state["hit_history"] = deque(last_snap["hit_history"], maxlen=5)
    await update.message.reply_text("↩️ Son hamle geri alındı. Guardian hafızası tazelendi.")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    
    if state["is_locked"]:
        await update.message.reply_text("🚨 SİSTEM KİLİTLİ: LÜTFEN KALK!\n/reset komutu ile yeni masaya geçebilirsin.")
        return

    text = update.message.text.strip().upper()
    if text == '↩️ GERİ AL':
        await undo(update, context); return
    if not text.isdigit(): return

    val = int(text)
    if state["waiting_for_balance"]:
        state["bakiye"] = val
        state["ath_bakiye"] = val
        state["waiting_for_balance"] = False
        state["balance_set"] = True
        await update.message.reply_text(f"💰 Kasa {val} TL kaydedildi. Koruma aktif!"); return

    # Geçmiş Kaydı (Undo için)
    snap = {k: (list(v) if isinstance(v, deque) else v) for k, v in state.items() if k != "snapshot"}
    state["snapshot"].append(snap)
    if len(state["snapshot"]) > 10: state["snapshot"].pop(0)

    # Kazanç & Hit Rate Kontrolü
    if state["balance_set"]:
        all_bets = list(set(state["last_main_bets"] + state["last_extra_bets"] + state["last_prob_bets"]))
        if all_bets and state["last_unit"] > 0:
            cost = len(all_bets) * state["last_unit"]
            state["bakiye"] -= cost
            if val in all_bets:
                state["bakiye"] += state["last_unit"] * 36
                state["hit_history"].append(1)
                await update.message.reply_text("✅ HİT!")
            else:
                state["hit_history"].append(0)
                await update.message.reply_text(f"❌ PAS ({val})")

    # EXIT LOGIC
    if state["balance_set"]:
        if state["bakiye"] > state["ath_bakiye"]: state["ath_bakiye"] = state["bakiye"]
        dd = (state["ath_bakiye"] - state["bakiye"]) / state["ath_bakiye"] if state["ath_bakiye"] > 0 else 0
        hr = sum(state["hit_history"]) / 5 if len(state["hit_history"]) >= 5 else 0.5
        
        if dd >= 0.25 or hr < 0.2:
            state["is_locked"] = True
            await update.message.reply_text("🚨 LÜTFEN KALK! 🚨\nAnaliz dengesi bozuldu veya kasa zirveden %25 düştü!")
            return

    state["history"].append(val)
    
    if len(state["history"]) == 10 and not state["balance_set"]:
        state["waiting_for_balance"] = True
        await update.message.reply_text("🎯 ISINMA TAMAMLANDI.\n⚠️ Lütfen kasanızı (balance) girin:")
        return

    m_t, e_t, p_t = smart_engine_hybrid(uid)
    
    m_b = set(); [m_b.update(get_neighbors(t, 2)) for t in m_t]
    e_b = set(); [e_b.update(get_neighbors(t, 1)) for t in e_t]
    p_b = set(); [p_b.update(get_neighbors(t, 1)) for t in p_t]
    
    state["last_main_bets"], state["last_extra_bets"], state["last_prob_bets"] = list(m_b), list(e_b), list(p_b)
    total_nums = len(set(state["last_main_bets"] + state["last_extra_bets"] + state["last_prob_bets"]))
    state["last_unit"] = max(math.floor((state["bakiye"] * 0.15) / total_nums), 1) if state["balance_set"] else 0

    prefix = f"💰 KASA: {state['bakiye']} TL | Birim (%15): {state['last_unit']} TL\n" if state['balance_set'] else f"📥 Isınma ({len(state['history'])}/10)\n"
    await update.message.reply_text(f"{prefix}🎯 MAIN: {m_t}\n⚡ EXTRA: {e_t}\n🔥 ŞANS: {p_t}")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset_bot))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
