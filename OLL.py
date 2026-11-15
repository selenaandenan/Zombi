import asyncio
import logging
import sqlite3
import json
import random
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, 
    InlineKeyboardButton, PreCheckoutQuery, LabeledPrice, WebAppInfo
)
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ================= НАСТРОЙКИ =================
TOKEN = "8647859964:AAFvXgbvIiuTmtAEPRWFkMFS8_Zeaf97p4I"  # <--- ВСТАВЬ ТОКЕН ОТ @BotFather
ADMIN_IDS = [8624408698]      # <--- ВСТАВЬ СВОЙ ID
VTB_CARD = "79041911584"      # Твой номер ВТБ
SITE_URL = "https://selenaandenan.github.io/Zombi/" # <--- ССЫЛКА НА ТВОЙ MINI APP (GitHub/Netlify)

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# ================= СОСТОЯНИЯ =================
class TopupState(StatesGroup):
    waiting_for_receipt = State()

# ================= БАЗА ДАННЫХ =================
conn = sqlite3.connect("casino.db", check_same_thread=False)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Таблица игроков (баланс)
cursor.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY, 
    balance REAL DEFAULT 0.0
)""")
conn.commit()

# ================= КЛАВИАТУРЫ =================
def kb_main():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Открыть Казино", web_app=WebAppInfo(url=SITE_URL))],
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="profile")],
        [InlineKeyboardButton(text="🆘 Поддержка", url="https://t.me/cluya")]
    ])

def kb_profile():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="topup")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
    ])

# ================= СТАРТ =================
@dp.message(CommandStart())
async def cmd_start(message: Message):
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
    conn.commit()
    
    await message.answer(
        f"🧟‍♂️ <b>Добро пожаловать в ZOMBIE CASINO!</b>\n\n"
        f"Крути кейсы, играй в рулетку и выбивай звезды.\n"
        f"Твой баланс: <b>{get_balance(message.from_user.id)} ⭐</b>\n\n"
        f"👇 Жми кнопку, чтобы начать:",
        reply_markup=kb_main()
    )

def get_balance(uid):
    user = cursor.execute("SELECT balance FROM users WHERE user_id = ?", (uid,)).fetchone()
    return user['balance'] if user else 0.0

@dp.callback_query(F.data == "back")
async def cb_back(cb: CallbackQuery):
    await cb.message.edit_text(
        f"🏠 Главное меню\n\nТвой баланс: <b>{get_balance(cb.from_user.id)} ⭐</b>",
        reply_markup=kb_main()
    )

# ================= ПРОФИЛЬ =================
@dp.callback_query(F.data == "profile")
async def cb_profile(cb: CallbackQuery):
    bal = get_balance(cb.from_user.id)
    await cb.message.edit_text(
        f"👤 <b>Личный кабинет</b>\n\n"
        f"🆔 ID: <code>{cb.from_user.id}</code>\n"
        f"💰 Баланс: <b>{bal} ⭐</b>",
        reply_markup=kb_profile()
    )

@dp.callback_query(F.data == "topup")
async def cb_topup(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text(
        f"💳 <b>Пополнение баланса</b>\n\n"
        f"Переведите нужную сумму на ВТБ:\n"
        f"<code>{VTB_CARD}</code>\n\n"
        f"⚠️ После перевода отправьте <b>фото/файл чека</b> сюда.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="profile")]])
    )
    await state.set_state(TopupState.waiting_for_receipt)

@dp.message(TopupState.waiting_for_receipt, F.photo | F.document)
async def catch_topup_receipt(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(admin_id, file_id, 
                caption=f"💳 <b>Чек на пополнение!</b>\n👤 @{message.from_user.username} (ID: {message.from_user.id})", 
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="✅ Начислить 500₽", callback_data=f"topup_ok_{message.from_user.id}")
                ]]))
        except: pass
        
    await message.answer("⏳ Чек отправлен админу. Ожидайте начисления.")
    await state.clear()

@dp.callback_query(F.data.startswith("topup_ok_"))
async def cb_topup_ok(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS: return
    target_user = int(cb.data.split("_")[2])
    
    cursor.execute("UPDATE users SET balance = balance + 500 WHERE user_id = ?", (target_user,))
    conn.commit()
    
    await bot.send_message(target_user, f"✅ <b>Баланс пополнен на 500 ⭐!</b>")
    await cb.message.edit_caption(caption="✅ Чек одобрен, баланс начислен.")

# ================= ОБРАБОТКА САЙТА (MINI APP) =================
@dp.message(F.web_app_data)
async def web_app_handler(message: Message):
    try:
        data = json.loads(message.web_app_data.data)
        user_id = message.from_user.id
        
        # 1. ОТКРЫТИЕ КЕЙСОВ
        if data.get("action") == "open_case":
            case_id = data.get("case_id")
            price = data.get("price", 0)
            
            if get_balance(user_id) < price:
                await message.answer("❌ <b>Недостаточно звезд!</b>")
                return
            
            cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (price, user_id))
            conn.commit()
            
            win_amount = 0
            if case_id == "cheap":
                prizes = [15, 25, 50, 100]
                weights = [70, 20, 8, 2] 
                win_amount = random.choices(prizes, weights=weights, k=1)[0]
            elif case_id == "expensive":
                prizes = [50, 100, 500]
                weights = [60, 30, 10] 
                win_amount = random.choices(prizes, weights=weights, k=1)[0]
            
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (win_amount, user_id))
            conn.commit()
            
            await message.answer(
                f"☣️ <b>КЕЙС ОТКРЫТ!</b>\n\n"
                f"💸 Потрачено: {price} ⭐\n"
                f"🎉 Выбито: <b>{win_amount} ⭐</b>\n"
                f"💰 Баланс: {get_balance(user_id)} ⭐",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🎰 Играть еще", web_app=WebAppInfo(url=SITE_URL))]
                ])
            )

        # 2. РУЛЕТКА
        elif data.get("action") == "roulette":
            price = data.get("price", 50)
            
            if get_balance(user_id) < price:
                await message.answer("❌ <b>Недостаточно звезд!</b>")
                return
            
            cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (price, user_id))
            conn.commit()
            
            multipliers = [0, 2, 3]
            weights = [60, 30, 10]
            result = random.choices(multipliers, weights=weights, k=1)[0]
            
            win = price * result
            
            if win > 0:
                cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (win, user_id))
                conn.commit()
                await message.answer(
                    f"🎡 <b>РУЛЕТКА</b>\n\n"
                    f"Выпало: <b>x{result}</b>\n"
                    f"💰 Выигрыш: <b>+{win} ⭐</b>\n"
                    f"💼 Баланс: {get_balance(user_id)} ⭐",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🎡 Крутить еще", web_app=WebAppInfo(url=SITE_URL))]
                    ])
                )
            else:
                await message.answer(
                    f"🎡 <b>РУЛЕТКА</b>\n\n"
                    f"Выпало: <b>x0</b>\n"
                    f"💸 Потеряно: <b>{price} ⭐</b>\n"
                    f"💼 Баланс: {get_balance(user_id)} ⭐",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🎡 Попробовать снова", web_app=WebAppInfo(url=SITE_URL))]
                    ])
                )

        # 3. ПОПОЛНЕНИЕ (С САЙТА)
        elif data.get("action") == "topup":
            await message.answer(
                f"💳 Переведите сумму на ВТБ:\n<code>{VTB_CARD}</code>\n\nИ отправьте чек сюда."
            )

    except Exception as e:
        logging.error(f"Ошибка казино: {e}")
        await message.answer("Ошибка при игре.")

# ================= ЗАПУСК =================
async def main():
    logging.basicConfig(level=logging.INFO)
    print("🎰 Казино-бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
