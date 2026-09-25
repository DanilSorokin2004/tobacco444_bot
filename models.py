from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class Product(Base):
    __tablename__ = 'products'

    id = Column(Integer, primary_key=True)
    barcode = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    category = Column(String(100), nullable=False)

    def __repr__(self):
        return f'<Product {self.barcode}: {self.name}>'

class Subscriber(Base):
    __tablename__ = "subscribers"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, nullable=False, index=True)
    username = Column(String(100), nullable=True)  # ← должно быть
    barcode = Column(String(50), ForeignKey("products.barcode"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product")

    def __repr__(self):
        return 'f<Subscriber {self.telegram_id} -> {self.barcode}>'