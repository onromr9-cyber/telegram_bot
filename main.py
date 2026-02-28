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
            "last_bets": [], "loss_streak": 0, "waiting_for_balance": True
        }
    return user_states[uid]

def get_neighbors(n, s=2):
    idx = WHEEL_MAP[n]
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

def smart_engine(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    loss_streak = state.get("loss_streak", 0)
    
    if len(hist) < 3:
        return [0, 10, 20], "🌱 Analiz başlatılıyor..."

    last_num = hist[-1]
    last_idx = WHEEL_MAP[last_num]
    
    # --- SENİN ÖNERİN: ÇAPRAZ SORGULAMA MANTIĞI ---
    # Çarkın tam karşısındaki index (180 derece)
    opposite_idx = (last_idx + 18) % 37
    opposite_num = WHEEL[opposite_idx]
    
    targets = []
    
    if loss_streak >= 1:
        # KAYIP VARSA: Çapraz (Aynalama) Modu Aktif
        # 1. Hedef: Son gelenin tam karşısı
        targets.append(opposite_num)
        
        # 2. Hedef: Karşı tarafın 3 yanındaki komşusu (Çapraz Kayma)
        targets.append(WHEEL[(opposite_idx + 3) % 37])
        
        # 3. Hedef: Karşı tarafın -3 yanındaki komşusu
        targets.append(WHEEL[(opposite_idx - 3) % 37])
        
        learning_msg = f"🔄 ÇAPRAZ MOD: {last_num} sayısının tam karşısı ({opposite_num}) hedeflendi."
    else:
        # KAZANÇ VARSA VEYA İLK ELDEYSE: Sıcak Takip
        scores = {num: 0 for num in range(37)}
        for i, n in enumerate(reversed(hist[-10:])):
            weight = 100 / (1.1**i)
            idx = WHEEL_MAP[n]
            for d in [-2, -1, 0, 1, 2]:
                scores[WHEEL[(idx + d) % 37]] += weight
        
        sorted_sc = sorted(scores.items(), key=lambda x: -x[1])
        targets = [sorted_sc[0][0], last_num, sorted_sc[1][0]]
        learning_msg = "📊 NORMAL MOD: Sıcak bölge ve akış takibi yapılıyor."

    return targets[:3], learning_msg

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = {"bakiye": 0, "history": deque(maxlen=50), "last_bets": [], "loss_streak": 0, "waiting_for_balance": True}
    await update.message.reply_text("⚖️ Çapraz Sorgu (Mirroring) Sistemi Yüklendi.\nKayıp yaşandığında çarkın tam zıt tarafına odaklanır.\nBakiyenizi girin:")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    
    try:
        text = update.message.text
        if state.get("waiting_for_balance"):
            state["bakiye"] = int(text); state["waiting_for_balance"] = False
            await update.message.reply_text(f"✅ Bakiye {state['bakiye']} TL. Başlayalım."); return

        res = int(text)
        if not (0 <= res <= 36): raise ValueError
        
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
