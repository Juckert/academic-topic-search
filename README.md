# Academic Topic Search

Локальный поиск похожих тем курсовых и ВКР. Сейчас подготовлен код для будущих
данных заказчика. Метрики качества не зафиксированы, гипотезы не подтверждены.

## Ветки

| Ветка | Добавленный подход |
| --- | --- |
| `baseline` | BM25 по тексту темы, загрузка корпуса, расчёт метрик |
| `dense` | Векторный поиск E5, локальный CPU/CUDA |
| `hybrid` | Объединение BM25 и E5 через RRF |
| `reranker` | Cross-encoder, общий pipeline, фильтры, пороги, Python API и CLI |
| `main` | Полная текущая версия, совпадает с `reranker` |

Ветки последовательны: каждая наследует предыдущую. История отражает подготовку
кода, а не проведённые исследования. Streamlit разрабатывается отдельно.

## Данные и запуск

Python 3.12. Поместите свой JSON-массив записей с полями `id`, `title` в
`data/topics.json`. Для другой схемы или JSONL/CSV измените
`configs/corpus-example.json`. Аннотации подключаются явно; метаданные необязательны.
Данные, веса и результаты остаются локально и исключены из Git.

```powershell
python -m unittest discover -s tests -v
python -m baseline.run --method bm25 --query "Поиск похожих тем"
```

BM25 использует только стандартную библиотеку. Проверочные записи внутри тестов
служат проверке кода и не являются набором для исследования качества.

## Метрики после получения данных

Для Hit@k/MRR@k подготовьте локальный JSON-массив запросов с полями
`query_id`, `query`, `expected_match_id` (строковый ID документа корпуса):

```powershell
python -m baseline.evaluate --method bm25 --queries data/queries.json --output results/bm25.json
```

Этот запуск оценивает поиск одного известного релевантного документа. Он не
оценивает отрицательные запросы и решение о дубле. `baseline.metrics.graded_metrics`
содержит расчёт nDCG/Recall по внешним оценкам релевантности 0–3 (релевантны 2–3);
при неразмеченных документах в выдаче метрики не вычисляются.
Разбиение данных, разметку и пороги предстоит согласовать на реальном корпусе.

## Нейронные модели

```powershell
python -m pip install -r requirements-dense-lock.txt
python -m baseline.download_model
python -m baseline.run --method dense --query "Поиск похожих тем"
```

Для CUDA используйте отдельное окружение и `requirements-cuda.txt` вместо CPU lock.
Устройство задаётся в `configs/dense-e5.json`: `cpu`, `cuda:0` или `auto`.
Скачивание весов нужно один раз; дальнейший поиск выполняется локально.
Работа CUDA требует проверки на целевом ПК, здесь доступен CPU.

## Гибридный поиск

`python -m baseline.run --method hybrid --query "Поиск похожих тем"`

Параметры RRF находятся в `configs/hybrid-rrf.json`; они пока не подобраны на данных.

## Общий pipeline и reranker

[Инструкции для Python API, CLI и CUDA](docs/LOCAL_RUN.md).

Профиль `configs/search-rerank.json` добавляет cross-encoder к гибридному поиску.

Для оценки полного pipeline на будущих размеченных данных:
`python -m baseline.evaluate --search-config configs/search-rerank.json --queries data/queries.json`.
Размер `candidate_limit` профиля должен быть не меньше максимального cutoff.

Эта версия: **reranker / main — полный код**.
