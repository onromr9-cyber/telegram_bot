import os
from collections import deque
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}

# Avrupa Ruleti Çark Dizilimi
WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 
         5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
WHEEL_MAP = {num: i for i, num in enumerate(WHEEL)}

# --- SENİN ÖZEL ANALİZ LİSTEN (STRATEJİK REFERANS) ---
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
        user_states[uid] = {"bakiye": 0, "history": deque(maxlen=50), "last_bets": [], "loss_streak": 0, "waiting_for_balance": True}
    return user_states[uid]

def get_neighbors(n, s=2):
    idx = WHEEL_MAP[n]
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

def smart_engine(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    
    if len(hist) < 3:
        return [hist[-1] if hist else 0, 10, 20], "🌱 Isınma: Veri toplanıyor..."

    last_num = hist[-1]
    scores = {num: 0 for num in range(37)}

    # 1. KATMAN: SENİN ÖZEL LİSTEN (Yüksek Öncelik)
    suggested_by_user = USER_STRATEGY_MAP.get(last_num, [])
    for s_num in suggested_by_user:
        scores[s_num] += 70  # Liste puanı

    # 2. KATMAN: MATEMATİKSEL ANALİZ (+/- 5 Sapma ve İstatistik)
    for i, n in enumerate(reversed(hist[-15:])):
        weight = 90 / (1.1**i)
        idx = WHEEL_MAP[n]
        for d in [-5, -1, 0, 1, 5]:
            scores[WHEEL[(idx + d) % 37]] += weight

    # 3. KATMAN: ÜÇGEN AÇI VE HİBRİT SEÇİM
    targets = []
    sorted_sc = sorted(scores.items(), key=lambda x: -x[1])

    for cand_num, score in sorted_sc:
        if len(targets) >= 3: break
        # Üçgen Açı Kontrolü (Hedefler arası en az 8 index mesafe)
        if all(abs(WHEEL_MAP[cand_num] - WHEEL_MAP[t]) >= 8 for t in targets):
            targets.append(cand_num)

    # Mesaj
    ref_match = any(t in suggested_by_user for t in targets)
    msg = "🎯 UZMAN HİBRİT: Senin listen ve botun analizi tam uyumlu!" if ref_match else "📐 DİNAMİK ANALİZ: Akış senin listenden saptı, bot denge kuruyor."
    
    return targets[:3], msg

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = {"bakiye": 0, "history": deque(maxlen=50), "last_bets": [], "loss_streak": 0, "waiting_for_balance": True}
    await update.message.reply_text("🚀 Hibrit Uzman Sistemi Yayında!\n✅ Özel Listen Tanımlandı.\n✅ Üçgen Açı ve +/- 5 Sapma Aktif.\nBaşlangıç bakiyeni gir:")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    
    try:
        text = update.message.text
        if state.get("waiting_for_balance"):
            state["bakiye"] = int(text); state["waiting_for_balance"] = False
            await update.message.reply_text(f"✅ Bakiye kaydedildi: {state['bakiye']} TL."); return

        res = int(text)
        if state["last_bets"]:
            cost = len(state["last_bets"]) * 10
            state["bakiye"] -= cost
            if res in state["last_bets"]:
                state["bakiye"] += 360; state["loss_streak"] = 0
                msg = f"✅ KAZANDINIZ! (+{360-cost} TL)"
            else:
                state["loss_streak"] += 1
                msg = f"❌ KAYBETTİNİZ ({res})"
            await update.message.reply_text(msg)
        
        state["history"].append(res)
        targets, d_msg = smart_engine(uid)
        
        # 3 Odak ve her birine 2 komşu
        current_bets = set()
        for t in targets:
            current_bets.update(get_neighbors(t, 2))
        
        state["last_bets"] = list(current_bets)
        
        await update.message.reply_text(
            f"{d_msg}\n"
            f"💰 Bakiye: {state['bakiye']} TL\n"
            f"🎯 Odaklar: {targets}\n"
            f"🎲 Bahis: {len(state['last_bets'])} sayı"
        )
    except ValueError: pass

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
