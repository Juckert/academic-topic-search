# Локальный pipeline

Сначала подключите корпус через `configs/corpus-example.json` (см. README).
Для нейронного поиска установите CPU-зависимости из `requirements-dense-lock.txt`
или CUDA-зависимости из `requirements-cuda.txt` в отдельное окружение.

```powershell
python -m baseline.download_model
python -m baseline.download_model --config configs/reranker.json
python -m topic_search --config configs/search-rerank.json --query "Поиск похожих тем"
python -m scripts.check_device --device cuda
```

Профили: `search.json` — BM25, `search-dense.json` — E5,
`search-hybrid.json` — RRF, `search-rerank.json` — RRF + cross-encoder.
`search-local-gpu.json` включает тот же pipeline на `cuda:0`.
Можно переопределить устройство через `--device cpu|cuda:0|auto`.
GPU-выполнение здесь не проверено; проверяйте на целевой RTX 5080.

```python
from topic_search import SearchPipeline

search = SearchPipeline.from_config("configs/search-rerank.json", device="auto")
result = search.search("Поиск похожих тем", top_k=5,
                       filters={"year": 2026}, exclude_ids=["current-topic-id"])
```

## Веб-сервис

HTTP-обёртка `topic_search/api.py` реализует [контракт API](API_CONTRACT.md).
Зависимости ставятся в `.venv` из `requirements-api.txt`.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-api.txt
.\.venv\Scripts\python.exe -m topic_search.api --config configs/search.json
```

Сервер слушает `http://127.0.0.1:8000`, маршруты — `/api/v1/filters` и
`/api/v1/search`. Профиль должен иметь `threshold: null`. Если корпус или модель
не загрузились, сервер запускается, пишет причину в лог и отвечает 503.
`dataset_id` и `dataset_version` берутся из конфигурации корпуса,
`pipeline_version` — из поля профиля или из метода (`bm25`, `hybrid+rerank`).

Проверка вместе с интерфейсом, один процесс (нужен Node.js 22.12+):

```powershell
.\scripts\serve.ps1                      # сборка frontend в режиме API и запуск
.\scripts\serve.ps1 -SkipBuild           # только API или уже собранный dist
.\scripts\serve.ps1 -Config configs/search-hybrid.json
```

Интерфейс и API открываются на `http://127.0.0.1:8000`. Собранный
`frontend/dist` раздаётся автоматически, если он есть. Для разработки интерфейса
запустите API отдельно, а в `frontend` — `npm run dev` с `VITE_SEARCH_MODE=api`
в `.env.local`; Vite перенаправит `/api` на порт 8000.

## Повторное использование pipeline

Создавайте экземпляр один раз и переиспользуйте его в поисковом сервисе.
При изменении корпуса создайте новый экземпляр. Индексы находятся в памяти.
[Контракт веб-интерфейса](API_CONTRACT.md) описывает HTTP-обёртку.
Фильтры и исключения применяются до отсечения кандидатов. Затем выполняются
reranker, необязательный порог и top-k. Значения метаданных сравниваются точно:
для CSV год обычно строковый, для JSON он может быть числом.

Порог по умолчанию отключён. Для включения передайте `threshold` с полями
`score_type` (`bm25`, `cosine`, `rrf`, `reranker_logit`) и `value`.
Шкала должна совпадать с итоговой оценкой профиля. Пороги требуется подобрать
на размеченных данных. Оценки не являются вероятностями дубля; пустая выдача
не доказывает новизну. Классификация дублей и генерация объяснений не реализованы.

E5 и reranker выполняются на выбранном CPU/CUDA, точное векторное сравнение,
BM25 и RRF — на CPU. Настройки моделей (batch size, max length) находятся
в JSON-конфигурациях. Длинные тексты обрезаются до max length.
