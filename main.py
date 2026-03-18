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

def triple_chain_engine(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    
    # 1. VEKTÖREL KAYMA (Momentum) ANALİZİ
    # J1: Son atlama mesafesi, J2: Bir önceki atlama mesafesi
    j1, j2 = 0, 0
    if len(hist) >= 3:
        j1 = (WHEEL_MAP[hist[-1]] - WHEEL_MAP[hist[-2]] + 37) % 37
        j2 = (WHEEL_MAP[hist[-2]] - WHEEL_MAP[hist[-3]] + 37) % 37

    # Chaos Factor: İvme değişimi (Düşükse ritim var, yüksekse kaos var)
    chaos = abs(j1 - j2)
    
    # 2. ÜÇLÜ ZİNCİR TAHMİNİ (Pivot Noktaları)
    # Pivot 1: Momentum Korunumu (Aynı hızla devam)
    p1 = (WHEEL_MAP[hist[-1]] + j1) % 37
    # Pivot 2: Ayna/Zıt Sıçrama (Counter-Jump)
    p2 = (WHEEL_MAP[hist[-1]] + (37 - j1)) % 37
    # Pivot 3: Aritmetik Ortalama (Yavaşlayan Momentum)
    avg_j = int((j1 + j2) / 2)
    p3 = (WHEEL_MAP[hist[-1]] + avg_j) % 37

    # 3. NOKTA ATIŞI LİSTELEME
    # Sadece S1 (Sağ-Sol 1) kullanarak alanı 9-14 sayıda tutuyoruz.
    targets = {WHEEL[p1], WHEEL[p2], WHEEL[p3], hist[-1]} # hist[-1] Repeat koruması
    
    return list(targets), chaos

async def generate_analysis_msg(uid):
    state = get_user_state(uid)
    pivots, chaos = triple_chain_engine(uid)
    
    # Hit Rate Kontrolü
    last_5 = list(state["hit_history"])[-5:]
    hit_rate = sum(last_5) / 5 if len(last_5) >= 5 else 1.0

    # Komşuluk oluşturma (Nokta Atışı için S1)
    all_bets_set = set()
    for p in pivots:
        all_bets_set.update(get_neighbors(p, 1))
    
    all_bets = list(all_bets_set)

    # --- GUARDIAN RİSK KONTROLÜ ---
    # Eğer kaos çok yüksekse (ivme sürekli değişiyorsa) veya hit rate yerlerdeyse:
    if chaos > 20 or hit_rate < 0.2:
        state["last_unit"] = 0
        state["last_all_bets"] = []
        return (f"🛑 **LÜTFEN KALK! (RİTİM KOPTU)**\n"
                f"───────────────────\n"
                f"⚠️ Kaos Katsayısı: {chaos}\n"
                f"📉 Başarı Oranı: {hit_rate}\n"
                f"📢 Top öngörülemez savruluyor. İZLE!")

    # Bakiye ve Unit Yönetimi (%7 Risk)
    risk_rate = 0.07 if state["win_streak"] < 2 else 0.10
    risk_miktari = state["bakiye"] * risk_rate
    state["last_unit"] = max(math.floor(risk_miktari / len(all_bets)), 1)
    state["last_all_bets"] = all_bets

    return (
        f"🎯 **TRIPLE CHAIN SNIPER**\n"
        f"💰 **KASA:** {state['bakiye']} | 🪙 **UNIT:** {state['last_unit']}\n"
        f"───────────────────\n"
        f"🔥 **PIVOT NOKTALAR:** {pivots}\n"
        f"🧩 **KAOS:** {chaos} | **KAPALI:** {len(all_bets)}\n"
        f"───────────────────\n"
        f"📢 Üçlü zincir ve momentum aktif.\n"
        f"🚀 **HİT RATE:** {hit_rate}"
    )

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    text = update.message.text.strip().upper()

    if text == '🗑️ SIFIRLA':
        if uid in user_states: del user_states[uid]
        await update.message.reply_text("🛡️ SİSTEM SIFIRLANDI."); return
    
    if text == '↩️ GERİ AL' and state["snapshot"]:
        state.update(state["snapshot"].pop()); await update.message.reply_text("↩️ Geri alındı."); return

    if not text.isdigit(): return
    val = int(text)

    # Snapshot Kaydı (Geri alma için)
    snap = {k: (list(v) if isinstance(v, deque) else v) for k, v in state.items() if k != "snapshot"}
    state["snapshot"].append(snap)

    if state["waiting_for_balance"]:
        state["bakiye"] = val; state["ana_kasa"] = val; state["waiting_for_balance"] = False; state["is_warmup_done"] = True
        msg = await generate_analysis_msg(uid); await update.message.reply_text(msg); return

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
    await update.message.reply_text("🦅 **TRIPLE CHAIN SNIPER v5**\nIsınma için 10 sayı girin...", parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True))

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
