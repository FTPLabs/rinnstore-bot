from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey, Integer,
    Numeric, String, Text, func, JSON, Index
)
from sqlalchemy.orm import relationship
from .database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_referral_code", "referral_code"),
    )

    id = Column(BigInteger, primary_key=True)
    username = Column(String(255))
    first_name = Column(String(255))
    last_name = Column(String(255))
    language_code = Column(String(10), default="ru")
    is_banned = Column(Boolean, default=False)
    referral_code = Column(String(32), unique=True)
    referred_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    referral_bonus = Column(Numeric(12, 2), default=Decimal("0"))
    balance = Column(Numeric(12, 2), default=Decimal("0"))
    total_spent = Column(Numeric(12, 2), default=Decimal("0"))
    terms_accepted = Column(Boolean, default=False)
    captcha_passed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    orders = relationship("Order", back_populates="user", lazy="selectin")


class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), unique=True)
    role = Column(String(32), default="manager")
    added_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    products = relationship("Product", back_populates="category", lazy="selectin")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id"))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    price = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), default="RUB")
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    image_url = Column(Text)
    discount_percent = Column(Numeric(5, 2), nullable=True)
    discount_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    category = relationship("Category", back_populates="products")
    items = relationship("ProductItem", back_populates="product", lazy="dynamic")


class ProductItem(Base):
    __tablename__ = "product_items"
    __table_args__ = (
        Index("ix_product_items_available", "product_id", "is_sold", "is_reserved"),
        Index("ix_product_items_order", "order_id"),
    )

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    data = Column(Text, nullable=False)
    is_sold = Column(Boolean, default=False)
    is_reserved = Column(Boolean, default=False)
    reserved_until = Column(DateTime(timezone=True), nullable=True)
    sold_at = Column(DateTime(timezone=True), nullable=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    product = relationship("Product", back_populates="items")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_user_id", "user_id"),
        Index("ix_orders_status", "status"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    status = Column(String(32), default="pending")
    total_amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), default="RUB")
    promo_code_id = Column(Integer, ForeignKey("promo_codes.id"), nullable=True)
    discount_amount = Column(Numeric(12, 2), default=Decimal("0"))
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", lazy="selectin")
    payments = relationship("Payment", back_populates="order", lazy="selectin")
    delivered_items = relationship("DeliveredItem", back_populates="order", lazy="selectin")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, default=1)
    unit_price = Column(Numeric(12, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    order = relationship("Order", back_populates="items")
    product = relationship("Product")
    delivered = relationship("DeliveredItem", back_populates="order_item", lazy="selectin")


class DeliveredItem(Base):
    __tablename__ = "delivered_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    order_item_id = Column(Integer, ForeignKey("order_items.id"), nullable=False)
    product_item_id = Column(Integer, ForeignKey("product_items.id"), nullable=False)
    delivered_at = Column(DateTime(timezone=True), server_default=func.now())

    order = relationship("Order", back_populates="delivered_items")
    order_item = relationship("OrderItem", back_populates="delivered")
    product_item = relationship("ProductItem")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    provider = Column(String(32), nullable=False)
    provider_invoice_id = Column(String(255), unique=True)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), default="USDT")
    status = Column(String(32), default="pending")
    pay_url = Column(Text)
    payload = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    paid_at = Column(DateTime(timezone=True), nullable=True)

    order = relationship("Order", back_populates="payments")


class PaymentEvent(Base):
    __tablename__ = "payment_events"

    id = Column(Integer, primary_key=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=False)
    event_type = Column(String(64), nullable=False)
    payload = Column(JSON)
    processed = Column(Boolean, default=False)
    idempotency_key = Column(String(255), unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id = Column(Integer, primary_key=True)
    code = Column(String(64), unique=True, nullable=False)
    discount_type = Column(String(32), default="percent")
    discount_value = Column(Numeric(10, 2), nullable=False)
    max_uses = Column(Integer, nullable=True)
    used_count = Column(Integer, default=0)
    min_order_amount = Column(Numeric(12, 2), default=Decimal("0"))
    expires_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    admin_id = Column(BigInteger, nullable=True)
    action = Column(String(128), nullable=False)
    entity_type = Column(String(64), nullable=True)
    entity_id = Column(Integer, nullable=True)
    details = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=False)
    description = Column(Text)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
