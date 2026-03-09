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
            "hit_history": deque(maxlen=10), # Son 10 elin isabet kaydı
            "last_all_bets": [], "consecutive_wins": 0, "consecutive_losses": 0,
            "is_warmup_done": False, "waiting_for_balance": False, "last_unit": 0
        }
    return user_states[uid]

# --- ENGINE V5.0 GUARDIAN SHIELD ---
async def smart_engine_v5_0(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    last_num = hist[-1]
    
    # 1. Analiz Motoru (v4.3 Temelli)
    jumps = [(WHEEL_MAP[hist[i]] - WHEEL_MAP[hist[i-1]] + 37) % 37 for i in range(1, len(hist))]
    chaos_factor = np.std(jumps[-6:]) if len(jumps) >= 6 else 10.0
    avg_jump = int(np.mean(jumps[-8:])) if len(jumps) >= 8 else 18

    # 2. Gizli Komşulu Puanlama
    scores = {num: 0 for num in range(37)}
    for i, n in enumerate(reversed(hist[-15:])):
        decay = 100 / (1.15**i)
        target_idx = (WHEEL_MAP[n] + avg_jump) % 37
        # Gizli tarama: Merkeze 100, yanlara 50, uzaklara 20 puan
        for d in [-2, -1, 0, 1, 2]:
            num = WHEEL[(target_idx + d) % 37]
            weight = 1.0 if d == 0 else 0.5
            scores[num] += decay * weight

    # Tekrar Sayısı ve Yakın Bölge Bonusu (Repeat Sistemi)
    scores[last_num] += 60
    for n in [WHEEL[(WHEEL_MAP[last_num]-1)%37], WHEEL[(WHEEL_MAP[last_num]+1)%37]]:
        scores[n] += 30

    sorted_sc = sorted(scores.items(), key=lambda x: -x[1])
    
    # 3. Odaklanmış Gizli Komşu Seçimi (En güçlü 9-10 sayı)
    final_bets = sorted(list(set([sorted_sc[i][0] for i in range(10)])))
    state["last_all_bets"] = final_bets

    # 4. KRİTİK UYARI VE DURDURMA SİSTEMİ
    hit_rate = sum(state["hit_history"]) / len(state["hit_history"]) if state["hit_history"] else 1.0
    kasa_erime = (state["ana_kasa"] - state["bakiye"]) / state["ana_kasa"] if state["ana_kasa"] > 0 else 0
    
    if chaos_factor > 16.0 or hit_rate < 0.2 or kasa_erime > 0.5:
        status, risk_percent = "🔴 LÜTFEN KALK! (Tehlike)", 0.0
        extra_msg = "⚠️ Masa dengesi bozuldu veya isabet oranı çok düşük!"
    elif chaos_factor > 11.0:
        status, risk_percent = "🟡 SARI MOD (Temkinli)", 0.04
        extra_msg = "📉 Ritim belirsiz, düşük bahis."
    else:
        status, risk_percent = "🟢 YEŞİL MOD (Güvenli)", 0.09
        extra_msg = "✅ Ritim stabil, oyuna devam."

    # Power-Up (Sadece Yeşil modda)
    if status.startswith("🟢") and state["consecutive_wins"] > 0:
        risk_percent = min(0.18, risk_percent + (state["consecutive_wins"] * 0.04))

    total_risk = state["bakiye"] * risk_percent
    unit = max(math.floor(total_risk / len(final_bets)), 1) if risk_percent > 0 else 0
    state["last_unit"] = unit

    msg = (
        f"📊 DURUM: {status}\n"
        f"🌀 KAOS: {chaos_factor:.1f} | 🎯 İSABET: {hit_rate:.1f}\n"
        f"💰 KASA: {state['bakiye']} | 🪙 UNIT: {state['last_unit']}\n"
        f"🎲 ADET: {len(final_bets)} | 🎯 RİSK: %{int(risk_percent*100)}\n"
        f"🔄 SON SAYI: {last_num}\n\n"
        f"🔥 ODAK: {final_bets}\n"
        f"📢 {extra_msg}"
    )
    return msg

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = get_user_state(uid)
    await update.message.reply_text("🛡️ GUARDIAN v5.0 SHIELD\nAnaliz motoru aktif. 10 sayı girin.")

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
        msg = await smart_engine_v5_0(uid); await update.message.reply_text(msg); return

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
            await update.message.reply_text(f"👁️ İZLEMEDE: {val}")

    state["history"].append(val)
    if len(state["history"]) == 10 and not state["is_warmup_done"]:
        state["waiting_for_balance"] = True
        await update.message.reply_text("🎯 KASA GİRİN:"); return
    elif len(state["history"]) >= 10:
        msg = await smart_engine_v5_0(uid); await update.message.reply_text(msg)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
