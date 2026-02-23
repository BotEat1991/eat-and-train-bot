import os
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ================= TOKEN =================
TOKEN = ("8292130898:AAHCMtiTawjClEo2BU9jklCE27-4Uynd_yA")  # export TOKEN="НОВЫЙ_ТОКЕН"


# ================= НАСТРОЙКИ =================
ACTIVITY = {
    "Минимальная (0–1 трен/нед)": 1.2,
    "Лёгкая (2–3 трен/нед)": 1.375,
    "Средняя (3–5 трен/нед)": 1.55,
    "Высокая (6–7 трен/нед)": 1.725,
    "Очень высокая (спорт/2р-д)": 1.9,
}

GOALS = {
    "Похудение": "cut",
    "Поддержание": "maintain",
    "Набор массы": "bulk",
}

ADJUST = {
    "Дефицит -20%": -0.20,
    "Дефицит -10%": -0.10,
    "Норма 0%": 0.0,
    "Профицит +10%": 0.10,
    "Профицит +20%": 0.20,
}


# ================= FSM =================
class Form(StatesGroup):
    weight = State()
    height = State()
    age = State()
    sex = State()
    activity = State()
    goal = State()
    adjust = State()


# ================= ФОРМУЛЫ =================
def mifflin(w, h, a, sex):
    base = 10 * w + 6.25 * h - 5 * a
    return base + 5 if sex == "m" else base - 161


def calc_macros(cal, w, goal):
    if goal == "cut":
        p, f = 2.3, 0.8
    elif goal == "bulk":
        p, f = 1.8, 1.0
    else:
        p, f = 2.0, 0.9

    protein = w * p
    fat = w * f
    carbs = max(0, (cal - (protein * 4 + fat * 9)) / 4)

    total = cal if cal > 0 else 1
    return (
        protein,
        fat,
        carbs,
        protein * 4 / total * 100,
        fat * 9 / total * 100,
        carbs * 4 / total * 100,
    )


# ================= BOT =================
dp = Dispatcher(storage=MemoryStorage())


@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(Form.weight)
    await message.answer("Введи вес (кг):")


@dp.message(Form.weight)
async def set_weight(message: Message, state: FSMContext):
    await state.update_data(weight=float(message.text))
    await state.set_state(Form.height)
    await message.answer("Введи рост (см):")


@dp.message(Form.height)
async def set_height(message: Message, state: FSMContext):
    await state.update_data(height=float(message.text))
    await state.set_state(Form.age)
    await message.answer("Введи возраст:")


@dp.message(Form.age)
async def set_age(message: Message, state: FSMContext):
    await state.update_data(age=int(message.text))
    await state.set_state(Form.sex)

    kb = InlineKeyboardBuilder()
    kb.button(text="Мужчина", callback_data="sex:m")
    kb.button(text="Женщина", callback_data="sex:f")
    kb.adjust(2)

    await message.answer("Выбери пол:", reply_markup=kb.as_markup())


@dp.callback_query(F.data.startswith("sex:"))
async def set_sex(callback: CallbackQuery, state: FSMContext):
    await state.update_data(sex=callback.data.split(":")[1])
    await state.set_state(Form.activity)

    kb = InlineKeyboardBuilder()
    for a in ACTIVITY:
        kb.button(text=a, callback_data=f"act:{a}")
    kb.adjust(1)

    await callback.message.edit_text("Выбери активность:", reply_markup=kb.as_markup())
    await callback.answer()


@dp.callback_query(F.data.startswith("act:"))
async def set_activity(callback: CallbackQuery, state: FSMContext):
    label = callback.data.split(":")[1]
    await state.update_data(activity=ACTIVITY[label])
    await state.set_state(Form.goal)

    kb = InlineKeyboardBuilder()
    for g in GOALS:
        kb.button(text=g, callback_data=f"goal:{g}")
    kb.adjust(1)

    await callback.message.edit_text("Выбери цель:", reply_markup=kb.as_markup())
    await callback.answer()


@dp.callback_query(F.data.startswith("goal:"))
async def set_goal(callback: CallbackQuery, state: FSMContext):
    label = callback.data.split(":")[1]
    await state.update_data(goal=GOALS[label])
    await state.set_state(Form.adjust)

    kb = InlineKeyboardBuilder()
    for adj in ADJUST:
        kb.button(text=adj, callback_data=f"adj:{adj}")
    kb.adjust(1)

    await callback.message.edit_text("Выбери дефицит/профицит:", reply_markup=kb.as_markup())
    await callback.answer()


@dp.callback_query(F.data.startswith("adj:"))
async def finish(callback: CallbackQuery, state: FSMContext):
    adj_label = callback.data.split(":")[1]
    data = await state.get_data()

    required = ("weight", "height", "age", "sex", "activity", "goal")
    if any(k not in data for k in required):
        await callback.message.edit_text("Ошибка. Нажми /start")
        await callback.answer()
        return

    bmr = mifflin(data["weight"], data["height"], data["age"], data["sex"])
    tdee = bmr * data["activity"]
    calories = tdee * (1 + ADJUST[adj_label])

    protein, fat, carbs, p_pct, f_pct, c_pct = calc_macros(
        calories, data["weight"], data["goal"]
    )

    text = (
        f"🔥 Результат\n\n"
        f"Калории: {round(calories)} ккал\n\n"
        f"Белки: {round(protein)} г\n"
        f"Жиры: {round(fat)} г\n"
        f"Углеводы: {round(carbs)} г\n\n"
        f"БЖУ (%):\n"
        f"Белки: {p_pct:.1f}%\n"
        f"Жиры: {f_pct:.1f}%\n"
        f"Углеводы: {c_pct:.1f}%"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Рассчитать заново", callback_data="restart")
    kb.adjust(1)

    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@dp.callback_query(F.data == "restart")
async def restart(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(Form.weight)
    await callback.message.edit_text("Введи вес (кг):")
    await callback.answer()


# ================= MAIN =================
async def main():
   
    bot = Bot(token=TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
