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
            "history": deque(maxlen=50), 
            "last_bets": [], 
            "loss_streak": 0, 
            "waiting_for_balance": True,
            "forbidden_regions": deque(maxlen=2), # Yasaklı bölgeler
            "last_region": None # Son tahmin bölgesi
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
        return [0, 10, 20], "🌱 Isınma Modu: Veri toplanıyor..."

    # Bölge Tanımları
    regions = {
        "V": [22, 18, 29, 7, 28, 12, 35, 3, 26, 0, 32, 15, 19, 4, 21, 2, 25],
        "T": [27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33],
        "O": [1, 20, 14, 31, 9, 17, 34, 6]
    }

    # 1. İNAT KIRMA: 2 el üst üste kaybedilen bölgeyi yasakla (KeyError düzeltildi)
    current_last_region = state.get("last_region")
    if loss_streak >= 2 and current_last_region:
        if current_last_region not in state["forbidden_regions"]:
            state["forbidden_regions"].append(current_last_region)

    # 2. ANALİZ: Son 7 sayıya göre +1 kaydırmalı ağırlık
    scores = {num: 0 for num in range(37)}
    for i, n in enumerate(reversed(hist[-7:])):
        weight = 100 / (1.2**i)
        idx = WHEEL_MAP[n]
        # Zamanlama hatasını önlemek için tahminleri +1 kaydır
        corrected_idx = (idx + 1) % 37 
        for d in [-2, -1, 0, 1, 2]:
            scores[WHEEL[(corrected_idx + d) % 37]] += weight

    # 3. YASAKLI BÖLGE FİLTRESİ
    sorted_sc = sorted(scores.items(), key=lambda x: -x[1])
    targets = []
    
    for cand_num, score in sorted_sc:
        if len(targets) >= 3: break
        
        # Sayının hangi bölgede olduğunu bul
        cand_region = next((k for k, v in regions.items() if cand_num in v), None)
        
        # Eğer bölge yasaklı değilse ekle
        if cand_region not in state["forbidden_regions"]:
            targets.append(cand_num)
            state["last_region"] = cand_region

    # Yedek Plan: Yasaklardan dolayı hedef kalmazsa çarkın zıt tarafına bak
    if not targets:
        last_idx = WHEEL_MAP[hist[-1]]
        targets = [WHEEL[(last_idx + 18) % 37], WHEEL[(last_idx + 10) % 37], 0]
        state["last_region"] = "ZIT"

    msg = f"🔄 Dinamik Analiz: {'Yasaklı bölge atlandı' if state['forbidden_regions'] else 'Akış takip ediliyor'}"
    return targets[:3], msg

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    # State'i tamamen sıfırla
    user_states[uid] = {
        "bakiye": 0, "history": deque(maxlen=50), "last_bets": [], 
        "loss_streak": 0, "waiting_for_balance": True, 
        "forbidden_regions": deque(maxlen=2), "last_region": None
    }
    await update.message.reply_text("⚖️ Sistem Başlatıldı.\nİnat kırma ve zamanlama düzeltme aktif.\nBaşlangıç bakiyenizi girin:")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    
    try:
        text = update.message.text
        
        # Bakiye Girişi
        if state.get("waiting_for_balance"):
            try:
                state["bakiye"] = int(text)
                state["waiting_for_balance"] = False
                await update.message.reply_text(f"✅ Bakiye {state['bakiye']} TL. İlk sayıyı girin.")
            except ValueError:
                await update.message.reply_text("Lütfen sadece rakam girin.")
            return

        res = int(text)
        if not (0 <= res <= 36): raise ValueError
        
        # Kazanç Değerlendirme
        if state["last_bets"]:
            cost = len(state["last_bets"]) * 10
            state["bakiye"] -= cost
            if res in state["last_bets"]:
                state["bakiye"] += 360
                state["loss_streak"] = 0
                state["forbidden_regions"].clear()
                msg = f"✅ KAZANDINIZ! (+{360-cost} TL)"
            else:
                state["loss_streak"] += 1
                msg = f"❌ KAYBETTİNİZ ({res})"
            await update.message.reply_text(msg)
        
        state["history"].append(res)
        targets, d_msg = smart_engine(uid)
        
        # Bahisleri Hesapla (3 Hedef + 2'şer Komşu)
        current_bets = set()
        for t in targets:
            current_bets.update(get_neighbors(t, 2))
        
        state["last_bets"] = list(current_bets)
        
        await update.message.reply_text(
            f"{d_msg}\n"
            f"🚫 Pas Geçilen Bölgeler: {list(state['forbidden_regions'])}\n"
            f"💰 Güncel Bakiye: {state['bakiye']} TL\n"
            f"🎯 Hedefler: {targets}\n"
            f"🎲 Toplam: {len(state['last_bets'])} sayı"
        )
        
    except ValueError:
        await update.message.reply_text("Lütfen 0-36 arası bir sayı girin.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
