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
    "history": deque(maxlen=30), "last_bet_map": {}, "fail_count": 0, "hit_streak": 0,
    "bankroll": 0, "initial_bankroll": 0, "waiting_bankroll": True, "watch_mode": False
})

def get_neighbors(num, n_range=1):
    idx = WHEEL_MAP[int(num)]
    return [WHEEL[(idx + i) % 37] for i in range(-n_range, n_range + 1)]

def get_mirror(num):
    return WHEEL[(WHEEL_MAP[num] + 18) % 37]

def calculate_bet_v13_3(state, raw_list):
    # Çakışan sayıları bul (Counter kullanarak)
    counts = collections.Counter(raw_list)
    total_slots = sum(counts.values()) # Kaç "birimlik" bahis var?
    
    # Kasa yönetimi (%10'dan başlar)
    risk_ratios = [0.10, 0.12, 0.15, 0.18, 0.20]
    idx = min(state["hit_streak"], len(risk_ratios) - 1)
    total_bet_money = state["bankroll"] * risk_ratios[idx]
    
    unit = max(1, round(total_bet_money / total_slots))
    
    # Sayı bazlı bahis haritası: {sayı: çarpan}
    bet_map = {num: count for num, count in counts.items()}
    return unit, bet_map, risk_ratios[idx]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = {
        "history": deque(maxlen=30), "last_bet_map": {}, "fail_count": 0, "hit_streak": 0,
        "bankroll": 0, "initial_bankroll": 0, "waiting_bankroll": True, "watch_mode": False
    }
    await update.message.reply_text("𝐆 𝐔 𝐀 𝐑 𝐃 𝐈 𝐀 𝐍 v13.3 (2X Mode)\nKasa girişini yapın:", reply_markup=REPLY_MARKUP)

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    text = update.message.text.strip()
    state = user_states[uid]

    if text in ['/start', '🗑️ SIFIRLA']: await start(update, context); return
    if text == '↩️ GERİ AL':
        if state["history"]: state["history"].pop(); state["last_bet_map"] = {}; await update.message.reply_text("↩️ Geri alındı."); return

    if not text.isdigit():
        await update.message.reply_text("lütfen rakam girin"); return
    
    val = int(text)
    if state["waiting_bankroll"]:
        state["bankroll"] = state["initial_bankroll"] = val
        state["waiting_bankroll"] = False
        await update.message.reply_text(f"💰 Kasa {val} yüklendi. 10 sayı bekleniyor..."); return

    num = val
    if num < 0 or num > 36: return

    # KASA HESAPLAMA
    if state["last_bet_map"]:
        unit = state.get("current_unit", 0)
        total_spent = sum(state["last_bet_map"].values()) * unit
        if num in state["last_bet_map"]:
            multiplier = state["last_bet_map"][num]
            win = (unit * multiplier * 36) - total_spent
            state["bankroll"] += win
            state["hit_streak"] += 1
            state["fail_count"] = 0
            await update.message.reply_text(f"🟢 HIT! ({multiplier}X) | +{win}\n💰 KASA: {state['bankroll']}")
            state["watch_mode"] = False
        else:
            state["bankroll"] -= total_spent
            state["hit_streak"] = 0
            state["fail_count"] += 1
            if not state["watch_mode"]:
                await update.message.reply_text(f"🔴 LOSE! | -{total_spent}\n💰 KASA: {state['bankroll']}")

    if not state["watch_mode"] and state["fail_count"] >= 3:
        state["watch_mode"] = True
        await update.message.reply_text("⚠️ LÜTFEN KALK! ⚠️\nRitim bozuldu, izleme modu."); return

    state["history"].append(num)

    # ANALİZ SİSTEMİ
    if len(state["history"]) >= 10 and not state["watch_mode"]:
        # Analizleri topla (Çakışmalar için küme kullanmıyoruz, liste kullanıyoruz)
        raw_list = []
        mirror = get_mirror(num)
        raw_list.extend(get_neighbors(mirror, 1)) # Ayna komşu
        raw_list.extend([WHEEL[(WHEEL_MAP[num] + 9) % 37], WHEEL[(WHEEL_MAP[num] - 9) % 37]]) # Jumps
        for p in STRATEGY_MAP.get(num, []):
            raw_list.extend(get_neighbors(p, 1)) # Strateji komşu
        raw_list.append(num) # Mutlak Tekrar
        
        unit, bet_map, ratio = calculate_bet_v13_3(state, raw_list)
        state["last_bet_map"] = bet_map
        state["current_unit"] = unit
        
        # Ekran Çıktısı Hazırlama
        doubles = [str(n) for n, c in bet_map.items() if c > 1]
        res = f"𝐆 𝐔 𝐀 𝐑 𝐃 𝐈 𝐀 𝐍 🛡️\n"
        res += f"━━━━━━━━━━━━━━\n"
        res += f"📍 SON: {num}\n"
        res += f"💸 YATIRIM: {sum(bet_map.values()) * unit} (%{int(ratio*100)})\n"
        res += f"🎯 BİRİM: {unit} Unit\n"
        res += f"━━━━━━━━━━━━━━\n"
        if doubles:
            res += f"🔥 2X YAPILACAK: {', '.join(doubles)}\n"
            res += f"━━━━━━━━━━━━━━\n"
        res += f"✅ BAHİS: {', '.join(map(str, sorted(bet_map.keys())))}\n"
        res += f"━━━━━━━━━━━━━━\n"
        res += f"💰 GÜNCEL KASA: {state['bankroll']}\n"
        res += f"📈 SERİ: {state['hit_streak']}"
        await update.message.reply_text(res)
    elif state["watch_mode"]:
        # Arka planda listeyi güncelle ki izleme modundan çıksın
        pass

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_input))
    app.run_polling()
