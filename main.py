import os, collections
from collections import deque
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- AYARLAR ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}

WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
WHEEL_MAP = {num: i for i, num in enumerate(WHEEL)}

STRATEGY_MAP = {
    0: [6,4,16], 1: [27,23,21], 2: [14,17,8], 3: [5,6,18], 4: [26,7,11], 5: [25,22,35], 
    6: [30,24,15], 7: [21,14,28], 8: [25,32,20], 9: [4,36,22], 10: [26,19,31], 
    11: [29,4,33], 12: [8,21,36], 13: [31,28,16], 14: [2,13,26], 15: [18,17,30], 
    16: [4,20,11], 17: [35,2,11], 18: [3,5,36], 19: [33,26,8], 20: [21,30,10], 
    21: [23,27,28], 22: [27,32,5], 23: [14,15,11], 24: [6,29,30], 25: [28,36,24], 
    26: [10,31,13], 27: [22,1,0], 28: [25,13,16], 29: [4,11,31], 30: [19,3,29], 
    31: [18,13,0], 32: [23,35,27], 33: [19,22,11], 34: [7,15,33], 35: [17,36,5], 36: [12,14,16]
}

MAIN_KEYBOARD = [['🗑️ SIFIRLA', '↩️ GERİ AL']]
REPLY_MARKUP = ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)

user_states = collections.defaultdict(lambda: {
    "history": deque(maxlen=30), "last_full_list": [], "fail_count": 0, "hit_streak": 0,
    "bankroll": 0, "waiting_bankroll": True, "watch_mode": False, "last_unit": 0
})

def get_neighbors(num, n_range=2):
    idx = WHEEL_MAP[int(num)]
    return [WHEEL[(idx + i) % 37] for i in range(-n_range, n_range + 1)]

def get_mirror(num):
    return WHEEL[(WHEEL_MAP[num] + 18) % 37]

def calculate_risk_unit(state, list_len):
    risk_percentages = [0.05, 0.08, 0.12, 0.15]
    idx = min(state["hit_streak"], len(risk_percentages) - 1)
    unit = round((state["bankroll"] * risk_percentages[idx]) / list_len)
    return max(unit, 1)

def get_hybrid_analysis(num):
    # AYNA (s2)
    mirror_pivot = get_mirror(num)
    m_list = set(get_neighbors(mirror_pivot, 2))
    
    # STRATEJİ (s1)
    s_pivots = STRATEGY_MAP.get(num, [])
    s_list = set()
    for p in s_pivots:
        s_list.update(get_neighbors(p, 1))
    
    full_list = m_list.union(s_list)
    return {
        "mirror": mirror_pivot,
        "strategy": s_pivots,
        "full_list": list(full_list)
    }

async def format_analysis_msg(state, num, data, title="🎯 HİBRİT ANALİZ"):
    total_nums = len(data["full_list"])
    total_risk = state["last_unit"] * total_nums
    separator = "━" * 15
    
    res = f"{title}\n{separator}\n"
    res += f"📍 SON: {num}\n\n"
    res += f"🔄 AYNA: {data['mirror']} (s2)\n"
    res += f"🔥 STRATEJİ: {', '.join(map(str, data['strategy']))} (s1)\n\n"
    res += f"{separator}\n"
    res += f"🎲 TOPLAM: {total_nums} Rakam\n"
    res += f"📊 UNIT: {state['last_unit']} | RISK: {total_risk}\n"
    res += f"💰 KASA: {state['bankroll']}"
    return res

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    user_states[update.effective_user.id] = {
        "history": deque(maxlen=30), "last_full_list": [], "fail_count": 0, "hit_streak": 0,
        "bankroll": 0, "waiting_bankroll": True, "watch_mode": False, "last_unit": 0
    }
    await update.message.reply_text("GUARDIAN v11.2\nKasa girişini yapın:", reply_markup=REPLY_MARKUP)

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    text = update.message.text.strip()
    state = user_states[uid]

    if text == '/start' or text == '🗑️ SIFIRLA': await start(update, context); return
    if text == '↩️ GERİ AL':
        if state["history"]: state["history"].pop(); state["last_full_list"] = []; await update.message.reply_text("↩️ Geri alındı."); return

    if not text.isdigit():
        await update.message.reply_text("lütfen rakam girin")
        return
    
    val = int(text)
    if not state["waiting_bankroll"] and (val < 0 or val > 36):
        await update.message.reply_text("lütfen rakam girin")
        return

    if state["waiting_bankroll"]:
        state["bankroll"] = val
        state["waiting_bankroll"] = False
        await update.message.reply_text(f"💰 Kasa {state['bankroll']} aktif.")
        return

    num = val

    if state["watch_mode"]:
        state["history"].append(num)
        if state["last_full_list"] and num in state["last_full_list"]:
            state["watch_mode"] = False
            state["fail_count"] = 0
            data = get_hybrid_analysis(num)
            state["last_unit"] = calculate_risk_unit(state, len(data["full_list"]))
            state["last_full_list"] = data["full_list"]
            res = await format_analysis_msg(state, num, data, title="🟢 RİTİM DÜZELDİ!")
            await update.message.reply_text(res)
        return 

    if state["last_full_list"]:
        if num in state["last_full_list"]:
            profit = (state["last_unit"] * 36) - (state["last_unit"] * len(state["last_full_list"]))
            state["bankroll"] += profit
            state["hit_streak"] += 1
            state["fail_count"] = 0
            await update.message.reply_text(f"🟢 HIT! (+{profit})\nKasa: {state['bankroll']}")
        else:
            loss = (state["last_unit"] * len(state["last_full_list"]))
            state["bankroll"] -= loss
            state["hit_streak"] = 0
            state["fail_count"] += 1
            await update.message.reply_text(f"🔴 LOSE! (-{loss})\nKasa: {state['bankroll']}")

    if state["fail_count"] >= 3:
        state["watch_mode"] = True
        await update.message.reply_text("🚨 RİTİM BOZULDU!\nSessiz izleme başladı.")
        return

    state["history"].append(num)
    if len(state["history"]) >= 10:
        data = get_hybrid_analysis(num)
        state["last_unit"] = calculate_risk_unit(state, len(data["full_list"]))
        state["last_full_list"] = data["full_list"]
        res = await format_analysis_msg(state, num, data)
        await update.message.reply_text(res)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_input))
    app.run_polling()

