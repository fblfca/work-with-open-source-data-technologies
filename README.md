# Лабораторная работа 1

Проект демонстрирует получение одного набора объектов из CSV, JSON, XML, REST API и динамической веб-страницы. В нём реализованы нормализация данных, REST CRUD, обработка ошибок Requests, Selenium и сравнение способов получения данных.

## Установка

Требуется Python 3.9 или новее и установленный Google Chrome.

```bash
python -m pip install -r requirements.txt
```

## Запуск

Сначала сформируйте нормализованные файлы:

```bash
python src/formats.py
```

В отдельном терминале запустите локальный backend:

```bash
python -m uvicorn backend.main:app --reload
```

После запуска backend выполните сценарии по очереди:

```bash
python src/api_client.py
python src/selenium_client.py
python src/compare_sources.py
```

## Результаты

- `data/processed/items_normalized.csv`, `.json`, `.xml` — нормализованные данные.
- `results/api_log.csv` — результаты REST CRUD и обработки ошибок.
- `results/selenium_items.csv` — строки динамической таблицы после фильтра Selenium.
- `results/comparison.csv` и `results/comparison_report.md` — сравнение файлов, API и Selenium.
