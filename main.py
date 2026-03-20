import os, collections
from collections import deque
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- AYARLAR ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {5813833511, 1278793650}

WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
WHEEL_MAP = {num: i for i, num in enumerate(WHEEL)}

# ROULETTE ZONES
ZONES = {
    "ZERO": [12, 35, 3, 26, 0, 32, 15],
    "VOISINS": [22, 18, 29, 7, 28, 12, 35, 3, 26, 0, 32, 15, 19, 4, 21, 2, 25],
    "TIERS": [27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33],
    "ORPHELINS": [1, 20, 14, 31, 9, 17, 34, 6]
}

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
    "bankroll": 0, "initial_bankroll": 0, "waiting_bankroll": True, "watch_mode": False, "current_unit": 0
})

def get_neighbors(num, n_range=1):
    idx = WHEEL_MAP[int(num)]
    return [WHEEL[(idx + i) % 37] for i in range(-n_range, n_range + 1)]

def shift_if_exists(current_list, num):
    temp_num = num
    while temp_num in current_list:
        idx = WHEEL_MAP[temp_num]
        temp_num = WHEEL[(idx + 1) % 37]
    return temp_num

def detect_hot_zone(history):
    if len(history) < 6: return None
    last_6 = list(history)[-6:]
    counts = {"ZERO": 0, "VOISINS": 0, "TIERS": 0, "ORPHELINS": 0}
    for n in last_6:
        for zone, nums in ZONES.items():
            if n in nums: counts[zone] += 1
    
    # Eğer bir bölge 6 elde 3 veya daha fazla geldiyse SICAK'tır
    for zone, count in counts.items():
        if count >= 3: return zone
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = {
        "history": deque(maxlen=30), "last_full_list": [], "fail_count": 0, "hit_streak": 0,
        "bankroll": 0, "initial_bankroll": 0, "waiting_bankroll": True, "watch_mode": False, "current_unit": 0
    }
    await update.message.reply_text("𝐆 𝐔 𝐀 𝐑 𝐃 𝐈 𝐀 𝐍 v14.0 (Heatmap) 🛡️\nKasa girişi yapın:", reply_markup=REPLY_MARKUP)

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    text = update.message.text.strip()
    state = user_states[uid]

    if text in ['/start', '🗑️ SIFIRLA']: await start(update, context); return
    if text == '↩️ GERİ AL':
        if state["history"]: state["history"].pop(); state["last_full_list"] = []; await update.message.reply_text("↩️ Geri alındı."); return

    if not text.isdigit(): return
    val = int(text)
    if state["waiting_bankroll"]:
        state["bankroll"] = val
        state["waiting_bankroll"] = False
        await update.message.reply_text(f"💰 Kasa {val} aktif. 10 sayı bekleniyor..."); return

    num = val
    if num < 0 or num > 36: return

    # --- KASA KONTROL ---
    if state["last_full_list"]:
        unit = state["current_unit"]
        if num in state["last_full_list"]:
            win = (unit * 36) - (len(state["last_full_list"]) * unit)
            state["bankroll"] += win; state["hit_streak"] += 1; state["fail_count"] = 0; state["watch_mode"] = False
            await update.message.reply_text(f"🟢 HIT! | +{win}\n💰 KASA: {state['bankroll']}")
        else:
            loss = len(state["last_full_list"]) * unit
            state["bankroll"] -= loss; state["hit_streak"] = 0; state["fail_count"] += 1
            if not state["watch_mode"]: await update.message.reply_text(f"🔴 LOSE! | -{loss}\n💰 KASA: {state['bankroll']}")

    if not state["watch_mode"] and state["fail_count"] >= 3:
        state["watch_mode"] = True
        await update.message.reply_text("⚠️ LÜTFEN KALK! ⚠️"); return

    state["history"].append(num)
    
    # --- ANALİZ MOTORU ---
    if len(state["history"]) >= 10:
        idx = WHEEL_MAP[num]
        temp_final = []
        hot_zone = detect_hot_zone(state["history"])

        # 1. HOT ZONE ÖNCELİĞİ (Sıcak bölge varsa oradan 3-4 sayı sabitle)
        hot_nums_to_display = []
        if hot_zone:
            # Sıcak bölgeden son gelen sayının en yakın 3 komşusunu al
            zone_neighbors = get_neighbors(num, 1) 
            for zn in zone_neighbors:
                if zn in ZONES[hot_zone]:
                    zn_s = shift_if_exists(temp_final, zn)
                    temp_final.append(zn_s)
                    hot_nums_to_display.append(zn_s)

        # 2. AYNA (+1)
        m_val = WHEEL[(idx + 18) % 37]
        for n in get_neighbors(m_val, 1):
            if n not in temp_final: temp_final.append(n)

        # 3. SEKTÖR (Nokta)
        raw_sectors = STRATEGY_MAP.get(num, [])
        disp_sectors = []
        for s in raw_sectors:
            s_s = shift_if_exists(temp_final, s)
            temp_final.append(s_s); disp_sectors.append(s_s)

        # 4. JUMP (+1)
        jumps = [WHEEL[(idx+9)%37], WHEEL[(idx-9)%37], WHEEL[(idx+18)%37]]
        disp_jumps = []
        for j in jumps:
            j_m = shift_if_exists(temp_final, j); disp_jumps.append(j_m)
            for neighbor in get_neighbors(j, 1):
                n_s = shift_if_exists(temp_final, neighbor)
                if n_s not in temp_final: temp_final.append(n_s)

        # 5. TEKRAR
        r_s = shift_if_exists(temp_final, num)
        if r_s not in temp_final: temp_final.append(r_s)

        state["last_full_list"] = list(set(temp_final))
        ratios = [0.10, 0.12, 0.15, 0.18, 0.20]
        unit = max(1, round((state["bankroll"] * ratios[min(state["hit_streak"], 4)]) / len(state["last_full_list"])))
        state["current_unit"] = unit

        if not state["watch_mode"]:
            res = f"𝐆 𝐔 𝐀 𝐑 𝐃 𝐈 𝐀 𝐍 v14.0 🛡️\n"
            res += f"━━━━━━━━━━━━━━\n"
            if hot_zone: res += f"🔥 SICAK BÖLGE: {hot_zone} 🔥\n━━━━━━━━━━━━━━\n"
            res += f"📍 SON: {num}\n"
            res += f"💸 YATIRIM: {len(state['last_full_list']) * unit}\n"
            res += f"🎯 BİRİM: {unit} Unit\n"
            res += f"━━━━━━━━━━━━━━\n"
            res += f"🔄 AYNA: {m_val} (+1)\n"
            res += f"🛡️ SEKTÖR: {', '.join(map(str, disp_sectors))} (Nokta)\n"
            res += f"🚀 JUMP: {', '.join(map(str, disp_jumps))} (+1)\n"
            res += f"💎 TEKRAR: {r_s}\n"
            res += f"━━━━━━━━━━━━━━\n"
            res += f"💰 KASA: {state['bankroll']} | SERİ: {state['hit_streak']}"
            await update.message.reply_text(res)
        elif num in state["last_full_list"]:
             await update.message.reply_text("🟢 RİTİM DÜZELDİ!"); state["watch_mode"] = False

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_input))
    app.run_polling()
