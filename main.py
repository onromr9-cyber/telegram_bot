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
            "hit_history": deque(maxlen=10),
            "last_all_bets": [], "consecutive_wins": 0, "consecutive_losses": 0,
            "is_warmup_done": False, "waiting_for_balance": False, "last_unit": 0
        }
    return user_states[uid]

def get_neighbors(n, s=2):
    idx = WHEEL_MAP[n]
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

# --- ENGINE V5.1 TRIPLE HIT ---
async def smart_engine_v5_1(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    last_num = hist[-1]
    
    # 1. Analiz Motoru
    jumps = [(WHEEL_MAP[hist[i]] - WHEEL_MAP[hist[i-1]] + 37) % 37 for i in range(1, len(hist))]
    chaos_factor = np.std(jumps[-6:]) if len(jumps) >= 6 else 10.0
    avg_jump = int(np.mean(jumps[-8:])) if len(jumps) >= 8 else 18

    # 2. Gizli Komşulu Puanlama
    scores = {num: 0 for num in range(37)}
    for i, n in enumerate(reversed(hist[-15:])):
        decay = 100 / (1.15**i)
        target_idx = (WHEEL_MAP[n] + avg_jump) % 37
        for d in [-2, -1, 0, 1, 2]:
            num = WHEEL[(target_idx + d) % 37]
            weight = 1.0 if d == 0 else 0.5
            scores[num] += decay * weight

    # Tekrar Sayısı ve Yakın Bölge Bonusu (Repeat Sistemi)
    scores[last_num] += 60
    for n in get_neighbors(last_num, 1): scores[n] += 30

    sorted_sc = sorted(scores.items(), key=lambda x: -x[1])
    
    # 3. ODAKLANMIŞ SİSTEM (3 Ana Hedef + 2 Komşu)
    top_3_targets = [sorted_sc[0][0], sorted_sc[1][0], sorted_sc[2][0]]
    all_bets = set()
    for t in top_3_targets:
        all_bets.update(get_neighbors(t, 2)) # 2 Komşulu Gizli Sistem
    
    final_bets = sorted(list(all_bets))
    state["last_all_bets"] = final_bets
    bet_count = len(final_bets)

    # 4. KRİTİK UYARI VE DURDURMA SİSTEMİ
    hit_rate = sum(state["hit_history"]) / len(state["hit_history"]) if state["hit_history"] else 1.0
    kasa_erime = (state["ana_kasa"] - state["bakiye"]) / state["ana_kasa"] if state["ana_kasa"] > 0 else 0
    
    if chaos_factor > 16.0 or hit_rate < 0.2 or kasa_erime > 0.5:
        status, risk_percent = "🔴 LÜTFEN KALK! (Tehlike)", 0.0
        extra_msg = "🚨 Masa dengesi bozuldu! Matematiksel kaos var."
    elif chaos_factor > 11.0:
        status, risk_percent = "🟡 SARI MOD (Temkinli)", 0.04
        extra_msg = "📉 Ritim belirsiz, düşük bahisli takip."
    else:
        status, risk_percent = "🟢 YEŞİL MOD (Güvenli)", 0.09
        extra_msg = "✅ Ritim stabil, kazanç serisi beklenebilir."

    # Power-Up (Artan Kazanç Oranı)
    if status.startswith("🟢") and state["consecutive_wins"] > 0:
        risk_percent = min(0.20, risk_percent + (state["consecutive_wins"] * 0.05))

    total_risk = state["bakiye"] * risk_percent
    unit = max(math.floor(total_risk / bet_count), 1) if risk_percent > 0 else 0
    state["last_unit"] = unit

    msg = (
        f"📊 DURUM: {status}\n"
        f"🌀 KAOS: {chaos_factor:.1f} | 🎯 İSABET: {hit_rate:.1f}\n"
        f"💰 KASA: {state['bakiye']} | 🪙 UNIT: {state['last_unit']}\n"
        f"🎲 ADET: {bet_count} | 🎯 RİSK: %{int(risk_percent*100)}\n"
        f"🔄 SON SAYI: {last_num}\n\n"
        f"🎯 ANA HEDEFLER: {top_3_targets}\n"
        f"🔥 ODAK (Gizli Komşu): {final_bets}\n"
        f"📢 {extra_msg}"
    )
    return msg

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = get_user_state(uid)
    await update.message.reply_text("🛡️ GUARDIAN v5.1 TRIPLE HIT\nSniper motoru hazır. 10 sayı girin.")

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
        msg = await smart_engine_v5_1(uid); await update.message.reply_text(msg); return

    if state["is_warmup_done"]:
        cost = len(state["last_all_bets"]) * state["last_unit"]
        if val in state["last_all_bets"] and state["last_unit"] > 0:
            state["bakiye"] += (state["last_unit"] * 36) - cost
            state["consecutive_wins"] += 1; state["consecutive_losses"] = 0
            state["hit_history"].append(1)
            await update.message.reply_text(f"✅ HİT! Sayı: {val}")
        elif state["last_unit"] > 0:
            state["bakiye"] -= cost
            state["consecutive_losses"] += 1; state["consecutive_wins"] = 0
            state["hit_history"].append(0)
            await update.message.reply_text(f"❌ PAS. Sayı: {val}")
        else:
            state["hit_history"].append(0)
            await update.message.reply_text(f"👁️ İZLEMEDE (Bahis Yok): {val}")

    state["history"].append(val)
    if len(state["history"]) == 10 and not state["is_warmup_done"]:
        state["waiting_for_balance"] = True
        await update.message.reply_text("🎯 KASA GİRİN:"); return
    elif len(state["history"]) >= 10:
        msg = await smart_engine_v5_1(uid); await update.message.reply_text(msg)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
