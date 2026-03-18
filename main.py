import os, math, collections
import numpy as np  # <--- YENİ EKLENDİ
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

def sniper_v6_numpy_engine(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    
    if len(hist) < 3:
        return [hist[-1]] if hist else [0], 0

    # 1. NUMPY İLE MOMENTUM ANALİZİ
    # Son 5 eldeki atlama mesafelerini (jumps) vektör olarak alıyoruz
    indices = [WHEEL_MAP[x] for x in hist[-6:]]
    jumps = np.diff(indices) % 37
    
    last_j = jumps[-1]  # Son atlama (J1)
    prev_j = jumps[-2]  # Bir önceki atlama (J2)
    
    # Kaos: İvme değişimi ve standart sapma kontrolü
    chaos = float(np.abs(last_j - prev_j))
    std_dev = float(np.std(jumps[-3:])) # Son 3 atlamanın tutarlılığı

    # 2. PİVOT HESAPLAMA (Vektörel Tahmin)
    p1 = (WHEEL_MAP[hist[-1]] + last_j) % 37      # Momentum Devamı
    p2 = (WHEEL_MAP[hist[-1]] + (37 - last_j)) % 37 # Counter-Jump (Zıt Sıçrama)
    mirror_idx = (WHEEL_MAP[hist[-1]] + 18) % 37   # Tekerlek Aynası
    
    pivots = {WHEEL[int(p1)], WHEEL[int(p2)], WHEEL[int(mirror_idx)]}
    
    # 3. ANTI-REPEAT & DOYUM FİLTRESİ
    # Eğer top aynı bölgeye (S1 yakınlığı) üst üste düştüyse o bölgeyi sil
    if np.abs(last_j) <= 2 or std_dev < 1.0:
        dead_zone = get_neighbors(hist[-1], 2)
        pivots = {p for p in pivots if p not in dead_zone}
        if not pivots:
            pivots = {WHEEL[int(mirror_idx)]}

    return list(pivots), chaos

async def generate_analysis_msg(uid):
    state = get_user_state(uid)
    pivots, chaos = sniper_v6_numpy_engine(uid)
    
    last_5 = list(state["hit_history"])[-5:]
    hit_rate = sum(last_5) / 5 if len(last_5) >= 5 else 1.0

    all_bets_set = set()
    for p in pivots:
        all_bets_set.update(get_neighbors(p, 1)) # Nokta Atışı: S1
    
    # 3. EL GELMEZ KURULI: Son sayıyı listeden ayıkla
    if len(state["history"]) >= 2 and state["history"][-1] in all_bets_set:
        all_bets_set.remove(state["history"][-1])

    all_bets = list(all_bets_set)

    # --- GUARDIAN SERT KONTROL ---
    if chaos > 22 or hit_rate < 0.2:
        state["last_unit"] = 0
        state["last_all_bets"] = []
        return (f"🛑 **LÜTFEN KALK!**\n"
                f"───────────────────\n"
                f"⚠️ Kaos: {chaos:.1f} | Verim: {hit_rate:.2f}\n"
                f"📢 Ritim koptu, kasa koruması aktif.")

    # Risk Yönetimi (%8 - %12 Dinamik)
    risk_rate = 0.08 if state["win_streak"] < 2 else 0.12
    risk_amount = state["bakiye"] * risk_rate
    state["last_unit"] = max(math.floor(risk_amount / len(all_bets)), 1)
    state["last_all_bets"] = all_bets

    return (
        f"🎯 **SNIPER v6 (NUMPY CORE)**\n"
        f"💰 **KASA:** {state['bakiye']} | 🪙 **UNIT:** {state['last_unit']}\n"
        f"───────────────────\n"
        f"🔥 **PİVOTLAR:** {pivots}\n"
        f"🧩 **KAOS:** {chaos:.1f} | **SAYI:** {len(all_bets)}\n"
        f"───────────────────\n"
        f"📈 **HEDEF:** %25 KAR\n"
        f"📢 'Anti-Repeat' ve 'Vektörel Hız' aktif."
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
    await update.message.reply_text("🦅 **SNIPER v6 (NUMPY)**\nMotor çalışıyor, 10 sayı girin...", parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True))

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
