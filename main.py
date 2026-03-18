import os, math, collections
from collections import deque
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- AYARLAR ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}

WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
WHEEL_MAP = {num: i for i, num in enumerate(WHEEL)}
KEYBOARD = [['↩️ GERİ AL', '🗑️ SIFIRLA']]

# Kullanıcı Veri Deposu
user_data = collections.defaultdict(lambda: {
    "history": deque(maxlen=20),
    "last_prediction": []
})

# --- MATEMATİKSEL MOTORLAR ---

def get_neighbors(num, n_range=2):
    """Belirlenen aralıkta komşuları getirir."""
    idx = WHEEL_MAP[int(num)]
    return [WHEEL[(idx + i) % 37] for i in range(-n_range, n_range + 1)]

def get_mirror(num):
    """Tekerleğin tam karşısındaki sayıyı getirir."""
    return WHEEL[(WHEEL_MAP[num] + 18) % 37]

def calculate_chaos(history):
    """Masanın ritim bozukluğunu ölçer."""
    if len(history) < 2: return 0
    dists = [abs(WHEEL_MAP[history[i]] - WHEEL_MAP[history[i-1]]) for i in range(1, len(history))]
    return sum(dists) / len(dists)

# --- ANA STRATEJİ MOTORU ---

def analyze_v8_9(uid):
    state = user_data[uid]
    hist = list(state["history"])
    if not hist: return "⚠️ Veri girişi bekleniyor..."
    
    last = hist[-1]
    
    # 1. ANA BÖLGE (Main - 2 neighbors)
    main_bets = set(get_neighbors(last, 2))
    
    # 2. GECİKMELİ RİTİM (Senin Teorin - Offset Logic)
    # Top 1 el uzağa kaçsa bile bir önceki bölgeyi (n-2) %50 koru
    extra_bets = set()
    if len(hist) > 1:
        extra_bets.update(get_neighbors(hist[-2], 1))
    
    # 3. AYNA ANALİZİ (Mirroring)
    mirror_val = get_mirror(last)
    extra_bets.update(get_neighbors(mirror_val, 1))
    
    # 4. KAÇIŞ VE TEKRAR (Exit Logic)
    escape_num = WHEEL[(WHEEL_MAP[last] + 9) % 37] # Cross-Wheel Jump
    extra_bets.add(last) # Tekrar ihtimali için son sayıyı ekle
    
    # --- FİLTRELEME VE KASA KORUMA ---
    final_list = list(main_bets | extra_bets)
    if escape_num not in final_list: final_list.append(escape_num)
    
    # 9 Sayı Sınırı (Kasa dostu yaklaşım)
    final_list = sorted(list(set(final_list)))[:9]
    state["last_prediction"] = final_list
    
    # Kaos Faktörü Kontrolü
    chaos = calculate_chaos(hist)
    
    # Mesaj Çıktısı
    res = f"🛡️ **𝐆 𝐔 𝐀 𝐑 𝐃 𝐈 𝐀 𝐍 v8.9**\n"
    res += f"📍 SON: {last} | 🌀 KAOS: {chaos:.1f}\n"
    res += f"───────────────────\n"
    res += f"🎯 **BAHİS:** `{', '.join(map(str, final_list))}`\n"
    res += f"💎 **KAÇIŞ:** {escape_num}\n"
    
    # Guardian Uyarı Sistemi
    if chaos > 22 or (len(hist) > 5 and chaos < 5):
        res += "\n🚨 **LÜTFEN KALK! (Ritim Bozuldu)**"
    
    return res

# --- HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    user_id = update.effective_user.id
    user_data[user_id]["history"].clear()
    await update.message.reply_text(
        "🛡️ **𝐆 𝐔 𝐀 𝐑 𝐃 𝐈 𝐀 𝐍 v8.9 Aktif!**\nSayı girerek analizi başlatın Patron.",
        reply_markup=ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True)
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    text = update.message.text

    if text == '🗑️ SIFIRLA':
        user_data[uid]["history"].clear()
        await update.message.reply_text("🔄 Tüm veriler temizlendi.")
        return
    
    if text == '↩️ GERİ AL':
        if user_data[uid]["history"]:
            user_data[uid]["history"].pop()
            await update.message.reply_text("⬅️ Son sayı silindi.")
        return

    if text.isdigit() and 0 <= int(text) <= 36:
        user_data[uid]["history"].append(int(text))
        response = analyze_v8_9(uid)
        await update.message.reply_text(response, parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ Hatalı giriş! 0-36 arası bir sayı girin.")

# --- RUN ---
if __name__ == '__main__':
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("🚀 Guardian v8.9 Yayında!")
    application.run_polling()
