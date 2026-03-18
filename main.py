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

# Sektör Tanımları
VOISINS = {22, 18, 29, 7, 28, 12, 35, 3, 26, 0, 32, 15, 19, 4, 21, 2, 25}
TIER = {27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33}
ORPHELINS = {1, 20, 14, 31, 9, 17, 34, 6}

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
    
    # 1. Ritim Analizi (Jump & Cross-Wheel)
    jump_avg = 0
    chaos_factor = 0
    if len(hist) >= 3:
        dists = [(WHEEL_MAP[hist[i]] - WHEEL_MAP[hist[i-1]] + 37) % 37 for i in range(-1, -3, -1)]
        jump_avg = int(sum(dists) / len(dists))
        chaos_factor = abs(dists[0] - dists[1]) # Ritim sapması

    # 2. Skorlama
    scores = {num: 0 for num in range(37)}
    for i, n in enumerate(reversed(hist[-15:])):
        decay = 100 / (1.15**i)
        p_idx = (WHEEL_MAP[n] + jump_avg) % 37
        for d in [-1, 0, 1]:
            num = WHEEL[(p_idx + d) % 37]
            scores[num] += decay

    sorted_sc = sorted(scores.items(), key=lambda x: -x[1])
    
    # MAIN (Merkezi Sayılar)
    main_t = []
    for cand, _ in sorted_sc:
        if len(main_t) >= 3: break
        if all(abs(WHEEL_MAP[cand] - WHEEL_MAP[t]) >= 6 for t in main_t):
            main_t.append(cand)
            
    # EXTRA (Tekrar Sayısı Dahil)
    extra_t = [hist[-1]] # Her zaman son sayı (Repeat Number) dahil
    for cand, _ in sorted_sc:
        if len(extra_t) >= 3: break
        if cand not in main_t and cand not in extra_t:
            extra_t.append(cand)

    # KAÇIŞ (Mirroring & Chaos Expansion)
    mirror_idx = (WHEEL_MAP[hist[-1]] + 18) % 37
    escape_num = WHEEL[mirror_idx]
    
    return main_t, extra_t, [escape_num], chaos_factor

async def generate_analysis_msg(uid):
    state = get_user_state(uid)
    m_t, e_t, esc_t, chaos = smart_engine_v3_core(uid)
    
    # Hit Rate Hesaplama
    last_5_hits = list(state["hit_history"])[-5:]
    hit_rate = sum(last_5_hits) / 5 if len(last_5_hits) >= 5 else 1.0
    
    # --- GUARDIAN STOP LOGIC ---
    kalk_uyarisi = False
    reasons = []
    if hit_rate < 0.2: reasons.append("Düşük Hit Oranı (<0.2)")
    if chaos > 15: reasons.append("Yüksek Kaos (Ritim Bozuk)")
    if state["fail_count"] >= 3: reasons.append("Ardışık Kayıp (Saturasyon)")
    
    if reasons:
        kalk_uyarisi = True
        status = "🛑 LÜTFEN KALK!"
        extra_msg = "⚠️ " + " | ".join(reasons)
        state["spectator_timer"] = 3
    else:
        status = "🟢 AGRESİF" if state["win_streak"] >= 2 else "🟢 GÜVENLİ"
        extra_msg = "📢 Analiz Stabil."

    # Dinamik Komşuluk (Chaos Factor Expansion)
    m_s = 2 + (1 if chaos > 10 else 0)
    e_s = 2 if state["fail_count"] > 0 else 1
    esc_s = 2

    m_b = set(); e_b = set(); esc_b = set()
    [m_b.update(get_neighbors(t, m_s)) for t in m_t]
    [e_b.update(get_neighbors(t, e_s)) for t in e_t]
    [esc_b.update(get_neighbors(t, esc_s)) for t in esc_t]
    
    all_bets = list(m_b | e_b | esc_b)
    state["last_all_bets"] = all_bets if not kalk_uyarisi else []

    # Kasa/Unit Yönetimi
    if not kalk_uyarisi:
        risk_rate = 0.12 * (1.5 if state["win_streak"] >= 2 else 1.0)
        risk_amount = state["bakiye"] * risk_rate
        state["last_unit"] = max(math.floor(risk_amount / len(all_bets)), 1)
    else:
        state["last_unit"] = 0

    return (
        f"📊 **DURUM:** {status}\n"
        f"💰 **KASA:** {state['bakiye']} | 🪙 **UNIT:** {state['last_unit']}\n"
        f"───────────────────\n"
        f"🎯 **MAIN (S{m_s}):** {m_t}\n"
        f"⚡ **EXTRA (S{e_s}):** {e_t}\n"
        f"🌀 **KAÇIŞ (S{esc_s}):** {esc_t}\n"
        f"───────────────────\n"
        f"🧩 **KAOS:** {chaos} | 📈 **HİT RATE:** {hit_rate}\n"
        f"📢 **{extra_msg}**"
    )

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    text = update.message.text.strip().upper()

    if text == '🗑️ SIFIRLA':
        user_states[uid] = get_user_state(uid)
        await update.message.reply_text("🛡️ SIFIRLANDI. 10 sayı girin."); return
    
    if text == '↩️ GERİ AL':
        if state["snapshot"]:
            last_snap = state["snapshot"].pop()
            # Deque'leri koruyarak geri yükleme
            for k, v in last_snap.items():
                if isinstance(state[k], deque):
                    state[k] = deque(v, maxlen=state[k].maxlen)
                else:
                    state[k] = v
            await update.message.reply_text("↩️ İşlem geri alındı."); return

    if not text.isdigit(): return
    val = int(text)

    # Snapshot Kaydı
    snap = {k: (list(v) if isinstance(v, deque) else v) for k, v in state.items() if k != "snapshot"}
    state["snapshot"].append(snap)
    if len(state["snapshot"]) > 10: state["snapshot"].pop(0)

    # Kasa Giriş Modu
    if state["waiting_for_balance"]:
        state["bakiye"] = val; state["ana_kasa"] = val; state["waiting_for_balance"] = False; state["is_warmup_done"] = True
        msg = await generate_analysis_msg(uid); await update.message.reply_text(msg); return

    # Oyun Döngüsü
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
            state["hit_history"].append(1 if val in state["last_all_bets"] else 0)
            await update.message.reply_text(f"👁️ İZLEME: {val}")

    state["history"].append(val)
    if len(state["history"]) == 10 and not state["is_warmup_done"]:
        state["waiting_for_balance"] = True
        await update.message.reply_text("🎯 ISINMA TAMAM. 💰 KASA GİRİN:")
        return
    elif len(state["history"]) >= 10:
        msg = await generate_analysis_msg(uid)
        await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = get_user_state(uid)
    await update.message.reply_text("🛡️ **GUARDIAN ONLINE**\nLütfen ilk 10 sayıyı girin.", parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True))

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
