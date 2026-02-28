import os
import math
from collections import deque
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}

WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 
         5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
WHEEL_MAP = {num: i for i, num in enumerate(WHEEL)}

# Kullanıcı Strateji Haritası (USER_STRATEGY_MAP) buraya eklenecek...

user_states = {}

def get_user_state(uid):
    if uid not in user_states:
        user_states[uid] = {
            "bakiye": 0, "history": deque(maxlen=50), "snapshot": [],
            "last_main_bets": [], "last_extra_bets": [], "last_prob_bets": [],
            "last_unit": 0, "is_learning": True, "waiting_for_balance": False
        }
    return user_states[uid]

def get_neighbors(n, s=1):
    idx = WHEEL_MAP[n]
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

# Sniper Tahmin Motoru
def smart_engine_sniper(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    if not hist: return [0,32,15], [19,4], [21]
    last_num = hist[-1]
    
    scores = {num: 0 for num in range(37)}
    jump_avg = 0
    if len(hist) >= 3:
        dist1 = (WHEEL_MAP[hist[-1]] - WHEEL_MAP[hist[-2]] + 37) % 37
        dist2 = (WHEEL_MAP[hist[-2]] - WHEEL_MAP[hist[-3]] + 37) % 37
        jump_avg = int(((dist1 + dist2) / 2) * 1.05)

    for i, n in enumerate(reversed(hist[-15:])):
        decay = 100 / (1.15**i)
        p_idx = (WHEEL_MAP[n] + jump_avg) % 37
        for d in [-1, 0, 1]:
            num = WHEEL[(p_idx + d) % 37]
            scores[num] += decay
            # Strateji haritası kontrolü...

    sorted_sc = sorted(scores.items(), key=lambda x: -x[1])
    
    # Hedef Belirleme: Main(3), Extra(2), Olasılık(1)
    main_targets = []
    for cand_num, _ in sorted_sc:
        if len(main_targets) >= 3: break
        if all(abs(WHEEL_MAP[cand_num] - WHEEL_MAP[t]) >= 9 for t in main_targets):
            main_targets.append(cand_num)

    extra_targets = [last_num] # Birinci sayı her zaman son gelenin tekrarı
    for cand_num, _ in sorted_sc:
        if len(extra_targets) >= 2: break
        if cand_num not in main_targets and cand_num != last_num:
            extra_targets.append(cand_num)

    prob_targets = []
    for cand_num, _ in sorted_sc:
        if len(prob_targets) >= 1: break
        if cand_num not in main_targets and cand_num not in extra_targets:
            prob_targets.append(cand_num)
            
    return main_targets, extra_targets, prob_targets

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = get_user_state(uid)
    reply_markup = ReplyKeyboardMarkup([['↩️ GERİ AL', '/reset']], resize_keyboard=True)
    await update.message.reply_text("🎯 SNIPER V7.1 AKTİF\nIsınma: İlk 10 sayıyı girin.", reply_markup=reply_markup)

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    text = update.message.text.strip()

    if text == '↩️ GERİ AL':
        # Geri alma mantığı...
        return

    if not text.isdigit():
        await update.message.reply_text("⚠️ Lütfen sayı giriniz!")
        return
    
    val = int(text)

    # Kasa Girişi Aşaması (ÖZEL DÜZELTME)
    if state["waiting_for_balance"]:
        state["bakiye"] = val
        state["waiting_for_balance"] = False
        await update.message.reply_text(f"💰 Kasa: {val} TL olarak ayarlandı!"); return

    # Rakam Kontrolü (Sadece oyun sırasında aktif)
    if val < 0 or val > 36:
        await update.message.reply_text("⚠️ Hata: 0-36 arası bir sayı girin!")
        return

    # Snapshot ve Isınma Kontrolü...
    if state["is_learning"]:
        state["history"].append(val)
        if len(state["history"]) < 10:
            await update.message.reply_text(f"📥 Isınma: {len(state['history'])}/10"); return
        else:
            state["is_learning"] = False
            state["waiting_for_balance"] = True
            await update.message.reply_text("✅ Isınma Bitti! Şimdi kasanızı (Örn: 10000) girin:"); return

    # Bahis ve Tahmin Mantığı (V7 Sniper)...
