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

user_states = {}

def get_user_state(uid):
    if uid not in user_states:
        user_states[uid] = {
            "bakiye": 0, "ana_kasa": 0, "history": deque(maxlen=100), 
            "hit_history": deque(maxlen=15), "last_all_bets": [], 
            "consecutive_wins": 0, "consecutive_losses": 0,
            "is_warmup_done": False, "waiting_for_balance": False, "last_unit": 0
        }
    return user_states[uid]

def get_neighbors(n, s=1):
    idx = WHEEL_MAP[n]
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

# --- ENGINE V4.9 GUARDIAN MASTER ---
async def smart_engine_v4_9(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    last_num = hist[-1]
    
    # 1. Ritim ve Kaos Analizi
    jumps = [(WHEEL_MAP[hist[i]] - WHEEL_MAP[hist[i-1]] + 37) % 37 for i in range(1, len(hist))]
    chaos_factor = np.std(jumps[-6:]) if len(jumps) >= 6 else 10.0
    avg_jump = int(np.mean(jumps[-8:])) if len(jumps) >= 8 else 18

    # 2. Gizli Komşulu Puanlama
    scores = {num: 0 for num in range(37)}
    for i, n in enumerate(reversed(hist[-15:])):
        decay = 100 / (1.15**i)
        target_idx = (WHEEL_MAP[n] + avg_jump) % 37
        # Gizli komşu etkisi (3 komşu taranır, merkez en yüksek puanı alır)
        for d in [-3, -2, -1, 0, 1, 2, 3]:
            num = WHEEL[(target_idx + d) % 37]
            weight = 1.0 if d == 0 else (0.5 if abs(d) == 1 else 0.2)
            scores[num] += decay * weight

    # Tekrar Sayısı Bonusu
    for n in get_neighbors(last_num, 1): scores[n] += 50 

    sorted_sc = sorted(scores.items(), key=lambda x: -x[1])
    
    # 3. Odaklanmış Seçim (10-12 Sayı)
    final_bets = sorted(list(set([sorted_sc[i][0] for i in range(11)])))
    state["last_all_bets"] = final_bets

    # 4. Trafik Işığı ve Risk Yönetimi
    if chaos_factor > 15.0:
        status, risk_percent = "🔴 SANAL TAKİP", 0.0
    elif chaos_factor > 10.0:
        status, risk_percent = "🟡 TEMKİNLİ (Sarı)", 0.05
    else:
        status, risk_percent = "🟢 DENGELİ (Yeşil)", 0.08

    # Win Streak (Power-Up) - Sadece Yeşil ve Sarı modda çalışır
    if state["consecutive_wins"] > 0 and risk_percent > 0:
        risk_percent += (state["consecutive_wins"] * 0.05)
        risk_percent = min(risk_percent, 0.20) # Maks %20 tavan

    total_risk = state["bakiye"] * risk_percent
    unit = max(math.floor(total_risk / len(final_bets)), 1) if state["bakiye"] > 0 else 0
    state["last_unit"] = unit

    msg = (
        f"📊 DURUM: {status}\n"
        f"🌀 KAOS: {chaos_factor:.1f} | 🎲 ADET: {len(final_bets)}\n"
        f"💰 KASA: {state['bakiye']} | 🪙 UNIT: {state['last_unit']}\n"
        f"🎯 RİSK: %{int(risk_percent*100)}\n\n"
        f"🔥 ODAK NOKTASI: {final_bets}"
    )
    return msg

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = get_user_state(uid)
    await update.message.reply_text("🛡️ GUARDIAN v4.9 MASTER\n(Sinyal Sistemi Aktif)", 
                                    reply_markup=ReplyKeyboardMarkup([['/reset']], resize_keyboard=True))

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
        msg = await smart_engine_v4_9(uid); await update.message.reply_text(msg); return

    if state["is_warmup_done"]:
        cost = len(state["last_all_bets"]) * state["last_unit"]
        if val in state["last_all_bets"] and state["last_unit"] > 0:
            state["bakiye"] += (state["last_unit"] * 36) - cost
            state["consecutive_wins"] += 1; state["consecutive_losses"] = 0
            await update.message.reply_text(f"✅ HİT! (+{(state['last_unit']*36)-cost})")
        elif state["last_unit"] > 0:
            state["bakiye"] -= cost
            state["consecutive_losses"] += 1; state["consecutive_wins"] = 0
            await update.message.reply_text(f"❌ PAS")
        else:
            await update.message.reply_text(f"👁️ İZLEMEDE: {val}")

    state["history"].append(val)
    if len(state["history"]) == 10 and not state["is_warmup_done"]:
        state["waiting_for_balance"] = True
        await update.message.reply_text("🎯 KASA GİRİN:"); return
    elif len(state["history"]) >= 10:
        msg = await smart_engine_v4_9(uid); await update.message.reply_text(msg)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()

