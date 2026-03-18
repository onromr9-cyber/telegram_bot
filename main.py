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

def sniper_v6_3_engine(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    if len(hist) < 3: return [hist[-1]] if hist else [0], 0

    indices = [WHEEL_MAP[x] for x in hist[-6:]]
    jumps = np.diff(indices) % 37
    last_j = jumps[-1]
    prev_j = jumps[-2]
    chaos = float(np.abs(last_j - prev_j))

    p1 = (WHEEL_MAP[hist[-1]] + last_j) % 37
    p2 = (WHEEL_MAP[hist[-1]] + (37 - last_j)) % 37
    mirror_idx = (WHEEL_MAP[hist[-1]] + 18) % 37
    return [WHEEL[int(p1)], WHEEL[int(p2)], WHEEL[int(mirror_idx)]], chaos

async def generate_analysis_msg(uid):
    state = get_user_state(uid)
    pivots, chaos = sniper_v6_3_engine(uid)
    last_5 = list(state["hit_history"])[-5:]
    hit_rate = sum(last_5) / 5 if len(last_5) >= 5 else 1.0

    all_bets_set = set()
    all_bets_set.update(get_neighbors(pivots[0], 2)) # Momentum S2
    all_bets_set.update(get_neighbors(pivots[1], 1)) # Counter S1
    all_bets_set.update(get_neighbors(pivots[2], 1)) # Mirror S1
    all_bets_set.update(get_neighbors(state["history"][-1], 1)) # Sigorta

    all_bets = list(all_bets_set)

    if chaos > 25 or hit_rate < 0.2:
        state["last_unit"] = 0
        state["last_all_bets"] = []
        return (f"🛑 **LÜTFEN KALK!**\n"
                f"───────────────────\n"
                f"⚠️ Kaos: {chaos:.1f} | Verim: {hit_rate:.2f}\n"
                f"📢 Analiz riskli. İZLE.")

    risk_rate = 0.08 if state["win_streak"] < 2 else 0.12
    risk_amount = state["bakiye"] * risk_rate
    state["last_unit"] = max(math.floor(risk_amount / len(all_bets)), 1)
    state["last_all_bets"] = all_bets

    return (
        f"🎯 **SNIPER v6.3 (ULTRA)**\n"
        f"💰 **KASA:** {state['bakiye']} | 🪙 **UNIT:** {state['last_unit']}\n"
        f"───────────────────\n"
        f"🔥 **PİVOTLAR:** {pivots}\n"
        f"🧩 **KAOS:** {chaos:.1f} | **SAYI:** {len(all_bets)}\n"
        f"───────────────────\n"
        f"🚀 **HİT RATE:** {hit_rate:.2f}"
    )

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    raw_text = update.message.text.strip().upper()

    if raw_text == '🗑️ SIFIRLA':
        if uid in user_states: del user_states[uid]
        await update.message.reply_text("🛡️ SIFIRLANDI."); return
    if raw_text == '↩️ GERİ AL' and state["snapshot"]:
        state.update(state["snapshot"].pop()); await update.message.reply_text("↩️ Geri alındı."); return

    if not raw_text.isdigit():
        await update.message.reply_text("⚠️ Sadece rakam girin!"); return

    val = int(raw_text)

    # Kasa Giriş Modu (Limit yok)
    if state["waiting_for_balance"]:
        state["bakiye"] = val; state["ana_kasa"] = val; state["waiting_for_balance"] = False; state["is_warmup_done"] = True
        msg = await generate_analysis_msg(uid); await update.message.reply_text(msg); return

    # Rulet Sayı Kontrolü (Sadece oyun sırasında)
    if not state["waiting_for_balance"] and (val < 0 or val > 36):
        await update.message.reply_text("❌ 0-36 arası sayı girin!"); return

    # Snapshot
    snap = {k: (list(v) if isinstance(v, deque) else v) for k, v in state.items() if k != "snapshot"}
    state["snapshot"].append(snap)

    if state["is_warmup_done"]:
        cost = len(state["last_all_bets"]) * state["last_unit"]
        if val in (state["last_all_bets"] or []) and state["last_unit"] > 0:
            state["bakiye"] += (state["last_unit"] * 36) - cost
            state["hit_history"].append(1); state["fail_count"] = 0; state["win_streak"] += 1
            await update.message.reply_text(f"✅ HİT! (+{state['last_unit']*36-cost})")
        elif state["last_unit"] > 0:
            state["bakiye"] -= cost
            state["hit_history"].append(0); state["fail_count"] += 1; state["win_streak"] = 0
            await update.message.reply_text(f"❌ PAS (-{cost})")
        else: state["hit_history"].append(1 if val in (state["last_all_bets"] or []) else 0)

    state["history"].append(val)
    
    if not state["is_warmup_done"]:
        if len(state["history"]) == 10:
            state["waiting_for_balance"] = True
            await update.message.reply_text("🎯 10 Sayı Tamam!\n💰 Güncel kasanızı girin (Örn: 10000):")
    else:
        msg = await generate_analysis_msg(uid)
        await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = get_user_state(uid)
    await update.message.reply_text("🦅 **SNIPER v6.3**\nSessiz ısınma modu aktif. İlk 10 sayıyı girin...", reply_markup=ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True))

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
