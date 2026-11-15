import asyncio
import logging
import sqlite3
import random
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, 
    InlineKeyboardButton, PreCheckoutQuery, LabeledPrice
)
from aiogram.fsm.storage.memory import MemoryStorage

# ================= НАСТРОЙКИ =================
TOKEN = "8647859964:AAFvXgbvIiuTmtAEPRWFkMFS8_Zeaf97p4I"
# ==================================

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# ================= БАЗА ДАННЫХ =================
conn = sqlite3.connect("casino.db", check_same_thread=False)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Таблица пользователей (храним внутренний баланс)
cursor.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0
)""")
conn.commit()

# ================= КЛАВИАТУРЫ =================
def kb_main():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Дешевый кейс (25 ⭐)", callback_data="case_cheap")],
        [InlineKeyboardButton(text="💎 Дорогой кейс (150 ⭐)", callback_data="case_expensive")],
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile")]
    ])

def kb_back():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back")]
    ])

# ================= ОБРАБОТЧИКИ =================
@dp.message(CommandStart())
async def cmd_start(message: Message):
    # Регистрируем пользователя
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
    conn.commit()
    
    await message.answer(
        "🎰 <b>Добро пожаловать в Кейс-Казино!</b>\n\n"
        "Крути кейсы и выбивай Звезды на свой баланс.\n"
        "Выбирай кейс ниже:",
        reply_markup=kb_main()
    )

@dp.callback_query(F.data == "profile")
async def cb_profile(cb: CallbackQuery):
    user = cursor.execute("SELECT balance FROM users WHERE user_id = ?", (cb.from_user.id,)).fetchone()
    bal = user['balance'] if user else 0
    
    await cb.message.edit_text(
        f"👤 <b>Ваш профиль</b>\n\n"
        f"🆔 ID: <code>{cb.from_user.id}</code>\n"
        f"💰 Баланс: <b>{bal} ⭐</b>",
        reply_markup=kb_back()
    )

@dp.callback_query(F.data == "back")
async def cb_back(cb: CallbackQuery):
    await cb.message.edit_text("🎰 Выбирай кейс:", reply_markup=kb_main())

# ================= ПОКУПКА КЕЙСОВ (СЧЕТА) =================
@dp.callback_query(F.data == "case_cheap")
async def buy_cheap(cb: CallbackQuery):
    await cb.message.answer_invoice(
        title="Дешевый кейс",
        description="Шанс выбить до 100 звезд!",
        payload="pay_case_cheap",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Дешевый кейс", amount=25)]
    )
    await cb.answer()

@dp.callback_query(F.data == "case_expensive")
async def buy_expensive(cb: CallbackQuery):
    await cb.message.answer_invoice(
        title="Дорогой кейс",
        description="Шанс выбить 500 звезд!",
        payload="pay_case_expensive",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Дорогой кейс", amount=150)]
    )
    await cb.answer()

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)

# ================= ЛОГИКА ВЫПАДЕНИЯ =================
@dp.message(F.successful_payment)
async def success_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    uid = message.from_user.id
    win_amount = 0
    
    if payload == "pay_case_cheap":
        # Дешевый: 15 (70%), 25 (20%), 50 (8%), 100 (2%)
        prizes = [15, 25, 50, 100]
        weights = [70, 20, 8, 2]
        win_amount = random.choices(prizes, weights=weights, k=1)[0]
        
    elif payload == "pay_case_expensive":
        # Дорогой: 50 (60%), 100 (30%), 500 (10%)
        prizes = [50, 100, 500]
        weights = [60, 30, 10]
        win_amount = random.choices(prizes, weights=weights, k=1)[0]

    if win_amount > 0:
        # Начисляем выигрыш на баланс
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (win_amount, uid))
        conn.commit()
        
        # Эффект интриги
        await message.answer("🎰 <b>Крутим барабаны...</b>")
        await asyncio.sleep(1.5)
        
        user = cursor.execute("SELECT balance FROM users WHERE user_id = ?", (uid,)).fetchone()
        
        await message.answer(
            f"🎉 <b>ДЖЕКПОТ!</b>\n\n"
            f"Вы выбили: <b>{win_amount} ⭐</b>!\n"
            f"💰 Ваш баланс: <b>{user['balance']} ⭐</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎰 Крутить еще", callback_data="back")]
            ])
        )

# ================= ЗАПУСК =================
async def main():
    logging.basicConfig(level=logging.INFO)
    print("🎰 Казино-бот запущено!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())