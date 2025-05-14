# exchange_API

### Первый запуск
Создаём окружение
```bash
python3 -m venv venv
```
Устанавливаем зависимости
```bash
pip install -r requirements.txt
```
Входим в окружение
```bash
source venv/bin/activate
```
Запускаем контейнер с БД
```bash
docker-compose up -d
```
Инициализируем БД
```bash
python3 init_db.py
```
Запускаем сервер
```bash
uvicorn main:app --reload
```