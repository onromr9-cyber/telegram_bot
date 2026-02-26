import os
import random
from collections import Counter, deque
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- AYARLAR VE ADMINLER ---
# Railway'de Variables kısmına BOT_TOKEN eklemeyi unutma!
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}

# Avrupa Ruleti Çark Dizilimi (Hataya yer bırakmamak için dinamik index)
WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 
         5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]

# Çok kullanıcılı veri deposu
user_states = {}

def get_user_state(uid):
    if uid not in user_states:
        user_states[uid] = {
            "bakiye": 1000,
            "history": deque(maxlen=50),
            "last_bets": set(),
            "targets": []
        }
    return user_states[uid]

def is_admin(uid):
    return uid in ADMIN_IDS

def get_neighbors(n, s=3):
    """Verilen sayının çark üzerindeki sağ ve sol komşularını getirir."""
    try:
        idx = WHEEL.index(n)
        return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]
    except ValueError:
        return []

def generate_main_guess(uid):
    """
    Agresif Hareketli Motor:
    Sadece son 7 sayıya odaklanır ve her tur tahminleri değiştirir.
    """
    state = get_user_state(uid)
    hist = list(state["history"])
    
    if len(hist) < 3: 
        return random.sample(WHEEL, 2)
    
    # Sadece son 7 sayıya bakarak '1' sayısı gibi eski verilere takılmayı önler
    recent_hist = hist[-7:] 
    scores = {num: 0 for num in range(37)}
    
    for i, h in enumerate(recent_hist):
        # Yeni sayılara (i) daha yüksek ağırlık vererek trendi takip eder
        weight = i + 1 
        idx = WHEEL.index(h)
        # Gelen sayının etrafındaki bölgeye puan dağıt
        for delta in [-1, 0, 1]:
            n = WHEEL[(idx + delta) % 37]
            scores[n] += (10 * weight)

    # En yüksek puanlı ilk 6 adayı belirle
    sorted_scores = sorted(scores.items(), key=lambda x: -x[1])
    top_6 = [num for num, score in sorted_scores[:6]]
    
    # En iyi 6 arasından rastgele 2 tanesini seçerek 'donma' sorununu çözer
    return random.sample(top_6, 2)

# --- TELEGRAM HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("❌ Yetkiniz yok.")
        return
    
    # Kullanıcı verisini sıfırla
    user_states[uid] = {
        "bakiye": 1000, 
        "history": deque(maxlen=50), 
        "last_bets": set(), 
        "targets": []
    }
    await update.message.reply_text("🎲 Bot Hazır!\nBakiyen: 1000 TL\nLütfen bir sayı girerek analizi başlat.")

async def handle_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid): return
    
    state = get_user_state(uid)
    text = update.message.text

    if not text.isdigit():
        await update.message.reply_text("Lütfen sadece 0-36 arası bir sayı giriniz.")
        return

    res = int(text)
    if not (0 <= res <= 36):
        await update.message.reply_text("Geçersiz sayı! 0-36 arası girin.")
        return

    # 1. Önceki Tahmin Sonucunu Değerlendir
    if state["last_bets"]:
        cost = len(state["last_bets"]) * 10
        state["bakiye"] -= cost
        if res in state["last_bets"]:
            win_amount = 360
            state["bakiye"] += win_amount
            await update.message.reply_text(f"✅ KAZANDIM! (+{win_amount - cost} TL)")
        else:
            await update.message.reply_text(f"❌ KAYBETTİM! (-{cost} TL)")

    # 2. Geçmişi Güncelle ve Yeni Tahmin Üret
    state["history"].append(res)
    state["targets"] = generate_main_guess(uid)
    
    # Risk Adaptif Mod: Bakiye düşükse alanı daraltır
    k_sayisi = 3 if state["bakiye"] > 300 else 2
    
    new_bets = set()
    for t in state["targets"]:
        new_bets.update(get_neighbors(t, k_sayisi))
    state["last_bets"] = list(new_bets)

    # 3. Bilgilendirme ve Sade Arayüz
    oran = (len(state["last_bets"]) / 37) * 100
    mod = "NORMAL" if state["bakiye"] > 300 else "RİSKLİ"
    
    msg = (f"💰 Bakiye: {state['bakiye']} TL\n"
           f"📊 Mod: {mod}\n"
           f"🎯 Hedefler: {state['targets']}\n"
           f"🎲 İhtimal: %{oran:.1f}")
    
    await update.message.reply_text(msg)

# --- ANA ÇALIŞTIRICI ---
if __name__ == '__main__':
    # Botu başlat
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Komutları ekle
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_game))
    
    print("Bot Railway/GitHub üzerinde çalışmaya hazır...")
    app.run_polling()
