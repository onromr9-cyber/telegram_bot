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
    
    if len(hist) < 3:
        return [0, 10, 20], "🌱 Isınma: Veri bekleniyor..."

    last_num = hist[-1]
    last_idx = WHEEL_MAP[last_num]
    
    # 1. MADDE: +/- 5 SAPMA HESABI VE SKORLAMA
    scores = {num: 0 for num in range(37)}
    for i, n in enumerate(reversed(hist[-15:])):
        weight = 100 / (1.12**i)
        idx = WHEEL_MAP[n]
        # Sadece sayıya değil, senin istediğin +/- 5 sapma noktalarına da puan ver
        for d in [-5, -2, -1, 0, 1, 2, 5]: 
            bonus = 1.5 if abs(d) == 5 else 1.0 # 5 sapma ihtimaline özel ağırlık
            scores[WHEEL[(idx + d) % 37]] += weight * bonus

    # 2. MADDE: TEKRAR EDEN BÖLGE KONTROLÜ
    # Eğer son iki sayı çarkta birbirine yakınsa (10 index içi), bölge takibi yap
    is_repeating = False
    if len(hist) >= 2:
        dist = abs(WHEEL_MAP[hist[-1]] - WHEEL_MAP[hist[-2]])
        if dist <= 6 or dist >= 31: # Yakın bölge veya 0 üzerinden geçiş
            is_repeating = True

    # 3. MADDE: ÜÇGEN AÇI SEÇİMİ (Birbirinden uzak 3 nokta)
    targets = []
    sorted_sc = sorted(scores.items(), key=lambda x: -x[1])

    # İlk hedef en yüksek skorlu sayı olsun
    targets.append(sorted_sc[0][0])

    # Diğer iki hedefi, ilk hedefe göre "Üçgen" (yaklaşık 120 derece - 12 index) uzaklıkta seç
    first_idx = WHEEL_MAP[targets[0]]
    
    # Çarktaki 120 ve 240 derecelik (yaklaşık 12-13 birim) bölgeleri tara
    ideal_angles = [(first_idx + 12) % 37, (first_idx + 24) % 37]
    
    for angle_idx in ideal_angles:
        # Belirlenen açıdaki en yüksek skorlu sayıyı bul (5 birimlik tolerans ile)
        best_in_angle = None
        max_s = -1
        for i in range(-4, 5): # Açı etrafında 4 sayı sağa-sola bak
            check_num = WHEEL[(angle_idx + i) % 37]
            if scores[check_num] > max_s and check_num not in targets:
                max_s = scores[check_num]
                best_in_angle = check_num
        
        if best_in_angle is not None:
            targets.append(best_in_angle)

    # Eğer üçgen tamamlanmadıysa (nadir durum), zorla ata
    if len(targets) < 3:
        targets.append(WHEEL[(first_idx + 18) % 37]) # Zıt tarafı ekle

    msg = "📐 ÜÇGEN MOD: Çark 120° açıyla kuşatıldı."
    if is_repeating:
        msg += " 🔥 BÖLGE TEKRARI: Aynı sektör takibi aktif!"

    return targets[:3], msg

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = {"bakiye": 0, "history": deque(maxlen=50), "last_bets": [], "loss_streak": 0, "waiting_for_balance": True}
    await update.message.reply_text("📐 Geometrik Üçgen Modu Aktif.\n🚀 +/- 5 Sapma Analizi Yapılıyor.\n🔥 Bölge Tekrarı Takibi Açık.\nBakiyenizi girin:")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    
    try:
        text = update.message.text
        if state.get("waiting_for_balance"):
            state["bakiye"] = int(text); state["waiting_for_balance"] = False
            await update.message.reply_text(f"✅ Bakiye {state['bakiye']} TL. İlk sayıyı girin."); return

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
        
        # Her hedefin etrafını 2 komşu ile kapat (Kapsama alanı)
        current_bets = set()
        for t in targets:
            current_bets.update(get_neighbors(t, 2))
        
        state["last_bets"] = list(current_bets)
        
        await update.message.reply_text(
            f"{d_msg}\n"
            f"💰 Bakiye: {state['bakiye']} TL\n"
            f"🎯 Üçgen Odaklar: {targets}\n"
            f"🎲 Toplam: {len(state['last_bets'])} sayı"
        )
    except ValueError:
        await update.message.reply_text("0-36 arası bir sayı girin.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    app.run_polling()
