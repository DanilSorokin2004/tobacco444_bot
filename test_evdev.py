import asyncio
import time
import httpx
import evdev
from evdev import InputDevice, categorize, ecodes

from database import get_session
from models import Product

SCANNER_PATH = "/dev/input/event14"   # ← твой сканер

API_URL = "http://127.0.0.1:8000/notify"
TIMEOUT = 0.3
DEDUP_TIMEOUT = 2.0

barcode = ""
last_key_time = time.time()
last_processed_barcode = ""
last_processed_time = 0

# Карта цифр evdev → строка
KEY_MAP = {
    ecodes.KEY_1: "1", ecodes.KEY_2: "2", ecodes.KEY_3: "3",
    ecodes.KEY_4: "4", ecodes.KEY_5: "5", ecodes.KEY_6: "6",
    ecodes.KEY_7: "7", ecodes.KEY_8: "8", ecodes.KEY_9: "9",
    ecodes.KEY_0: "0",
}


def find_product(code: str):
    session = get_session()
    product = session.query(Product).filter_by(barcode=code).first()
    session.close()
    return product


def process_barcode(code: str):
    global last_processed_barcode, last_processed_time

    now = time.time()
    if code == last_processed_barcode and (now - last_processed_time) < DEDUP_TIMEOUT:
        print(f"[DEDUP] Игнорирую повтор: {code}")
        return
    last_processed_barcode = code
    last_processed_time = now

    if not code.isdigit() or len(code) not in (8, 12, 13):
        return

    product = find_product(code)
    if product:
        print(f"✅ {code} → {product.name} ({product.category})")
        try:
            r = httpx.post(API_URL, json={"barcode": code}, timeout=5)
            data = r.json()
            sent = data.get("sent", 0)
            if sent > 0:
                print(f"   📨 Уведомлений отправлено: {sent}")
            else:
                print(f"   ℹ️  Подписчиков нет")
        except Exception as e:
            print(f"   ⚠️  Не удалось отправить в API: {e}")
    else:
        print(f"❌ {code} → товар не найден")


async def main():
    device = InputDevice(SCANNER_PATH)
    print(f"Сканер: {device.name}")
    print("Сканируй штрихкод... (Ctrl+C для выхода)")

    global barcode, last_key_time

    async for event in device.async_read_loop():
        if event.type != ecodes.EV_KEY:
            continue

        key_event = categorize(event)
        if key_event.keystate != key_event.key_down:
            continue

        # Цифра
        if event.code in KEY_MAP:
            barcode += KEY_MAP[event.code]
            last_key_time = time.time()

        # Enter — конец штрихкода
        elif event.code == ecodes.KEY_ENTER:
            if barcode:
                process_barcode(barcode)
                barcode = ""

        # Проверка таймаута
        if barcode and (time.time() - last_key_time) > TIMEOUT:
            process_barcode(barcode)
            barcode = ""


if __name__ == "__main__":
    asyncio.run(main())