import os, math, collections
from collections import deque
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- AYARLAR ---
TOKEN = os.getenv("BOT_TOKEN") 
ADMIN_IDS = {5813833511, 1278793650} 

WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
WHEEL_MAP = {num: i for i, num in enumerate(WHEEL)}
KEYBOARD = [['↩️ GERİ AL', '🗑️ SIFIRLA']]

VOISINS = {22, 18, 29, 7, 28, 12, 35, 3, 26, 0, 32, 15, 19, 4, 21, 2, 25}
TIER = {27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33}
ORPHELINS = {1, 20, 14, 31, 9, 17, 34, 6}

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
            "bakiye": 0, "ana_kasa": 0, "history": deque(maxlen=100), 
            "hit_history": deque(maxlen=15), "last_all_bets": [], 
            "fail_count": 0, "win_streak": 0, "spectator_timer": 0, "is_warmup_done": False, 
            "waiting_for_balance": False, "last_unit": 0, "current_sector": "N/A",
            "snapshot": []
        }
    return user_states[uid]

def get_sector(n):
    if n in VOISINS: return "VOISINS"
    if n in TIER: return "TIER"
    if n in ORPHELINS: return "ORPHELINS"
    return "N/A"

def get_neighbors(n, s=1):
    idx = WHEEL_MAP[n]
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

def smart_engine_v3_core(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    last_5 = hist[-5:]
    sector_counts = collections.Counter([get_sector(n) for n in last_5])
    dominant_sector = sector_counts.most_common(1)[0][0]
    state["current_sector"] = dominant_sector

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
            if get_sector(num) == dominant_sector: scores[num] *= 1.5
            if num in USER_STRATEGY_MAP.get(hist[-1], []): scores[num] *= 2.0

    sorted_sc = sorted(scores.items(), key=lambda x: -x[1])
    main_t = []
    for cand_num, _ in sorted_sc:
        if len(main_t) >= 3: break
        if all(abs(WHEEL_MAP[cand_num] - WHEEL_MAP[t]) >= 7 for t in main_t): main_t.append(cand_num)
    
    extra_t = [hist[-1]] 
    for cand_num, _ in sorted_sc:
        if len(extra_t) >= 3: break 
        if cand_num not in main_t and cand_num not in extra_t: extra_t.append(cand_num)

    mirror_idx = (WHEEL_MAP[hist[-1]] + 18) % 37
    escape_t = [WHEEL[mirror_idx]]
    return main_t, extra_t, escape_t

async def generate_analysis_msg(uid):
    state = get_user_state(uid)
    m_t, e_t, esc_t = smart_engine_v3_core(uid)
    m_b, e_b, esc_b = set(), set(), set()
    
    m_s = 2
    e_s = 2 if state["fail_count"] >= 1 else 1
    esc_s = 2 if state["fail_count"] >= 1 else 1

    [m_b.update(get_neighbors(t, m_s)) for t in m_t]
    [e_b.update(get_neighbors(t, e_s)) for t in e_t]
    [esc_b.update(get_neighbors(t, esc_s)) for t in esc_t]
    
    all_bets = list(m_b | e_b | esc_b)
    state["last_all_bets"] = all_bets
    
    kasa_erime = (state["ana_kasa"] - state["bakiye"]) / state["ana_kasa"] if state["ana_kasa"] > 0 else 0
    
    if state["spectator_timer"] > 0:
        state["last_unit"], status, extra_msg = 0, "🟡 İZLEME MODU", f"🚨 DUR VE İZLE! Kalan: {state['spectator_timer']}"
    elif state["fail_count"] >= 3 or kasa_erime > 0.40:
        state["spectator_timer"] = 5 
        state["last_unit"], status, extra_msg = 0, "🟡 İZLEME MODU", "🚨 3 PAS! Ritim koptu, DUR VE İZLE."
    else:
        base_risk = 0.14 if state["fail_count"] == 0 else 0.07
        multiplier = 1.0
        if state["win_streak"] == 2: multiplier = 1.2
        elif state["win_streak"] >= 3: multiplier = 1.5
        
        risk_rate = base_risk * multiplier
        risk_miktari = state["bakiye"] * risk_rate
        state["last_unit"] = max(math.floor(risk_miktari / len(all_bets)), 1)
        
        status = "🟢 AGRESİF" if state["win_streak"] >= 2 else ("🟢 GÜVENLİ" if state["fail_count"] == 0 else "🟠 TEMKİNLİ")
        extra_msg = f"🔥 {state['win_streak']} SERİ! Kademeli artış aktif." if state["win_streak"] >= 2 else "📢 Analiz aktif, devam."

    return (
        f"📊 DURUM: {status}\n"
        f"💰 KASA: {state['bakiye']} | 🪙 UNIT: {state['last_unit']}\n\n"
        f"🔥 MAIN (S{m_s}): {m_t}\n"
        f"⚡ EXTRA (S{e_s}): {e_t}\n"
        f"🌀 KAÇIŞ (S{esc_s}): {esc_t}\n\n"
        f"🧭 SEKTÖR: {state['current_sector']}\n"
        f"📢 {extra_msg}"
    )

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    text = update.message.text.strip().upper()

    if text == '🗑️ SIFIRLA':
        if uid in user_states: del user_states[uid]
        await update.message.reply_text("🛡️ SIFIRLANDI. 10 sayı girin.", reply_markup=ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True)); return
    
    if text == '↩️ GERİ AL':
        if state["snapshot"]:
            last_snap = state["snapshot"].pop()
            state.update({k: (deque(v, maxlen=state[k].maxlen) if isinstance(state[k], deque) else v) for k, v in last_snap.items()})
            await update.message.reply_text("↩️ Geri alındı."); return
        else:
            await update.message.reply_text("↩️ Kayıt yok."); return

    # --- AKILLI GÜVENLİK FİLTRESİ (DÜZELTİLDİ) ---
    if not text.isdigit():
        await update.message.reply_text("⚠️ UYARI: Lütfen sadece rakam girin!")
        return
    
    val = int(text)
    
    # Kasa beklemiyorsak rulet sayısı kontrolü yap (0-36)
    if not state["waiting_for_balance"]:
        if val < 0 or val > 36:
            await update.message.reply_text(f"⚠️ HATA: {val} geçersiz! (0-36 arası girin)")
            return
    # --------------------------------------------

    # Snapshot
    snap = {k: (list(v) if isinstance(v, deque) else v) for k, v in state.items() if k != "snapshot"}
    state["snapshot"].append(snap)
    if len(state["snapshot"]) > 10: state["snapshot"].pop(0)

    if state["waiting_for_balance"]:
        state["bakiye"] = val; state["ana_kasa"] = val; state["waiting_for_balance"] = False; state["is_warmup_done"] = True
        msg = await generate_analysis_msg(uid); await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True)); return

    if state["is_warmup_done"]:
        if state["spectator_timer"] > 0: state["spectator_timer"] -= 1

        cost = len(state["last_all_bets"]) * state["last_unit"]
        if val in state["last_all_bets"] and state["last_unit"] > 0:
            state["bakiye"] += (state["last_unit"] * 36) - cost
            state["hit_history"].append(1); state["fail_count"] = 0; state["win_streak"] += 1
            await update.message.reply_text(f"✅ HİT! (Seri: {state['win_streak']})")
        elif state["last_unit"] > 0:
            state["bakiye"] -= cost
            state["hit_history"].append(0); state["fail_count"] += 1; state["win_streak"] = 0
            await update.message.reply_text(f"❌ PAS ({val})")
        else:
            is_virtual_hit = val in state["last_all_bets"]
            if is_virtual_hit: state["fail_count"] = 0; state["win_streak"] += 1
            else: state["fail_count"] += 1; state["win_streak"] = 0
            await update.message.reply_text(f"👁️ İZLEMEDE: {val} ({'✅' if is_virtual_hit else '❌'})")

    state["history"].append(val)
    if len(state["history"]) == 10 and not state["is_warmup_done"]:
        state["waiting_for_balance"] = True
        await update.message.reply_text("🎯 ISINMA TAMAM.\n💰 KASA GİRİN:", reply_markup=ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True)); return
    elif len(state["history"]) < 10: return 

    msg = await generate_analysis_msg(uid)
    await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = get_user_state(uid)
    await update.message.reply_text("🛡️ SAFE GUARDIAN v5.11\nAkıllı filtre aktif (Kasa girişi düzeldi).", reply_markup=ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True))

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
