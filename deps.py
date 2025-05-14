from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from database import SessionLocal
from models import User

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(authorization: str = Header(None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("TOKEN "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing Authorization header")
    api_key = authorization[6:].strip()
    user = db.query(User).filter_by(api_key=api_key).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return user 