import os, math, collections, numpy as np
from collections import deque
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- AYARLAR ---
TOKEN = "BURAYA_TOKEN_YAZ"
ADMIN_IDS = {5813833511, 1278793650} # Senin ve arkadaşının ID'si

WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
WHEEL_MAP = {num: i for i, num in enumerate(WHEEL)}
KEYBOARD = [['↩️ GERİ AL', '🗑️ SIFIRLA']]

user_states = {}

def get_user_state(uid):
    if uid not in user_states:
        user_states[uid] = {
            "bakiye": 0, "history": deque(maxlen=100),
            "hit_history": deque(maxlen=10), "last_all_bets": [],
            "fail_count": 0, "is_warmup_done": False,
            "waiting_for_balance": False, "last_unit": 0, 
            "is_monitoring": False, "snapshot": []
        }
    return user_states[uid]

def get_neighbors(n, s=1):
    idx = WHEEL_MAP[n]
    return [WHEEL[(idx + i) % 37] for i in range(-s, s + 1)]

def mindful_engine(uid):
    state = get_user_state(uid)
    hist = list(state["history"])
    if len(hist) < 5: return [hist[-1]], 0

    # Ritim ve Kaos Analizi
    indices = [WHEEL_MAP[x] for x in hist[-10:]]
    jumps = np.diff(indices) % 37
    avg_jump = int(np.median(jumps[-4:]))
    chaos = float(np.std(jumps[-6:]))

    # BALANCE PİVOTLARI (8-9 SAYI HEDEFİ)
    # Ana Pivot (Momentum) + Ayna (Karşıtlık) + Kaçış (Stabilite)
    p1 = WHEEL[(WHEEL_MAP[hist[-1]] + avg_jump) % 37]
    p2 = WHEEL[(WHEEL_MAP[hist[-1]] + 18) % 37] 
    
    # 8 Sayılık Blok Oluşturma
    bets = set()
    bets.update(get_neighbors(p1, 1)) # 3 Sayı (Momentum)
    bets.update(get_neighbors(p2, 1)) # 3 Sayı (Ayna)
    bets.update(get_neighbors(hist[-1], 0)) # 1 Sayı (Tekrar)
    
    # Eğer kaos düşükse son sayı komşusunu ekle, yüksekse pivotu genişlet
    if chaos < 12:
        bets.update(get_neighbors(p1, 2))
    else:
        # Kaçış Algoritması (Chaos Factor Dynamic Expansion)
        escape_num = (p1 + 5) % 37
        bets.add(escape_num)

    return list(bets), chaos

async def generate_analysis_msg(uid):
    state = get_user_state(uid)
    bets, chaos = mindful_engine(uid)
    state["last_all_bets"] = bets
    
    # Hit Rate Analizi
    last_5 = list(state["hit_history"])[-5:]
    hit_rate = sum(last_5) / 5 if len(last_5) >= 5 else 0.5

    # 🛑 GUARDIAN ÇIKIŞ MANTIĞI (EXIT LOGIC)
    if chaos > 18.0 or state["fail_count"] >= 3 or hit_rate < 0.2:
        state["is_monitoring"] = True
        state["last_unit"] = 0
        return (f"🟡 **İZLEME MODU (DUR!)**\n"
                f"───────────────────\n"
                f"⚠️ Kaos: {chaos:.1f} | Verim: {hit_rate:.2f}\n"
                f"🚨 **LÜTFEN KALK!**\n"
                f"📢 Masa dengesi bozuldu. Sanal hit gelene kadar izle.")

    state["is_monitoring"] = False
    unit_val = max(math.floor((state["bakiye"] * 0.05) / len(bets)), 1)
    state["last_unit"] = unit_val

    return (
        f"🎯 **MİNDFUL SNIPER v7.5**\n"
        f"💰 KASA: {state['bakiye']} | 🪙 UNIT: {unit_val}\n"
        f"───────────────────\n"
        f"🔥 BAHİS: {sorted(bets)}\n"
        f"📏 SAYI ADEDİ: {len(bets)}\n"
        f"───────────────────\n"
        f"📢 Ritim: {'✅' if chaos < 12 else '⚠️'}\n"
        f"🚀 Hit Rate (5): {hit_rate:.2f}"
    )

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    state = get_user_state(uid)
    text = update.message.text.strip().upper()

    # Kontroller
    if text == '🗑️ SIFIRLA':
        if uid in user_states: del user_states[uid]
        await update.message.reply_text("🛡️ SİSTEM SIFIRLANDI."); return
    
    if text == '↩️ GERİ AL' and state["snapshot"]:
        state.update(state["snapshot"].pop()); await update.message.reply_text("↩️ Geri alındı."); return

    if not text.isdigit():
        await update.message.reply_text("⚠️ Lütfen sadece RAKAM girin (0-36)."); return
    
    val = int(text)
    if val > 36:
        await update.message.reply_text("⚠️ Hatalı rakam! 0-36 arası girin."); return

    if state["waiting_for_balance"]:
        state["bakiye"] = val; state["waiting_for_balance"] = False; state["is_warmup_done"] = True
        msg = await generate_analysis_msg(uid); await update.message.reply_text(msg, parse_mode='Markdown'); return

    # Snapshot (Geri alabilmek için)
    snap = {k: (list(v) if isinstance(v, deque) else v) for k, v in state.items() if k != "snapshot"}
    state["snapshot"].append(snap)

    # Sonuç İşleme
    if state["is_warmup_done"]:
        is_hit = val in state["last_all_bets"]
        cost = len(state["last_all_bets"]) * state["last_unit"]
        
        if is_hit:
            if state["last_unit"] > 0:
                gain = (state["last_unit"] * 36) - cost
                state["bakiye"] += gain
                await update.message.reply_text(f"✅ HİT! (+{gain})")
            else:
                await update.message.reply_text(f"👁️ SANAL HİT! Ritim yakalanıyor.")
            state["hit_history"].append(1); state["fail_count"] = 0
        else:
            if state["last_unit"] > 0:
                state["bakiye"] -= cost
                await update.message.reply_text(f"❌ PAS (-{cost})")
            else:
                await update.message.reply_text(f"👁️ İzleme devam ediyor...")
            state["hit_history"].append(0); state["fail_count"] += 1

    state["history"].append(val)
    if not state["is_warmup_done"] and len(state["history"]) == 10:
        state["waiting_for_balance"] = True
        await update.message.reply_text("🎯 10 Isınma Sayısı Tamam. Kasa Gir:"); return
    
    if state["is_warmup_done"]:
        msg = await generate_analysis_msg(uid)
        await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    user_states[uid] = get_user_state(uid)
    await update.message.reply_text("🛡️ **𝐆 𝐔 𝐀 𝐑 𝐃 𝐈 𝐀 𝐍 v7.5**\n\nAnaliz için 10 sayı girin...", reply_markup=ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True))

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, play))
    print("Bot çalışıyor...")
    app.run_polling()
