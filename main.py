import os
import math
import collections
import numpy as np
from collections import deque
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- AYARLAR ---
TOKEN = os.getenv("BOT_TOKEN") 
ADMIN_IDS = {5813833511, 1278793650} 

WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
WHEEL_MAP = {num: i for i, num in enumerate(WHEEL)}

VOISINS = {22, 18, 29, 7, 28, 12, 35, 3, 26, 0, 32, 15, 19, 4, 21, 2, 25}
TIER = {27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33}
ORPHELINS = {1, 20, 14, 31, 9, 17, 34, 6}

user_states = {}

def get_user_state(uid):
    if uid not in user_states:
        user_states[uid] = {
            "bakiye": 0, "ana_kasa": 0, "history": deque(maxlen=100), 
            "hit_history": deque(maxlen=12), "is_locked": False, "snapshot": [],
            "last_all_bets": [], "fail_count": 0, "is_warmup_done": False, 
            "waiting_for_balance": False, "last_unit": 0, "current_sector": "N/A",
            "virtual_mode": False
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

# --- CESUR ENGINE V4.2 ---
async def smart_engine_v4_2(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    
    # 1. Kaos Analizi
    jumps = [(WHEEL_MAP[hist[i]] - WHEEL_MAP[hist[i-1]] + 37) % 37 for i in range(1, len(hist))]
    chaos_factor = np.std(jumps[-6:]) if len(jumps) >= 6 else 10.0
    avg_jump = int(np.mean(jumps[-8:])) if len(jumps) >= 8 else 18

    # 🚨 CESARET AYARI: Kaos eşiği 12.5'ten 16.0'a esnetildi
    if chaos_factor > 16.0:
        state["virtual_mode"] = True
    elif chaos_factor < 13.0: 
        state["virtual_mode"] = False

    # 2. Sıcak Sayı ve Durgun Masa Analizi
    hot_counts = collections.Counter(hist[-25:])
    hot_numbers = [num for num, count in hot_counts.items() if count >= 3]
    
    # Durgun Masa Kontrolü (Son 4 atış birbirine yakın mı?)
    is_stagnant = np.std([WHEEL_MAP[x] for x in hist[-4:]]) < 6 if len(hist) >= 4 else False

    # 3. Puanlama
    last_5_sectors = [get_sector(n) for n in hist[-5:]]
    dominant_sector = collections.Counter(last_5_sectors).most_common(1)[0][0]
    
    scores = {num: 0 for num in range(37)}
    for i, n in enumerate(reversed(hist[-20:])):
        decay = 100 / (1.10**i) # Decay biraz daha yumuşatıldı
        target_idx = (WHEEL_MAP[n] + avg_jump) % 37
        for d in [-1, 0, 1]:
            num = WHEEL[(target_idx + d) % 37]
            scores[num] += decay
            if get_sector(num) == dominant_sector: scores[num] *= 1.5
            if num in hot_numbers: scores[num] *= 2.5
            if is_stagnant: scores[num] *= 1.3 # Durgun masa bonusu

    sorted_sc = sorted(scores.items(), key=lambda x: -x[1])
    
    # Bahis Grupları
    main_t = [sorted_sc[0][0], sorted_sc[1][0]]
    extra_t = [hist[-1], sorted_sc[2][0]]
    mirror_idx = (WHEEL_MAP[hist[-1]] + 18) % 37
    escape_t = [WHEEL[mirror_idx]]

    # Dinamik Alan: Cesur modda komşu sayısı daha agresif
    n_size = 2 if chaos_factor > 7 else 1
    
    m_b, e_b, esc_b = set(), set(), set()
    [m_b.update(get_neighbors(t, 2)) for t in main_t]
    [e_b.update(get_neighbors(t, n_size)) for t in extra_t]
    [esc_b.update(get_neighbors(t, 2)) for t in escape_t] # Kaçış alanı 1'den 2'ye çıkarıldı
    
    all_bets = list(m_b | e_b | esc_b)
    state["last_all_bets"] = all_bets
    
    # Kasa Yönetimi (%15 Risk - Biraz daha agresif)
    risk_cap = state["bakiye"] * 0.15
    unit = max(math.floor(risk_cap / len(all_bets)), 1) if state["bakiye"] > 0 else 0
    state["last_unit"] = unit

    status_label = "🚫 SANAL (İzle)" if state["virtual_mode"] else ("🟢 AGRESİF" if chaos_factor < 10 else "🟡 NORMAL")
    
    msg = (
        f"📊 MOD: {status_label}\n"
        f"🌀 KAOS: {chaos_factor:.1f} | 🧭 SEKTÖR: {dominant_sector}\n"
        f"💰 KASA: {state['bakiye']} | 🪙 BET: {state['last_unit']}\n\n"
        f"🎯 MAIN: {main_t}\n"
        f"⚡ EXTRA: {extra_t}\n"
        f"🔥 KAÇIŞ: {escape_t}"
    )
    return msg

# --- TELEGRAM BOT HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = get_user_state(uid)
    await update.message.reply_text("🛡️ GUARDIAN v4.2 (CESUR SNIPER)\nAnaliz için 10 sayı girin.", 
                                    reply_markup=ReplyKeyboardMarkup([['↩️ GERİ AL', '/reset']], resize_keyboard=True))

async def reset_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in user_states: del user_states[uid]
    await start(update, context)

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    
    if state["is_locked"]:
        await update.message.reply_text("🚨 LÜTFEN KALK! Masadan ayrılın."); return

    text = update.message.text.strip().upper()
    if text == '↩️ GERİ AL':
        if state["snapshot"]: state.update(state["snapshot"].pop())
        await update.message.reply_text("↩️ Geri alındı."); return
    if not text.isdigit(): return

    val = int(text)

    if state["waiting_for_balance"]:
        state["bakiye"] = val; state["ana_kasa"] = val; state["waiting_for_balance"] = False; state["is_warmup_done"] = True
        msg = await smart_engine_v4_2(uid)
        await update.message.reply_text(f"💰 KASA: {val} OK.\n\n{msg}"); return

    if state["is_warmup_done"]:
        snap = {k: (list(v) if isinstance(v, deque) else v) for k, v in state.items() if k != "snapshot"}
        state["snapshot"].append(snap)

        if not state["virtual_mode"]:
            cost = len(state["last_all_bets"]) * state["last_unit"]
            if val in state["last_all_bets"]:
                state["bakiye"] += (state["last_unit"] * 36) - cost
                state["hit_history"].append(1); state["fail_count"] = 0
                await update.message.reply_text(f"✅ HİT! ({val})")
            else:
                state["bakiye"] -= cost
                state["hit_history"].append(0); state["fail_count"] += 1
                await update.message.reply_text(f"❌ PAS ({val})")
        else:
            await update.message.reply_text(f"👁️ SANAL TAKİP: {val}")

        # Profit Lock (%30 Kar Hedefi)
        if state["bakiye"] > state["ana_kasa"] * 1.6:
             await update.message.reply_text("💎 HEDEF GÖRÜLDÜ. Kârı al ve çık!")

        hr_last_5 = sum(list(state["hit_history"])[-5:]) / 5 if len(state["hit_history"]) >= 5 else 1.0
        if state["fail_count"] >= 6 or (hr_last_5 < 0.15 and not state["virtual_mode"]):
            state["is_locked"] = True
            await update.message.reply_text("🚨 LÜTFEN KALK! Denge bozuldu."); return

    state["history"].append(val)
    if len(state["history"]) == 10 and not state["is_warmup_done"]:
        state["waiting_for_balance"] = True
        await update.message.reply_text("🎯 ISINMA TAMAM. KASA GİRİN:"); return
    elif len(state["history"]) < 10:
        await update.message.reply_text(f"📥 {len(state['history'])}/10"); return

    msg = await smart_engine_v4_2(uid)
    await update.message.reply_text(msg)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset_bot))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
