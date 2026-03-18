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
    "history": deque(maxlen=30),
    "last_prediction": [],
    "bankroll": 0,
    "waiting_bankroll": True,
    "data_ready": False
})

# --- YARDIMCI FONKSİYONLAR ---
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
    main_bets = set(get_neighbors(num, 2))
    if mode == "OFFSET" and len(hist) > 1:
        main_bets.update(get_neighbors(hist[-2], 1))
    mirror = WHEEL[(WHEEL_MAP[num] + 18) % 37]
    extra = set(get_neighbors(mirror, 1))
    extra.add(num)
    final = sorted(list(main_bets | extra))[:9]
    state["last_prediction"] = final
    return final

# --- TELEGRAM HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    uid = update.effective_user.id
    user_states[uid] = {
        "history": deque(maxlen=30),
        "last_prediction": [],
        "bankroll": 0,
        "waiting_bankroll": True,
        "data_ready": False
    }
    await update.message.reply_text("🛡️ **𝐆 𝐔 𝐀 𝐑 𝐃 𝐈 𝐀 𝐍 v9.5 BAŞLADI**\nLütfen kasanızı girin (Örn: 10000):")

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    text = update.message.text.strip()
    state = user_states[uid]

    # --- GENEL GİRİŞ DENETİMİ (VALIDATION) ---
    if text not in ['🗑️ SIFIRLA', '↩️ GERİ AL']:
        if not text.isdigit():
            await update.message.reply_text("🚫 **HATA:** Sadece rakam giriniz! Harf veya sembol kullanamazsınız.")
            return
        
        val = int(text)
        # Kasa girişi değilse 36 kontrolü yap
        if not state["waiting_bankroll"] and (val < 0 or val > 36):
            await update.message.reply_text("🚫 **HATA:** Geçersiz sayı! Rulette sadece 0-36 arası rakamlar bulunur.")
            return

    # Kasa Girişi İşleme
    if state["waiting_bankroll"]:
        state["bankroll"] = int(text)
        state["waiting_bankroll"] = False
        await update.message.reply_text(f"💰 Kasa **{state['bankroll']}** birim olarak mühürlendi.\nŞimdi ilk 10 sayıyı girin (Veri toplama aşaması).",
                                       reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True))
        return

    if text == '🗑️ SIFIRLA':
        await start(update, context)
        return

    if text == '↩️ GERİ AL':
        if state["history"]:
            state["history"].pop()
            await update.message.reply_text("⬅️ Son sayı silindi.")
        return

    # Sayı İşleme
    num = int(text)
    
    # 1. Veri Toplama (İlk 10 Sayı)
    if len(state["history"]) < 10:
        state["history"].append(num)
        remaining = 10 - len(state["history"])
        if remaining > 0:
            await update.message.reply_text(f"📥 Veri Toplanıyor: {len(state['history'])}/10\nKalan: {remaining} sayı.")
        else:
            state["data_ready"] = True
            await update.message.reply_text("✅ Veri toplama bitti! Bot artık aktif tahmin üretecek.")
        return

    # 2. Lose Kontrolü
    if state["last_prediction"] and num not in state["last_prediction"]:
        current_sec = get_sector(num)
        prev_sec = get_sector(state["history"][-1])
        keyboard = [[InlineKeyboardButton(f"🌀 OFFSET ({prev_sec})", callback_data='mode_off')],
                    [InlineKeyboardButton(f"🎯 MOMENTUM ({current_sec})", callback_data='mode_mom')],
                    [InlineKeyboardButton("🛡️ İZLE", callback_data='mode_watch')]]
        await update.message.reply_text(f"⚠️ **LOSE!** Sayı: {num} ({current_sec})\nHangi stratejiyi uygulayalım Patron?",
                                       reply_markup=InlineKeyboardMarkup(keyboard))
        context.user_data['pending_num'] = num
        return

    # 3. Hit / Otomatik Tahmin
    state["history"].append(num)
    final = await generate_prediction(uid, num)
    await update.message.reply_text(f"✅ **ANALİZ**\n📍 SON: {num}\n🎯 **BAHİS:** `{', '.join(map(str, final))}`", parse_mode="Markdown")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    await query.answer()
    
    num = context.user_data.get('pending_num')
    state = user_states[uid]
    state["history"].append(num)
    
    mode = "OFFSET" if query.data == 'mode_off' else "MOMENTUM"
    final = await generate_prediction(uid, num, mode=mode)
    await query.edit_message_text(f"🕹️ **KARAR: {mode}**\n📍 SON: {num}\n🎯 **BAHİS:** `{', '.join(map(str, final))}`", parse_mode="Markdown")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_input))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.run_polling()
