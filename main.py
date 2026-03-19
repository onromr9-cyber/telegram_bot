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
    "bankroll": 0, "initial_bankroll": 0, "waiting_bankroll": True, "watch_mode": False, "last_unit": 0
})

def get_neighbors(num, n_range=1):
    idx = WHEEL_MAP[int(num)]
    return [WHEEL[(idx + i) % 37] for i in range(-n_range, n_range + 1)]

def get_mirror(num):
    return WHEEL[(WHEEL_MAP[num] + 18) % 37]

def get_sniper_v13(num):
    # 1. AYNA (s2)
    mirror_pivot = get_mirror(num)
    m_list = set(get_neighbors(mirror_pivot, 1)) # Range 1'e düşürüldü sayı şişmemesi için
    
    # 2. CROSS-WHEEL JUMP
    jump_1 = WHEEL[(WHEEL_MAP[num] + 9) % 37]
    jump_2 = WHEEL[(WHEEL_MAP[num] - 9) % 37]
    j_list = {jump_1, jump_2}
    
    # 3. STRATEJİ + KOMŞU (Yanında Kalma Sorunu Çözümü)
    s_pivots = STRATEGY_MAP.get(num, [])
    s_list = set()
    for p in s_pivots:
        s_list.update(get_neighbors(p, 1)) # Her strateji sayısının 1 komşusunu al
    
    # 4. MUTLAK TEKRAR
    repeat_num = {num}
    
    full_list = m_list.union(j_list).union(s_list).union(repeat_num)
    return {"mirror": mirror_pivot, "strategy": s_pivots, "full_list": list(full_list)}

async def format_analysis_msg(state, num, data):
    total_nums = len(data["full_list"])
    res = f"𝐆 𝐔 𝐀 𝐑 𝐃 𝐈 𝐀 𝐍 🛡️\n"
    res += f"📍 SON: {num}\n\n"
    res += f"🔄 AYNA: {data['mirror']} (+1)\n"
    res += f"🛡️ SEKTÖR: {', '.join(map(str, data['strategy']))} (+1)\n"
    res += f"💎 TEKRAR: {num}\n\n"
    res += f"🎲 TOPLAM: {total_nums} Rakam\n"
    res += f"💰 KASA: {state['bankroll']}"
    return res

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    user_states[update.effective_user.id] = {
        "history": deque(maxlen=30), "last_full_list": [], "fail_count": 0, "hit_streak": 0,
        "bankroll": 0, "initial_bankroll": 0, "waiting_bankroll": True, "watch_mode": False, "last_unit": 0
    }
    await update.message.reply_text("GUARDIAN v13.0 ACTIVE\nKasa miktarını girin:", reply_markup=REPLY_MARKUP)

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
    if state["waiting_bankroll"]:
        state["bankroll"] = val
        state["initial_bankroll"] = val
        state["waiting_bankroll"] = False
        await update.message.reply_text(f"💰 Kasa {state['bankroll']} yüklendi. İlk 10 sayı girişi bekleniyor...")
        return

    num = val
    # KAZANÇ/KAYIP HESABI
    if state["last_full_list"]:
        if num in state["last_full_list"]:
            state["hit_streak"] += 1
            state["fail_count"] = 0
            await update.message.reply_text(f"🟢 HIT! | Rakam: {num}\nKasa: {state['bankroll']}")
        else:
            state["hit_streak"] = 0
            state["fail_count"] += 1
            await update.message.reply_text(f"🔴 LOSE! | Rakam: {num}\nKasa: {state['bankroll']}")

    # GUARD LOGIC (LÜTFEN KALK!)
    if state["fail_count"] >= 3 or (state["bankroll"] < state["initial_bankroll"] * 0.8):
        state["watch_mode"] = True
        await update.message.reply_text("⚠️ LÜTFEN KALK! ⚠️\nRitim bozuldu veya kasa riskte. İzleme moduna geçiliyor.")
        state["last_full_list"] = [] # Analizi temizle

    state["history"].append(num)

    # İZLEME MODUNDAN ÇIKIŞ (Kaçış Algoritması)
    if state["watch_mode"]:
        # Eğer izleme modunda bir tahmin listesi varsa ve tutarsa çık
        # (Buraya basit bir düzelme kontrolü eklenebilir)
        pass 

    if len(state["history"]) >= 10 and not state["watch_mode"]:
        data = get_sniper_v13(num)
        state["last_full_list"] = data["full_list"]
        res = await format_analysis_msg(state, num, data)
        await update.message.reply_text(res)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_input))
    app.run_polling()
