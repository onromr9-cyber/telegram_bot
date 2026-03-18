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

def get_user_state(uid):
    if uid not in user_states:
        user_states[uid] = {
            "bakiye": 0, "ana_kasa": 0, "history": deque(maxlen=100),
            "hit_history": deque(maxlen=10), "last_all_bets": [],
            "fail_count": 0, "win_streak": 0, "is_warmup_done": False,
            "waiting_for_balance": False, "last_unit": 0, "snapshot": []
        }
    return user_states[uid]

user_states = {}

def get_neighbors(n, s=1):
    idx = WHEEL_MAP[n]
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

def sniper_engine_v4(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    
    # 1. Ritim & Kaos Analizi
    jump_avg = 0
    chaos_factor = 0
    if len(hist) >= 3:
        dists = [(WHEEL_MAP[hist[i]] - WHEEL_MAP[hist[i-1]] + 37) % 37 for i in range(-1, -3, -1)]
        jump_avg = int(sum(dists) / len(dists))
        chaos_factor = abs(dists[0] - dists[1])

    # 2. Nokta Atışı Skorlama
    scores = {num: 0 for num in range(37)}
    for i, n in enumerate(reversed(hist[-12:])):
        decay = 100 / (1.2**i) # Daha sert sönümleme (Son sayılar daha önemli)
        p_idx = (WHEEL_MAP[n] + jump_avg) % 37
        scores[WHEEL[p_idx]] += decay

    sorted_sc = sorted(scores.items(), key=lambda x: -x[1])
    
    # MAIN: En yüksek puanlı 2 merkez sayı
    main_points = [sorted_sc[0][0], sorted_sc[1][0]]
    
    # EXTRA: Son gelen sayı (Repeat) ve 2. en iyi aday
    extra_points = [hist[-1], sorted_sc[2][0]]
    
    # KAÇIŞ: Tam ayna noktası
    mirror_idx = (WHEEL_MAP[hist[-1]] + 18) % 37
    escape_points = [WHEEL[mirror_idx]]

    return main_points, extra_points, escape_points, chaos_factor

async def generate_analysis_msg(uid):
    state = get_user_state(uid)
    m_p, e_p, esc_p, chaos = sniper_engine_v4(uid)
    
    # Hit Rate (Son 5 el)
    last_5 = list(state["hit_history"])[-5:]
    hit_rate = sum(last_5) / 5 if len(last_5) >= 5 else 1.0

    # --- NOKTA ATIŞI FİLTRESİ (DAR KOMŞULUK) ---
    # Sadece S1 (Sağ-Sol 1) kullanıyoruz. Maksimum 15-18 sayı.
    m_b = set(); e_b = set(); esc_b = set()
    [m_b.update(get_neighbors(p, 1)) for p in m_p]
    [e_b.update(get_neighbors(p, 1)) for p in e_p]
    [esc_b.update(get_neighbors(p, 1)) for p in esc_p]
    
    all_bets = list(m_b | e_b | esc_b)

    # --- GUARDIAN ÇIKIŞ MANTIĞI ---
    if hit_rate < 0.2 or chaos > 18 or state["fail_count"] >= 3:
        state["last_unit"] = 0
        state["last_all_bets"] = []
        return (f"🛑 **LÜTFEN KALK!**\n"
                f"───────────────────\n"
                f"⚠️ Ritim koptu veya verim düştü.\n"
                f"📈 Hit Rate: {hit_rate} | Kaos: {chaos}\n"
                f"📢 Masa dengelenene kadar İZLE.")

    # Risk Yönetimi (Kasanın %6'sı ile nokta atışı)
    risk_rate = 0.06 if state["win_streak"] < 2 else 0.09
    risk_amount = state["bakiye"] * risk_rate
    state["last_unit"] = max(math.floor(risk_amount / len(all_bets)), 1)
    state["last_all_bets"] = all_bets

    return (
        f"🎯 **SNIPER v4 (NOKTA ATIŞI)**\n"
        f"💰 **KASA:** {state['bakiye']} | 🪙 **UNIT:** {state['last_unit']}\n"
        f"───────────────────\n"
        f"🔥 **MERKEZ:** {m_p}\n"
        f"⚡ **DESTEK:** {e_p}\n"
        f"🌀 **KAÇIŞ:** {esc_p}\n"
        f"───────────────────\n"
        f"📊 **KAPALI:** {len(all_bets)} Sayı | **KAOS:** {chaos}\n"
        f"🚀 Kararlı yapı: Minimum risk, maksimum odak."
    )

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    text = update.message.text.strip().upper()

    if text == '🗑️ SIFIRLA':
        if uid in user_states: del user_states[uid]
        await update.message.reply_text("🛡️ SIFIRLANDI."); return
    
    if text == '↩️ GERİ AL' and state["snapshot"]:
        state.update(state["snapshot"].pop()); await update.message.reply_text("↩️ Geri alındı."); return

    if not text.isdigit(): return
    val = int(text)

    # Snapshot
    snap = {k: (list(v) if isinstance(v, deque) else v) for k, v in state.items() if k != "snapshot"}
    state["snapshot"].append(snap)

    if state["waiting_for_balance"]:
        state["bakiye"] = val; state["ana_kasa"] = val; state["waiting_for_balance"] = False; state["is_warmup_done"] = True
        msg = await generate_analysis_msg(uid); await update.message.reply_text(msg); return

    if state["is_warmup_done"]:
        cost = len(state["last_all_bets"]) * state["last_unit"]
        if val in state["last_all_bets"] and state["last_unit"] > 0:
            state["bakiye"] += (state["last_unit"] * 36) - cost
            state["hit_history"].append(1); state["fail_count"] = 0; state["win_streak"] += 1
            await update.message.reply_text(f"✅ HİT! (+{state['last_unit']*36})")
        elif state["last_unit"] > 0:
            state["bakiye"] -= cost
            state["hit_history"].append(0); state["fail_count"] += 1; state["win_streak"] = 0
            await update.message.reply_text(f"❌ PAS (-{cost})")
        else:
            state["hit_history"].append(1 if val in (state["last_all_bets"] or []) else 0)

    state["history"].append(val)
    if len(state["history"]) == 10 and not state["is_warmup_done"]:
        state["waiting_for_balance"] = True
        await update.message.reply_text("🎯 ISINMA TAMAM. 💰 KASA GİRİN:")
    elif len(state["history"]) >= 10:
        msg = await generate_analysis_msg(uid)
        await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = get_user_state(uid)
    await update.message.reply_text("🛡️ **SNIPER GUARDIAN**\nSayı girişi bekliyor...", parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True))

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
