import os
import random
from collections import deque
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}

WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 
         5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]

WHEEL_MAP = {num: i for i, num in enumerate(WHEEL)}
user_states = {}

def get_user_state(uid):
    if uid not in user_states:
        user_states[uid] = {
            "bakiye": 0, "history": deque(maxlen=50), 
            "last_bets": [], "loss_streak": 0, 
            "waiting_for_balance": True,
            "drift_correction": 0 # Sapma düzeltme (Öğrenilen hata payı)
        }
    return user_states[uid]

def get_neighbors(n, s=2):
    idx = WHEEL_MAP[n]
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

def smart_engine(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    
    if len(hist) < 5:
        return [0, 10, 20], "🌱 Hazırlık: Yeterli veri toplanıyor..."

    # --- SÜREKLİ ÖĞRENME ANALİZİ ---
    last_num = hist[-1]
    last_idx = WHEEL_MAP[last_num]
    
    # 1. Hata Payı Öğrenimi (Error Margin Learning)
    # Eğer son tahminde yakına düştüysek sapmayı hesapla
    if state["last_bets"] and last_num not in state["last_bets"]:
        # En yakın tahminimize ne kadar uzaktı?
        min_dist = 37
        for bet in state["last_bets"]:
            dist = (last_idx - WHEEL_MAP[bet] + 37) % 37
            if dist > 18: dist -= 37
            if abs(dist) < abs(min_dist): min_dist = dist
        
        # Eğer hata payı 5 sayıdan azsa, kurpiyerin "atış sapmasını" öğren
        if abs(min_dist) <= 6:
            state["drift_correction"] = min_dist
    else:
        state["drift_correction"] = 0 # Tam isabet varsa sıfırla

    # 2. Yoğunluk ve Frekans Analizi
    scores = {num: 0 for num in range(37)}
    for i, n in enumerate(reversed(hist[-20:])): # Son 20 sayıya bak
        weight = 100 / (1.08**i)
        idx = WHEEL_MAP[n]
        # Puan dağıtırken öğrenilen sapmayı (drift) ekle
        corrected_idx = (idx + state["drift_correction"]) % 37
        for d in [-2, -1, 0, 1, 2]:
            scores[WHEEL[(int(corrected_idx) + d) % 37]] += weight

    sorted_sc = sorted(scores.items(), key=lambda x: -x[1])
    
    # 3. Dinamik Karar
    targets = []
    targets.append(sorted_sc[0][0]) # En güçlü sıcak sayı
    
    # Çarkın karşı tarafını kontrol et (Dengeleme)
    opposite_idx = (last_idx + 18) % 37
    targets.append(WHEEL[opposite_idx])
    
    # Üçüncü hedef: En çok puan alan 2. sayı
    targets.append(sorted_sc[1][0])

    learning_msg = f"🧠 ÖĞRENME: Sapma Düzeltme: {state['drift_correction']} | "
    if abs(state['drift_correction']) > 0:
        learning_msg += "Hedefler kaydırıldı."
    else:
        learning_msg += "Merkez odaklar seçildi."

    return targets[:3], learning_msg

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = {"bakiye": 0, "history": deque(maxlen=50), "last_bets": [], "loss_streak": 0, "waiting_for_balance": True, "drift_correction": 0}
    await update.message.reply_text("🤖 Sürekli Öğrenme Aktif.\nHer sayıda hata payımı hesaplayıp hedeflerimi güncelleyeceğim.\nBakiyenizi girin:")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    
    try:
        text = update.message.text
        if state.get("waiting_for_balance"):
            state["bakiye"] = int(text); state["waiting_for_balance"] = False
            await update.message.reply_text(f"✅ Bakiye: {state['bakiye']} TL. İlk sayıyı girin."); return

        res = int(text)
        if not (0 <= res <= 36): raise ValueError
        
        # Sonuç Değerlendirme
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
        
        # Bahisleri hazırla
        current_bets = set()
        for t in targets: current_bets.update(get_neighbors(t, 2))
        state["last_bets"] = list(current_bets)
        
        await update.message.reply_text(
            f"{d_msg}\n"
            f"💰 Bakiye: {state['bakiye']} TL\n"
            f"🎯 Odaklar: {targets}\n"
            f"🎲 Bahis: {len(state['last_bets'])} sayı"
        )
    except ValueError:
        await update.message.reply_text("0-36 arası bir sayı girin.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
