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

def sniper_v6_engine(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    
    # 1. MOMENTUM ANALİZİ (Vektörel Kayma)
    j1, j2 = 0, 0
    if len(hist) >= 3:
        j1 = (WHEEL_MAP[hist[-1]] - WHEEL_MAP[hist[-2]] + 37) % 37
        j2 = (WHEEL_MAP[hist[-2]] - WHEEL_MAP[hist[-3]] + 37) % 37

    chaos = abs(j1 - j2)
    
    # 2. PİVOT HESAPLAMA
    p1 = (WHEEL_MAP[hist[-1]] + j1) % 37      # Devam ivmesi
    p2 = (WHEEL_MAP[hist[-1]] + (37 - j1)) % 37 # Geri sekme (Counter)
    mirror_idx = (WHEEL_MAP[hist[-1]] + 18) % 37 # Tam karşı bölge
    
    pivots = {WHEEL[p1], WHEEL[p2], WHEEL[mirror_idx]}
    
    # 3. ANTI-REPEAT (DOYUM) FİLTRESİ
    # Eğer son iki sayı aynıysa veya çok yakınsa (S1), o bölgeyi listeden çıkar.
    if len(hist) >= 2 and abs(WHEEL_MAP[hist[-1]] - WHEEL_MAP[hist[-2]]) <= 1:
        dead_zone = get_neighbors(hist[-1], 2) # Doymuş bölge (Geniş filtre)
        pivots = {p for p in pivots if p not in dead_zone}
        # Eğer tüm pivotlar silindiyse, sadece tam zıt tarafa (Ayna) odaklan
        if not pivots:
            pivots = {WHEEL[mirror_idx]}

    return list(pivots), chaos

async def generate_analysis_msg(uid):
    state = get_user_state(uid)
    pivots, chaos = sniper_v6_engine(uid)
    
    # Hit Oranı (Son 5 El)
    last_5 = list(state["hit_history"])[-5:]
    hit_rate = sum(last_5) / 5 if len(last_5) >= 5 else 1.0

    # Dar Komşuluk (Nokta Atışı için S1)
    all_bets_set = set()
    for p in pivots:
        all_bets_set.update(get_neighbors(p, 1))
    
    # 3. El gelmez mantığı: Son sayıyı listeden kesin olarak çıkarıyoruz (Doyum)
    if len(list(state["history"])) >= 2:
        if state["history"][-1] in all_bets_set:
            all_bets_set.remove(state["history"][-1])

    all_bets = list(all_bets_set)

    # --- SERT GUARDIAN FİLTRESİ ---
    if chaos > 22 or hit_rate < 0.2:
        state["last_unit"] = 0
        state["last_all_bets"] = []
        return (f"🛑 **LÜTFEN KALK! (SNIPER KAPALI)**\n"
                f"───────────────────\n"
                f"⚠️ Kaos: {chaos} | Başarı: {hit_rate}\n"
                f"📢 Masa analizi yapılamıyor. Matematik bozuldu.")

    # Risk Yönetimi (%8 Kasa Kullanımı)
    risk_rate = 0.08 if state["win_streak"] < 2 else 0.12
    risk_miktari = state["bakiye"] * risk_rate
    state["last_unit"] = max(math.floor(risk_miktari / len(all_bets)), 1)
    state["last_all_bets"] = all_bets

    return (
        f"🎯 **SNIPER v6 (ANTI-REPEAT)**\n"
        f"💰 **KASA:** {state['bakiye']} | 🪙 **UNIT:** {state['last_unit']}\n"
        f"───────────────────\n"
        f"🔥 **HEDEF NOKTALAR:** {pivots}\n"
        f"🧩 **KAOS:** {chaos} | **SAYI:** {len(all_bets)}\n"
        f"───────────────────\n"
        f"📈 **NET KAR HEDEFİ:** %20+\n"
        f"📢 'Aynı sayı 3. kez gelmez' kuralı aktif."
    )

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    text = update.message.text.strip().upper()

    if text == '🗑️ SIFIRLA':
        if uid in user_states: del user_states[uid]
        await update.message.reply_text("🛡️ SİSTEM BAŞTAN KURULDU."); return
    
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
    await update.message.reply_text("🦅 **SNIPER v6: ANTI-REPEAT**\n10 sayı girerek motoru ateşleyin...", parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True))

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
