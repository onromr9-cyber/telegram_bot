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
            "bakiye": 0, "history": deque(maxlen=100),
            "hit_history": deque(maxlen=10), "last_all_bets": [],
            "win_streak": 0, "is_warmup_done": False,
            "waiting_for_balance": False, "last_unit": 0, "snapshot": []
        }
    return user_states[uid]

def get_neighbors(n, s=1):
    idx = WHEEL_MAP[n]
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

def precision_sniper_engine(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    if len(hist) < 4: return [hist[-1]] if hist else [0], 0

    # NumPy ile hassas momentum analizi
    indices = [WHEEL_MAP[x] for x in hist[-8:]]
    jumps = np.diff(indices) % 37
    avg_jump = int(np.mean(jumps[-3:])) # Son 3 atışın ortalaması
    chaos = float(np.std(jumps[-5:]))    # Standart sapma (Kaos Ölçer)

    # 🎯 SNIPER NOKTALARI
    # 1. Momentum Noktası
    p1 = WHEEL[(WHEEL_MAP[hist[-1]] + avg_jump) % 37]
    # 2. Ayna (Simetri)
    p2 = WHEEL[(WHEEL_MAP[hist[-1]] + 18) % 37]
    # 3. Son Sayı (Tekrar Sigortası)
    p3 = hist[-1]

    return [p1, p2, p3], chaos

async def generate_analysis_msg(uid):
    state = get_user_state(uid)
    pivots, chaos = precision_sniper_engine(uid)
    
    # Hit Rate Kontrolü (Son 5 el)
    last_5 = list(state["hit_history"])[-5:]
    hit_rate = sum(last_5) / 5 if len(last_5) >= 5 else 1.0

    # NOKTA ATIŞI LİSTESİ OLUŞTURMA (Max 10-12 Sayı)
    all_bets_set = set()
    all_bets_set.update(get_neighbors(pivots[0], 1)) # Ana Pivot S1 (3 sayı)
    all_bets_set.update(get_neighbors(pivots[1], 1)) # Ayna S1 (3 sayı)
    all_bets_set.update([pivots[2]])                 # Son Sayı (1 sayı) - Komşusuz direkt!

    all_bets = list(all_bets_set)
    state["last_all_bets"] = all_bets

    # 🛑 EXIT LOGIC (Cerrahi Durdurma)
    if chaos > 12.0 or (len(last_5) == 5 and hit_rate <= 0.2):
        state["last_unit"] = 0
        return (f"🚨 **LÜTFEN KALK!**\n"
                f"───────────────────\n"
                f"⚠️ Ritim Kaybı: {chaos:.1f}\n"
                f"⚠️ Verim: {hit_rate:.2f}\n"
                f"📢 Masa 'Sniper' için uygun değil. İzle.")

    # Risk Yönetimi
    unit_val = max(math.floor((state["bakiye"] * 0.10) / len(all_bets)), 1)
    state["last_unit"] = unit_val

    return (
        f"🎯 **SNIPER PRECISION v1**\n"
        f"💰 KASA: {state['bakiye']} | 🪙 UNIT: {unit_val}\n"
        f"───────────────────\n"
        f"🔥 **ANA (S1):** {pivots[0]}\n"
        f"🌀 **AYNA (S1):** {pivots[1]}\n"
        f"💎 **SON SAYI:** {pivots[2]}\n"
        f"───────────────────\n"
        f"🧩 Ritim Sapması: {chaos:.1f}\n"
        f"📢 Toplam {len(all_bets)} sayı. Nokta atışı aktif!"
    )

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    text = update.message.text.strip().upper()

    if text == '🗑️ SIFIRLA':
        if uid in user_states: del user_states[uid]
        await update.message.reply_text("🗑️ Temizlendi. 10 sayı girin."); return
    
    if text == '↩️ GERİ AL' and state["snapshot"]:
        state.update(state["snapshot"].pop())
        await update.message.reply_text("↩️ Geri alındı."); return

    if not text.isdigit():
        await update.message.reply_text("⚠️ Sadece rakam!"); return

    val = int(text)

    if state["waiting_for_balance"]:
        state["bakiye"] = val; state["waiting_for_balance"] = False; state["is_warmup_done"] = True
        msg = await generate_analysis_msg(uid); await update.message.reply_text(msg, parse_mode='Markdown'); return

    if not state["waiting_for_balance"] and (val < 0 or val > 36):
        await update.message.reply_text("❌ 0-36 arası!"); return

    # Snapshot
    snap = {k: (list(v) if isinstance(v, deque) else v) for k, v in state.items() if k != "snapshot"}
    state["snapshot"].append(snap)

    if state["is_warmup_done"]:
        cost = len(state["last_all_bets"]) * state["last_unit"]
        if val in state["last_all_bets"] and state["last_unit"] > 0:
            gain = (state["last_unit"] * 36) - cost
            state["bakiye"] += gain
            state["hit_history"].append(1); state["win_streak"] += 1
            await update.message.reply_text(f"✅ HİT! (+{gain})")
        elif state["last_unit"] > 0:
            state["bakiye"] -= cost
            state["hit_history"].append(0); state["win_streak"] = 0
            await update.message.reply_text(f"❌ PAS (-{cost})")

    state["history"].append(val)
    
    if not state["is_warmup_done"]:
        if len(state["history"]) == 10:
            state["waiting_for_balance"] = True
            await update.message.reply_text("🎯 Isınma bitti. Kasa girin:"); return
    else:
        msg = await generate_analysis_msg(uid)
        await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = get_user_state(uid)
    await update.message.reply_text("🎯 **SNIPER PRECISION**\nİlk 10 sayıyı girin...", reply_markup=ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True))

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
