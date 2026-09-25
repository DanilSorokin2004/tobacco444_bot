import asyncio
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.client.session.aiohttp import AiohttpSession

from database import get_session
from models import Product, Subscriber

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

proxy_url = "socks5://127.0.0.1:10808"
session = AiohttpSession(proxy=proxy_url)
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher()


@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        f"Привет, {message.from_user.full_name}!\n\n"
        "Я бот табачного магазина «Табак 444».\n"
        "Сообщаю, когда нужный товар снова появился в наличии.\n\n"
        "Команды:\n"
        "/find <штрихкод> — проверить, есть ли товар в базе\n"
        "/subscribe <штрихкод> — подписаться на уведомление\n"
        "/my_subs — мои подписки\n"
        "/unsubscribe <штрихкод> — отписаться"
    )


@dp.message(Command("find"))
async def cmd_find(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /find <штрихкод>")
        return

    barcode = args[1].strip()
    session = get_session()
    product = session.query(Product).filter_by(barcode=barcode).first()
    session.close()

    if product:
        await message.answer(f"✅ {product.barcode} → {product.name} ({product.category})")
    else:
        await message.answer(f"❌ Товар со штрихкодом {barcode} не найден")


@dp.message(Command("subscribe"))
async def cmd_subscribe(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /subscribe <штрихкод>")
        return

    barcode = args[1].strip()
    session = get_session()

    product = session.query(Product).filter_by(barcode=barcode).first()
    if not product:
        session.close()
        await message.answer(f"❌ Товар со штрихкодом {barcode} не найден")
        return

    existing = (
        session.query(Subscriber)
        .filter_by(telegram_id=message.from_user.id, barcode=barcode)
        .first()
    )
    if existing:
        session.close()
        await message.answer(f"Ты уже подписан на «{product.name}»")
        return

    sub = Subscriber(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        barcode=barcode,
    )
    session.add(sub)
    session.commit()
    session.close()

    await message.answer(f"✅ Подписка оформлена: «{product.name}». Сообщу, когда появится.")


@dp.message(Command("my_subs"))
async def cmd_my_subs(message: Message):
    session = get_session()
    subs = session.query(Subscriber).filter_by(telegram_id=message.from_user.id).all()

    if not subs:
        session.close()
        await message.answer("У тебя пока нет подписок.")
        return

    lines = ["Твои подписки:"]
    for s in subs:
        product = session.query(Product).filter_by(barcode=s.barcode).first()
        name = product.name if product else s.barcode
        lines.append(f"• {name} ({s.barcode})")

    session.close()
    await message.answer("\n".join(lines))


@dp.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /unsubscribe <штрихкод>")
        return

    barcode = args[1].strip()
    session = get_session()
    sub = (
        session.query(Subscriber)
        .filter_by(telegram_id=message.from_user.id, barcode=barcode)
        .first()
    )
    if not sub:
        session.close()
        await message.answer("Такой подписки нет.")
        return

    session.delete(sub)
    session.commit()
    session.close()
    await message.answer(f"✅ Отписка от {barcode} оформлена.")


async def main():
    print("Бот запущен. Нажми Ctrl+C для остановки.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())