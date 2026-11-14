import asyncio
import logging
import sys
import json
import os
import random
import shutil
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union

# === ВЕБ-ЗАГЛУШКА ДЛЯ RENDER (ОБЯЗАТЕЛЬНО В САМОМ ВЕРХУ) ===
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is active!")

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

threading.Thread(target=run_server, daemon=True).start()
# ==========================================================

# Импорты игровых модулей и словарей
from vocabulary_detective import DETECTIVE_SCENARIOS
from vocabulary_adventure import ADVENTURE_SCENARIOS
from vocabulary_chat_sim import CHAT_SCENARIOS, FAIL_SCENARIOS, VICTORY_SCENARIOS

from aiogram import Bot, Dispatcher, F, Router, html
from aiogram.filters import Command, StateFilter, CommandStart, Filter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    PreCheckoutQuery,
    LabeledPrice,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    ErrorEvent,
    ChatMemberUpdated
)
from aiogram.exceptions import TelegramAPIError

from vocabulary_homework import get_random_homework_task, get_task_by_key

# ==============================================================================
# СОЗДАЕМ РОУТЕР
# ==============================================================================
router = Router()

@router.message(F.text.in_(["📚 Домашнее задание", "/homework", "📝 ДЗ"]))
async def handle_homework_request(message: Message) -> None:
    task_key, hw = get_random_homework_task()
    
    keyboard_buttons = []
    for opt in hw["options"]:
        marker = "1" if opt["correct"] else "0"
        keyboard_buttons.append([
            InlineKeyboardButton(text=opt["text"], callback_data=f"hw_ans:{marker}")
        ])
    
    keyboard_buttons.append([InlineKeyboardButton(text="🔄 Другое ДЗ", callback_data="hw_reload")])
    keyboard_buttons.append([InlineKeyboardButton(text="📖 Справочник падежей", callback_data="action_grammar_shortcut")])
    keyboard_buttons.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="action_main_menu")])

    hw_text = (
        f"🎯 **{hw['title']}**\n\n"
        f"💡 _{hw['description']}_\n\n"
        f"❓ **Задание:**\n{hw['task_text']}"
    )

    await message.answer(
        hw_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "hw_reload")
async def reload_homework_callback(callback: CallbackQuery) -> None:
    task_key, hw = get_random_homework_task()
    
    keyboard_buttons = []
    for opt in hw["options"]:
        marker = "1" if opt["correct"] else "0"
        keyboard_buttons.append([
            InlineKeyboardButton(text=opt["text"], callback_data=f"hw_ans:{marker}")
        ])
    
    keyboard_buttons.append([InlineKeyboardButton(text="🔄 Другое ДЗ", callback_data="hw_reload")])
    keyboard_buttons.append([InlineKeyboardButton(text="📖 Справочник падежей", callback_data="action_grammar_shortcut")])
    keyboard_buttons.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="action_main_menu")])

    await callback.message.edit_text(
        f"🎯 **{hw['title']}**\n\n"
        f"💡 _{hw['description']}_\n\n"
        f"❓ **Задание:**\n{hw['task_text']}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons),
        parse_mode="Markdown"
    )
    await callback.answer()


# ==============================================================================
# ИГРОВЫЕ МОДУЛИ И ПРЕМИУМ-КВЕСТЫ
# ==============================================================================

# --- 1. Детективный квест ---
@router.message(F.text.in_(["🔍 Детективный квест", "/detective", "🕵️‍♂️ Расследование"]))
async def start_detective_quest(message: Message) -> None:
    user_id = message.from_user.id
    database = load_db()
    user_data = database.get(str(user_id), {})
    is_premium = user_data.get("is_premium", False)

    if not is_premium:
        await message.answer(
            "🔒 **Детективный квест «Дело №404» доступен по Премиум-подписке!**\n\n"
            "Масштабное расследование кражи в Лондоне: сбор улик, допросы, тайные локации и проверка сленга.\n"
            "Стоимость доступа: **50 Telegram Stars (⭐)**.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⭐ Купить Премиум за 50 Звезд", callback_data="buy_premium_trigger")]
            ]),
            parse_mode="Markdown"
        )
        return

    money = 50
    energy = 100
    rep = 10
    clues = 0
    scene = DETECTIVE_SCENARIOS["start"]

    keyboard_buttons = []
    for btn in scene["buttons"]:
        m_change = btn.get("money", 0)
        e_change = btn.get("energy", 0)
        r_change = btn.get("rep", 0)
        c_change = btn.get("clues", 0)

        cb_data = f"det:{btn['next']}:{money + m_change}:{energy + e_change}:{rep + r_change}:{clues + c_change}"
        keyboard_buttons.append([InlineKeyboardButton(text=btn["text"], callback_data=cb_data)])

    stats_line = f"💷 £{money} | ⚡ {energy}% | 🔥 Реп: {rep} | 🔎 Улики: {clues}"
    text = f"{stats_line}\n━━━━━━━━━━━━━━━━━━━\n\n*{scene['title']}*\n\n{scene['text']}"

    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("det:"))
async def process_detective_choice(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    next_key = parts[1]
    money = int(parts[2])
    energy = int(parts[3])
    rep = int(parts[4])
    clues = int(parts[5])

    scene = DETECTIVE_SCENARIOS.get(next_key, DETECTIVE_SCENARIOS["start"])

    keyboard_buttons = []
    for btn in scene.get("buttons", []):
        new_m = money + btn.get("money", 0)
        new_e = energy + btn.get("energy", 0)
        new_r = rep + btn.get("rep", 0)
        new_c = clues + btn.get("clues", 0)

        cb_data = f"det:{btn['next']}:{new_m}:{new_e}:{new_r}:{new_c}"
        keyboard_buttons.append([InlineKeyboardButton(text=btn["text"], callback_data=cb_data)])

    stats_line = f"💷 £{money} | ⚡ {energy}% | 🔥 Реп: {rep} | 🔎 Улики: {clues}"
    text = f"{stats_line}\n━━━━━━━━━━━━━━━━━━━\n\n*{scene['title']}*\n\n{scene['text']}"

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons),
        parse_mode="Markdown"
    )
    await callback.answer()


# --- 2. Чат-симулятор ---
@router.message(F.text.in_(["💬 Чат-симулятор", "/chat_sim", "📱 Симулятор"]))
async def start_chat_simulator(message: Message) -> None:
    user_id = message.from_user.id
    database = load_db()
    user_data = database.get(str(user_id), {})
    is_premium = user_data.get("is_premium", False)

    if not is_premium:
        await message.answer(
            "🔒 **Чат-симулятор доступен по Премиум-подписке!**\n\n"
            "Интерактивная переписка с коллегами, шпионами и друзьями на живом английском.\n"
            "Стоимость доступа: **50 Telegram Stars (⭐)**.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⭐ Купить Премиум за 50 Звезд", callback_data="buy_premium_trigger")]
            ]),
            parse_mode="Markdown"
        )
        return

    scene = CHAT_SCENARIOS["start"]
    keyboard_buttons = []
    for opt in scene["options"]:
        marker = "1" if opt["correct"] else "0"
        keyboard_buttons.append([
            InlineKeyboardButton(text=opt["text"], callback_data=f"chatsim:{opt['next']}:{marker}")
        ])

    chat_text = (
        f"💬 **{scene['character']}**\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"📱 *{scene['dialogue']}*"
    )

    await message.answer(
        chat_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("chatsim:"))
async def process_chat_choice(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    next_key = parts[1]
    is_correct = parts[2] == "1"

    if next_key.startswith("victory_"):
        scen = CHAT_SCENARIOS[next_key]
        await callback.message.edit_text(
            f"🎉 **{scen['title']}**\n\n{scen['text']}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=VICTORY_SCENARIOS['button'], callback_data="chatsim_restart")]
            ]),
            parse_mode="Markdown"
        )
        await callback.answer()
        return

    if not is_correct or next_key.startswith("fail_"):
        scen = CHAT_SCENARIOS.get(next_key, {"title": "💀 Game Over", "text": "Вы совершили фатальную ошибку в диалоге."})
        await callback.message.edit_text(
            f"❌ **{scen['title']}**\n\n{scen['text']}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=FAIL_SCENARIOS['button'], callback_data="chatsim_restart")]
            ]),
            parse_mode="Markdown"
        )
        await callback.answer()
        return

    scene = CHAT_SCENARIOS.get(next_key, CHAT_SCENARIOS["start"])
    keyboard_buttons = []
    for opt in scene["options"]:
        marker = "1" if opt["correct"] else "0"
        keyboard_buttons.append([
            InlineKeyboardButton(text=opt["text"], callback_data=f"chatsim:{opt['next']}:{marker}")
        ])

    chat_text = (
        f"💬 **Эмуляция чата | Собеседник: {scene['character']}**\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ *{scene.get('feedback', 'Ответ принят.')}*\n\n"
        f"📱 *{scene['dialogue']}*"
    )

    await callback.message.edit_text(
        chat_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "chatsim_restart")
async def restart_chatsim(callback: CallbackQuery) -> None:
    scene = CHAT_SCENARIOS["start"]
    keyboard_buttons = []
    for opt in scene["options"]:
        marker = "1" if opt["correct"] else "0"
        keyboard_buttons.append([
            InlineKeyboardButton(text=opt["text"], callback_data=f"chatsim:{opt['next']}:{marker}")
        ])

    chat_text = (
        f"💬 **{scene['character']}**\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"📱 *{scene['dialogue']}*"
    )
    await callback.message.edit_text(
        chat_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons),
        parse_mode="Markdown"
    )
    await callback.answer()


# --- 3. Квест в Лондоне (RPG) ---
@router.message(F.text.in_(["🗺️ Квест в Лондоне", "/adventure", "🕹️ RPG-игра"]))
async def start_adventure_quest(message: Message) -> None:
    user_id = message.from_user.id
    database = load_db()
    user_data = database.get(str(user_id), {})
    is_premium = user_data.get("is_premium", False)

    if not is_premium:
        await message.answer(
            "🔒 **Кинематографический триллер «Лондонский след» доступен по Премиум-подписке!**\n\n"
            "Полноценная сюжетная новелла, десятки развилок, опасные выборы и проверка на знание британского сленга.\n"
            "Стоимость доступа: **50 Telegram Stars (⭐)**.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⭐ Купить Премиум за 50 Звезд", callback_data="buy_premium_trigger")]
            ]),
            parse_mode="Markdown"
        )
        return

    money = 40
    energy = 100
    rep = 10
    scene = ADVENTURE_SCENARIOS["start"]

    keyboard_buttons = []
    for btn in scene["buttons"]:
        cb_data = f"adv:{btn['next']}:{money + btn.get('money', 0)}:{energy + btn.get('energy', 0)}:{rep + btn.get('rep', 0)}"
        keyboard_buttons.append([InlineKeyboardButton(text=btn["text"], callback_data=cb_data)])

    stats_line = f"💷 **Деньги:** £{money} | ⚡ **Энергия:** {energy}% | 🔥 **Репутация:** {rep}"
    text = f"{stats_line}\n━━━━━━━━━━━━━━━━━━━\n\n*{scene['title']}*\n\n{scene['text']}"

    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("adv:"))
async def process_adventure_choice(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    next_scene_key = parts[1]
    money = int(parts[2])
    energy = int(parts[3])
    rep = int(parts[4])

    scene = ADVENTURE_SCENARIOS.get(next_scene_key, ADVENTURE_SCENARIOS["start"])

    keyboard_buttons = []
    for btn in scene.get("buttons", []):
        new_money = money + btn.get("money", 0)
        new_energy = energy + btn.get("energy", 0)
        new_rep = rep + btn.get("rep", 0)
        
        cb_data = f"adv:{btn['next']}:{new_money}:{new_energy}:{new_rep}"
        keyboard_buttons.append([InlineKeyboardButton(text=btn["text"], callback_data=cb_data)])

    stats_line = f"💷 **Деньги:** £{money} | ⚡ **Энергия:** {energy}% | 🔥 **Репутация:** {rep}"
    text = f"{stats_line}\n━━━━━━━━━━━━━━━━━━━\n\n*{scene['title']}*\n\n{scene['text']}"

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons),
        parse_mode="Markdown"
    )
    await callback.answer()


# ==============================================================================
# ЗАЩИЩЕННЫЙ ИМПОРТ СЛОВАРЕЙ ВСЕХ УРОВНЕЙ (A1, A2, B1, B2, C1)
# ==============================================================================
try:
    from vocabulary_a1 import WORDS_A1
except ImportError:
    WORDS_A1 = [
        {"word": "Hello", "trans": "[həˈloʊ]", "ru": "Привет", "ex": "Hello world, nice to meet you."},
        {"word": "Cat", "trans": "[kæt]", "ru": "Кот", "ex": "The cat is sleeping on the warm sofa."},
        {"word": "Water", "trans": "[ˈwɔː.tər]", "ru": "Вода", "ex": "Please give me a glass of water."}
    ]

try:
    from vocabulary_a2 import WORDS_A2
except ImportError:
    WORDS_A2 = [
        {"word": "Example", "trans": "[ɪɡˈzɑːm.pəl]", "ru": "Пример", "ex": "This is a classic example of clean code."},
        {"word": "Journey", "trans": "[ˈdʒɜː.ni]", "ru": "Путешествие", "ex": "Life is a long and exciting journey."}
    ]

try:
    from vocabulary_b1 import WORDS_B1
except ImportError:
    WORDS_B1 = [
        {"word": "Access", "trans": "[ˈæk.ses]", "ru": "Доступ", "ex": "Get access to confidential system files."},
        {"word": "Develop", "trans": "[dɪˈvel.əp]", "ru": "Развивать", "ex": "Develop high-performance applications in Python."}
    ]

try:
    from vocabulary_b2 import WORDS_B2
except ImportError:
    WORDS_B2 = [
        {"word": "Ability", "trans": "[əˈbɪl.ə.ti]", "ru": "Способность", "ex": "Natural ability to solve complex mathematical problems."},
        {"word": "Efficient", "trans": "[ɪˈfɪʃ.ənt]", "ru": "Эффективный", "ex": "Efficient algorithms save CPU time and memory."}
    ]

try:
    from vocabulary_c1 import WORDS_C1
except ImportError:
    WORDS_C1 = [
        {"word": "Abundant", "trans": "[əˈbʌn.dənt]", "ru": "Изобильный", "ex": "Abundant natural resources in this specific region."},
        {"word": "Ephemeral", "trans": "[ɪˈfem.ər.əl]", "ru": "Эфемерный", "ex": "Ephemeral digital trends come and go rapidly."}
    ]

# ==============================================================================
# ЛОГИРОВАНИЕ И КОНФИГУРАЦИЯ БАЗЫ ДАННЫХ
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("LanguageBotCore")

BOT_TOKEN = "9136166835:AAFyiKv_mEdALdqv_jppx4iWbng37SRP-RQ"
ADMIN_TELEGRAM_ID = 9136166835

DB_FILENAME = "users_database.json"
DB_BACKUP_FILENAME = "users_database_backup.json"

def initialize_database() -> None:
    if not os.path.exists(DB_FILENAME):
        logger.info("Создание нового файла базы данных пользователей...")
        initial_data = {}
        with open(DB_FILENAME, "w", encoding="utf-8") as f:
            json.dump(initial_data, f, ensure_ascii=False, indent=4)

def load_db() -> Dict[str, Any]:
    initialize_database()
    try:
        with open(DB_FILENAME, "r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError as jde:
        logger.error(f"Поврежден файл JSON базы данных ({jde}). Восстановление из бэкапа...")
        if os.path.exists(DB_BACKUP_FILENAME):
            try:
                with open(DB_BACKUP_FILENAME, "r", encoding="utf-8") as backup_file:
                    data = json.load(backup_file)
                return data
            except Exception:
                pass
        return {}
    except Exception:
        return {}

def save_db(data: Dict[str, Any]) -> None:
    try:
        if os.path.exists(DB_FILENAME):
            shutil.copy(DB_FILENAME, DB_BACKUP_FILENAME)
        with open(DB_FILENAME, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Ошибка сохранения БД: {e}")

initialize_database()


# ==============================================================================
# МАШИНА СОСТОЯНИЙ (FSM)
# ==============================================================================
class BotStates(StatesGroup):
    selecting_vocabulary_level = State()
    active_learning_session = State()
    quiz_question_active = State()
    settings_editing_profile = State()
    admin_broadcast_message = State()
    support_dialogue = State()


# ==============================================================================
# СПРАВОЧНИК ПАДЕЖЕЙ
# ==============================================================================
EXTENDED_GRAMMAR_DATABASE = {
    "nominatiivi": {
        "title": "Nominatiivi (Именительный падеж)",
        "questions": "Kuka? Mikä? (Кто? Что?)",
        "purpose": "Словарная форма слова.",
        "rules": "Нулевое окончание в единственном числе.",
        "examples": ["Tämä on auto. (Это машина.)", "Koira nukkuu. (Собака спит.)"],
        "tips": "Используется при прямом упоминании."
    },
    "genetiivi": {
        "title": "Genetiivi (Родительный падеж)",
        "questions": "Kenen? Minkä? (Кого? Чего?)",
        "purpose": "Обозначает принадлежность.",
        "rules": "Окончание: -n.",
        "examples": ["Tämä on isän auto. (Это машина отца.)"],
        "tips": "Обратите внимание на чередование ступеней."
    },
    "partitiivi": {
        "title": "Partitiivi (Партитив)",
        "questions": "Ketä? Mitä? (Кого? Что?)",
        "purpose": "Применяется после числительных и при отрицании.",
        "rules": "Окончания: -a, -ä, -ta, -tä.",
        "examples": ["Minä syön leipää. (Я ем хлеб.)", "En ymmärrä. (Я не понимаю.)"],
        "tips": "Самый частый падеж в речи."
    }
}


# ==============================================================================
# КЛАВИАТУРЫ
# ==============================================================================
def build_main_menu_keyboard(is_administrator: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="📚 Учить слова"), KeyboardButton(text="🎯 Режим тестов")],
        [KeyboardButton(text="🔍 Детективный квест"), KeyboardButton(text="💬 Чат-симулятор")],
        [KeyboardButton(text="🗺️ Квест в Лондоне"), KeyboardButton(text="⭐ Купить Премиум")],
        [KeyboardButton(text="👤 Профиль и Статистика"), KeyboardButton(text="📖 Справочник падежей")],
        [KeyboardButton(text="⚙️ Настройки")]
    ]
    if is_administrator:
        rows.append([KeyboardButton(text="👑 Панель администратора")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, persistent=True)

def build_levels_selection_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🟢 Уровень A1", callback_data="setlevel_a1")],
            [InlineKeyboardButton(text="🟢 Уровень A2", callback_data="setlevel_a2")],
            [InlineKeyboardButton(text="🟡 Уровень B1", callback_data="setlevel_b1")],
            [InlineKeyboardButton(text="🟠 Уровень B2", callback_data="setlevel_b2")],
            [InlineKeyboardButton(text="🔴 Уровень C1 (Премиум ⭐)", callback_data="setlevel_c1")],
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="action_main_menu")]
        ]
    )

def build_learning_actions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Следующее слово", callback_data="action_next_word")],
            [InlineKeyboardButton(text="🔤 Изменить уровень", callback_data="action_change_level")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="action_main_menu")]
        ]
    )

def build_grammar_directory_keyboard() -> InlineKeyboardMarkup:
    keyboard_rows = []
    for code, info in EXTENDED_GRAMMAR_DATABASE.items():
        short_title = info["title"].split(" ")[0]
        keyboard_rows.append([InlineKeyboardButton(text=f"📌 {short_title}", callback_data=f"grammar_info_{code}")])
    keyboard_rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="action_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


# ==============================================================================
# БАЗОВЫЕ ОБРАБОТЧИКИ (/start, ПРОФИЛЬ, СПРАВОЧНИК)
# ==============================================================================
@router.message(CommandStart())
async def handle_start_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    uid_str = str(message.from_user.id)
    database = load_db()
    
    if uid_str not in database:
        database[uid_str] = {
            "username": message.from_user.username or "NoUsername",
            "first_name": message.from_user.first_name or "Ученик",
            "level": "a1",
            "words_learned": 0,
            "correct_answers": 0,
            "quiz_score": 0,
            "is_premium": False,
            "joined_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_db(database)

    is_admin = message.from_user.id == ADMIN_TELEGRAM_ID
    
    welcome_message = (
        f"👋 Здравствуй, **{html.quote(message.from_user.first_name)}**!\n\n"
        "Добро пожаловать в систему изучения языковой лексики и премиум-квестов.\n"
        "Выбирай нужный раздел в меню ниже 👇"
    )
    
    await message.answer(
        welcome_message,
        parse_mode="Markdown",
        reply_markup=build_main_menu_keyboard(is_administrator=is_admin)
    )

@router.message(F.text == "👤 Профиль и Статистика")
async def handle_profile_request(message: Message) -> None:
    uid_str = str(message.from_user.id)
    database = load_db()
    user_info = database.get(uid_str, {
        "level": "a1", "words_learned": 0, "correct_answers": 0,
        "quiz_score": 0, "is_premium": False, "joined_date": "Неизвестно"
    })
    
    sub_status = "🟢 Активна (Премиум ⭐)" if user_info.get("is_premium") else "⚪️ Базовый"
    
    profile_text = (
        f"📊 **Твой персональный профиль:**\n\n"
        f"👤 Имя: {html.quote(message.from_user.first_name)}\n"
        f"🆔 ID: `{message.from_user.id}`\n"
        f"📈 Уровень: `{user_info.get('level').upper()}`\n"
        f"🧠 Просмотрено слов: `{user_info.get('words_learned', 0)}`\n"
        f"✨ Правильных ответов: `{user_info.get('correct_answers', 0)}`\n"
        f"🏆 Очки: `{user_info.get('quiz_score', 0)}`\n"
        f"💎 Подписка: {sub_status}\n"
    )
    await message.answer(profile_text, parse_mode="Markdown")

@router.message(F.text == "📖 Справочник падежей")
async def handle_grammar_menu_request(message: Message) -> None:
    await message.answer(
        "📚 **Интерактивный справочник грамматики:**",
        parse_mode="Markdown",
        reply_markup=build_grammar_directory_keyboard()
    )

@router.callback_query(F.data.startswith("grammar_info_"))
async def process_grammar_card_callback(callback: CallbackQuery) -> None:
    code = callback.data.split("_")[2]
    data = EXTENDED_GRAMMAR_DATABASE.get(code)
    if not data:
        await callback.answer("⚠️ Не найдено.", show_alert=True)
        return
    exs = "\n".join([f"• {ex}" for ex in data["examples"]])
    text = f"📖 **{data['title']}**\n\n❓ Вопросы: `{data['questions']}`\n\n🎯 Назначение: {data['purpose']}\n\n💡 Примеры:\n{exs}"
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=build_grammar_directory_keyboard())
    await callback.answer()

@router.callback_query(F.data == "action_main_menu")
async def process_return_to_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    is_admin = callback.from_user.id == ADMIN_TELEGRAM_ID
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer("🏠 Главное меню:", reply_markup=build_main_menu_keyboard(is_administrator=is_admin))
    await callback.answer()


# ==============================================================================
# МОДУЛЬ ОБУЧЕНИЯ СЛОВАМ И ТЕСТОВ
# ==============================================================================
@router.message(F.text == "📚 Учить слова")
async def entry_vocabulary_training(message: Message, state: FSMContext) -> None:
    await message.answer(
        "🔤 **Выбери языковой уровень:**",
        parse_mode="Markdown",
        reply_markup=build_levels_selection_keyboard()
    )
    await state.set_state(BotStates.selecting_vocabulary_level)

@router.callback_query(F.data.startswith("setlevel_"), StateFilter(BotStates.selecting_vocabulary_level, BotStates.active_learning_session))
async def process_vocabulary_level_selection(callback: CallbackQuery, state: FSMContext) -> None:
    lvl = callback.data.split("_")[1]
    uid_str = str(callback.from_user.id)
    
    if lvl == "c1":
        database = load_db()
        if not database.get(uid_str, {}).get("is_premium", False):
            await callback.answer("⚠️ Уровень C1 доступен только по Премиум-подписке ⭐!", show_alert=True)
            return

    database = load_db()
    if uid_str in database:
        database[uid_str]["level"] = lvl
        save_db(database)

    await state.update_data(active_vocab_level=lvl)
    await state.set_state(BotStates.active_learning_session)
    await callback.message.edit_text(f"✅ Уровень изменен на **{lvl.upper()}**.", parse_mode="Markdown")
    await dispatch_random_vocabulary_card(callback.message, lvl, replace_message=True)
    await callback.answer()

async def dispatch_random_vocabulary_card(message: Message, level_code: str, replace_message: bool = False) -> None:
    maps = {"a1": WORDS_A1, "a2": WORDS_A2, "b1": WORDS_B1, "b2": WORDS_B2, "c1": WORDS_C1}
    pool = maps.get(level_code, WORDS_A1)
    word = random.choice(pool)
    
    card = (
        f"📖 **Карточка ({level_code.upper()})**\n\n"
        f"🔤 **{html.quote(word.get('word', ''))}**\n"
        f"🔊 `{html.quote(word.get('trans', ''))}`\n"
        f"🇷🇺 **{html.quote(word.get('ru', ''))}**\n\n"
        f"💡 *{html.quote(word.get('ex', ''))}*"
    )
    
    uid_str = str(message.chat.id)
    database = load_db()
    if uid_str in database:
        database[uid_str]["words_learned"] = database[uid_str].get("words_learned", 0) + 1
        save_db(database)

    if replace_message:
        try:
            await message.edit_text(card, parse_mode="Markdown", reply_markup=build_learning_actions_keyboard())
        except Exception:
            await message.answer(card, parse_mode="Markdown", reply_markup=build_learning_actions_keyboard())
    else:
        await message.answer(card, parse_mode="Markdown", reply_markup=build_learning_actions_keyboard())

@router.callback_query(F.data == "action_next_word", StateFilter(BotStates.active_learning_session))
async def process_next_word_button(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    lvl = data.get("active_vocab_level", "a1")
    await dispatch_random_vocabulary_card(callback.message, lvl, replace_message=True)
    await callback.answer()

@router.callback_query(F.data == "action_change_level")
async def process_change_level_button(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text("🔤 Выбери уровень:", parse_mode="Markdown", reply_markup=build_levels_selection_keyboard())
    await state.set_state(BotStates.selecting_vocabulary_level)
    await callback.answer()

@router.message(F.text == "🎯 Режим тестов")
async def entry_quiz_session(message: Message, state: FSMContext) -> None:
    uid_str = str(message.from_user.id)
    database = load_db()
    lvl = database.get(uid_str, {}).get("level", "a1")
    maps = {"a1": WORDS_A1, "a2": WORDS_A2, "b1": WORDS_B1, "b2": WORDS_B2, "c1": WORDS_C1}
    pool = maps.get(lvl, WORDS_A1)
    
    correct = random.choice(pool)
    distractors = random.sample([i for i in pool if i["word"] != correct["word"]], min(3, len(pool) - 1))
    options = distractors + [correct]
    random.shuffle(options)
    
    await state.update_data(quiz_correct_ru=correct["ru"])
    await state.set_state(BotStates.quiz_question_active)
    
    btns = [[InlineKeyboardButton(text=opt["ru"], callback_data=f"quizanswer_{opt['ru']}")] for opt in options]
    btns.append([InlineKeyboardButton(text="❌ Выход", callback_data="action_main_menu")])
    
    await message.answer(
        f"🎯 **Тест ({lvl.upper()})**\n\nКак переводится: **{html.quote(correct['word'])}**?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=btns)
    )

@router.callback_query(F.data.startswith("quizanswer_"), StateFilter(BotStates.quiz_question_active))
async def evaluate_user_quiz_answer(callback: CallbackQuery, state: FSMContext) -> None:
    chosen = callback.data.split("_", 1)[1]
    data = await state.get_data()
    correct = data.get("quiz_correct_ru")
    uid_str = str(callback.from_user.id)
    database = load_db()
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Следующий", callback_data="action_next_quiz")],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="action_main_menu")]
    ])
    
    if chosen == correct:
        if uid_str in database:
            database[uid_str]["correct_answers"] = database[uid_str].get("correct_answers", 0) + 1
            database[uid_str]["quiz_score"] = database[uid_str].get("quiz_score", 0) + 15
            save_db(database)
        await callback.message.edit_text("✅ **Верно! (+15 очков)** 🎉", parse_mode="Markdown", reply_markup=markup)
    else:
        await callback.message.edit_text(f"❌ **Ошибка.** Правильно: *{correct}*.", parse_mode="Markdown", reply_markup=markup)
    await callback.answer()

@router.callback_query(F.data == "action_next_quiz")
async def process_next_quiz_question(callback: CallbackQuery, state: FSMContext) -> None:
    await entry_quiz_session(callback.message, state)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()


# ==============================================================================
# НАСТРОЙКИ И ОПЛАТА (TELEGRAM STARS)
# ==============================================================================
@router.message(F.text == "⚙️ Настройки")
async def handle_settings_menu_request(message: Message) -> None:
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Сбросить статистику", callback_data="settings_reset_stats")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="action_main_menu")]
    ])
    await message.answer("⚙️ **Настройки:**", parse_mode="Markdown", reply_markup=markup)

@router.callback_query(F.data == "settings_reset_stats")
async def process_reset_user_statistics(callback: CallbackQuery) -> None:
    uid_str = str(callback.from_user.id)
    database = load_db()
    if uid_str in database:
        database[uid_str]["words_learned"] = 0
        database[uid_str]["correct_answers"] = 0
        database[uid_str]["quiz_score"] = 0
        save_db(database)
    await callback.answer("🔄 Статистика сброшена!", show_alert=True)
    await callback.message.edit_text("✅ Данные обнулены.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="action_main_menu")]
    ]))

@router.message(Command("buy"))
@router.message(F.text.in_(["⭐ Купить Премиум", "buy_premium_trigger"]))
async def handle_buy_premium_request(message: Message) -> None:
    prices = [LabeledPrice(label="Премиум доступ ко всем играм и C1", amount=50)]
    await message.answer_invoice(
        title="⭐ Премиум-подписка",
        description="Открывает детектив, чат-симулятор, квест в Лондоне и уровень C1!",
        prices=prices,
        payload="premium_sub_payload",
        currency="XTR",
        provider_token=""
    )

@router.pre_checkout_query()
async def process_pre_checkout_validation(pre_checkout_query: PreCheckoutQuery) -> None:
    await pre_checkout_query.answer(ok=True)

@router.message(F.successful_payment)
async def process_successful_stars_payment(message: Message) -> None:
    uid_str = str(message.from_user.id)
    database = load_db()
    if uid_str in database:
        database[uid_str]["is_premium"] = True
        save_db(database)
    
    is_admin = message.from_user.id == ADMIN_TELEGRAM_ID
    await message.answer(
        "🎉 **Оплата прошла успешно! Премиум активирован!** ⭐\nВсе игры и уровень C1 теперь разблокированы.",
        parse_mode="Markdown",
        reply_markup=build_main_menu_keyboard(is_administrator=is_admin)
    )


# ==============================================================================
# ЗАПУСК БОТА
# ==============================================================================
async def main() -> None:
    logger.info("Запуск бота...")
    bot = Bot(token=BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    dp.include_router(router)
    
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except TelegramAPIError as e:
        logger.critical(f"Ошибка API: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
