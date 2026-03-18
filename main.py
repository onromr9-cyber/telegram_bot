import os, math, collections
import numpy as np
from collections import deque
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- AYARLAR ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}

WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
WHEEL_MAP = {num: i for i, num in enumerate(WHEEL)}
KEYBOARD = [['↩️ GERİ AL', '🗑️ SIFIRLA']]

user_states = {}

def get_user_state(uid):
    if uid not in user_states:
        user_states[uid] = {
            "bakiye": 0, "ana_kasa": 0, "history": deque(maxlen=100),
            "hit_history": deque(maxlen=10), "last_all_bets": [],
            "fail_count": 0, "win_streak": 0, "is_warmup_done": False,
            "waiting_for_balance": False, "last_unit": 0, "snapshot": []
        }
    return user_states[uid]

def get_neighbors(n, s=1):
    idx = WHEEL_MAP[n]
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

def guardian_engine_v7(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    if len(hist) < 3: return [hist[-1]] if hist else [0], 0

    indices = [WHEEL_MAP[x] for x in hist[-6:]]
    jumps = np.diff(indices) % 37
    last_j = jumps[-1]
    prev_j = jumps[-2]
    chaos = float(np.abs(last_j - prev_j))

    # Tahmin Kanalları
    p1 = WHEEL[(WHEEL_MAP[hist[-1]] + last_j) % 37] # Momentum
    p2 = WHEEL[(WHEEL_MAP[hist[-1]] + (37 - last_j)) % 37] # Counter
    p3 = WHEEL[(WHEEL_MAP[hist[-1]] + 18) % 37] # Mirror

    pivots = [p1]
    for cand in [p2, p3]:
        if cand in pivots:
            cand = WHEEL[(WHEEL_MAP[cand] + 1) % 37]
        pivots.append(cand)

    return pivots, chaos

async def generate_analysis_msg(uid):
    state = get_user_state(uid)
    pivots, chaos = guardian_engine_v7(uid)
    last_5 = list(state["hit_history"])[-5:]
    hit_rate = sum(last_5) / 5 if len(last_5) >= 5 else 1.0

    # Kaos durumuna göre komşu sayısı (S2 veya S3)
    main_s = 3 if chaos > 15 else 2
    
    all_bets_set = set()
    all_bets_set.update(get_neighbors(pivots[0], main_s))
    all_bets_set.update(get_neighbors(pivots[1], 1))
    all_bets_set.update(get_neighbors(pivots[2], 1))
    all_bets_set.update(get_neighbors(state["history"][-1], 1))

    all_bets = list(all_bets_set)

    if chaos > 28 or hit_rate < 0.2:
        state["last_unit"] = 0
        state["last_all_bets"] = []
        return (f"🛑 **LÜTFEN KALK!**\n"
                f"───────────────────\n"
                f"📍 SON SAYI: {state['history'][-1]}\n"
                f"⚠️ KAOS: {chaos:.1f} | VERİM: {hit_rate:.2f}\n"
                f"📢 ANALİZ RİSKLİ. İZLE.")

    risk_rate = 0.08 if state["win_streak"] < 2 else 0.12
    risk_amount = state["bakiye"] * risk_rate
    state["last_unit"] = max(math.floor(risk_amount / len(all_bets)), 1)
    state["last_all_bets"] = all_bets

    return (
        f"🛡️ **𝐆 𝐔 𝐀 Ｒ 𝐃 𝐈 Ａ Ｎ v7.1** 🛡️\n"
        f"💰 **KASA:** {state['bakiye']} | 🪙 **UNIT:** {state['last_unit']}\n"
        f"───────────────────\n"
        f"📍 **SON SAYI:** {state['history'][-1]}\n\n"
        f"🔥 **ANA (S{main_s}):** {pivots[0]}\n"
        f"⚡ **EK-1 (S1):** {pivots[1]}\n"
        f"🌀 **EK-2 (S1):** {pivots[2]}\n"
        f"🛡️ **SİGORTA (S1):** {state['history'][-1]}\n"
        f"───────────────────\n"
        f"🧩 **KAOS:** {chaos:.1f} | 🚀 **HİT:** {hit_rate:.2f}"
    )

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    raw_text = update.message.text.strip().upper()

    if raw_text == '🗑️ SIFIRLA':
        if uid in user_states: del user_states[uid]
        await update.message.reply_text("🛡️ SIFIRLANDI. 10 sayı girin."); return
    
    if raw_text == '↩️ GERİ AL' and state["snapshot"]:
        state.update(state["snapshot"].pop())
        await update.message.reply_text("↩️ Geri alındı."); return

    if not raw_text.isdigit():
        await update.message.reply_text("⚠️ Sadece rakam!"); return

    val = int(raw_text)

    if state["waiting_for_balance"]:
        state["bakiye"] = val; state["ana_kasa"] = val; state["waiting_for_balance"] = False; state["is_warmup_done"] = True
        msg = await generate_analysis_msg(uid); await update.message.reply_text(msg, parse_mode='Markdown'); return

    if not state["waiting_for_balance"] and (val < 0 or val > 36):
        await update.message.reply_text("❌ 0-36 gir!"); return

    snap = {k: (list(v) if isinstance(v, deque) else v) for k, v in state.items() if k != "snapshot"}
    state["snapshot"].append(snap)

    if state["is_warmup_done"]:
        cost = len(state["last_all_bets"]) * state["last_unit"]
        if val in (state["last_all_bets"] or []) and state["last_unit"] > 0:
            gain = (state["last_unit"] * 36) - cost
            state["bakiye"] += gain
            state["hit_history"].append(1); state["fail_count"] = 0; state["win_streak"] += 1
            await update.message.reply_text(f"✅ HİT! (+{gain})")
        elif state["last_unit"] > 0:
            state["bakiye"] -= cost
            state["hit_history"].append(0); state["fail_count"] += 1; state["win_streak"] = 0
            await update.message.reply_text(f"❌ PAS (-{cost})")
        else:
            state["hit_history"].append(1 if val in (state["last_all_bets"] or []) else 0)

    state["history"].append(val)
    
    if not state["is_warmup_done"]:
        if len(state["history"]) == 10:
            state["waiting_for_balance"] = True
            await update.message.reply_text("🎯 10 Sayı Tamam!\n💰 Kasa girin:")
    else:
        msg = await generate_analysis_msg(uid)
        await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = get_user_state(uid)
    await update.message.reply_text("🛡️ **GUARDIAN v7.1**\nIsınma için 10 sayı girin...", reply_markup=ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True))

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
