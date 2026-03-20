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

def get_mirror(num):
    return WHEEL[(WHEEL_MAP[num] + 18) % 37]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = {
        "history": deque(maxlen=30), "last_full_list": [], "fail_count": 0, "hit_streak": 0,
        "bankroll": 0, "initial_bankroll": 0, "waiting_bankroll": True, "watch_mode": False, "current_unit": 0
    }
    await update.message.reply_text("𝐆 𝐔 𝐀 𝐑 𝐃 𝐈 𝐀 𝐍 v13.5 (Visual Update)\nKasa girişini yapın:", reply_markup=REPLY_MARKUP)

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
        await update.message.reply_text(f"💰 Kasa {val} yüklendi. 10 sayı bekleniyor..."); return

    num = val
    if num < 0 or num > 36: return

    # KASA HESABI (Sessizce arka planda çalışır)
    if state["last_full_list"]:
        unit = state["current_unit"]
        total_spent = len(state["last_full_list"]) * unit # Basit hesap: Her sayı 1 unit
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
        await update.message.reply_text("⚠️ LÜTFEN KALK! ⚠️\nRitim bozuldu, izleme modu."); return

    state["history"].append(num)

    # ANALİZ SİSTEMİ
    if len(state["history"]) >= 10:
        # Analizleri hesapla (Ancak sadece ana sayıları ekrana yazdıracağız)
        mirror = get_mirror(num)
        sectors = STRATEGY_MAP.get(num, [])
        repeat = [num]

        # Arka planda tam listeyi koru ki kasa ve ritim takibi bozulmasın
        all_nums = []
        all_nums.extend(get_neighbors(mirror, 1))
        for s in sectors: all_nums.extend(get_neighbors(s, 1))
        all_nums.append(num)
        all_nums.extend([WHEEL[(WHEEL_MAP[num] + 9) % 37], WHEEL[(WHEEL_MAP[num] - 9) % 37]]) # Jumps
        
        counts = collections.Counter(all_nums)
        state["last_full_list"] = list(counts.keys())
        
        # Risk Yönetimi (%10)
        ratios = [0.10, 0.12, 0.15, 0.18, 0.20]
        idx = min(state["hit_streak"], len(ratios) - 1)
        # Basit Unit hesabı: Riske edilecek parayı, kapattığımız ceb sayısına bölüyoruz
        unit = max(1, round((state["bankroll"] * ratios[idx]) / len(state["last_full_list"])))
        state["current_unit"] = unit

        if not state["watch_mode"]:
            # Ekran Çıktısı (Tam istediğin parçalı ve (+1) formatı)
            res = f"𝐆 𝐔 𝐀 𝐑 𝐃 𝐈 𝐀 𝐍 🛡️\n"
            res += f"━━━━━━━━━━━━━━\n"
            res += f"📍 SON: {num}\n"
            res += f"💸 YATIRIM: {len(state['last_full_list']) * unit} (%{int(ratios[idx]*100)})\n"
            res += f"🎯 BİRİM: {unit} Unit\n"
            res += f"━━━━━━━━━━━━━━\n"
            
            # İkinci resimdeki formatı uygula
            res += f"🔄 AYNA: {mirror} (+1)\n"
            res += f"🛡️ SEKTÖR: {', '.join(map(str, sorted(sectors)))} (+1)\n"
            res += f"🚀 JUMP: {all_nums[-2]}, {all_nums[-1]} (Tam)\n" # Jump'lar tekil kalabilir
            res += f"💎 TEKRAR: {num}\n"
            res += f"━━━━━━━━━━━━━━\n"
            res += f"💰 GÜNCEL KASA: {state['bankroll']}\n"
            res += f"📈 SERİ: {state['hit_streak']}"
            await update.message.reply_text(res)
        elif num in state["last_full_list"]:
             await update.message.reply_text("🟢 RİTİM DÜZELDİ! Şimdi bahis zamanı.")
             state["watch_mode"] = False

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_input))
    app.run_polling()
