# Запуск на сервере Ubuntu

Сервис — обычное ASGI-приложение FastAPI `topic_search.asgi:app`. Его запускает
uvicorn. Тот же процесс раздаёт собранный интерфейс из `frontend/dist`, поэтому
интерфейс и API открываются по одному адресу.

Нужны Python 3.12 с venv и git. Node.js 22.12+ требуется только для сборки
интерфейса.

## 1. Системные пакеты

```bash
sudo apt update
sudo apt install -y git python3 python3-venv
python3 --version   # ожидается 3.12

# В стандартных репозиториях Ubuntu Node.js может быть старее 22.12
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
sudo apt install -y nodejs
```

## 2. Код и данные

```bash
sudo mkdir -p /opt/topic-search && sudo chown "$USER" /opt/topic-search
git clone <адрес репозитория> /opt/topic-search
cd /opt/topic-search
mkdir -p data
```

Корпус не хранится в Git. Скопируйте его с рабочей машины:

```bash
scp data/topics.json <пользователь>@<сервер>:/opt/topic-search/data/
```

Формат полей задаётся в `configs/corpus-example.json`. Там же находятся `dataset_id` и `dataset_version`.

## 3. Окружение и сборка интерфейса

```bash
cd /opt/topic-search
python3 -m venv .venv
.venv/bin/pip install -r requirements-api.txt
(cd frontend && npm ci --ignore-scripts && VITE_SEARCH_MODE=api npm run build)
```

## 4. Запуск

```bash
.venv/bin/uvicorn topic_search.asgi:app --host 0.0.0.0 --port 8000
```

Откройте `http://<адрес сервера>:8000`. Если включён ufw, откройте порт:
`sudo ufw allow 8000/tcp`.

Шаги 3–4 можно выполнить одной командой. Она собирает интерфейс и запускает тот же uvicorn:

```bash
.venv/bin/python -m scripts.serve --host 0.0.0.0 --port 8000
.venv/bin/python -m scripts.serve --skip-build --host 0.0.0.0   # без пересборки
```

Настройки сервиса передаются через переменные окружения:

| Переменная | Значение по умолчанию | Назначение |
| --- | --- | --- |
| `TOPIC_SEARCH_CONFIG` | `configs/search.json` | Профиль поиска |
| `TOPIC_SEARCH_DEVICE` | из профиля | `cpu`, `cuda:0` или `auto` для нейронных моделей |
| `TOPIC_SEARCH_FRONTEND_DIST` | `frontend/dist` | Собранный интерфейс; пустое значение отключает раздачу |

Запускайте один процесс, без `--workers`: каждый процесс заново загружает корпус и модели в память.
Если корпус или модель не загрузились, сервис всё равно стартует, пишет причину в лог,
а API отвечает 503.

Для профилей dense, hybrid и rerank дополнительно установите `requirements-dense-lock.txt`
(или `requirements-cuda.txt`) и скачайте модели. Подробности — в [LOCAL_RUN](LOCAL_RUN.md).

## 5. Постоянный запуск через systemd

Файл `/etc/systemd/system/topic-search.service`:

```ini
[Unit]
Description=Academic topic search
After=network.target

[Service]
User=<пользователь>
WorkingDirectory=/opt/topic-search
Environment=TOPIC_SEARCH_CONFIG=configs/search.json
ExecStart=/opt/topic-search/.venv/bin/uvicorn topic_search.asgi:app --host 0.0.0.0 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now topic-search
sudo systemctl status topic-search
journalctl -u topic-search -f
```

Обновление:

```bash
cd /opt/topic-search && git pull
.venv/bin/pip install -r requirements-api.txt
(cd frontend && npm ci --ignore-scripts && VITE_SEARCH_MODE=api npm run build)
sudo systemctl restart topic-search
```

Сервис отдаёт HTTP без шифрования. Для доступа из интернета поставьте перед ним nginx
с HTTPS и запускайте uvicorn с `--host 127.0.0.1`.
