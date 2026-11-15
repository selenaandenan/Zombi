import asyncio
import logging
import sqlite3
import json
import random
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, 
    InlineKeyboardButton, WebAppInfo, PreCheckoutQuery
)
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ================= НАСТРОЙКИ =================
TOKEN = "8647859964:AAFvXgbvIiuTmtAEPRWFkMFS8_Zeaf97p4I"  # <--- ВСТАВЬ ТОКЕН ОТ @BotFather
ADMIN_IDS = [8624408698]      # <--- ВСТАВЬ СВОЙ ID
VTB_CARD = "79041911584"      # Твой номер ВТБ
SITE_URL = "https://selenaandenan.github.io/Zombi/"

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# ================= СОСТОЯНИЯ (FSM) =================
class UserState(StatesGroup):
    waiting_topup_amount = State()
    waiting_topup_receipt = State()
    waiting_withdraw_amount = State()
    waiting_withdraw_details = State()

# ================= БАЗА ДАННЫХ =================
conn = sqlite3.connect("casino.db", check_same_thread=False)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Таблица пользователей
cursor.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY, 
    balance REAL DEFAULT 0.0,
    total_wagered REAL DEFAULT 0.0,
    reg_date TEXT DEFAULT CURRENT_TIMESTAMP
)""")

# Таблица заявок на вывод/пополнение
cursor.execute("""CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    type TEXT,
    amount REAL,
    details TEXT,
    status TEXT DEFAULT 'pending',
    date TEXT DEFAULT CURRENT_TIMESTAMP
)""")

# Таблица истории игр
cursor.execute("""CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    game TEXT,
    bet REAL,
    win REAL,
    date TEXT DEFAULT CURRENT_TIMESTAMP
)""")
conn.commit()

# ================= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =================
def get_balance(uid):
    user = cursor.execute("SELECT balance FROM users WHERE user_id = ?", (uid,)).fetchone()
    return user['balance'] if user else 0.0

def update_balance(uid, amount):
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, uid))
    conn.commit()

def log_game(uid, game, bet, win):
    cursor.execute("INSERT INTO history (user_id, game, bet, win) VALUES (?, ?, ?, ?)", (uid, game, bet, win))
    cursor.execute("UPDATE users SET total_wagered = total_wagered + ? WHERE user_id = ?", (bet, uid))
    conn.commit()

# ================= КЛАВИАТУРЫ =================
def kb_main():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Открыть Казино", web_app=WebAppInfo(url=SITE_URL))],
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="profile")],
        [InlineKeyboardButton(text="🏆 Топ игроков", callback_data="top")],
        [InlineKeyboardButton(text="🆘 Поддержка", url="https://t.me/cluya")]
    ])

def kb_profile():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Пополнить", callback_data="topup")],
        [InlineKeyboardButton(text="💸 Вывести", callback_data="withdraw")],
        [InlineKeyboardButton(text="📜 История игр", callback_data="history")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
    ])

def kb_cancel():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="back")]
    ])

# ================= СТАРТ =================
@dp.message(CommandStart())
async def cmd_start(message: Message):
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
    conn.commit()
    await message.answer(
        f"🧟‍♂️ <b>Добро пожаловать в ZOMBIE CASINO!</b>\n\n"
        f"Твой баланс: <b>{get_balance(message.from_user.id)} ⭐</b>\n\n"
        f"👇 Жми кнопку, чтобы начать:",
        reply_markup=kb_main()
    )

@dp.callback_query(F.data == "back")
async def cb_back(cb: CallbackQuery):
    await cb.message.edit_text("🏠 Главное меню", reply_markup=kb_main())

# ================= ПРОФИЛЬ =================
@dp.callback_query(F.data == "profile")
async def cb_profile(cb: CallbackQuery):
    bal = get_balance(cb.from_user.id)
    user = cursor.execute("SELECT total_wagered FROM users WHERE user_id = ?", (cb.from_user.id,)).fetchone()
    wagered = user['total_wagered'] if user else 0
    
    await cb.message.edit_text(
        f"👤 <b>Личный кабинет</b>\n\n"
        f"🆔 ID: <code>{cb.from_user.id}</code>\n"
        f"💰 Баланс: <b>{bal} ⭐</b>\n"
        f"🎲 Всего проставлено: <b>{wagered} ⭐</b>",
        reply_markup=kb_profile()
    )

@dp.callback_query(F.data == "history")
async def cb_history(cb: CallbackQuery):
    games = cursor.execute("SELECT game, bet, win, date FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 10", (cb.from_user.id,)).fetchall()
    text = "📜 <b>Последние 10 игр:</b>\n\n"
    if not games:
        text += "Вы еще не играли."
    else:
        for g in games:
            emoji = "🟢" if g['win'] > g['bet'] else "🔴"
            text += f"{emoji} {g['game']} | Ставка: {g['bet']} | Выигрыш: {g['win']}\n"
    
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="profile")]]))

@dp.callback_query(F.data == "top")
async def cb_top(cb: CallbackQuery):
    top_users = cursor.execute("SELECT user_id, total_wagered FROM users WHERE total_wagered > 0 ORDER BY total_wagered DESC LIMIT 5").fetchall()
    text = "🏆 <b>Топ игроков по ставкам:</b>\n\n"
    for i, u in enumerate(top_users, 1):
        text += f"{i}. ID <code>{u['user_id']}</code> — {u['total_wagered']} ⭐\n"
    
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]]))

# ================= ПОПОЛНЕНИЕ =================
@dp.callback_query(F.data == "topup")
async def cb_topup(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text(f"💳 Введите сумму пополнения (в ⭐):\n\nРеквизиты: <code>{VTB_CARD}</code>", reply_markup=kb_cancel())
    await state.set_state(UserState.waiting_topup_amount)

@dp.message(UserState.waiting_topup_amount)
async def process_topup_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text)
        if amount <= 0: raise ValueError
        await state.update_data(amount=amount)
        await message.answer("✅ Теперь отправьте фото/файл чека:")
        await state.set_state(UserState.waiting_topup_receipt)
    except:
        await message.answer("Введите число больше 0!")

@dp.message(UserState.waiting_topup_receipt, F.photo | F.document)
async def process_topup_receipt(message: Message, state: FSMContext):
    data = await state.get_data()
    amount = data['amount']
    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    
    cursor.execute("INSERT INTO requests (user_id, type, amount, details) VALUES (?, 'topup', ?, ?)", (message.from_user.id, amount, file_id))
    req_id = cursor.lastrowid
    conn.commit()
    
    await message.answer("⏳ Заявка на пополнение отправлена админу!", reply_markup=kb_main())
    await state.clear()
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(admin_id, file_id, caption=f"💳 <b>Пополнение #{req_id}</b>\n👤 @{message.from_user.username}\n💰 Сумма: {amount} ⭐", 
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"appr_topup_{req_id}")
                ]]))
        except: pass

@dp.callback_query(F.data.startswith("appr_topup_"))
async def appr_topup(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS: return
    req_id = int(cb.data.split("_")[2])
    
    req = cursor.execute("SELECT user_id, amount FROM requests WHERE id = ?", (req_id,)).fetchone()
    if not req: return
    
    update_balance(req['user_id'], req['amount'])
    cursor.execute("UPDATE requests SET status = 'approved' WHERE id = ?", (req_id,))
    conn.commit()
    
    await bot.send_message(req['user_id'], f"✅ Ваш баланс пополнен на {req['amount']} ⭐!")
    await cb.message.edit_caption(caption="✅ Пополнение подтверждено.")

# ================= ВЫВОД =================
@dp.callback_query(F.data == "withdraw")
async def cb_withdraw(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("💸 Введите сумму для вывода (мин. 100 ⭐):", reply_markup=kb_cancel())
    await state.set_state(UserState.waiting_withdraw_amount)

@dp.message(UserState.waiting_withdraw_amount)
async def process_withdraw_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text)
        if amount < 100: 
            await message.answer("Минимум 100 ⭐!")
            return
        if get_balance(message.from_user.id) < amount:
            await message.answer("❌ Недостаточно средств!")
            return
        
        await state.update_data(amount=amount)
        await message.answer("💳 Введите номер карты или СБП:")
        await state.set_state(UserState.waiting_withdraw_details)
    except:
        await message.answer("Введите число!")

@dp.message(UserState.waiting_withdraw_details)
async def process_withdraw_details(message: Message, state: FSMContext):
    data = await state.get_data()
    amount = data['amount']
    details = message.text
    
    update_balance(message.from_user.id, -amount)
    cursor.execute("INSERT INTO requests (user_id, type, amount, details) VALUES (?, 'withdraw', ?, ?)", (message.from_user.id, amount, details))
    req_id = cursor.lastrowid
    conn.commit()
    
    await message.answer("⏳ Заявка на вывод создана. Ожидайте перевода!", reply_markup=kb_main())
    await state.clear()
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, f"💸 <b>ВЫВОД #{req_id}</b>\n👤 @{message.from_user.username}\n💰 {amount} ⭐\n💳 Реквизиты: <code>{details}</code>", 
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="✅ Выплачено", callback_data=f"done_withdraw_{req_id}")
                ]]))
        except: pass

@dp.callback_query(F.data.startswith("done_withdraw_"))
async def done_withdraw(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS: return
    req_id = int(cb.data.split("_")[2])
    req = cursor.execute("SELECT user_id FROM requests WHERE id = ?", (req_id,)).fetchone()
    
    cursor.execute("UPDATE requests SET status = 'paid' WHERE id = ?", (req_id,))
    conn.commit()
    
    await bot.send_message(req['user_id'], "✅ Ваш вывод выполнен!")
    await cb.message.edit_text("✅ Вывод закрыт.")

# ================= ОБРАБОТКА ИГР С САЙТА =================
@dp.message(F.web_app_data)
async def web_app_handler(message: Message):
    try:
        data = json.loads(message.web_app_data.data)
        user_id = message.from_user.id
        bal = get_balance(user_id)
        action = data.get("action")

        # 1 и 2. КЕЙСЫ
        if action == "open_case":
            case_id = data.get("case_id")
            price = float(data.get("price", 0))
            
            if bal < price:
                await message.answer("❌ <b>Недостаточно звезд!</b>")
                return
            
            update_balance(user_id, -price)
            
            win_amount = 0
            if case_id == "cheap":
                # Шансы: 80% на 15, 15% на 25, 4% на 50, 1% на 100
                prizes = [15, 25, 50, 100]
                weights = [80, 15, 4, 1] 
                win_amount = random.choices(prizes, weights=weights, k=1)[0]
            elif case_id == "expensive":
                # Шансы: 70% на 50, 20% на 100, 10% на 500
                prizes = [50, 100, 500]
                weights = [70, 20, 10] 
                win_amount = random.choices(prizes, weights=weights, k=1)[0]
            
            update_balance(user_id, win_amount)
            log_game(user_id, f"Кейс {case_id}", price, win_amount)
            
            await message.answer(
                f"☣️ <b>КЕЙС ОТКРЫТ!</b>\n\n"
                f"💸 Ставка: {price} ⭐\n"
                f"🎉 Выигрыш: <b>{win_amount} ⭐</b>\n"
                f"💰 Баланс: {get_balance(user_id)} ⭐",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🎰 Играть еще", web_app=WebAppInfo(url=SITE_URL))
                ]])
            )

        # 3. РУЛЕТКА
        elif action == "roulette":
            price = float(data.get("price", 50))
            if bal < price:
                await message.answer("❌ <b>Недостаточно звезд!</b>")
                return
            
            update_balance(user_id, -price)
            
            # 70% - X0, 20% - X2, 10% - X3
            mult = random.choices([0, 2, 3], weights=[70, 20, 10], k=1)[0]
            win = price * mult
            update_balance(user_id, win)
            log_game(user_id, "Рулетка", price, win)
            
            if win > 0:
                await message.answer(
                    f"🎡 <b>РУЛЕТКА</b>\n\n"
                    f"Выпало: <b>x{mult}</b>\n"
                    f"💰 Выигрыш: <b>+{win} ⭐</b>\n"
                    f"💼 Баланс: {get_balance(user_id)} ⭐",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🎡 Еще", web_app=WebAppInfo(url=SITE_URL))
                    ]])
                )
            else:
                await message.answer(
                    f"🎡 <b>РУЛЕТКА</b>\n\n"
                    f"Выпало: <b>x0</b>\n"
                    f"💸 Потеряно: <b>{price} ⭐</b>\n"
                    f"💼 Баланс: {get_balance(user_id)} ⭐",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🎡 Еще", web_app=WebAppInfo(url=SITE_URL))
                    ]])
                )

        # 4. КОЛЕСО ФОРТУНЫ
        elif action == "wheel":
            price = float(data.get("price", 100))
            if bal < price:
                await message.answer("❌ Мало звезд!")
                return
            
            update_balance(user_id, -price)
            # Шансы: 70% - X0, 15% - X1.5, 13% - X3, 2% - X10
            mult = random.choices([0, 1.5, 3, 10], weights=[70, 15, 13, 2], k=1)[0]
            win = int(price * mult)
            update_balance(user_id, win)
            log_game(user_id, "Колесо", price, win)
            
            if win > 0:
                await message.answer(f"🎯 Колесо: Выпало <b>x{mult}</b>.\nВыигрыш: <b>+{win} ⭐</b>\nБаланс: {get_balance(user_id)}")
            else:
                await message.answer(f"🎯 Колесо: Выпало <b>x0</b>.\nПотеряно: <b>{price} ⭐</b>\nБаланс: {get_balance(user_id)}")

        # 5. МИННОЕ ПОЛЕ
        elif action == "mines":
            price = float(data.get("price", 30))
            if bal < price:
                await message.answer("❌ Мало звезд!")
                return
            
            update_balance(user_id, -price)
            # Шанс на победу 40%
            is_win = random.random() < 0.40 
            
            if is_win:
                win = int(price * 2.5)
                update_balance(user_id, win)
                log_game(user_id, "Минное поле", price, win)
                await message.answer(f"💎 Вы нашли алмаз! Выигрыш: <b>+{win} ⭐</b>\nБаланс: {get_balance(user_id)}")
            else:
                log_game(user_id, "Минное поле", price, 0)
                await message.answer(f"💀 Вы нарвались на зомби! Потеряно: <b>{price} ⭐</b>\nБаланс: {get_balance(user_id)}")

        # 6. МОНЕТКА
        elif action == "coinflip":
            price = float(data.get("price", 20))
            if bal < price:
                await message.answer("❌ Мало звезд!")
                return
            
            update_balance(user_id, -price)
            # Шанс на победу 45%
            is_win = random.random() < 0.45
            
            if is_win:
                win = price * 2
                update_balance(user_id, win)
                log_game(user_id, "Монетка", price, win)
                await message.answer(f"🪙 Орел! Выигрыш: <b>+{win} ⭐</b>\nБаланс: {get_balance(user_id)}")
            else:
                log_game(user_id, "Монетка", price, 0)
                await message.answer(f"🪙 Решка! Потеряно: <b>{price} ⭐</b>\nБаланс: {get_balance(user_id)}")

        # 7. СЛОТЫ
        elif action == "slots":
            price = float(data.get("price", 40))
            if bal < price:
                await message.answer("❌ Мало звезд!")
                return
            
            update_balance(user_id, -price)
            # 5% джекпот, 15% x2, 80% проигрыш
            r = random.random()
            if r < 0.05:
                win = price * 10
                update_balance(user_id, win)
                log_game(user_id, "Слоты", price, win)
                await message.answer(f"7️⃣ ДЖЕКПОТ! Выигрыш: <b>+{win} ⭐</b>\nБаланс: {get_balance(user_id)}")
            elif r < 0.20:
                win = price * 2
                update_balance(user_id, win)
                log_game(user_id, "Слоты", price, win)
                await message.answer(f"💎 Выигрыш x2: <b>+{win} ⭐</b>\nБаланс: {get_balance(user_id)}")
            else:
                log_game(user_id, "Слоты", price, 0)
                await message.answer(f"🎰 Вы проиграли {price} ⭐.\nБаланс: {get_balance(user_id)}")

        # 8. ПОПОЛНЕНИЕ / ВЫВОД С САЙТА
        elif action == "topup":
            await message.answer("💳 Зайдите в /start -> Профиль -> Пополнить.")
        elif action == "withdraw":
            await message.answer("💸 Зайдите в /start -> Профиль -> Вывести.")

    except Exception as e:
        logging.error(f"Ошибка сайта: {e}")

# ================= ЗАПУСК =================
async def main():
    logging.basicConfig(level=logging.INFO)
    print("🎰 Казино-бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
