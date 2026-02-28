import os
import random
from collections import deque
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}

# Avrupa Ruleti Çark Dizilimi
WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 
         5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]

WHEEL_MAP = {num: i for i, num in enumerate(WHEEL)}
user_states = {}

def get_user_state(uid):
    if uid not in user_states:
        user_states[uid] = {
            "bakiye": 0, 
            "history": deque(maxlen=40), 
            "last_bets": [], 
            "loss_streak": 0,
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
    
    if len(hist) < 3: return [0, 10, 20] # Başlangıç için güvenli bölgeler

    # --- STRATEJİ GÜNCELLEMESİ ---
    if loss_streak < 5:
        # NORMAL MOD: Sıcak bölgeleri ve son geleni takip et
        scores = {num: 0 for num in range(37)}
        for i, n in enumerate(reversed(hist[-15:])):
            weight = 100 / (1.1**i)
            idx = WHEEL_MAP[n]
            for d in [-2, -1, 0, 1, 2]:
                scores[WHEEL[(idx + d) % 37]] += weight
        
        sorted_candidates = sorted(scores.items(), key=lambda x: -x[1])
        targets = [sorted_candidates[0][0], hist[-1], sorted_candidates[1][0]]
    else:
        # 5+ KAYIP MODU: Sektör Analizi (Topun kaçtığı 120 derecelik dilimi bul)
        last_indices = [WHEEL_MAP[n] for n in hist[-6:]]
        sectors = [0, 0, 0] # 0-11, 12-23, 24-36 indexleri arası
        for idx in last_indices:
            if 0 <= idx <= 12: sectors[0] += 1
            elif 13 <= idx <= 24: sectors[1] += 1
            else: sectors[2] += 1
        
        cold_sector_idx = sectors.index(min(sectors))
        # O sektörün içinden 3 stratejik nokta seç (Maliyet artırmadan vuruş yerini değiştir)
        if cold_sector_idx == 0: targets = [32, 21, 17]
        elif cold_sector_idx == 1: targets = [13, 8, 24]
        else: targets = [9, 7, 3]

    # Benzersiz hedefleri döndür
    final_targets = []
    for t in targets:
        if t not in final_targets: final_targets.append(t)
    return final_targets[:3]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = {"bakiye": 0, "history": deque(maxlen=40), "last_bets": [], "loss_streak": 0, "waiting_for_balance": True}
    await update.message.reply_text("🎰 Hoş geldiniz! Lütfen başlangıç bakiyenizi girin:")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    
    try:
        text = update.message.text
        if state.get("waiting_for_balance"):
            state["bakiye"] = int(text)
            state["waiting_for_balance"] = False
            await update.message.reply_text(f"✅ Bakiye {state['bakiye']} TL olarak kaydedildi. İlk sayıyı girerek başlayabilirsiniz.")
            return

        res = int(text)
        if not (0 <= res <= 36): raise ValueError
        
        # Sonuç Değerlendirme
        if state["last_bets"]:
            cost = len(state["last_bets"]) * 10
            state["bakiye"] -= cost
            if res in state["last_bets"]:
                state["bakiye"] += 360
                state["loss_streak"] = 0
                msg = f"✅ KAZANDINIZ! (+{360-cost} TL)"
            else:
                state["loss_streak"] += 1
                msg = f"❌ KAYBETTİNİZ ({res})"
            await update.message.reply_text(msg)
        
        state["history"].append(res)
        targets = smart_engine(uid)
        
        # 3 Hedef + 2 Komşu (Sabit Strateji)
        current_bets = set()
        for t in targets:
            current_bets.update(get_neighbors(t, 2))
        
        state["last_bets"] = list(current_bets)
        prob = (len(state["last_bets"]) / 37) * 100
        
        # Kullanıcı Bilgilendirme
        mod_msg = "⚠️ Seri Kayıp Koruması Aktif (Sektör Modu)" if state["loss_streak"] >= 5 else "📊 Normal Takip Modu"
        
        await update.message.reply_text(
            f"{mod_msg}\n"
            f"💰 Güncel Bakiye: {state['bakiye']} TL\n"
            f"🎯 Hedefler: {targets}\n"
            f"🎲 Bahis: {len(state['last_bets'])} sayı / %{prob:.1f}"
        )
        
    except ValueError:
        await update.message.reply_text("Lütfen 0-36 arası bir sayı girin.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
