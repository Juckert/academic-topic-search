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

Создавайте экземпляр один раз и переиспользуйте его из Streamlit. При изменении
корпуса создайте новый экземпляр. Индексы находятся в памяти.
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
