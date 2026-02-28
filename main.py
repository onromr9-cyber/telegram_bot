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
            "bakiye": 0, 
            "history": deque(maxlen=40), 
            "last_bets": [], 
            "waiting_for_balance": True # Başlangıçta bakiye sorması için
        }
    return user_states[uid]

def get_neighbors(n, s=2): # Komşu sayısı 2 olarak güncellendi
    idx = WHEEL_MAP[n]
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

def smart_engine(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    
    # 3 Sayı hedefi
    target_count = 3
    scores = {num: 0 for num in range(37)}
    
    # Son verileri analiz et
    for i, n in enumerate(reversed(hist[-12:])):
        weight = 100 / (1.15**i)
        idx = WHEEL_MAP[n]
        for d in [-2, -1, 0, 1, 2]:
            scores[WHEEL[(idx + d) % 37]] += weight

    sorted_candidates = sorted(scores.items(), key=lambda x: -x[1])
    
    targets = []
    # Her zaman son geleni 1. hedef yap (Sıcak sayı koruması)
    if hist:
        targets.append(hist[-1])
        
    for cand in sorted_candidates:
        if len(targets) >= target_count: break
        if cand[0] not in targets:
            # Sayılar çarkta birbirine çok yakın olmasın (Dağılım)
            if all(abs(WHEEL_MAP[cand[0]] - WHEEL_MAP[t]) > 2 for t in targets):
                targets.append(cand[0])
    
    return targets

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    
    user_states[uid] = {
        "bakiye": 0, 
        "history": deque(maxlen=40), 
        "last_bets": [], 
        "waiting_for_balance": True
    }
    await update.message.reply_text("🎰 Hoş geldin! Lütfen oyuna başlayacağın toplam bakiyeyi gir (Örn: 2500):")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    
    try:
        text = update.message.text
        
        # Bakiye Giriş Kontrolü
        if state.get("waiting_for_balance"):
            state["bakiye"] = int(text)
            state["waiting_for_balance"] = False
            await update.message.reply_text(f"✅ Bakiye {state['bakiye']} TL olarak ayarlandı.\nŞimdi gelen ilk sayıyı girerek analizi başlatabilirsin.")
            return

        res = int(text)
        if not (0 <= res <= 36): raise ValueError
        
        # Kazanç/Kayıp Hesaplama
        if state["last_bets"]:
            cost = len(state["last_bets"]) * 10 # Her sayıya 10 birim bahis varsayımı
            state["bakiye"] -= cost
            if res in state["last_bets"]:
                state["bakiye"] += 360
                msg_res = f"✅ KAZANDIK! (+{360-cost} TL)"
            else:
                msg_res = f"❌ PAS ({res})"
            await update.message.reply_text(msg_res)
        
        state["history"].append(res)
        targets = smart_engine(uid)
        
        # 3 Sayı + 2'şer Komşu Ayarı
        current_bets = set()
        for t in targets:
            current_bets.update(get_neighbors(t, 2)) # 2 Komşu
        
        state["last_bets"] = list(current_bets)
        prob = (len(state["last_bets"]) / 37) * 100
        
        await update.message.reply_text(
            f"💰 Güncel Bakiye: {state['bakiye']} TL\n"
            f"📍 Hedef Sayılar: {targets}\n"
            f"🎲 Toplam Bahis: {len(state['last_bets'])} sayı\n"
            f"📊 Kapsama Alanı: %{prob:.1f}"
        )
        
    except ValueError:
        await update.message.reply_text("Lütfen geçerli bir sayı girin.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
