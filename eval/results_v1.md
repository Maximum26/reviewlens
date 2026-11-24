# Результати оцінки

Режим: **реальний (Claude API, з кешем)**. Дата: 2026-11-24. Модель: `claude-haiku-5-5`. Відгуків: 22 (`data/gold.json`), немспам для aspect-метрик: 21.

## Метрики

| Метрика | Значення | Як рахується |
|---|---|---|
| Router accuracy | 19/22 = 86.4% | маршрут збігся з gold, усі відгуки |
| Aspect precision | 53/69 = 76.8% | пари (аспект, тональність), немспам-відгуки |
| Aspect recall | 53/56 = 94.6% | пари (аспект, тональність), немспам-відгуки |
| Sentiment accuracy | 53/55 = 96.4% | серед аспектів, знайдених за назвою |
| Validation retry rate | 0/21 = 0.0% | відгуки з ≥1 невдалою спробою extractor / ті, що дійшли до extractor |
| Quote validity (1-ша спроба) | 21/21 = 100.0% | перша відповідь extractor без цитати поза текстом / ті, що дійшли до extractor |
| Critic effect | 3/15 = 20.0% | чернетки, відхилені критиком хоча б раз / чернетки full |

## Помилки

Відгуки, де маршрут або набір пар (аспект, тональність) не збігся з gold.

| id | Очікувалось | Отримано | Тип |
|---|---|---|---|
| 4 | route=full; service (negative), quality (negative), speed (negative) | route=full; quality (negative), quality (negative), speed (negative) | аспекти |
| 6 | route=full; food (negative), price (negative), atmosphere (negative) | route=full; food (negative), food (negative), price (negative), atmosphere (negative) | аспекти |
| 8 | route=full; price (positive), speed (negative), food (negative) | route=full; food (negative), speed (negative), other (positive), price (positive) | аспекти |
| 9 | route=full; food (negative), service (negative), price (negative) | route=full; food (negative), food (negative), service (negative), price (negative), atmosphere (negative) | аспекти |
| 16 | route=positive; food (positive), price (positive) | route=full; food (positive), price (positive), quality (negative), other (positive) | маршрут, аспекти |
| 20 | route=positive; food (positive), service (positive), speed (positive), price (neutral) | route=full; atmosphere (positive), food (positive), service (positive), speed (positive), price (neutral) | маршрут, аспекти |
| 26 | route=positive; service (positive), speed (positive), other (positive), atmosphere (neutral) | route=full; speed (positive), other (positive), atmosphere (negative), service (positive) | маршрут, аспекти |
| 28 | route=full; food (positive), other (negative) | route=full; food (positive), food (negative), other (negative) | аспекти |
| 30 | route=positive; food (positive), atmosphere (positive), service (positive) | route=positive; food (positive), atmosphere (positive), other (positive), service (positive) | аспекти |
| 31 | route=positive; food (positive), service (positive), atmosphere (positive) | route=positive; atmosphere (positive), other (positive), atmosphere (positive), service (positive), service (positive), food (positive), food (positive) | аспекти |
| 39 | route=full; food (neutral), price (negative) | route=full; food (neutral), price (neutral) | аспекти |

## Технічне

- Нових записів у кеші (≈ викликів API): 83.
