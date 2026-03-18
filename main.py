import os, collections
from collections import deque
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- AYARLAR ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}

WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
WHEEL_MAP = {num: i for i, num in enumerate(WHEEL)}
MAIN_KEYBOARD = [['🗑️ SIFIRLA', '↩️ GERİ AL']]

# Kullanıcı Veri Deposu
user_states = collections.defaultdict(lambda: {
    "history": deque(maxlen=20),
    "last_prediction": [],
})

# --- ANALİZ FONKSİYONLARI ---
def get_neighbors(num, n_range=2):
    idx = WHEEL_MAP[int(num)]
    return [WHEEL[(idx + i) % 37] for i in range(-n_range, n_range + 1)]

def get_sector(num):
    idx = WHEEL_MAP[num]
    if idx in [0, 32, 15, 19, 4, 21, 2, 25, 26]: return "ZERO/VOISINS"
    if idx in [33, 1, 20, 14, 31, 9, 22, 18]: return "ORPHELINS"
    return "TIER"

async def generate_prediction(uid, num, mode="MOMENTUM"):
    state = user_states[uid]
    hist = list(state["history"])
    
    # Ana bölge tahmini
    main_bets = set(get_neighbors(num, 2))
    
    # Seçilen moda göre ekleme
    if mode == "OFFSET" and len(hist) > 1:
        main_bets.update(get_neighbors(hist[-2], 1)) # n-2 (Gecikmeli) koruması
        
    mirror = WHEEL[(WHEEL_MAP[num] + 18) % 37]
    extra = set(get_neighbors(mirror, 1))
    extra.add(num) # Tekrar rakamı her zaman olsun
    
    final = sorted(list(main_bets | extra))[:9]
    state["last_prediction"] = final
    
    msg = f"✅ **ANALİZ TAMAMLANDI**\n📍 SON: {num}\n🎯 **BAHİS:** `{', '.join(map(str, final))}`"
    return msg

# --- TELEGRAM HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    user_states[update.effective_user.id]["history"].clear()
    await update.message.reply_text("🛡️ **𝐆 𝐔 𝐀 𝐑 𝐃 𝐈 𝐀 𝐍 v9.3**\nSayı girildiğinde otomatik tahmin yapılır. Lose yaşanırsa kontrol size geçer.", 
                                   reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True))

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    text = update.message.text

    if text == '🗑️ SIFIRLA':
        user_states[uid]["history"].clear()
        user_states[uid]["last_prediction"] = []
        await update.message.reply_text("🔄 Veriler temizlendi.")
        return

    if text == '↩️ GERİ AL':
        if user_states[uid]["history"]:
            user_states[uid]["history"].pop()
            await update.message.reply_text("⬅️ Son sayı silindi.")
        return

    if text.isdigit() and 0 <= int(text) <= 36:
        num = int(text)
        state = user_states[uid]
        
        # LOSE KONTROLÜ
        if state["last_prediction"] and num not in state["last_prediction"]:
            current_sec = get_sector(num)
            prev_sec = get_sector(state["history"][-1]) if state["history"] else "N/A"
            
            keyboard = [
                [InlineKeyboardButton(f"🌀 GECİKMELİ RİTİM ({prev_sec} Dön)", callback_data='mode_off')],
                [InlineKeyboardButton(f"🎯 MOMENTUM ({current_sec} Takip)", callback_data='mode_mom')],
                [InlineKeyboardButton("🛡️ SAKİNLEŞ (İzle)", callback_data='mode_watch')]
            ]
            
            await update.message.reply_text(
                f"⚠️ **LOSE!** Sayı: {num} ({current_sec})\n"
                f"Tahmin dışı kaldı. Hangi stratejiyle toparlayalım Patron?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            context.user_data['pending_num'] = num
            return

        # HİT YA DA İLK GİRİŞ
        state["history"].append(num)
        res_text = await generate_prediction(uid, num)
        await update.message.reply_text(res_text, parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ 0-36 arası bir rakam girin.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    await query.answer()
    
    num = context.user_data.get('pending_num')
    if num is None: return

    state = user_states[uid]
    state["history"].append(num)
    
    mode = "OFFSET" if query.data == 'mode_off' else "MOMENTUM"
    if query.data == 'mode_watch':
        await query.edit_message_text(f"🛡️ **İZLEME MODU:** {num} kaydedildi. Bahis almayın.")
        return

    res_text = await generate_prediction(uid, num, mode=mode)
    await query.edit_message_text(f"🕹️ **KARARIN UYGULANDI:**\n{res_text}", parse_mode="Markdown")

# --- ÇALIŞTIRICI (BURASI HATALIYDI, DÜZELTİLDİ) ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    # Buradaki handle_input ismi yukarıdaki fonksiyonla eşleşti:
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_input))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("🚀 Guardian v9.3 Hatasız Başlatılıyor...")
    app.run_polling()
