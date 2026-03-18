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
    "hit_streak": 0, # Üst üste kazanç sayısı
    "bankroll": 0,
    "waiting_bankroll": True,
    "watch_mode": False,
    "critical_state": False,
    "last_unit": 0
})

# --- ANALİZ FONKSİYONLARI ---
def get_neighbors(num, n_range=2):
    idx = WHEEL_MAP[int(num)]
    return [WHEEL[(idx + i) % 37] for i in range(-n_range, n_range + 1)]

def get_mirror(num):
    return WHEEL[(WHEEL_MAP[num] + 18) % 37]

# --- PROGRESSIVE RISK HESAPLAMA ---
def calculate_risk_unit(state):
    # Kazandıkça artan risk yüzdesi: %5 -> %8 -> %12 -> %15 (Maks %15)
    risk_percentages = [0.05, 0.08, 0.12, 0.15]
    idx = min(state["hit_streak"], len(risk_percentages) - 1)
    target_risk_sum = state["bankroll"] * risk_percentages[idx]
    
    # 11 sayı basacağımızı varsayarak (v9.6 mantığı), sayı başına düşen unit
    unit = round(target_risk_sum / 11)
    return max(unit, 1) # Minimum 1 unit

# --- MOTOR ---
async def generate_pivot_analysis(uid, num, mode="MOMENTUM"):
    state = user_states[uid]
    hist = list(state["history"])
    
    pivot_main = num
    full_list = set(get_neighbors(pivot_main, 2))
    pivot_mirror = get_mirror(num)
    full_list.update(get_neighbors(pivot_mirror, 1))
    pivot_extra = hist[-2] if mode == "OFFSET" and len(hist) > 1 else WHEEL[(WHEEL_MAP[num] + 9) % 37]
    full_list.update(get_neighbors(pivot_extra, 1))
    
    state["last_full_list"] = list(full_list)
    unit = calculate_risk_unit(state)
    state["last_unit"] = unit
    
    msg = f"🎯 **𝐀𝐍𝐀𝐋İ𝐙 v9.9 (𝐏𝐑𝐎𝐆𝐑𝐄𝐒𝐒İ𝐕𝐄)**\n📍 SON: {num}\n\n"
    msg += f"🔥 **ANA PİVOT:** `{pivot_main}` (±2)\n"
    msg += f"💎 **EKSTRA 1:** `{pivot_mirror}` (±1)\n"
    msg += f"💎 **EKSTRA 2:** `{pivot_extra}` (±1)\n\n"
    msg += f"📈 **BAHİS PLANI:**\n"
    msg += f"💰 Kasa: {state['bankroll']}\n"
    msg += f"🪙 Unit/Sayı: **{unit}**\n"
    msg += f"📉 Toplam Risk: {unit * len(full_list)}\n"
    msg += f"🔥 Seri: {state['hit_streak']} Hit"
    return msg

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    user_states[update.effective_user.id] = {
        "history": deque(maxlen=30), "last_full_list": [], "fail_count": 0, "hit_streak": 0,
        "bankroll": 0, "waiting_bankroll": True, "watch_mode": False, "critical_state": False, "last_unit": 0
    }
    await update.message.reply_text("🛡️ **𝐆 𝐔 𝐀 𝐑 𝐃 𝐈 𝐀 𝐍 v9.9 Yayında!**\nLütfen başlangıç kasanızı girin:")

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
        await update.message.reply_text(f"💰 Kasa {state['bankroll']} mühürlendi. 10 sayı sessiz mod aktif.")
        return

    if text == '🗑️ SIFIRLA': await start(update, context); return
    num = int(text)

    # İZLEME MODU
    if state["watch_mode"]:
        state["history"].append(num)
        if state["last_full_list"] and num in state["last_full_list"]:
            state["watch_mode"] = False
            state["fail_count"] = 0
            state["hit_streak"] = 0 # İzlemeden çıkınca güvenli riskle başla
            await update.message.reply_text(f"🟢 **RİTİM DÜZELDİ!**\nTop beklenen bölgeye ({num}) düştü. Şimdi girişi yapabilirsin!")
        return

    # LOSE / HIT / BANKROLL GÜNCELLEME
    if state["last_full_list"]:
        if num in state["last_full_list"]:
            profit = (state["last_unit"] * 36) - (state["last_unit"] * len(state["last_full_list"]))
            state["bankroll"] += profit
            state["hit_streak"] += 1
            state["fail_count"] = 0
            state["critical_state"] = False
        else:
            state["bankroll"] -= (state["last_unit"] * len(state["last_full_list"]))
            state["hit_streak"] = 0 # Seri bozulunca risk %5'e döner
            state["fail_count"] += 1

    # KRİTİK ANALİZ (2 EL LOSE)
    if state["fail_count"] == 2 and not state["critical_state"]:
        state["critical_state"] = True
        keyboard = [[InlineKeyboardButton("🚀 DEVAM ET", callback_data='c_cont')], [InlineKeyboardButton("⏸️ BEKLE", callback_data='c_wait')]]
        await update.message.reply_text(f"⚠️ **KRİTİK ANALİZ (2/2)!**\nKasa: {state['bankroll']}\nÖnerim: Ritim kayıyor, kararı sen ver.", reply_markup=InlineKeyboardMarkup(keyboard))
        context.user_data['pending_num'] = num
        return

    if state["fail_count"] >= 3:
        state["watch_mode"] = True
        await update.message.reply_text("🚨 **RİTİM BOZULDU!**\nİzleme moduna geçiyorum. GÜVENLİ sinyalini bekle.")
        return

    state["history"].append(num)
    if len(state["history"]) > 10:
        res = await generate_pivot_analysis(uid, num)
        await update.message.reply_text(res, parse_mode="Markdown")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    await query.answer()
    state = user_states[uid]
    num = context.user_data.get('pending_num')

    if query.data == 'c_cont':
        state["history"].append(num)
        res = await generate_pivot_analysis(uid, num)
        await query.edit_message_text(f"🕹️ **KARAR: DEVAM**\n{res}", parse_mode="Markdown")
    elif query.data == 'c_wait':
        await query.edit_message_text("⏸️ Beklemede. Bir sonraki sayıyı girin.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_input))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.run_polling()
