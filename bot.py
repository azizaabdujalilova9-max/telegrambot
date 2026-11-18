import asyncio
import logging
import os
import random
import sqlite3
from pathlib import Path
from typing import Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from dotenv import load_dotenv

import database
from quiz_format import QuizFormatError, parse_quiz_json


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID_VALUE = os.getenv("ADMIN_ID", "").strip()
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(BASE_DIR / "quiz_bot.sqlite3")))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi. .env fayliga bot tokenini kiriting.")
if not ADMIN_ID_VALUE.isdigit():
    raise RuntimeError("ADMIN_ID topilmadi yoki noto'g'ri. .env fayliga Telegram user ID ni kiriting.")
ADMIN_ID = int(ADMIN_ID_VALUE)

router = Router()
dispatcher = Dispatcher()
dispatcher.include_router(router)
active_quizzes: dict[int, dict[str, Any]] = {}


class QuizStates(StatesGroup):
    waiting_for_question_count = State()


def is_admin(user_id: int) -> bool:
    print(user_id, "USER ID")
    return user_id == ADMIN_ID


def home_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="📝 Testlarni ko'rish", callback_data="user:tests")]]
    if is_admin(user_id):
        buttons.append([InlineKeyboardButton(text="⚙️ Admin panel", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📚 Testlarni boshqarish", callback_data="admin:list")],
            [InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="home")],
        ]
    )


def test_list_keyboard(tests: list[dict[str, Any]], admin: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    for test in tests:
        label = f"{test['title']} ({test['question_count']} ta savol)"
        action = "admin:delete" if admin else "user:test"
        buttons.append([InlineKeyboardButton(text=label[:64], callback_data=f"{action}:{test['id']}")])
    buttons.append([InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def question_keyboard(question_index: int, options: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=str(display_index),
            callback_data=f"quiz:answer:{question_index}:{display_index - 1}",
        )
        for display_index, _ in enumerate(options, start=1)
    ]
    rows = [buttons[index:index + 4] for index in range(0, len(buttons), 4)]
    rows.append([InlineKeyboardButton(text="⏹ To'xtatish", callback_data="quiz:stop")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def count_keyboard(test_id: int, question_count: int) -> InlineKeyboardMarkup:
    choices = sorted({count for count in (5, 10, 20) if count < question_count})
    choices.append(question_count)
    buttons = [
        InlineKeyboardButton(
            text="Hammasi" if count == question_count else str(count),
            callback_data=f"user:count:{test_id}:{count}",
        )
        for count in choices
    ]
    rows = [buttons[index:index + 3] for index in range(0, len(buttons), 3)]
    rows.append(
        [InlineKeyboardButton(text="Boshqa son kiritish", callback_data=f"user:custom:{test_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_question(quiz: dict[str, Any]) -> str:
    index = quiz["index"]
    question = quiz["questions"][index]
    choices = question["options"]
    options_text = "\n".join(f"{number}) {text}" for number, (_, text) in enumerate(choices, start=1))
    return (
        f"Savol {index + 1}/{len(quiz['questions'])}:\n"
        f"{question['question']}\n\n"
        f"Variantlar:\n{options_text}"
    )


async def start_quiz(
    message: Message,
    state: FSMContext,
    user_id: int,
    test_id: int,
    requested_count: int,
) -> None:
    test = database.get_test(DATABASE_PATH, test_id)
    questions = database.get_questions(DATABASE_PATH, test_id)
    if test is None or not questions:
        await state.clear()
        await message.answer("Bu test mavjud emas yoki savollari yo'q.")
        return

    selected_questions = random.sample(questions, min(requested_count, len(questions)))
    for question in selected_questions:
        indexed_options = list(enumerate(question["options"]))
        random.shuffle(indexed_options)
        question["options"] = indexed_options
        question["shuffled_correct_index"] = next(
            index for index, (original_index, _) in enumerate(indexed_options)
            if original_index == question["correct_index"]
        )

    active_quizzes[user_id] = {
        "test_id": test_id,
        "title": test["title"],
        "questions": selected_questions,
        "index": 0,
        "correct": 0,
        "answers": [],
        "answered": False,
    }
    await state.clear()
    quiz = active_quizzes[user_id]
    await message.answer(
        format_question(quiz),
        reply_markup=question_keyboard(0, quiz["questions"][0]["options"]),
    )


async def finish_quiz(user_id: int, message: Message, feedback: str = "") -> None:
    quiz = active_quizzes.pop(user_id, None)
    if quiz is None:
        await message.answer("Faol test topilmadi.")
        return
    total = len(quiz["answers"])
    correct = quiz["correct"]
    database.save_attempt(
        DATABASE_PATH,
        user_id,
        quiz["test_id"],
        quiz["title"],
        total,
        correct,
        quiz["answers"],
    )
    percent = round(correct * 100 / total) if total else 0
    result = (
        f"🏁 Test yakunlandi!\n"
        f"Test: {quiz['title']}\n"
        f"Natija: {correct}/{total}\n"
        f"Foiz: {percent}%"
        f"{feedback}"
    )
    await message.edit_text(result, reply_markup=home_keyboard(user_id))


@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    database.save_user(
        DATABASE_PATH,
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
    )
    await state.clear()
    await message.answer(
        "Assalomu alaykum! Kerakli testni tanlang.",
        reply_markup=home_keyboard(message.from_user.id),
    )


@router.message(Command("admin"))
async def handle_admin_command(message: Message) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        await message.answer("Bu buyruq faqat admin uchun.")
        return
    await message.answer(
        "Admin panel.\nTest qo'shish uchun JSON faylni shu chatga yuboring.",
        reply_markup=admin_keyboard(),
    )


@router.callback_query(F.data == "home")
async def handle_home(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    await state.clear()
    if callback.message.text:
        await callback.message.edit_text(
            "Assalomu alaykum! Kerakli testni tanlang.",
            reply_markup=home_keyboard(callback.from_user.id),
        )
    await callback.answer()


@router.callback_query(F.data == "user:tests")
async def handle_test_list(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer()
        return
    tests = database.list_tests(DATABASE_PATH)
    if not tests:
        await callback.message.edit_text("Hozircha testlar mavjud emas.", reply_markup=home_keyboard(callback.from_user.id))
    else:
        await callback.message.edit_text("Yechish uchun testni tanlang:", reply_markup=test_list_keyboard(tests))
    await callback.answer()


@router.callback_query(F.data.startswith("user:test:"))
async def handle_test_selected(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    test_id = int(callback.data.split(":")[2])
    test = database.get_test(DATABASE_PATH, test_id)
    questions = database.get_questions(DATABASE_PATH, test_id)
    if test is None or not questions:
        await callback.answer("Test topilmadi.", show_alert=True)
        return
    await state.update_data(test_id=test_id)
    await state.set_state(QuizStates.waiting_for_question_count)
    await callback.message.edit_text(
        f"“{test['title']}” testida {len(questions)} ta savol bor.\n"
        "Nechta savol yechmoqchisiz?",
        reply_markup=count_keyboard(test_id, len(questions)),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("user:count:"))
async def handle_count_selected(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await callback.answer()
        return
    _, _, test_id_text, count_text = callback.data.split(":")
    await callback.message.delete()
    await start_quiz(
        callback.message,
        state,
        callback.from_user.id,
        int(test_id_text),
        int(count_text),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("user:custom:"))
async def handle_custom_count(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await callback.answer()
        return
    test_id = int(callback.data.split(":")[2])
    await state.update_data(test_id=test_id)
    await state.set_state(QuizStates.waiting_for_question_count)
    await callback.message.answer("Yechmoqchi bo'lgan savollar sonini raqamda yuboring.")
    await callback.answer()


@router.message(QuizStates.waiting_for_question_count)
async def handle_custom_count_message(message: Message, state: FSMContext) -> None:
    if message.from_user is None or message.text is None:
        await message.answer("Savollar sonini raqamda yuboring.")
        return
    if not message.text.strip().isdigit():
        await message.answer("Iltimos, savollar sonini musbat raqamda kiriting.")
        return
    test_id = (await state.get_data()).get("test_id")
    test = database.get_test(DATABASE_PATH, test_id) if test_id is not None else None
    questions = database.get_questions(DATABASE_PATH, test_id) if test is not None else []
    requested_count = int(message.text.strip())
    if test is None or not questions:
        await state.clear()
        await message.answer("Bu test mavjud emas yoki savollari yo'q.")
        return
    if not 1 <= requested_count <= len(questions):
        await message.answer(f"1 dan {len(questions)} gacha bo'lgan sonni kiriting.")
        return
    await start_quiz(message, state, message.from_user.id, test_id, requested_count)


@router.callback_query(F.data.startswith("quiz:answer:"))
async def handle_answer(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer()
        return
    quiz = active_quizzes.get(callback.from_user.id)
    if quiz is None:
        await callback.answer("Test sessiyasi tugagan. /start ni bosing.", show_alert=True)
        return
    _, _, question_index_text, selected_index_text = callback.data.split(":")
    question_index, selected_index = int(question_index_text), int(selected_index_text)
    if question_index != quiz["index"] or quiz["answered"]:
        await callback.answer("Bu savolga javob berilgan.")
        return
    question = quiz["questions"][question_index]
    if not 0 <= selected_index < len(question["options"]):
        await callback.answer("Noto'g'ri variant.", show_alert=True)
        return

    selected_original_index, selected_text = question["options"][selected_index]
    is_correct = selected_original_index == question["correct_index"]
    quiz["answered"] = True
    quiz["correct"] += int(is_correct)
    quiz["answers"].append(
        {
            "question": question["question"],
            "selected_option": selected_text,
            "is_correct": is_correct,
        }
    )
    feedback = "\n\n✅ To'g'ri!" if is_correct else (
        f"\n\n❌ Noto'g'ri.\nTo'g'ri javob: "
        f"{question['options'][question['shuffled_correct_index']][1]}"
    )

    if question_index + 1 == len(quiz["questions"]):
        await finish_quiz(callback.from_user.id, callback.message, feedback)
    else:
        next_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="➡️ Keyingi savol", callback_data=f"quiz:next:{question_index}")],
                [InlineKeyboardButton(text="⏹ To'xtatish", callback_data="quiz:stop")],
            ]
        )
        await callback.message.edit_text(format_question(quiz) + feedback, reply_markup=next_keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("quiz:next:"))
async def handle_next_question(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer()
        return
    quiz = active_quizzes.get(callback.from_user.id)
    if quiz is None:
        await callback.answer("Test sessiyasi tugagan. /start ni bosing.", show_alert=True)
        return
    question_index = int(callback.data.split(":")[2])
    if question_index != quiz["index"] or not quiz["answered"]:
        await callback.answer("Bu savol allaqachon o'tkazilgan.")
        return
    quiz["index"] += 1
    quiz["answered"] = False
    await callback.message.edit_text(
        format_question(quiz),
        reply_markup=question_keyboard(quiz["index"], quiz["questions"][quiz["index"]]["options"]),
    )
    await callback.answer()


@router.callback_query(F.data == "quiz:stop")
async def handle_stop_quiz(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer()
        return
    if callback.from_user.id not in active_quizzes:
        await callback.answer("Faol test topilmadi.")
        return
    await finish_quiz(callback.from_user.id, callback.message)
    await callback.answer()


@router.callback_query(F.data == "admin:menu")
async def handle_admin_menu(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer()
        return
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    await callback.message.edit_text(
        "Admin panel.\nTest qo'shish uchun JSON faylni shu chatga yuboring.",
        reply_markup=admin_keyboard(),
    )
    await callback.answer()


@router.message(F.document)
async def handle_json_upload(message: Message) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        await message.answer("Test faylini faqat admin qo'sha oladi.")
        return
    document = message.document
    if document is None or not document.file_name or Path(document.file_name).suffix.lower() != ".json":
        await message.answer("Iltimos, .json formatidagi fayl yuboring.")
        return
    try:
        downloaded = await message.bot.download(document)
        if downloaded is None:
            raise OSError("Telegram faylni yuklab bermadi.")
        quiz_data = parse_quiz_json(downloaded.read())
        test_id = database.add_test(
            DATABASE_PATH,
            quiz_data["title"],
            quiz_data["description"],
            quiz_data["questions"],
        )
    except QuizFormatError as error:
        await message.answer(f"JSON formati xato:\n{error}")
        return
    except (OSError, TelegramAPIError):
        logging.exception("Test JSON faylini yuklashda xatolik")
        await message.answer("Faylni o'qib bo'lmadi. JSON UTF-8 formatida ekanini tekshiring.")
        return
    except sqlite3.Error:
        logging.exception("Testni bazaga saqlashda kutilmagan xatolik")
        await message.answer("Testni saqlashda xatolik yuz berdi.")
        return
    await message.answer(
        f"✅ “{quiz_data['title']}” testi qo'shildi.\n"
        f"Savollar soni: {len(quiz_data['questions'])}\nID: {test_id}"
    )


@router.callback_query(F.data == "admin:list")
async def handle_admin_test_list(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer()
        return
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    tests = database.list_tests(DATABASE_PATH)
    text = "O'chirish uchun testni tanlang:" if tests else "O'chirish uchun testlar mavjud emas."
    await callback.message.edit_text(text, reply_markup=test_list_keyboard(tests, admin=True))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:delete:"))
async def handle_delete_prompt(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer()
        return
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    test_id = int(callback.data.split(":")[2])
    test = database.get_test(DATABASE_PATH, test_id)
    if test is None:
        await callback.answer("Test topilmadi.")
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Ha, o'chirilsin", callback_data=f"admin:confirm:{test_id}"),
                InlineKeyboardButton(text="Bekor qilish", callback_data="admin:list"),
            ]
        ]
    )
    await callback.message.edit_text(
        f"“{test['title']}” testini o'chirmoqchimisiz?",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:confirm:"))
async def handle_delete_confirm(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer()
        return
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    test_id = int(callback.data.split(":")[2])
    deleted = database.delete_test(DATABASE_PATH, test_id)
    await callback.message.edit_text(
        "✅ Test o'chirildi." if deleted else "Test topilmadi.",
        reply_markup=admin_keyboard(),
    )
    await callback.answer()


async def main() -> None:
    database.initialize_database(DATABASE_PATH)
    bot = Bot(token=BOT_TOKEN)
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
