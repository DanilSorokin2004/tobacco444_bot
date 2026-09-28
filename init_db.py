from database import init_db, get_session
from models import Product

INITIAL_PRODUCTS = [
    {'barcode': '4605648038536', 'name': 'Corsar coffee', 'category': 'Сигариллы'},
    {'barcode': '4006396099433', 'name': 'Chapman vanilla', 'category': 'Сигареты', 'photo': 'img/Chapman Vanilla.jpg'},
    {'barcode': '4687202523344', 'name': 'THE SCANDALIST', 'category': 'Жидкость для электронных сигарет'},
]

def seed():
    init_db()
    session = get_session()


    added = 0
    for item in INITIAL_PRODUCTS:
        exists = session.query(Product).filter_by(barcode=item['barcode']).first()
        if not exists:
            session.add(Product(**item))
            added += 1

    session.commit()
    session.close()
    print(f'Добавлено товаров: {added}')

if __name__ == '__main__':
    seed()