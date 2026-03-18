import os, math, collections
from collections import deque
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- AYARLAR ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}

WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
WHEEL_MAP = {num: i for i, num in enumerate(WHEEL)}
MAIN_KEYBOARD = [['↩️ GERİ AL', '🗑️ SIFIRLA']]

# Kullanıcı Veri Deposu
user_states = collections.defaultdict(lambda: {
    "history": deque(maxlen=20),
    "temp_num": None
})

# --- ANALİZ FONKSİYONLARI ---

def get_neighbors(num, n_range=2):
    idx = WHEEL_MAP[int(num)]
    return [WHEEL[(idx + i) % 37] for i in range(-n_range, n_range + 1)]

def get_mirror(num):
    return WHEEL[(WHEEL_MAP[num] + 18) % 37]

def calculate_chaos(history):
    if len(history) < 2: return 0
    dists = [abs(WHEEL_MAP[history[i]] - WHEEL_MAP[history[i-1]]) for i in range(1, len(history))]
    return sum(dists) / len(dists)

# --- TELEGRAM HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    uid = update.effective_user.id
    user_states[uid]["history"].clear()
    await update.message.reply_text(
        "🛡️ **𝐆 𝐔 𝐀 𝐑 𝐃 𝐈 𝐀 𝐍 v9.0 Aktif!**\nPatron hoş geldin. İlk sayıyı girerek motoru başlat.",
        reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
    )

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    text = update.message.text

    if text == '🗑️ SIFIRLA':
        user_states[uid]["history"].clear()
        await update.message.reply_text("🔄 Tüm veriler sıfırlandı.")
        return
    
    if text == '↩️ GERİ AL':
        if user_states[uid]["history"]:
            user_states[uid]["history"].pop()
            await update.message.reply_text("⬅️ Son sayı silindi.")
        return

    if text.isdigit() and 0 <= int(text) <= 36:
        num = int(text)
        user_states[uid]["temp_num"] = num
        
        # Strateji Seçenekleri (Butonlar)
        keyboard = [
            [InlineKeyboardButton("🌀 GECİKMELİ RİTİM (Offset)", callback_data='mode_off')],
            [InlineKeyboardButton("🎯 MOMENTUM (Sıcak Takip)", callback_data='mode_mom')],
            [InlineKeyboardButton("🛡️ İZLE VE BEKLE", callback_data='mode_watch')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"📍 **SON SAYI: {num}**\nAnaliz hazır. Hangi stratejiyi uygulayalım?",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text("⚠️ Lütfen 0-36 arası geçerli bir sayı girin.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    await query.answer()
    
    state = user_states[uid]
    num = state["temp_num"]
    state["history"].append(num)
    hist = list(state["history"])
    
    if query.data == 'mode_watch':
        await query.edit_message_text(f"🛡️ **İZLEME MODU:** {num} kaydedildi. Bahis almayın.")
        return

    # --- STRATEJİ HESAPLAMA ---
    main_bets = set(get_neighbors(num, 2))
    extra_bets = set()
    
    if query.data == 'mode_off' and len(hist) > 1:
        # Gecikmeli Ritim: n-2 bölgesini koru
        extra_bets.update(get_neighbors(hist[-2], 1))
    
    # Ayna ve Kaçış Her Zaman Aktif (Sigorta)
    mirror_val = get_mirror(num)
    extra_bets.update(get_neighbors(mirror_val, 1))
    extra_bets.add(num) # Tekrar rakamı
    
    escape_num = WHEEL[(WHEEL_MAP[num] + 9) % 37]
    
    # Filtreleme (Maks 9 Sayı)
    final_list = sorted(list(set(list(main_bets) + list(extra_bets))))[:9]
    if escape_num not in final_list: final_list.append(escape_num)
    
    chaos = calculate_chaos(hist)
    
    # Mesaj Oluşturma
    res = f"✅ **STRATEJİ: {'OFFSET' if query.data == 'mode_off' else 'MOMENTUM'}**\n"
    res += f"📍 SON: {num} | 🌀 KAOS: {chaos:.1f}\n"
    res += f"───────────────────\n"
    res += f"🎯 **BAHİS:** `{', '.join(map(str, final_list))}`\n"
    res += f"💎 **KAÇIŞ:** {escape_num}\n"
    
    if chaos > 22:
        res += "\n🚨 **LÜTFEN KALK! (Dengesiz Ritim)**"
    
    await query.edit_message_text(res, parse_mode="Markdown")

# --- ANA ÇALIŞTIRICI ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("🚀 Guardian v9.0 INTERACTIVE Yayında!")
    app.run_polling()
