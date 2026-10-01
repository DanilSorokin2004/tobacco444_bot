import asyncio
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
)
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import get_session
from models import Product, Subscriber

from sqlalchemy import func

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
PROXY_URL = "http://127.0.0.1:10808"
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))

# --- Telegram Bot ---
session = AiohttpSession(proxy=PROXY_URL,  timeout=120)
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher()


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

class AddProduct(StatesGroup):
    name = State()
    category = State()
    barcode = State()
    photo = State()

class Broadcast(StatesGroup):
    message = State()

# ==================== КОМАНДЫ ====================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
                f"Привет, {message.from_user.full_name}! 👋\n\n"
        "Я бот табачного магазина «Табак 444».\n"
        "Помогу узнать, когда нужный товар снова появится в наличии.\n\n"
        "🔍 Как найти товар:\n"
        "Напиши /find <название или штрихкод>\n"
        "Например: /find chapman\n\n"
        "🔔 Как подписаться:\n"
        "Найди товар и нажми кнопку «Подписаться». "
        "Я сообщу, когда он появится.\n\n"
        "📋 Мои подписки: /my_subs\n"
        "❓ Все команды: /help\n\n"
        "Если что-то непонятно — нажми /help 😊"
    )

@dp.message(Command('admin'))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer('⛔ У тебя нет доступа к админ-панели')
        return

    await message.answer(
        '🔧 Админ-панель «Табак 444»\n\n'
        'Доступные команды:\n'
        '/add_product — добавить товар\n'
        '/stats — статистика\n'
        '/broadcast — рассылка подписчикам\n'
        '/delete_product — удалить товар'
    )

@dp.message(Command('stats'))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(f'⛔ У Вас нет доступа.')

    session_db = get_session()

    # Товары
    total_products = session_db.query(Product.category).count()

    # Категории
    total_categories = session_db.query(Product.category).distinct().count()

    # Subscribes
    total_subs = session_db.query(Subscriber).count()

    # Unique clients
    total_clients = session_db.query(Subscriber.telegram_id).distinct().count()

    # Топ 3 товаров по подпискам
    top_products = (
        session_db.query(
            Subscriber.barcode,
            func.count(Subscriber.id).label('subs_count')
        )
        .group_by(Subscriber.barcode)
        .order_by(func.count(Subscriber.id).desc())
        .limit(5)
        .all()
    )

    # Статистика для топ 5
    top_lines = []
    for barcode, count in top_products:
        p = session_db.query(Product).filter_by(barcode=barcode).first()
        name = p.name if p else barcode
        top_lines.append(f'  • {name} — {count}')

    session_db.close()

    text = (
        f'📊 Статистика «Табак 444»\n\n'
        f'📦 Товаров: {total_products}\n'
        f'📂 Категорий: {total_categories}\n'
        f'🔔 Подписок: {total_subs}\n'
        f'👥 Уникальных клиентов: {total_clients}\n'
    )

    if top_lines:
        text += '\n🏆 Топ-5 товаров по подпискам:\n' + '\n'.join(top_lines)

    await message.answer(text)

@dp.message(Command('broadcast'))
async def cmd_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer('⛔ У тебя нет доступа')
        return

    await state.set_state(Broadcast.message)
    await message.answer(
        '📢 Рассылка сообщения\n\n'
        'Отправь текст, который нужно разослать всем клиентам.\n\n'
        '⚠️ Сообщение получат все, у кого есть хотя бы одна подписка.\n\n'
        'Для отмены: /cancel'
    )

@dp.message(Broadcast.message)
async def broadcast_send(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
            await message.answer('⛔ У тебя нет доступа')
            return

    text = message.text.strip() if message.text else ''

    if not text:
        await message.answer('❌ Отправь текстовое сообщение')

    await state.clear()

    # Собираем уникальные telegram_id всех, у кого есть подписки
    session_db = get_session()
    clients = (
        session_db.query(Subscriber.telegram_id)
        .distinct()
        .all()
    )
    session_db.close()

    telegram_ids = [c[0] for c in clients]

    if not telegram_ids:
        await message.answer('В базе нет клиентов с подписками')
        return

    # Подтверждение
    await message.answer(
        f'📢 Начинаю рассылку...\n'
        f'Получателей: {len(telegram_ids)}'
    )

    sent = 0
    failed = 0

    for tg_id in telegram_ids:
        try:
            await bot.send_message(
                tg_id,
                f'📢 Сообщение от «Табак 444»:\n\n{text}'
            )
            sent += 1
        except Exception as e:
            failed += 1
            print(f'Ошибка отправки {tg_id}: {type(e).__name__}: {e}')

    await message.answer(
        f'✅ Рассылка завершена!\n\n'
        f'📨 Отправлено: {sent}\n'
        f'❌ Ошибок: {failed}'
    )

@dp.message(Command('add_product'))
async def cmd_add_product(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer('⛔ У тебя нет доступа')

    await state.set_state(AddProduct.name)
    await message.answer(
        '📦 Добавление товара\n\n'
        'Шаг 1/4: Введи название товара.\n'
        'Например: Winston Blue\n\n'
        'Для отмены: /cancel'
    )

@dp.message(Command('delete_product'))
async def cmd_delete_product(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer('⛔ У тебя нет доступа')
        return

    session_db = get_session()
    products = session_db.query(Product).all()

    if not products:
        session_db.close()
        await message.answer('В базе нет товаров')

    # Собираем данные до закрытия сессии
    products_data = [
        {'name': p.name, 'barcode': p.barcode, 'category': p.category}
        for p in products
    ]
    session_db.close()

    # Формируем inline-кнопки — по одной на товар
    buttons = []
    for p in products_data:
        buttons.append([
            InlineKeyboardButton(
                text=f"🗑 {p['name']} ({p['barcode']})",
                callback_data=f"del:{p['barcode']}"
            )
        ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(
        "🗑 Выбери товар для удаления:\n\n"
        "⚠️ Внимание: удаление также удалит все подписки на этот товар.",
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith('del:'))
async def cb_delete_product(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer('⛔ Нет доступа', show_alert=True)
        return

    barcode = callback.data.split(':', 1)[1]
    session_db = get_session()

    product = session_db.query(Product).filter_by(barcode=barcode).first()
    if not product:
        session_db.close()
        await callback.answer('Товар не найден', show_alert=True)
        return

    product_name = product.name

    # Delete subscribes
    session_db.query(Subscriber).filter_by(barcode=barcode).delete()

    # Delete goods
    session_db.delete(product)
    session_db.commit()
    session_db.close()

    # Changing a message
    await callback.message.edit_text(
        f'✅ Товар удалён:\n\n'
        f'📦 {product_name}\n'
        f'Штрихкод: {barcode}\n\n'
        f'Все подписки на этот товар также удалены.'
    )
    await callback.answer('✅ Товар удалён')

@dp.message(Command('cancel')) 
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer('❌ Добавление товара отменено')

@dp.message(AddProduct.name)
async def add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AddProduct.category)
    await message.answer(
        'Шаг 2/4: Введи категорию товара'
        'Например: Сигареты\n\n'
        'Для отмены: /cancel'
    )

@dp.message(AddProduct.photo, -F.photo)
async def add_photo_wrong(message: Message):
    await message.answer(
        '❌ Нужно отправить фото товара.\n'
        'Отправь картинку или /cancel'
    )

@dp.message(AddProduct.category)
async def add_category(message: Message, state: FSMContext):
    await state.update_data(category=message.text.strip())
    await state.set_state(AddProduct.barcode)
    await message.answer(
        'Шаг 3/4: Введи штрихкод товара'
        'Например: 4601234567890\n\n'
        'Для отмены: /cancel'
    )

@dp.message(AddProduct.barcode)
async def add_barcode(message: Message, state: FSMContext):
    barcode = message.text.strip()

    if not barcode.isdigit() or len(barcode) not in (8, 12, 13):
        await message.answer(
            '❌ Штрихкод должен содержать 8, 12 или 13 цифр.\n'
            'Попробуй ещё раз или /cancel'
        )
        return

    session_db = get_session()
    exists = session_db.query(Product).filter_by(barcode=barcode).first()
    session_db.close()

    if exists:
        await message.answer(
             f'❌ Товар со штрихкодом {barcode} уже есть в базе.\n'
            'Введи другой штрихкод или /cancel'
        )
        return

    await state.update_data(barcode=barcode)
    await state.set_state(AddProduct.photo)
    await message.answer(
        'Шаг 4/4: Отправь фото товара.\n\n'
        'Для отмены: /cancel'
    )

@dp.message(AddProduct.photo, F.photo)
async def add_photo(message: Message, state: FSMContext):
    photo = message.photo[-1]
    file_id = photo.file_id

    data = await state.get_data()
    await state.clear()

    session_db = get_session()
    product = Product(
        barcode=data['barcode'],
        name=data['name'],
        category=data['category'],
        photo=file_id,
    )
    session_db.add(product)
    session_db.commit()
    session_db.close()

    await message.answer(
        f"✅ Товар добавлен!\n\n"
        f"📦 {data['name']}\n"
        f"Категория: {data['category']}\n"
        f"Штрихкод: {data['barcode']}"
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 Справка по боту «Табак 444»\n\n"
        "🔍 Поиск товара:\n"
        "/find <название> — найти по названию\n"
        "/find <штрихкод> — найти по штрихкоду\n\n"
        "🔔 Подписки:\n"
        "/subscribe <штрихкод> — подписаться\n"
        "/unsubscribe <штрихкод> — отписаться\n"
        "/my_subs — мои подписки\n\n"
        "📦 Просмотр товаров:\n"
        "/all — все товары\n"
        "/categories — список категорий\n"
        "/category <название> — товары в категории\n\n"
        "💡 Как это работает:\n"
        "Когда товар появляется в магазине, "
        "я присылаю уведомление всем, кто на него подписан.",
    )

@dp.message(Command("find"))
async def cmd_find(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /find <штрихкод или название>")
        return

    query = args[1].strip()
    session_db = get_session()

    # Поиск по штрихкоду
    if query.isdigit() and len(query) in (8, 12, 13):
        product = session_db.query(Product).filter_by(barcode=query).first()
        if not product:
            session_db.close()
            await message.answer(f"❌ Товар со штрихкодом {query} не найден")
            return
        # Вытаскиваем данные до закрытия сессии
        p_data = {
            "name": product.name,
            "category": product.category,
            "barcode": product.barcode,
            "photo": product.photo,
        }
        session_db.close()
        await send_product_card(message, p_data)
        return

    # Поиск по названию
    products = (
        session_db.query(Product)
        .filter(Product.name.ilike(f"%{query}%"))
        .limit(5)
        .all()
    )
    if not products:
        session_db.close()
        await message.answer(f"❌ По запросу «{query}» ничего не найдено")
        return

    # Собираем данные до закрытия сессии
    products_data = [
        {'name': p.name, 'category': p.category, 'barcode': p.barcode, 'photo': p.photo}
        for p in products
    ]
    session_db.close()

    for p_data in products_data:
        await send_product_card(message, p_data)


@dp.message(Command("subscribe"))
async def cmd_subscribe(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /subscribe <штрихкод>")
        return

    barcode = args[1].strip()
    session_db = get_session()

    product = session_db.query(Product).filter_by(barcode=barcode).first()
    if not product:
        session_db.close()
        await message.answer(f"❌ Товар со штрихкодом {barcode} не найден")
        return

    product_name = product.name

    existing = (
        session_db.query(Subscriber)
        .filter_by(telegram_id=message.from_user.id, barcode=barcode)
        .first()
    )
    if existing:
        session_db.close()
        await message.answer(f"Ты уже подписан на «{product_name}»")
        return

    sub = Subscriber(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        barcode=barcode,
    )
    session_db.add(sub)
    session_db.commit()
    session_db.close()

    await message.answer(f"✅ Подписка оформлена: «{product_name}»")


@dp.message(Command("my_subs"))
async def cmd_my_subs(message: Message):
    session_db = get_session()
    subs = (
        session_db.query(Subscriber)
        .filter_by(telegram_id=message.from_user.id)
        .all()
    )

    if not subs:
        session_db.close()
        await message.answer("У тебя пока нет подписок.")
        return

    lines = ["Твои подписки:"]
    for s in subs:
        p = session_db.query(Product).filter_by(barcode=s.barcode).first()
        name = p.name if p else s.barcode
        lines.append(f"• {name} ({s.barcode})")

    session_db.close()
    await message.answer("\n".join(lines))


@dp.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /unsubscribe <штрихкод>")
        return

    barcode = args[1].strip()
    session_db = get_session()
    sub = (
        session_db.query(Subscriber)
        .filter_by(telegram_id=message.from_user.id, barcode=barcode)
        .first()
    )
    if not sub:
        session_db.close()
        await message.answer("Такой подписки нет.")
        return

    session_db.delete(sub)
    session_db.commit()
    session_db.close()
    await message.answer(f"✅ Отписка от {barcode} оформлена.")


# ==================== КАРТОЧКА ТОВАРА ====================

async def send_product_card(message: Message, p_data: dict):
    """Отправляет карточку товара с фото (если есть) и inline-кнопкой подписки."""
    session_db = get_session()
    is_subscribed = (
        session_db.query(Subscriber)
        .filter_by(telegram_id=message.from_user.id, barcode=p_data["barcode"])
        .first()
        is not None
    )
    session_db.close()

    if is_subscribed:
        btn = InlineKeyboardButton(
            text="🔕 Отписаться",
            callback_data=f"unsub:{p_data['barcode']}",
        )
    else:
        btn = InlineKeyboardButton(
            text="🔔 Подписаться",
            callback_data=f"sub:{p_data['barcode']}",
        )

    kb = InlineKeyboardMarkup(inline_keyboard=[[btn]])

    caption = (
        f"📦 *{p_data['name']}*\n"
        f"Категория: {p_data['category']}\n"
        f"Штрихкод: `{p_data['barcode']}`"
    )

    if p_data.get('photo'):
            photo_value = p_data['photo']
            try:
                if photo_value.startswith(('AgAC', 'BQAC', 'AQAD')):
                    await message.answer_photo(
                        photo=photo_value,
                        caption=caption,
                        parse_mode='Markdown',
                        reply_markup=kb,
                    )
                else:
                    await message.answer_photo(
                        photo=FSInputFile(photo_value),
                        caption=caption,
                        parse_mode='Markdown',
                        reply_markup=kb,
                    )
            except Exception as e:
                print(f'[PHOTO ERROR] {e}')
                await message.answer(caption, parse_mode='Markdown', reply_markup=kb)

    else:
        await message.answer(caption, parse_mode='Markdown', reply_markup=kb)
  

# ==================== CALLBACK-КНОПКИ ====================

@dp.callback_query(F.data.startswith("sub:"))
async def cb_subscribe(callback: CallbackQuery):
    barcode = callback.data.split(":", 1)[1]
    session_db = get_session()
    product = session_db.query(Product).filter_by(barcode=barcode).first()
    if not product:
        session_db.close()
        await callback.answer("Товар не найден", show_alert=True)
        return

    product_name = product.name

    existing = (
        session_db.query(Subscriber)
        .filter_by(telegram_id=callback.from_user.id, barcode=barcode)
        .first()
    )
    if existing:
        session_db.close()
        await callback.answer("Ты уже подписан", show_alert=True)
        return

    sub = Subscriber(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        barcode=barcode,
    )
    session_db.add(sub)
    session_db.commit()
    session_db.close()

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔕 Отписаться", callback_data=f"unsub:{barcode}")
    ]])
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer(f"✅ Подписка оформлена: «{product_name}»")


@dp.callback_query(F.data.startswith("unsub:"))
async def cb_unsubscribe(callback: CallbackQuery):
    barcode = callback.data.split(":", 1)[1]
    session_db = get_session()
    sub = (
        session_db.query(Subscriber)
        .filter_by(telegram_id=callback.from_user.id, barcode=barcode)
        .first()
    )
    if not sub:
        session_db.close()
        await callback.answer("Вы не подписаны", show_alert=True)
        return

    session_db.delete(sub)
    session_db.commit()
    session_db.close()

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔔 Подписаться", callback_data=f"sub:{barcode}")
    ]])
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer("🔕 Отписка оформлена")

@dp.callback_query(F.data == "my_subs")
async def cb_my_subs(callback: CallbackQuery):
    session_db = get_session()
    subs = (
        session_db.query(Subscriber)
        .filter_by(telegram_id=callback.from_user.id)
        .all()
    )
    if not subs:
        session_db.close()
        await callback.answer("У тебя пока нет подписок", show_alert=True)
        return

    lines = ["Твои подписки:"]
    for s in subs:
        p = session_db.query(Product).filter_by(barcode=s.barcode).first()
        name = p.name if p else s.barcode
        lines.append(f"• {name} ({s.barcode})")

    session_db.close()
    await callback.message.answer("\n".join(lines))
    await callback.answer()

@dp.message(Command('all'))
async def cmd_all(message: Message):
    session_db = get_session()
    products = session_db.query(Product).all()

    if not products:
        session_db.close()
        await message.answer('В базе пока нет такого товара')
        return

    # Сбор данных до закрытия сессии
    products_data = [
        {'name': p.name, 'category': p.category, 'barcode': p.barcode}
        for p in products
    ]
    session_db.close()

    await message.answer(f'📦 Всего товаров: {len(products_data)}')

    for p_data in products_data:
        await send_product_card(message, p_data)

@dp.message(Command('categories'))
async def cmd_categories(message: Message):
    session_db = get_session()
    # Уникальные категории
    categories = (
        session_db.query(Product.category)
        .distinct()
        .all()
    )
    session_db.close()

    categories = [c[0] for c in categories if c[0]]

    if not categories:
        await message.answer('В базе пока нет категорий')
        return

    lines = ['📂 Категории:']
    for c in categories:
        lines.append(f'• {c}')

    lines.append('\n Использование: /category <название>')
    await message.answer('\n'.join(lines))

@dp.message(Command('category'))
async def cmd_category(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer('Использование: /category <название>')
        return

    category = args[1].strip().lower()
    session_db = get_session()
    all_products = session_db.query(Product).all()

    products_data = [
        {'name': p.name, 'category': p.category, 'barcode': p.barcode, 'photo': p.photo}
        for p in all_products
        if p.category and category in p.category.lower()
    ]
    session_db.close()

    if not products_data:
        await message.answer(f'❌ Категория «{args[1]}» не найдена')
        return

    await message.answer(f'📂 Категория «{args[1]}»: {len(products_data)} товаров')
    for p_data in products_data:
        await send_product_card(message, p_data)

# ==================== РАССЫЛКА ====================

async def notify_subscribers(barcode: str) -> int:
    print(f"[DEBUG] notify_subscribers вызван с barcode={barcode!r}")
    session_db = get_session()

    product = session_db.query(Product).filter_by(barcode=barcode).first()
    if not product:
        session_db.close()
        print(f"[DEBUG] Товар {barcode} не найден")
        return 0

    # Вытаскиваем данные товара до закрытия сессии
    product_name = product.name
    product_category = product.category
    product_barcode = product.barcode

    subs = session_db.query(Subscriber).filter_by(barcode=barcode).all()
    # Вытаскиваем telegram_id до закрытия сессии
    telegram_ids = [s.telegram_id for s in subs]

    session_db.close()

    print(f"[DEBUG] Найдено подписчиков: {len(telegram_ids)}")
    print(f"[DEBUG] Товар: {product_name} ({product_category})")

    if not telegram_ids:
        return 0

    sent = 0
    for tg_id in telegram_ids:
        try:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="🔕 Отписаться",
                    callback_data=f"unsub:{product_barcode}"
                )
            ]])
            await bot.send_message(
                tg_id,
                f"🔔 Товар снова в наличии!\n\n"
                f"{product_name} ({product_category})\n"
                f"Штрихкод: {product_barcode}\n\n"
                f"Заходи в «Табак 444»!",
                reply_markup=kb,
            )
            sent += 1
        except Exception as e:
            print(f"Ошибка отправки {tg_id}: {type(e).__name__}: {e}")
    return sent


# ==================== FASTAPI ====================

class NotifyRequest(BaseModel):
    barcode: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[DEBUG] Запускаю polling...")
    polling_task = asyncio.create_task(dp.start_polling(bot))
    print("[DEBUG] Polling запущен")
    yield
    polling_task.cancel()
    await bot.session.close()


app = FastAPI(lifespan=lifespan)


@app.post("/notify")
async def notify(req: NotifyRequest):
    sent = await notify_subscribers(req.barcode)
    if sent == 0:
        return {"status": "ok", "sent": 0, "message": "Нет подписчиков или товар не найден"}
    return {"status": "ok", "sent": sent}


@app.get("/health")
async def health():
    return {"status": "healthy"}


# ==================== ЗАПУСК ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)