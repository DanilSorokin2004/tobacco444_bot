import sys
import time
import threading
import keyboard
from database import get_session
from models import Product
import httpx

sys.stdout.write('\033[?25l')

barcode = ""
last_key_time = time.time()
lock = threading.Lock()
TIMEOUT = 0.3

API_URL = "http://127.0.0.1:8000/notify" 

def find_product(code: str):
    session = get_session()
    product = session.query(Product).filter_by(barcode=code).first()
    session.close()
    return product


def process_barcode(code: str):
    if not code.isdigit() or len(code) not in (8, 12, 13):
        return
    product = find_product(code)
    # Стираем текущую строку (где эхо сканера) и возвращаемся в начало
    print("\r\033[K", end="")
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


def on_press(event):
    global barcode, last_key_time
    if event.event_type != keyboard.KEY_DOWN:
        return

    if len(event.name) == 1:
        with lock:
            barcode += event.name
            last_key_time = time.time()


def watchdog():
    global barcode
    while True:
        time.sleep(0.1)
        code = ""                          # ← объявляем заранее
        with lock:
            if barcode and (time.time() - last_key_time) > TIMEOUT:
                code = barcode
                barcode = ""
        if code:
            process_barcode(code)


print("Сканируй штрихкод... (Esc для выхода)")

keyboard.on_press(on_press, suppress=True)

# Отдельный поток следит за таймаутом
threading.Thread(target=watchdog, daemon=True).start()

keyboard.wait('esc')
print("Выход.")