FROM python:3.12-slim

WORKDIR /server

RUN apt update -y && apt upgrade -y

RUN apt install uvicorn -y

COPY requirements.txt requirements.txt

RUN pip install -r requirements.txt

COPY . .

ENTRYPOINT [ "uvicorn", "main:app", "--port","8888", "--host", "0.0.0.0"]