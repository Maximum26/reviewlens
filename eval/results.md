# Результати оцінки

Режим: **реальний (Claude API, з кешем)**. Дата: 2026-11-25. Модель: `claude-haiku-5-5`. Відгуків: 22 (`data/gold.json`), немспам для aspect-метрик: 21.

## Метрики

| Метрика | Значення | Як рахується |
|---|---|---|
| Router accuracy | 22/22 = 100.0% | маршрут збігся з gold, усі відгуки |
| Aspect precision | 53/63 = 84.1% | пари (аспект, тональність), немспам-відгуки |
| Aspect recall | 53/56 = 94.6% | пари (аспект, тональність), немспам-відгуки |
| Sentiment accuracy | 53/55 = 96.4% | серед аспектів, знайдених за назвою |
| Validation retry rate | 2/21 = 9.5% | відгуки з ≥1 невдалою спробою extractor / ті, що дійшли до extractor |
| Quote validity (1-ша спроба) | 21/21 = 100.0% | перша відповідь extractor без цитати поза текстом / ті, що дійшли до extractor |
| Critic effect | 2/12 = 16.7% | чернетки, відхилені критиком хоча б раз / чернетки full |

## Помилки

Відгуки, де маршрут або набір пар (аспект, тональність) не збігся з gold.

| id | Очікувалось | Отримано | Тип |
|---|---|---|---|
| 8 | route=full; price (positive), speed (negative), food (negative) | route=full; food (negative), speed (negative), other (positive), price (positive) | аспекти |
| 9 | route=full; food (negative), service (negative), price (negative) | route=full; food (negative), service (negative), price (negative), atmosphere (negative) | аспекти |
| 16 | route=positive; food (positive), price (positive) | route=positive; food (positive), price (positive), food (negative), other (positive) | аспекти |
| 20 | route=positive; food (positive), service (positive), speed (positive), price (neutral) | route=positive; atmosphere (positive), food (neutral), service (positive), speed (positive), price (neutral) | аспекти |
| 26 | route=positive; service (positive), speed (positive), other (positive), atmosphere (neutral) | route=positive; speed (positive), other (positive), atmosphere (negative), service (positive) | аспекти |
| 28 | route=full; food (positive), other (negative) | route=full; food (positive), food (negative), service (negative) | аспекти |
| 31 | route=positive; food (positive), service (positive), atmosphere (positive) | route=positive; atmosphere (positive), service (positive), food (positive), other (positive) | аспекти |

## Технічне

- Нових записів у кеші (≈ викликів API): 64.

## v1 → v2

Зміни v2: промпт екстрактора (одна пара аспект+тональність, одна цитата), промпт роутера (full лише з конкретною жалобою), кодова склейка дублів пар після валідації. Дані ті самі (22 відгуки).

| Метрика | v1 | v2 |
|---|---|---|
| Router accuracy | 19/22 = 86.4% | 22/22 = 100.0% |
| Aspect precision | 53/69 = 76.8% | 53/63 = 84.1% |
| Aspect recall | 53/56 = 94.6% | 53/56 = 94.6% |
| Sentiment accuracy | 53/55 = 96.4% | 53/55 = 96.4% |
| Validation retry rate | 0/21 = 0.0% | 2/21 = 9.5% |
| Quote validity (1-ша спроба) | 21/21 = 100.0% | 21/21 = 100.0% |
| Critic effect | 3/15 = 20.0% | 2/12 = 16.7% |
