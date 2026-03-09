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

# Sektör Tanımları
VOISINS = {22, 18, 29, 7, 28, 12, 35, 3, 26, 0, 32, 15, 19, 4, 21, 2, 25}
TIER = {27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33}
ORPHELINS = {1, 20, 14, 31, 9, 17, 34, 6}

user_states = {}

def get_user_state(uid):
    if uid not in user_states:
        user_states[uid] = {
            "bakiye": 0, "ana_kasa": 0, "history": deque(maxlen=100), 
            "hit_history": deque(maxlen=15), "is_locked": False, "snapshot": [],
            "last_all_bets": [], "consecutive_wins": 0, "consecutive_losses": 0,
            "is_warmup_done": False, "waiting_for_balance": False, "last_unit": 0,
            "current_sector": "N/A"
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

# --- ENGINE V4.5 ---
async def smart_engine_v4_5(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    
    # 1. Kaos ve Ritim
    jumps = [(WHEEL_MAP[hist[i]] - WHEEL_MAP[hist[i-1]] + 37) % 37 for i in range(1, len(hist))]
    chaos_factor = np.std(jumps[-6:]) if len(jumps) >= 6 else 10.0
    avg_jump = int(np.mean(jumps[-8:])) if len(jumps) >= 8 else 18

    # 2. Sektör Analizi
    last_5_sectors = [get_sector(n) for n in hist[-5:]]
    dominant_sector = collections.Counter(last_5_sectors).most_common(1)[0][0]
    state["current_sector"] = dominant_sector

    # 3. Puanlama (Hassas ve Sektör Ağırlıklı)
    scores = {num: 0 for num in range(37)}
    for i, n in enumerate(reversed(hist[-15:])):
        decay = 100 / (1.15**i)
        target_idx = (WHEEL_MAP[n] + avg_jump) % 37
        for d in [-1, 0, 1]:
            num = WHEEL[(target_idx + d) % 37]
            scores[num] += decay
            if get_sector(num) == dominant_sector: scores[num] *= 1.4 # Sektör Bonusu

    sorted_sc = sorted(scores.items(), key=lambda x: -x[1])
    
    # 4. Bahis Seçimi (Sektör ve Repeat Kombini)
    top_targets = [sorted_sc[0][0], sorted_sc[1][0], sorted_sc[2][0], hist[-1]]
    all_bets = set()
    for t in top_targets:
        all_bets.update(get_neighbors(t, 1))
    
    final_bets = sorted(list(all_bets))
    state["last_all_bets"] = final_bets

    # 5. Power-Up Risk Yönetimi
    if state["consecutive_losses"] >= 2:
        risk_percent = 0.03
    elif state["consecutive_wins"] == 0:
        risk_percent = 0.06
    elif state["consecutive_wins"] == 1:
        risk_percent = 0.12
    elif state["consecutive_wins"] == 2:
        risk_percent = 0.25
    else:
        risk_percent = 0.50

    total_risk = state["bakiye"] * risk_percent
    unit = max(math.floor(total_risk / len(final_bets)), 1) if state["bakiye"] > 0 else 0
    state["last_unit"] = unit

    status = "🚀 POWER-UP" if state["consecutive_wins"] > 0 else ("🛡️ DEFANS" if state["consecutive_losses"] >= 2 else "⚖️ STANDART")
    
    msg = (
        f"📊 MOD: {status}\n"
        f"🌀 KAOS: {chaos_factor:.1f} | 🧭 SEKTÖR: {dominant_sector}\n"
        f"🎲 ADET: {len(final_bets)} Sayı | 🎯 RİSK: %{int(risk_percent*100)}\n"
        f"💰 KASA: {state['bakiye']} | 🪙 UNIT: {state['last_unit']}\n\n"
        f"🔥 OYNA: {final_bets}"
    )
    return msg

# --- HANDLERS (Start ve Play Fonksiyonları) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = get_user_state(uid)
    await update.message.reply_text("🛡️ GUARDIAN v4.5 (Sektör + Power-Up)\n10 sayı girerek başlayın.")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    
    text = update.message.text.strip().upper()
    if text == '/RESET':
        if uid in user_states: del user_states[uid]
        await start(update, context); return
    if not text.isdigit(): return
    val = int(text)

    if state["waiting_for_balance"]:
        state["bakiye"] = val; state["ana_kasa"] = val; state["waiting_for_balance"] = False; state["is_warmup_done"] = True
        msg = await smart_engine_v4_5(uid); await update.message.reply_text(msg); return

    if state["is_warmup_done"]:
        cost = len(state["last_all_bets"]) * state["last_unit"]
        if val in state["last_all_bets"]:
            state["bakiye"] += (state["last_unit"] * 36) - cost
            state["consecutive_wins"] += 1
            state["consecutive_losses"] = 0
            await update.message.reply_text(f"✅ HİT! Seri: {state['consecutive_wins']} | Sektör: {get_sector(val)}")
        else:
            state["bakiye"] -= cost
            state["consecutive_losses"] += 1
            state["consecutive_wins"] = 0
            await update.message.reply_text(f"❌ PAS. Sektör: {get_sector(val)}")

    state["history"].append(val)
    if len(state["history"]) == 10 and not state["is_warmup_done"]:
        state["waiting_for_balance"] = True
        await update.message.reply_text("🎯 ISINMA TAMAM. KASA GİRİN:"); return
    elif len(state["history"]) >= 10:
        msg = await smart_engine_v4_5(uid)
        await update.message.reply_text(msg)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
