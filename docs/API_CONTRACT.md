# API поиска учебных тем

Предлагаемый контракт frontend и backend. Базовый путь — `/api/v1`, формат запросов и ответов — JSON в UTF-8.

[OpenAPI со схемами и примерами](openapi.json)

Все перечисленные поля обязательны. Если значение отсутствует, передаётся `null` там, где он разрешён в типе поля.

## GET /api/v1/filters

Запрос без тела. Ответ HTTP 200:

| Поле | Тип | Значение |
|---|---|---|
| `api_version` | string | `1.0` |
| `dataset_id` | string | Идентификатор каталога, 1–128 символов |
| `dataset_version` | string | Версия каталога, 1–128 символов |
| `corpus_size` | integer | Число записей в каталоге, от 0 |
| `departments` | string[] | Уникальные подразделения, до 2000 значений по 1–300 символов |
| `years` | integer[] | Уникальные годы от 1900 до 2200 |
| `score_type` | string | Шкала оценок из таблицы ниже |
| `candidate_limit` | integer | Максимальное число работ в ответе, от 1 до 50 |

## POST /api/v1/search

### Поля запроса

| Поле | Тип | Значение |
|---|---|---|
| `title` | string | Название темы, 1–500 символов, содержит букву или цифру |
| `annotation` | string или null | Необязательная аннотация, до 3498 символов |
| `filters` | object | Объект с двумя полями ниже |
| `filters.department` | string или null | Подразделение из `departments`; `null` — все подразделения |
| `filters.year` | integer или null | Год из `years`; `null` — все годы |

Тексты передаются без пробелов по краям. Пустая аннотация передаётся как `null`. Если указаны оба фильтра, найденные работы соответствуют обоим значениям.

~~~json
{
  "title": "Оценка устойчивости банков",
  "annotation": null,
  "filters": { "department": null, "year": 2026 }
}
~~~

### Поля ответа HTTP 200

| Поле | Тип | Значение |
|---|---|---|
| `api_version` | string | `1.0` |
| `search_id` | string | Идентификатор проверки, 1–128 символов |
| `query` | object | Поля выполненного запроса в формате выше |
| `method` | string | Обозначение метода: `bm25`, `dense` или `hybrid` |
| `reranker_enabled` | boolean | Признак дополнительного ранжирования |
| `score_type` | string | Шкала итоговой оценки |
| `dataset_id`, `dataset_version` | string | Идентификатор и версия каталога, по 1–128 символов |
| `pipeline_version` | string | Версия поискового сервиса, 1–128 символов |
| `corpus_size` | integer | Число записей в каталоге, от 0 |
| `eligible_documents` | integer | Число записей, соответствующих фильтрам, от 0 |
| `candidate_limit` | integer | Максимальное число работ в ответе, от 1 до 50 |
| `candidate_count` | integer | Длина массива `hits`, от 0 до `candidate_limit` |
| `status` | string | `results` или `empty` |
| `empty_reason` | string или null | Причина пустой выдачи или `null` |
| `hits` | object[] | Найденные работы, до 50 записей в порядке убывания `score` |

`candidate_count` не превышает `eligible_documents`, а `eligible_documents` — `corpus_size`. Идентификаторы работ в `hits` уникальны.

- Непустой ответ: `status: results`, `empty_reason: null`, в `hits` есть записи.
- Пустой ответ: `status: empty`, `candidate_count: 0`, `hits: []`.
- `empty_reason: filters_or_exclusions` — область поиска пуста.
- `empty_reason: no_candidates` — область содержит записи, подходящие работы не найдены.

### Поля найденной работы в hits

| Поле | Тип | Значение |
|---|---|---|
| `id` | string | Стабильный идентификатор работы, 1–128 символов |
| `title` | string | Название, 1–500 символов |
| `annotation` | string или null | Аннотация, до 12000 символов |
| `annotation_origin` | string | `original`, `generated`, `unknown` или `missing` |
| `metadata` | object | Метаданные из таблицы ниже |
| `score` | number | Итоговая оценка в шкале `score_type` |
| `score_type` | string | Совпадает с `score_type` в корне ответа |
| `retrieval_score` | number | Дополнительный балл поиска, возвращённый сервером |
| `retrieval_score_type` | string | Шкала дополнительного балла: `bm25`, `cosine` или `rrf` |

Происхождение аннотации: `original` — из источника, `generated` — создана автоматически, `unknown` — неизвестно. При отсутствии аннотации передаются `annotation: null` и `annotation_origin: missing`.

### Поля metadata

| Поле | Тип | Значение |
|---|---|---|
| `year` | integer или null | Год от 1900 до 2200 |
| `department` | string или null | Подразделение, до 300 символов |
| `program` | string или null | Направление, до 300 символов |
| `work_type` | string или null | Тип работы, до 100 символов |
| `source_url` | string или null | Абсолютная HTTP(S)-ссылка без учётных данных, до 2048 символов |

### Значения score_type

| Значение | Допустимый балл |
|---|---|
| `bm25` | Конечное число от 0 |
| `cosine` | От -1 до 1 с допуском 0.000001 |
| `rrf` | Конечное число от 0 |
| `reranker_logit` | Конечное число |

Оценки передаются в указанной шкале. Допустимые сочетания `method`, `reranker_enabled` и `score_type` заданы в OpenAPI.

## Ответы с ошибкой

| HTTP | error.code | Значение |
|---|---|---|
| 422 | `invalid_request` | Некорректный текст или фильтр |
| 503 | `search_unavailable` | Поиск временно недоступен |
| 500 | `internal_error` | Внутренняя ошибка сервера |

| Поле | Тип | Значение |
|---|---|---|
| `api_version` | string | `1.0` |
| `error` | object | Объект ошибки |
| `error.code` | string | Код из таблицы выше |
| `error.message` | string | Сообщение для пользователя, 1–300 символов |
| `error.field` | string или null | Поле запроса с ошибкой, до 128 символов; `null` для общей ошибки |

`error.message` не содержит traceback, локальные пути, секреты или содержимое окружения.

~~~json
{
  "api_version": "1.0",
  "error": {
    "code": "invalid_request",
    "message": "Проверьте длину аннотации.",
    "field": "annotation"
  }
}
~~~
