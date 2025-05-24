from pydantic import BaseModel, Field, UUID4
from typing import Optional, List, Dict, Union, Literal
from datetime import datetime
import enum

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

class NewUser(BaseModel):
    name: str = Field(..., min_length=3)

class User(BaseModel):
    id: UUID4
    name: str
    role: UserRole
    api_key: str

    class Config:
        from_attributes = True

class Instrument(BaseModel):
    name: str
    ticker: str = Field(..., pattern=r"^[A-Z]{2,10}$")

    class Config:
        from_attributes = True

class Level(BaseModel):
    price: int
    qty: int

class L2OrderBook(BaseModel):
    bid_levels: List[Level]
    ask_levels: List[Level]

class LimitOrderBody(BaseModel):
    direction: Direction
    ticker: str
    qty: int
    price: int

class MarketOrderBody(BaseModel):
    direction: Direction
    ticker: str
    qty: int

class LimitOrder(BaseModel):
    id: UUID4
    status: OrderStatus
    user_id: UUID4
    timestamp: datetime
    body: LimitOrderBody
    filled: int = 0

class MarketOrder(BaseModel):
    id: UUID4
    status: OrderStatus
    user_id: UUID4
    timestamp: datetime
    body: MarketOrderBody

class CreateOrderResponse(BaseModel):
    success: Literal[True] = True
    order_id: UUID4

class Transaction(BaseModel):
    ticker: str
    amount: int
    price: int
    timestamp: datetime

    class Config:
        from_attributes = True

class Ok(BaseModel):
    success: Literal[True] = True

class BodyDeposit(BaseModel):
    user_id: UUID4
    ticker: str
    amount: int

class BodyWithdraw(BaseModel):
    user_id: UUID4
    ticker: str
    amount: int

class ValidationError(BaseModel):
    loc: List[Union[str, int]]
    msg: str
    type: str

class HTTPValidationError(BaseModel):
    detail: List[ValidationError] = [] 