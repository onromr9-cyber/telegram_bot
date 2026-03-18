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
    "last_full_list": [],
    "fail_count": 0,
    "bankroll": 0,
    "waiting_bankroll": True
})

# --- ANALİZ MOTORU ---
def get_neighbors(num, n_range=2):
    idx = WHEEL_MAP[int(num)]
    return [WHEEL[(idx + i) % 37] for i in range(-n_range, n_range + 1)]

def get_mirror(num):
    return WHEEL[(WHEEL_MAP[num] + 18) % 37]

def get_sector(num):
    idx = WHEEL_MAP[num]
    if idx in [0, 32, 15, 19, 4, 21, 2, 25, 26]: return "ZERO/VOISINS"
    if idx in [33, 1, 20, 14, 31, 9, 22, 18]: return "ORPHELINS"
    return "TIER"

async def generate_pivot_prediction(uid, num, mode="MOMENTUM"):
    state = user_states[uid]
    hist = list(state["history"])
    
    pivot_main = num
    full_list = set(get_neighbors(pivot_main, 2))
    
    pivot_mirror = get_mirror(num)
    full_list.update(get_neighbors(pivot_mirror, 1))
    
    if mode == "OFFSET" and len(hist) > 1:
        pivot_extra = hist[-2]
    else:
        pivot_extra = WHEEL[(WHEEL_MAP[num] + 9) % 37]
        
    full_list.update(get_neighbors(pivot_extra, 1))
    state["last_full_list"] = list(full_list)
    
    msg = f"🎯 **𝐒İ𝐍𝐘𝐀𝐋 𝐀𝐍𝐀𝐋İ𝐙İ (v9.7)**\n📍 SON: {num}\n\n"
    msg += f"🔥 **ANA PİVOT:** `{pivot_main}` (±2 Komşu)\n"
    msg += f"💎 **EKSTRA 1:** `{pivot_mirror}` (±1 Komşu)\n"
    msg += f"💎 **EKSTRA 2:** `{pivot_extra}` (±1 Komşu)\n\n"
    msg += f"📢 Mod: {mode} | 🛡️ Güvenli"
    return msg

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    user_states[update.effective_user.id] = {"history": deque(maxlen=30), "last_full_list": [], "fail_count": 0, "bankroll": 0, "waiting_bankroll": True}
    await update.message.reply_text("🛡️ **𝐆 𝐔 𝐀 𝐑 𝐃 𝐈 𝐀 𝐍 v9.7**\nLütfen kasanızı girin:")

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    text = update.message.text.strip()
    state = user_states[uid]

    if not text.isdigit() and text not in ['🗑️ SIFIRLA', '↩️ GERİ AL']:
        await update.message.reply_text("🚫 Sadece rakam!")
        return

    if state["waiting_bankroll"]:
        state["bankroll"] = int(text)
        state["waiting_bankroll"] = False
        await update.message.reply_text(f"💰 Kasa: {state['bankroll']}\nİlk 10 sayıyı girin (Veri toplama).", reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True))
        return

    if text == '🗑️ SIFIRLA': await start(update, context); return
    num = int(text)
    
    # LOSE KONTROLÜ
    if state["last_full_list"] and num not in state["last_full_list"] and len(state["history"]) >= 10:
        state["fail_count"] += 1
        
        # 3. EL KAYIP KRİZİ
        if state["fail_count"] >= 3:
            current_sec = get_sector(num)
            prev_sec = get_sector(state["history"][-1])
            
            keyboard = [[InlineKeyboardButton("🌀 OFFSET'e Geç", callback_data='p_off')],
                        [InlineKeyboardButton("🎯 MOMENTUM'da Kal", callback_data='p_mom')]]
            
            await update.message.reply_text(
                f"🚨 **KRİTİK DURUM (3/3 LOSE)!**\n"
                f"Patron, masa ritmi çok bozdu. Son sayı {num} ({current_sec}).\n\n"
                f"🧠 **BENİM FİKRİM:** Şu an top {prev_sec} bölgesine dönmek istiyor olabilir, **OFFSET** denemek mantıklı.\n\n"
                f"Sen ne yapmak istersin?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            context.user_data['pending_num'] = num
            return
        else:
            # 3. el değilse sessizce kaydet ve yeni tahmin ver
            await update.message.reply_text(f"❌ Iska ({state['fail_count']}/3). Analiz güncelleniyor...")
    else:
        # HİT durumunda sayacı sıfırla
        if state["last_full_list"]:
            state["fail_count"] = 0

    state["history"].append(num)
    if len(state["history"]) < 10:
        await update.message.reply_text(f"📥 Veri: {len(state['history'])}/10")
    else:
        res = await generate_pivot_prediction(uid, num)
        await update.message.reply_text(res, parse_mode="Markdown")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    await query.answer()
    
    num = context.user_data.get('pending_num')
    state = user_states[uid]
    state["history"].append(num)
    state["fail_count"] = 0 # Karar verildiği için sıfırla
    
    mode = "OFFSET" if query.data == 'p_off' else "MOMENTUM"
    res = await generate_pivot_prediction(uid, num, mode=mode)
    await query.edit_message_text(f"🕹️ **KARAR UYGULANDI: {mode}**\n{res}", parse_mode="Markdown")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_input))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.run_polling()
