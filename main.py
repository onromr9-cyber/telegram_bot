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
    "bankroll": 0, "initial_bankroll": 0, "waiting_bankroll": True, "watch_mode": False, "current_unit": 0
})

def get_neighbors(num, n_range=1):
    idx = WHEEL_MAP[int(num)]
    return [WHEEL[(idx + i) % 37] for i in range(-n_range, n_range + 1)]

def shift_if_exists(target_list, num):
    current_num = num
    while current_num in target_list:
        idx = WHEEL_MAP[current_num]
        current_num = WHEEL[(idx + 1) % 37]
    return current_num

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = {
        "history": deque(maxlen=30), "last_full_list": [], "fail_count": 0, "hit_streak": 0,
        "bankroll": 0, "initial_bankroll": 0, "waiting_bankroll": True, "watch_mode": False, "current_unit": 0
    }
    await update.message.reply_text("𝐆 𝐔 𝐀 𝐑 𝐃 𝐈 𝐀 𝐍 v13.8 🛡️\nKasa girişini yapın:", reply_markup=REPLY_MARKUP)

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    text = update.message.text.strip()
    state = user_states[uid]

    if text in ['/start', '🗑️ SIFIRLA']: await start(update, context); return
    if text == '↩️ GERİ AL':
        if state["history"]: state["history"].pop(); state["last_full_list"] = []; await update.message.reply_text("↩️ Geri alındı."); return

    if not text.isdigit():
        await update.message.reply_text("lütfen rakam girin"); return
    
    val = int(text)
    if state["waiting_bankroll"]:
        state["bankroll"] = state["initial_bankroll"] = val
        state["waiting_bankroll"] = False
        await update.message.reply_text(f"💰 Kasa {val} aktif. İlk 10 sayı bekleniyor..."); return

    num = val
    if num < 0 or num > 36: return

    # KASA HESABI
    if state["last_full_list"]:
        unit = state["current_unit"]
        total_spent = len(state["last_full_list"]) * unit
        if num in state["last_full_list"]:
            win = (unit * 36) - total_spent
            state["bankroll"] += win
            state["hit_streak"] += 1
            state["fail_count"] = 0
            state["watch_mode"] = False
            await update.message.reply_text(f"🟢 HIT! | +{win}\n💰 KASA: {state['bankroll']}")
        else:
            state["bankroll"] -= total_spent
            state["hit_streak"] = 0
            state["fail_count"] += 1
            if not state["watch_mode"]:
                await update.message.reply_text(f"🔴 LOSE! | -{total_spent}\n💰 KASA: {state['bankroll']}")

    if not state["watch_mode"] and state["fail_count"] >= 3:
        state["watch_mode"] = True
        await update.message.reply_text("⚠️ LÜTFEN KALK! ⚠️\nRitim bozuldu."); return

    state["history"].append(num)

    # ANALİZ SİSTEMİ
    if len(state["history"]) >= 10:
        idx = WHEEL_MAP[num]
        final_list = []

        # 1. AYNA (+1)
        m_val = WHEEL[(idx + 18) % 37]
        for n in get_neighbors(m_val, 1):
            if n not in final_list: final_list.append(n)

        # 2. SEKTÖR (Nokta) - Kaydırmalı
        sectors = STRATEGY_MAP.get(num, [])
        disp_sectors = []
        for s in sectors:
            s_final = shift_if_exists(final_list, s)
            final_list.append(s_final)
            disp_sectors.append(s_final)

        # 3. JUMP (+1) - Kaydırmalı
        jumps = [WHEEL[(idx+9)%37], WHEEL[(idx-9)%37], WHEEL[(idx+18)%37]]
        disp_jumps = []
        for j in jumps:
            # Sadece ana durakları göster ama arka planda komşuları ekle
            j_final = shift_if_exists(final_list, j)
            disp_jumps.append(j_final)
            # Komşuları ekle
            for n in get_neighbors(j, 1):
                n_final = shift_if_exists(final_list, n)
                final_list.append(n_final)

        # 4. TEKRAR
        r_final = shift_if_exists(final_list, num)
        final_list.append(r_final)

        state["last_full_list"] = list(set(final_list))
        
        # Risk & Unit
        ratios = [0.10, 0.12, 0.15, 0.18, 0.20]
        r_idx = min(state["hit_streak"], len(ratios) - 1)
        unit = max(1, round((state["bankroll"] * ratios[r_idx]) / len(state["last_full_list"])))
        state["current_unit"] = unit

        if not state["watch_mode"]:
            # EKRAN ÇIKTISI (Kısaltılmış ve Sade)
            res = f"𝐆 𝐔 𝐀 𝐑 𝐃 𝐈 𝐀 𝐍 🛡️\n"
            res += f"━━━━━━━━━━━━━━\n"
            res += f"📍 SON: {num}\n"
            res += f"💸 YATIRIM: {len(state['last_full_list']) * unit} (%{int(ratios[r_idx]*100)})\n"
            res += f"🎯 BİRİM: {unit} Unit\n"
            res += f"━━━━━━━━━━━━━━\n"
            res += f"🔄 AYNA: {m_val} (+1)\n"
            res += f"🛡️ SEKTÖR: {', '.join(map(str, disp_sectors))} (Nokta)\n"
            res += f"🚀 JUMP: {', '.join(map(str, disp_jumps))} (+1)\n"
            res += f"💎 TEKRAR: {r_final}\n"
            res += f"━━━━━━━━━━━━━━\n"
            res += f"💰 GÜNCEL KASA: {state['bankroll']}\n"
            res += f"📈 SERİ: {state['hit_streak']}"
            await update.message.reply_text(res)
        elif num in state["last_full_list"]:
             await update.message.reply_text("🟢 RİTİM DÜZELDİ!"); state["watch_mode"] = False

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_input))
    app.run_polling()
