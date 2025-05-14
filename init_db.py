from database import engine, Base
from sqlalchemy import inspect
from models import *

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print(engine.url)
    print("Tables created.")
    insp = inspect(engine)
    print("Tables in DB: ", insp.get_table_names())