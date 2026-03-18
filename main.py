import os, collections
from collections import deque
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

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
    "last_unit": 0
})

# --- ANALİZ MOTORU ---
def get_neighbors(num, n_range=2):
    idx = WHEEL_MAP[int(num)]
    return [WHEEL[(idx + i) % 37] for i in range(-n_range, n_range + 1)]

def get_mirror(num):
    return WHEEL[(WHEEL_MAP[num] + 18) % 37]

def calculate_risk_unit(state):
    # %5 -> %8 -> %12 -> %15 Progressive Risk
    risk_percentages = [0.05, 0.08, 0.12, 0.15]
    idx = min(state["hit_streak"], len(risk_percentages) - 1)
    unit = round((state["bankroll"] * risk_percentages[idx]) / 11)
    return max(unit, 1)

def get_analysis_data(uid, num):
    state = user_states[uid]
    hist = list(state["history"])
    p_main = num
    p_mirror = get_mirror(num)
    p_extra = WHEEL[(WHEEL_MAP[num] + 9) % 37] # Kaçış Pivotu
    
    full_list = set(get_neighbors(p_main, 2))
    full_list.update(get_neighbors(p_mirror, 1))
    full_list.update(get_neighbors(p_extra, 1))
    
    return {"pivots": {"ANA": p_main, "MIRROR": p_mirror, "EXTRA": p_extra}, "full_list": list(full_list)}

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    user_states[update.effective_user.id] = {
        "history": deque(maxlen=30), "last_full_list": [], "fail_count": 0, "hit_streak": 0,
        "bankroll": 0, "waiting_bankroll": True, "watch_mode": False, "last_unit": 0
    }
    await update.message.reply_text("🛡️ **𝐆 𝐔 𝐀 𝐑 𝐃 𝐈 𝐀 𝐍 v10.3**\nKasa girişini yapın (10 sayı Sessiz Mod):")

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
        await update.message.reply_text(f"💰 Kasa `{state['bankroll']}` kaydedildi. 10 sayı girin.", parse_mode="Markdown")
        return

    if text == '🗑️ SIFIRLA': await start(update, context); return
    if text == '↩️ GERİ AL':
        if state["history"]: state["history"].pop(); await update.message.reply_text("⬅️ Geri alındı."); return

    num = int(text)

    # 1. İZLEME MODU (Watch Mode)
    if state["watch_mode"]:
        state["history"].append(num)
        if state["last_full_list"] and num in state["last_full_list"]:
            state["watch_mode"] = False
            state["fail_count"] = 0
            state["hit_streak"] = 0
            await update.message.reply_text(f"🟢 **RİTİM DÜZELDİ!**\nSon sayı `{num}` bölgeye girdi. Masa güvenli, ŞİMDİ GİR!", parse_mode="Markdown")
        # İzleme modunda başka hiçbir mesaj atmaz.
        return 

    # 2. LOSE / HIT HESAPLAMA
    if state["last_full_list"]:
        if num in state["last_full_list"]:
            profit = (state["last_unit"] * 36) - (state["last_unit"] * len(state["last_full_list"]))
            state["bankroll"] += profit
            state["hit_streak"] += 1
            state["fail_count"] = 0
            await update.message.reply_text(f"🟢 **𝐇İ𝐓! (+{profit})**\n💰 Kasa: `{state['bankroll']}` | Seri: `{state['hit_streak']}`", parse_mode="Markdown")
        else:
            loss = (state["last_unit"] * len(state["last_full_list"]))
            state["bankroll"] -= loss
            state["hit_streak"] = 0
            state["fail_count"] += 1
            await update.message.reply_text(f"🔴 **𝐋𝐎𝐒𝐄! (-{loss})**\n💰 Kasa: `{state['bankroll']}`", parse_mode="Markdown")

    # 3. RİTİM BOZULMA KONTROLÜ (3. LOSE)
    if state["fail_count"] >= 3:
        state["watch_mode"] = True
        await update.message.reply_text("🚨 **RİTİM BOZULDU!**\nOtomatik izleme moduna geçildi. Rakam girmeye devam et, 'GÜVENLİ' sinyalini bekle.")
        return

    # 4. ANALİZ ÜRETİMİ (10 Sayıdan Sonra)
    state["history"].append(num)
    if len(state["history"]) >= 10:
        data = get_analysis_data(uid, num)
        state["last_unit"] = calculate_risk_unit(state)
        state["last_full_list"] = data["full_list"]
        total_risk = state["last_unit"] * len(data["full_list"])
        
        res = f"🎯 **𝐀𝐍𝐀𝐋İ𝐙 PANELİ**\n━━━━━━━━━━━━━\n"
        res += f"📍 SON: `{num}`\n\n"
        res += f"🔥 **ANA PİVOT:** `{data['pivots']['ANA']}` (±2)\n"
        res += f"💎 **AYNA:** `{data['pivots']['MIRROR']}` (±1)\n"
        res += f"💎 **EXTRA:** `{data['pivots']['EXTRA']}` (±1)\n\n"
        res += f"📊 **BAHİS:**\n"
        res += f"🪙 Unit/Sayı: `{state['last_unit']}`\n"
        res += f"📉 Toplam Risk: `{total_risk}`"
        await update.message.reply_text(res, parse_mode="Markdown")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_input))
    app.run_polling()
