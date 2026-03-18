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

user_states = collections.defaultdict(lambda: {
    "history": deque(maxlen=30),
    "last_full_list": [],
    "fail_count": 0,
    "hit_streak": 0,
    "bankroll": 0,
    "waiting_bankroll": True,
    "watch_mode": False,
    "critical_state": False,
    "last_unit": 0,
    "last_pivots": {}
})

# --- ANALİZ MOTORU ---
def get_neighbors(num, n_range=2):
    idx = WHEEL_MAP[int(num)]
    return [WHEEL[(idx + i) % 37] for i in range(-n_range, n_range + 1)]

def get_mirror(num):
    return WHEEL[(WHEEL_MAP[num] + 18) % 37]

def calculate_risk_unit(state):
    risk_percentages = [0.05, 0.08, 0.12, 0.15]
    idx = min(state["hit_streak"], len(risk_percentages) - 1)
    # 11 sayı üzerinden unit hesabı
    unit = round((state["bankroll"] * risk_percentages[idx]) / 11)
    return max(unit, 1)

def get_analysis_data(uid, num, mode="MOMENTUM"):
    state = user_states[uid]
    hist = list(state["history"])
    p_main = num
    p_mirror = get_mirror(num)
    p_extra = hist[-2] if mode == "OFFSET" and len(hist) > 1 else WHEEL[(WHEEL_MAP[num] + 9) % 37]
    
    full_list = set(get_neighbors(p_main, 2)) # 5 sayı
    full_list.update(get_neighbors(p_mirror, 1)) # 3 sayı
    full_list.update(get_neighbors(p_extra, 1)) # 3 sayı
    
    return {"pivots": {"ANA": p_main, "MIRROR": p_mirror, "EXTRA": p_extra}, "full_list": list(full_list)}

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    user_states[update.effective_user.id] = {
        "history": deque(maxlen=30), "last_full_list": [], "fail_count": 0, "hit_streak": 0,
        "bankroll": 0, "waiting_bankroll": True, "watch_mode": False, "critical_state": False, "last_unit": 0, "last_pivots": {}
    }
    await update.message.reply_text("🛡️ **𝐆 𝐔 𝐀 𝐑 𝐃 𝐈 𝐀 𝐍 v10.1**\nKasa girişini yapın:")

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
        await update.message.reply_text(f"💰 Kasa {state['bankroll']} kaydedildi. 10 sayı girişi bekleniyor...")
        return

    if text == '🗑️ SIFIRLA': await start(update, context); return
    num = int(text)

    # İZLEME MODU
    if state["watch_mode"]:
        state["history"].append(num)
        if state["last_full_list"] and num in state["last_full_list"]:
            state["watch_mode"] = False
            state["fail_count"] = 0
            await update.message.reply_text(f"🟢 **RİTİM YAKALANDI!**\nSon sayı {num} bölgeye girdi. Masa güvenli, ŞİMDİ GİR!")
        else:
            await update.message.reply_text(f"👀 İzleniyor: {num}... Beklemede kal.")
        return

    # LOSE / HIT / VISUAL PANEL
    if state["last_full_list"]:
        if num in state["last_full_list"]:
            profit = (state["last_unit"] * 36) - (state["last_unit"] * len(state["last_full_list"]))
            state["bankroll"] += profit
            state["hit_streak"] += 1
            state["fail_count"] = 0
            state["critical_state"] = False
            await update.message.reply_text(f"🟢 **𝐇İ𝐓!**\n━━━━━━━━━━━━━\n➕ Kazanç: `{profit}`\n💰 Güncel Kasa: `{state['bankroll']}`\n🔥 Seri: `{state['hit_streak']}`")
        else:
            loss = (state["last_unit"] * len(state["last_full_list"]))
            state["bankroll"] -= loss
            state["hit_streak"] = 0
            state["fail_count"] += 1
            await update.message.reply_text(f"🔴 **𝐋𝐎𝐒𝐄!**\n━━━━━━━━━━━━━\n➖ Kayıp: `{loss}`\n💰 Güncel Kasa: `{state['bankroll']}`\n📉 Seri Sıfırlandı.")

    # KRİTİK ANALİZ (2 EL LOSE)
    if state["fail_count"] == 2 and not state["critical_state"]:
        state["critical_state"] = True
        data = get_analysis_data(uid, num)
        state["last_pivots"] = data["pivots"]
        state["last_full_list"] = data["full_list"]
        
        keyboard = [[InlineKeyboardButton("🚀 DEVAM ET", callback_data='c_cont')],
                    [InlineKeyboardButton("⏸️ BEKLE", callback_data='c_wait')]]
        
        msg = f"⚠️ **KRİTİK ANALİZ (2/2)**\n━━━━━━━━━━━━━\n"
        msg += f"🧠 **ÖNERİLEN RAKAMLAR:**\n"
        msg += f"📍 ANA: `{data['pivots']['ANA']}` (±2)\n"
        msg += f"📍 AYNA: `{data['pivots']['MIRROR']}` (±1)\n"
        msg += f"📍 EXTRA: `{data['pivots']['EXTRA']}` (±1)\n\n"
        msg += f"Masa dengesi bozuluyor. Kararın nedir?"
        
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        context.user_data['pending_num'] = num
        return

    if state["fail_count"] >= 3:
        state["watch_mode"] = True
        await update.message.reply_text("🚨 **RİTİM BOZULDU!**\nİzleme moduna geçildi. 'GÜVENLİ' sinyalini bekle.")
        return

    # VERİ İŞLEME VE ANALİZ (10. Sayıdan Sonra Başlar)
    state["history"].append(num)
    if len(state["history"]) >= 10:
        data = get_analysis_data(uid, num)
        state["last_unit"] = calculate_risk_unit(state)
        state["last_full_list"] = data["full_list"]
        total_risk = state["last_unit"] * len(data["full_list"])
        
        res = f"🎯 **𝐀𝐍𝐀𝐋İ𝐙 PANELİ**\n━━━━━━━━━━━━━\n"
        res += f"📍 SON: `{num}`\n\n"
        res += f"🔥 **ANA PİVOT:** `{data['pivots']['ANA']}`\n"
        res += f"   └─ *Komşu: ±2 (Toplam 5)*\n"
        res += f"💎 **AYNA:** `{data['pivots']['MIRROR']}`\n"
        res += f"   └─ *Komşu: ±1 (Toplam 3)*\n"
        res += f"💎 **EXTRA:** `{data['pivots']['EXTRA']}`\n"
        res += f"   └─ *Komşu: ±1 (Toplam 3)*\n\n"
        res += f"📊 **BAHİS DETAYI:**\n"
        res += f"🪙 Sayı Başı Unit: `{state['last_unit']}`\n"
        res += f"📉 Toplam Risk: `{total_risk}`\n"
        res += f"💰 Kasa: `{state['bankroll']}`"
        await update.message.reply_text(res, parse_mode="Markdown")
    else:
        await update.message.reply_text(f"📥 Veri Toplanıyor: {len(state['history'])}/10")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    await query.answer()
    state = user_states[uid]
    num = context.user_data.get('pending_num')

    if query.data == 'c_cont':
        state["history"].append(num)
        state["last_unit"] = calculate_risk_unit(state)
        total_risk = state["last_unit"] * 11
        res = f"🚀 **DEVAM EDİLİYOR**\n━━━━━━━━━━━━━\n"
        res += f"📍 PİVOTLAR: `{state['last_pivots']['ANA']}`, `{state['last_pivots']['MIRROR']}`, `{state['last_pivots']['EXTRA']}`\n"
        res += f"📊 Basılacak Unit: `{state['last_unit']}`\n"
        res += f"📉 Toplam Risk: `{total_risk}`"
        await query.edit_message_text(res, parse_mode="Markdown")
    elif query.data == 'c_wait':
        state["hit_streak"] = 0
        await query.edit_message_text("⏸️ **PAS GEÇİLDİ.** Yeni sayıyı bekliyorum.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_input))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.run_polling()
