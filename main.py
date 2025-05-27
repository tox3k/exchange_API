from fastapi import FastAPI, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_
from uuid import uuid4, UUID
from database import engine, Base, SessionLocal
from models import Instrument, User as UserModel, UserRole, Balance, Order as OrderModel, Direction, OrderStatus, Transaction as TransactionModel
from schemas import NewUser, User as UserSchema, Instrument as InstrumentSchema, Ok, BodyDeposit, BodyWithdraw, L2OrderBook, Level, Transaction as TransactionSchema, LimitOrderBody, MarketOrderBody, CreateOrderResponse, LimitOrder, MarketOrder
from deps import get_db, get_current_user
from contextlib import asynccontextmanager
from typing import List, Union
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
import json
import uvicorn

# Настройка логгера
logger = logging.getLogger("api_logger")
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler("api_requests.log")
time_format = '%H:%M:%S'
file_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt=time_format))
logger.addHandler(file_handler)

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        method = request.method
        url = str(request.url)
        api_key = request.headers.get('authorization')
        if api_key != None:
            api_key = api_key.split(' ')[1]
        params = dict(request.query_params)
        body = None
        if method in ("POST", "PUT", "PATCH"):
            try:
                body_bytes = await request.body()
                body = body_bytes.decode("utf-8")
                # Попробуем распарсить как JSON для красоты
                try:
                    body = json.dumps(json.loads(body), ensure_ascii=False)
                except Exception:
                    pass
            except Exception:
                body = None
        log_msg = f"{method} {('/api' + url.split('/api')[1]) if '/api' in url else url} | api_key={api_key} | params={params}"
        if body:
            log_msg += f" | body={body}"
        logger.info(log_msg)
        response = await call_next(request)
        # Логируем статус-код и тело ответа (до 1000 символов)
        status_code = response.status_code
        resp_body = b""
        async for chunk in response.body_iterator:
            resp_body += chunk
        # Восстанавливаем асинхронный итератор для корректного ответа клиенту
        async def new_body_iterator():
            yield resp_body
        response.body_iterator = new_body_iterator()
        try:
            resp_text = resp_body.decode("utf-8")
        except Exception:
            resp_text = str(resp_body)
        
        return response

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()
    try:
        # RUB
        rub = db.query(Instrument).filter_by(ticker=RUB_TICKER).first()
        if not rub:
            db.add(Instrument(ticker=RUB_TICKER, name=RUB_NAME))
            db.commit()
        # ADMIN user
        admin = db.query(UserModel).filter_by(name="admin").first()
        if not admin:
            api_key = "key-fb5efdda-f0cf-41cd-ad1f-6452847e1eef"
            admin = UserModel(name="admin", api_key=api_key, role=UserRole.ADMIN)
            db.add(admin)
            db.commit()
            print(f"Admin user created! api_key: {api_key}")
        else:
            print(f"Admin user already exists. api_key: {admin.api_key}")
    finally:
        db.close()
    yield

app = FastAPI(title="Toy exchange", version="0.1.0", lifespan=lifespan)

RUB_TICKER = "RUB"
RUB_NAME = "Российский рубль"

app.add_middleware(LoggingMiddleware)

@app.get("/")
def root():
    return {"msg": "Toy exchange API"}

@app.post("/api/v1/public/register", response_model=UserSchema, tags=["public"], summary="Register", description="Регистрация пользователя в платформе.")
async def register(new_user: NewUser, db: Session = Depends(get_db)):
    api_key = f"key-{uuid4()}"
    user = UserModel(name=new_user.name, api_key=api_key, role=UserRole.USER)
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="User already exists")
    return user

@app.get("/api/v1/public/instrument", response_model=list[InstrumentSchema], tags=["public"], summary="List Instruments", description="Список доступных инструментов")
async def list_instruments(db: Session = Depends(get_db)):
    instruments = db.query(Instrument).all()
    return instruments

@app.get("/api/v1/balance", tags=["balance"], summary="Get Balances", response_model=dict)
async def get_balances(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    balances = db.query(Balance).filter_by(user_id=current_user.id).all()
    result = {b.ticker: b.amount for b in balances}
    return result

@app.post("/api/v1/admin/instrument", response_model=Ok, tags=["admin"], summary="Add Instrument")
async def add_instrument(instr: InstrumentSchema, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admin can add instruments")
    if db.query(Instrument).filter_by(ticker=instr.ticker).first():
        raise HTTPException(status_code=400, detail="Instrument already exists")
    db.add(Instrument(ticker=instr.ticker, name=instr.name))
    db.commit()
    return Ok()

@app.post("/api/v1/admin/balance/deposit", response_model=Ok, tags=["admin"], summary="Deposit", description="Пополнение баланса")
async def deposit(body: BodyDeposit, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admin can deposit")
    user = db.query(UserModel).filter_by(id=body.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    instr = db.query(Instrument).filter_by(ticker=body.ticker).first()
    if not instr:
        raise HTTPException(status_code=404, detail="Instrument not found")
    if body.amount < 0:
        raise HTTPException(status_code=400, detail="Can't deposit negative amount.")
    balance = db.query(Balance).filter_by(user_id=body.user_id, ticker=body.ticker).first()
    if not balance:
        balance = Balance(user_id=body.user_id, ticker=body.ticker, amount=body.amount)
        db.add(balance)
    else:
        balance.amount += body.amount
    db.commit()
    return Ok()

@app.post("/api/v1/admin/balance/withdraw", response_model=Ok, tags=["admin"], summary="Withdraw", description="Вывод доступных средств с баланса")
async def withdraw(body: BodyWithdraw, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admin can withdraw")
    user = db.query(UserModel).filter_by(id=body.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    instr = db.query(Instrument).filter_by(ticker=body.ticker).first()
    if not instr:
        raise HTTPException(status_code=404, detail="Instrument not found")
    balance = db.query(Balance).filter_by(user_id=body.user_id, ticker=body.ticker).first()
    if not balance or balance.amount < body.amount:
        raise HTTPException(status_code=400, detail="Insufficient funds")
    balance.amount -= body.amount
    db.commit()
    return Ok()

@app.delete("/api/v1/admin/user/{user_id}", response_model=UserSchema, tags=["admin", "user"], summary="Delete User")
def delete_user(user_id: UUID, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admin can delete users")
    user = db.query(UserModel).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db.delete(user)
    db.commit()
    return user

@app.get("/api/v1/public/orderbook/{ticker}", response_model=L2OrderBook, tags=["public"], summary="Get Orderbook", description="Текущие заявки")
async def get_orderbook(ticker: str, limit: int = 10, db: Session = Depends(get_db)):
    # Показываем лучшие заявки (bid/ask) по цене
    bids = db.query(OrderModel).filter(OrderModel.ticker == ticker, OrderModel.direction == Direction.BUY, or_(OrderModel.status == OrderStatus.NEW, OrderModel.status == OrderStatus.PARTIALLY_EXECUTED)).order_by(OrderModel.price.desc()).limit(limit).all()
    asks = db.query(OrderModel).filter(OrderModel.ticker == ticker, OrderModel.direction == Direction.SELL, or_(OrderModel.status == OrderStatus.NEW, OrderModel.status == OrderStatus.PARTIALLY_EXECUTED)).order_by(OrderModel.price.asc()).limit(limit).all()
    
    bid_prices = {}
    good_bids = []
    for bid in bids:
        if bid.price != None:
            if bid.price not in bid_prices:
                bid_prices[bid.price] = 0
                good_bids.append(bid)
            bid_prices[bid.price] += bid.qty - bid.filled
            
    ask_prices = {}
    good_asks = []
    for ask in asks:
        if ask.price != None:
            if ask.price not in ask_prices:
                ask_prices[ask.price] = 0
                good_asks.append(ask)
            
            ask_prices[ask.price] += ask.qty - ask.filled
    bid_levels = [Level(price=o.price, qty=bid_prices[o.price]) for o in good_bids if o.price is not None]
    ask_levels = [Level(price=o.price, qty=ask_prices[o.price]) for o in good_asks if o.price is not None]
    return L2OrderBook(bid_levels=bid_levels, ask_levels=ask_levels)

@app.get("/api/v1/public/transactions/{ticker}", response_model=list[TransactionSchema], tags=["public"], summary="Get Transaction History", description="История сделок")
async def get_transaction_history(ticker: str, limit: int = 10, db: Session = Depends(get_db)):
    txs = db.query(TransactionModel).filter_by(ticker=ticker).order_by(TransactionModel.timestamp.desc()).limit(limit).all()
    return [TransactionSchema.from_orm(tx) for tx in txs]

@app.post("/api/v1/order", response_model=CreateOrderResponse, tags=["order"], summary="Create Order")
async def create_order(request: Request, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    body = await request.json()
    if 'price' in body:
        order_type = 'LIMIT'
        order_body = LimitOrderBody(**body)
    else:
        order_type = 'MARKET'
        order_body = MarketOrderBody(**body)
        orderbook = await get_orderbook(order_body.ticker, db=db)
        print(orderbook)
        # Проверка наличия существующих ордеров для немедленного исполнения рыночных
        if order_body.direction == 'SELL':
            total_bids = 0
            for order_item in orderbook.bid_levels:
                total_bids += order_item.qty
            if total_bids < order_body.qty:
                raise HTTPException(status_code=400, detail=f'Can\'t execute order, not enough BUY-orders on exchange.')
        else:
            total_asks = 0
            for order_item in orderbook.ask_levels:
                total_asks += order_item.qty
            if total_asks < order_body.qty:
                raise HTTPException(status_code=400, detail=f'Can\'t execute order, not enough SELL-orders on exchange.')
            
    ticker = order_body.ticker or RUB_TICKER
    instr = db.query(Instrument).filter_by(ticker=ticker).first()
    if not instr:
        raise HTTPException(status_code=404, detail="Instrument not found")
    # Проверка достаточности средств перед созданием ордера
    if order_body.direction == Direction.BUY:
        # Для покупки: достаточно RUB?
        total_cost = (order_body.price if order_type == 'LIMIT' else 0) * order_body.qty
        balance = db.query(Balance).filter_by(user_id=current_user.id, ticker=RUB_TICKER).first()
        if order_type == 'LIMIT' and (not balance or balance.amount < total_cost):
            raise HTTPException(status_code=400, detail="Insufficient RUB balance for buy order")
    else:
        # Для продажи: достаточно актива?
        asset_balance = db.query(Balance).filter_by(user_id=current_user.id, ticker=ticker).first()
        if not asset_balance or asset_balance.amount < order_body.qty:
            raise HTTPException(status_code=400, detail="Insufficient asset balance for sell order")
    
    order = OrderModel(
        user_id=current_user.id,
        type=order_type,
        direction=order_body.direction,
        ticker=ticker,
        qty=order_body.qty,
        price=getattr(order_body, 'price', None)
    )
    db.add(order)
    db.flush()
    # --- Matching engine ---
    to_fill = order.qty
    price = order.price if order_type == 'LIMIT' else None
    direction = order.direction
    # BUY: ищем SELL, SELL: ищем BUY
    if direction == Direction.BUY:
        # Для BUY ищем SELL с min ценой <= нашей
        q = db.query(OrderModel).filter(
            OrderModel.ticker == ticker,
            OrderModel.direction == Direction.SELL,
            OrderModel.status != OrderStatus.CANCELLED,
            OrderModel.status != OrderStatus.EXECUTED
        )
        if price:
            q = q.filter(OrderModel.price <= price)
        q = q.order_by(OrderModel.price.asc(), OrderModel.timestamp.asc())
    else:
        # Для SELL ищем BUY с max ценой >= нашей
        q = db.query(OrderModel).filter(
            OrderModel.ticker == ticker,
            OrderModel.direction == Direction.BUY,
            OrderModel.status != OrderStatus.CANCELLED,
            OrderModel.status != OrderStatus.EXECUTED

        )
        if price:
            q = q.filter(OrderModel.price >= price)
        q = q.order_by(OrderModel.price.desc(), OrderModel.timestamp.asc())
    matches = q.all()
    for match in matches:
        if to_fill == 0:
            break
        match_available = match.qty - match.filled
        fill_qty = min(to_fill, match_available)
        # Цена сделки
        deal_price = match.price if match.price is not None else order.price
        # Обновляем балансы
        if direction == Direction.BUY:
            # Покупатель current_user, продавец match.user_id
            # Списать deal_price*fill_qty у buyer (RUB), зачислить ticker
            # Списать ticker у seller, зачислить RUB
            buyer_balance = db.query(Balance).filter_by(user_id=current_user.id, ticker=RUB_TICKER).first()
            if not buyer_balance or buyer_balance.amount < deal_price * fill_qty:
                break  # Недостаточно средств
            seller_balance = db.query(Balance).filter_by(user_id=match.user_id, ticker=ticker).first()
            if not seller_balance or seller_balance.amount < fill_qty:
                continue  # У продавца нет актива
            # Списать RUB у buyer
            buyer_balance.amount -= deal_price * fill_qty
            # Зачислить актив buyer
            user_asset = db.query(Balance).filter_by(user_id=current_user.id, ticker=ticker).first()
            if not user_asset:
                user_asset = Balance(user_id=current_user.id, ticker=ticker, amount=0)
                db.add(user_asset)
                db.commit()
            user_asset.amount += fill_qty
            # Списать актив у seller
            seller_balance.amount -= fill_qty
            # Зачислить RUB seller
            seller_rub = db.query(Balance).filter_by(user_id=match.user_id, ticker=RUB_TICKER).first()
            if not seller_rub:
                seller_rub = Balance(user_id=match.user_id, ticker=RUB_TICKER, amount=0)
                db.add(seller_rub)
                db.commit()
            seller_rub.amount += deal_price * fill_qty
        else:
            # SELL: продавец current_user, покупатель match.user_id
            # Списать актив у seller, зачислить RUB
            # Списать RUB у buyer, зачислить актив
            seller_balance = db.query(Balance).filter_by(user_id=current_user.id, ticker=ticker).first()
            if not seller_balance or seller_balance.amount < fill_qty:
                break  # Недостаточно актива
            buyer_balance = db.query(Balance).filter_by(user_id=match.user_id, ticker=RUB_TICKER).first()
            if not buyer_balance or buyer_balance.amount < deal_price * fill_qty:
                continue  # У покупателя нет RUB
            # Списать актив у seller
            seller_balance.amount -= fill_qty
            # Зачислить RUB seller
            seller_rub = db.query(Balance).filter_by(user_id=current_user.id, ticker=RUB_TICKER).first()
            if not seller_rub:
                seller_rub = Balance(user_id=current_user.id, ticker=RUB_TICKER, amount=0)
                db.add(seller_rub)
                db.commit()
            seller_rub.amount += deal_price * fill_qty
            # Списать RUB у buyer
            buyer_balance.amount -= deal_price * fill_qty
            # Зачислить актив buyer
            buyer_asset = db.query(Balance).filter_by(user_id=match.user_id, ticker=ticker).first()
            if not buyer_asset:
                buyer_asset = Balance(user_id=match.user_id, ticker=ticker, amount=0)
                db.add(buyer_asset)
                db.commit()
            buyer_asset.amount += fill_qty
        # Обновляем ордера
        match.filled += fill_qty
        if match.filled == match.qty:
            match.status = OrderStatus.EXECUTED
        else:
            match.status = OrderStatus.PARTIALLY_EXECUTED
        order.filled += fill_qty
        if order.filled == order.qty:
            order.status = OrderStatus.EXECUTED
        else:
            order.status = OrderStatus.PARTIALLY_EXECUTED
        # Запись о сделке
        db.add(TransactionModel(ticker=ticker, amount=fill_qty, price=deal_price))
        to_fill -= fill_qty
    if to_fill != 0 and order_type == 'MARKET':
        db.delete(order)
        raise HTTPException(status_code=400, detail="Can't execute immediately")
    db.commit()
    db.refresh(order)
    order_id = order.id
    return CreateOrderResponse(order_id=order_id)

@app.get("/api/v1/order", response_model=List[Union[LimitOrder, MarketOrder]], tags=["order"], summary="List Orders")
def list_orders(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    orders = db.query(OrderModel).filter_by(user_id=current_user.id).all()
    result = []
    for o in orders:
        if o.type == 'LIMIT':
            result.append(LimitOrder(
                id=o.id, status=o.status, user_id=o.user_id, timestamp=o.timestamp,
                body=LimitOrderBody(direction=o.direction, ticker=o.ticker, qty=o.qty, price=o.price),
                filled=o.filled
            ))
        else:
            result.append(MarketOrder(
                id=o.id, status=o.status, user_id=o.user_id, timestamp=o.timestamp,
                body=MarketOrderBody(direction=o.direction, ticker=o.ticker, qty=o.qty)
            ))
    return result

@app.get("/api/v1/order/{order_id}", response_model=Union[LimitOrder, MarketOrder], tags=["order"], summary="Get Order")
def get_order(order_id: UUID, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    o = db.query(OrderModel).filter_by(id=order_id, user_id=current_user.id).first()
    if not o:
        raise HTTPException(status_code=404, detail="Order not found")
    if o.type == 'LIMIT':
        return LimitOrder(
            id=o.id, status=o.status, user_id=o.user_id, timestamp=o.timestamp,
            body=LimitOrderBody(direction=o.direction, ticker=o.ticker, qty=o.qty, price=o.price),
            filled=o.filled
        )
    else:
        return MarketOrder(
            id=o.id, status=o.status, user_id=o.user_id, timestamp=o.timestamp,
            body=MarketOrderBody(direction=o.direction, ticker=o.ticker, qty=o.qty)
        )

@app.delete("/api/v1/order/{order_id}", response_model=Ok, tags=["order"], summary="Cancel Order")
def cancel_order(order_id: UUID, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    o = db.query(OrderModel).filter_by(id=order_id, user_id=current_user.id).first()
    if not o:
        raise HTTPException(status_code=404, detail="Order not found")
    if o.status in [OrderStatus.EXECUTED, OrderStatus.CANCELLED]:
        raise HTTPException(status_code=400, detail="Order cannot be cancelled")
    o.status = OrderStatus.CANCELLED
    db.commit()
    return Ok()

@app.delete("/api/v1/admin/instrument/{ticker}", response_model=Ok, tags=["admin"], summary="Delete Instrument", description="Удаление инструмента")
def delete_instrument(ticker: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admin can delete instruments")
    if ticker == RUB_TICKER:
        raise HTTPException(status_code=400, detail="Cannot delete RUB instrument")
    instr = db.query(Instrument).filter_by(ticker=ticker).first()
    if not instr:
        raise HTTPException(status_code=404, detail="Instrument not found")
    
    db.delete(instr)
    db.commit()
    return Ok()

# if __name__ == '__main__':
#     uvicorn.run(app, host="0.0.0.0", port=8000)