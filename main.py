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

# --- SENİN ÖZEL STRATEJİK REFERANS LİSTEN ---
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
            "bakiye": 0, 
            "history": deque(maxlen=50), 
            "last_bets": [], 
            "loss_streak": 0, 
            "waiting_for_balance": True,
            "predicted_history": deque(maxlen=2) # Gecikme kontrolü için son 2 tahmin
        }
    return user_states[uid]

def get_neighbors(n, s=2):
    idx = WHEEL_MAP[n]
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

def smart_engine(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    loss_streak = state.get("loss_streak", 0)
    
    if len(hist) < 5:
        return [hist[-1] if hist else 0, 10, 20], "🌱 Isınma Modu (%d/5 Veri)..." % len(hist)

    last_num = hist[-1]
    scores = {num: 0 for num in range(37)}

    # 1. GECİKMELİ TAKİP (Son 2 turda çıkmayan sıcak rakamlar)
    for past_targets in state["predicted_history"]:
        for p_num in past_targets:
            scores[p_num] += 45 # Gecikme telafi puanı

    # 2. MOMENTUM & İLERİ PROJEKSİYON (İvme hesabı)
    jump_avg = 0
    if len(hist) >= 3:
        dist1 = (WHEEL_MAP[hist[-1]] - WHEEL_MAP[hist[-2]] + 37) % 37
        dist2 = (WHEEL_MAP[hist[-2]] - WHEEL_MAP[hist[-3]] + 37) % 37
        # Gecikmeyi önlemek için ivmeyi %20 ileri kaydırıyoruz
        jump_avg = int(((dist1 + dist2) / 2) * 1.2)

    # 3. HİBRİT PUANLAMA (Senin Listen + Matematik + İvme)
    suggested_by_user = USER_STRATEGY_MAP.get(last_num, [])
    
    for i, n in enumerate(reversed(hist[-15:])):
        weight = 100 / (1.1**i)
        idx = WHEEL_MAP[n]
        # İleriyi hedefleyen index
        predicted_idx = (idx + jump_avg) % 37
        
        for d in [-5, -2, -1, 0, 1, 2, 5]:
            num = WHEEL[(predicted_idx + d) % 37]
            scores[num] += weight
            if num in suggested_by_user:
                scores[num] *= 1.6 # Senin listene yüksek güven

    # 4. DİNAMİK HEDEF SEÇİMİ (Farklılık Garantisi & Üçgen Açı)
    targets = []
    sorted_sc = sorted(scores.items(), key=lambda x: -x[1])
    
    # Bir önceki elin tıpatıp aynısını vermemek için kontrol
    last_predictions = state["predicted_history"][-1] if state["predicted_history"] else []

    for cand_num, score in sorted_sc:
        if len(targets) >= 3: break
        
        # Çeşitlilik kuralı: En az 1-2 rakam yeni olsun
        if cand_num in last_predictions and len(targets) < 1:
            continue

        # Geometrik mesafe (Üçgen açı)
        min_dist = 6 if loss_streak >= 2 else 9 
        if all(abs(WHEEL_MAP[cand_num] - WHEEL_MAP[t]) >= min_dist for t in targets):
            targets.append(cand_num)

    # Yeni tahminleri gecikme takibi için hafızaya al
    state["predicted_history"].append(targets)

    # Mesaj kurgusu
    if loss_streak >= 2:
        msg = "🎯 NOKTA ATIŞI: Gecikme payı ivmeye eklendi!"
    elif any(t in suggested_by_user for t in targets):
        msg = "⏳ GECİKME TELAFİSİ: Senin referansın ve pusu listesi eşleşti!"
    else:
        msg = "📐 GEOMETRİK ANALİZ: Çark ritmi kontrol ediliyor."

    return targets[:3], msg

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = {
        "bakiye": 0, "history": deque(maxlen=50), "last_bets": [], 
        "loss_streak": 0, "waiting_for_balance": True,
        "predicted_history": deque(maxlen=2)
    }
    await update.message.reply_text("⚖️ ZAMAN KAYMALI HİBRİT SİSTEM AKTİF!\n- Gecikme Telafisi (Son 2 Tur)\n- İleri Projeksiyon (+%20 İvme)\n- Özel Listen & Üçgen Açı\n\nBakiyenizi girin:")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    
    try:
        text = update.message.text
        if state.get("waiting_for_balance"):
            state["bakiye"] = int(text); state["waiting_for_balance"] = False
            await update.message.reply_text(f"💰 Kasa: {state['bakiye']} TL. İlk sayıyı girin."); return

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
        
        current_bets = set()
        for t in targets:
            current_bets.update(get_neighbors(t, 2))
        
        state["last_bets"] = list(current_bets)
        
        await update.message.reply_text(
            f"{d_msg}\n"
            f"💰 Güncel Kasa: {state['bakiye']} TL\n"
            f"🎯 Tahmin Odakları: {targets}\n"
            f"🎲 Toplam Bahis: {len(state['last_bets'])} sayı"
        )
    except ValueError: pass

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
