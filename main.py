import os
from collections import deque
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}

# Avrupa Ruleti Çark Dizilimi
WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 
         5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
WHEEL_MAP = {num: i for i, num in enumerate(WHEEL)}

USER_STRATEGY_MAP = {
    0: [6,4,16], 1: [27,23,21], 2: [14,17,8], 3: [5,6,18], 4: [26,7,11], 5: [25,15,35], 
    6: [22,24,12], 7: [21,14,28], 8: [12,32,20], 9: [4,36,22], 10: [26,19,31], 
    11: [29,4,33], 12: [23,32,36], 13: [31,28,16], 14: [25,13,26], 15: [35,6,30], 
    16: [17,20,11], 17: [3,2,1], 18: [19,35,10], 19: [33,29,8], 20: [21,30,10], 
    21: [23,27,28], 22: [27,32,5], 23: [14,15,3], 24: [6,29,30], 25: [28,36,24], 
    26: [10,31,13], 27: [18,20,32], 28: [2,13,16], 29: [4,11,31], 30: [16,3,29], 
    31: [18,13,1], 32: [23,35,9], 33: [19,22,11], 34: [7,31,6], 35: [17,36,5], 36: [12,14,4]
}

user_states = {}

def get_user_state(uid):
    if uid not in user_states:
        user_states[uid] = {
            "bakiye": 0, "history": deque(maxlen=50), 
            "last_main_bets": [], "last_extra_bets": [],
            "loss_streak": 0, "waiting_for_balance": True
        }
    return user_states[uid]

def get_neighbors(n, s=2):
    idx = WHEEL_MAP[n]
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

def smart_engine(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    last_num = hist[-1] if hist else 0 

    if len(hist) < 3:
        # Başlangıçta gelen sayı ve tekrarlanan sayı kuralı
        return [0, 10, 20], [last_num, 5, 15, last_num], "🌱 Analiz Hazırlanıyor..."

    scores = {num: 0 for num in range(37)}
    jump_avg = 0
    if len(hist) >= 3:
        dist1 = (WHEEL_MAP[hist[-1]] - WHEEL_MAP[hist[-2]] + 37) % 37
        dist2 = (WHEEL_MAP[hist[-2]] - WHEEL_MAP[hist[-3]] + 37) % 37
        jump_avg = int(((dist1 + dist2) / 2) * 1.2)

    suggested_by_user = USER_STRATEGY_MAP.get(last_num, [])
    for i, n in enumerate(reversed(hist[-15:])):
        weight = 100 / (1.1**i)
        predicted_idx = (WHEEL_MAP[n] + jump_avg) % 37
        for d in [-5, -2, -1, 0, 1, 2, 5]:
            num = WHEEL[(predicted_idx + d) % 37]
            scores[num] += weight
            if num in suggested_by_user: scores[num] *= 1.6

    sorted_sc = sorted(scores.items(), key=lambda x: -x[1])
    main_targets = []
    for cand_num, score in sorted_sc:
        if len(main_targets) >= 3: break
        if all(abs(WHEEL_MAP[cand_num] - WHEEL_MAP[t]) >= 9 for t in main_targets):
            main_targets.append(cand_num)

    # EKSTRA KURALI: İlk sayı son gelen, ortadakiler yeni, sonuncu tekrar.
    extra_targets = [last_num]
    for cand_num, score in sorted_sc:
        if len(extra_targets) >= 3: break 
        if cand_num not in main_targets and cand_num != last_num:
            if all(abs(WHEEL_MAP[cand_num] - WHEEL_MAP[t]) >= 5 for t in (main_targets + extra_targets)):
                extra_targets.append(cand_num)
    
    extra_targets.append(last_num) # 4. sayı tekrar eden sayı

    return main_targets, extra_targets, "🚀 Analiz Aktif!"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = get_user_state(uid)
    reply_markup = ReplyKeyboardMarkup([['/reset']], resize_keyboard=True)
    await update.message.reply_text("⚖️ SİSTEM BAŞLATILDI\nLütfen başlangıç bakiyenizi girin:", reply_markup=reply_markup)

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in user_states: del user_states[uid]
    await start(update, context)

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    text = update.message.text.strip()

    if not text.isdigit():
        await update.message.reply_text("⚠️ Hata: Lütfen sadece sayısal değer girin!")
        return

    val = int(text)

    if state["waiting_for_balance"]:
        state["bakiye"] = val
        state["waiting_for_balance"] = False
        await update.message.reply_text(f"💰 Kasa: {val} TL\nŞimdi çarkta çıkan ilk sayıyı girin:")
        return

    if val < 0 or val > 36:
        await update.message.reply_text("⚠️ Hata: 0-36 arası bir sayı girin!")
        return

    # Kazanç/Kayıp Hesaplama
    total_bets = list(set(state["last_main_bets"] + state["last_extra_bets"]))
    if total_bets:
        cost = len(total_bets) * 10
        state["bakiye"] -= cost
        if val in state["last_main_bets"]:
            state["bakiye"] += 360
            await update.message.reply_text(f"✅ ANA TAHMİN BİLDİ! (+{360-cost} TL)")
        elif val in state["last_extra_bets"]:
            state["bakiye"] += 360
            await update.message.reply_text(f"🔥 EKSTRA TAHMİN BİLDİ! (+{360-cost} TL)")
        else:
            await update.message.reply_text(f"❌ KAYIP ({val})")

    state["history"].append(val)
    main_t, extra_t, d_msg = smart_engine(uid)

    # Bahisleri Komşularıyla Listeleme
    m_bets = set()
    for t in main_t: m_bets.update(get_neighbors(t, 2))
    state["last_main_bets"] = list(m_bets)

    e_bets = set()
    for t in list(set(extra_t)): e_bets.update(get_neighbors(t, 1))
    state["last_extra_bets"] = list(e_bets)

    await update.message.reply_text(
        f"{d_msg}\n💰 Güncel Kasa: {state['bakiye']} TL\n\n"
        f"🎯 MAIN (2 Komşu): {main_t}\n"
        f"⚡ EXTRA (1 Komşu): {extra_t}\n\n"
        f"🎲 Oynanan Toplam Sayı: {len(set(state['last_main_bets'] + state['last_extra_bets']))}"
    )

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
