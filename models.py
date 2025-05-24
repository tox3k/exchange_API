from sqlalchemy import Column, String, Integer, DateTime, Enum, ForeignKey, Boolean, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum
import uuid
from database import Base

class UserRole(str, enum.Enum):
    USER = "USER"
    ADMIN = "ADMIN"

class OrderStatus(str, enum.Enum):
    NEW = "NEW"
    EXECUTED = "EXECUTED"
    PARTIALLY_EXECUTED = "PARTIALLY_EXECUTED"
    CANCELLED = "CANCELLED"

class Direction(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.USER, nullable=False)
    api_key = Column(String, unique=True, nullable=False)
    orders = relationship("Order", back_populates="user", cascade="all, delete")
    balances = relationship("Balance", back_populates="user", cascade="all, delete")

class Instrument(Base):
    __tablename__ = "instruments"
    ticker = Column(String(10), primary_key=True)
    name = Column(String, nullable=False)
    orders = relationship("Order", back_populates="instrument", cascade="all, delete")
    transactions = relationship("Transaction", back_populates="instrument", cascade="all, delete")
    balances = relationship("Balance", back_populates="instrument", cascade="all, delete")

class Balance(Base):
    __tablename__ = "balances"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    ticker = Column(String(10), ForeignKey("instruments.ticker"), nullable=False)
    amount = Column(Integer, default=0, nullable=False)
    user = relationship("User", back_populates="balances")
    instrument = relationship("Instrument")

class Order(Base):
    __tablename__ = "orders"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(Enum(OrderStatus), default=OrderStatus.NEW, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    type = Column(String, nullable=False)  # 'LIMIT' or 'MARKET'
    direction = Column(Enum(Direction), nullable=False)
    ticker = Column(String(10), ForeignKey("instruments.ticker"), nullable=False)
    qty = Column(Integer, nullable=False)
    price = Column(Integer)  # nullable for market orders
    filled = Column(Integer, default=0)
    user = relationship("User", back_populates="orders")
    instrument = relationship("Instrument")

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), ForeignKey("instruments.ticker"), nullable=False)
    amount = Column(Integer, nullable=False)
    price = Column(Integer, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    instrument = relationship("Instrument")