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
            "waiting_for_balance": True
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
        return [0, 10, 20], "🌱 Analiz için veri toplanıyor..."

    # --- AGRESİF MOD (3+ KAYIP DURUMUNDA) ---
    if loss_streak >= 3:
        # Bölge Tanımları
        regions = {
            "Voisins (Sıfır Bölgesi)": [22, 18, 29, 7, 28, 12, 35, 3, 26, 0, 32, 15, 19, 4, 21, 2, 25],
            "Tiers (Seri 5/8)": [27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33],
            "Orphelins (Yetimler)": [1, 20, 14, 31, 9, 17, 34, 6]
        }
        
        # Son 5 sayının hangi bölgelere düştüğünü kontrol et
        hits = {k: 0 for k in regions.keys()}
        for n in hist[-5:]:
            for r_name, r_nums in regions.items():
                if n in r_nums: hits[r_name] += 1
        
        # En az gelen (kaçan) bölgeyi bul
        cold_region_name = min(hits, key=hits.get)
        cold_nums = regions[cold_region_name]
        
        # Agresif Seçim: Bu bölgenin içinden çark dizilimine göre yayılmış 3 nokta seç
        # Bölgeyi temsil eden merkez ve uç noktalar
        targets = [cold_nums[0], cold_nums[len(cold_nums)//2], cold_nums[-1]]
        
        msg = f"🔥 AGRESİF MOD: {cold_region_name} bölgesine pusu kuruldu!"
        return targets, msg

    # --- NORMAL ÖĞRENME MODU (3 KAYIPTAN AZSA) ---
    scores = {num: 0 for num in range(37)}
    for i, n in enumerate(reversed(hist[-20:])):
        weight = 100 / (1.1**i)
        idx = WHEEL_MAP[n]
        for d in [-2, -1, 0, 1, 2]:
            scores[WHEEL[(idx + d) % 37]] += weight

    sorted_sc = sorted(scores.items(), key=lambda x: -x[1])
    # En güçlü odak, son gelenin zıttı ve 2. güçlü odak
    targets = [sorted_sc[0][0], WHEEL[(WHEEL_MAP[hist[-1]] + 18) % 37], sorted_sc[1][0]]
    
    return targets[:3], "📊 Normal Mod: İstatistiksel takip yapılıyor."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = {"bakiye": 0, "history": deque(maxlen=50), "last_bets": [], "loss_streak": 0, "waiting_for_balance": True}
    await update.message.reply_text("⚖️ Sistem Hazır.\n3 kayıptan sonra Agresif Sektör Moduna geçer.\nBakiyenizi girin:")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    
    try:
        text = update.message.text
        if state.get("waiting_for_balance"):
            state["bakiye"] = int(text); state["waiting_for_balance"] = False
            await update.message.reply_text(f"✅ Bakiye: {state['bakiye']} TL. Başlayalım."); return

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
        
        # Bahis Hazırlığı
        current_bets = set()
        for t in targets: current_bets.update(get_neighbors(t, 2))
        state["last_bets"] = list(current_bets)
        
        await update.message.reply_text(
            f"{d_msg}\n"
            f"💰 Bakiye: {state['bakiye']} TL\n"
            f"🎯 Odaklar: {targets}\n"
            f"🎲 Bahis: {len(state['last_bets'])} sayı | Seri Kayıp: {state['loss_streak']}"
        )
    except ValueError:
        await update.message.reply_text("0-36 arası bir sayı girin.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
