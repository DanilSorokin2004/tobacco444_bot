from database import get_session
from models import Product

session = get_session()
products = session.query(Product).all()

for p in products:
    print(f'{p.barcode} - {p.name} ({p.category})')

session.close()