"""Этап E: сравнение файлов, REST API и Selenium.

Запускать при работающем backend:
    python src/compare_sources.py
"""

import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Dict, List

import pandas as pd
import requests

import selenium_client


PROJECT_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_DIR / "data" / "raw"
RESULTS_DIR = PROJECT_DIR / "results"
BASE_URL = "http://127.0.0.1:8000"
COMPARISON_CSV_PATH = RESULTS_DIR / "comparison.csv"
COMPARISON_REPORT_PATH = RESULTS_DIR / "comparison_report.md"


def read_xml_items(path: Path) -> pd.DataFrame:
    """Читает XML через ElementTree так же, как требуется в этапе A."""

    root = ET.parse(path).getroot()
    records = []

    for item in root.findall("item"):
        records.append({element.tag: element.text for element in item})

    return pd.DataFrame(records)


def load_file_data() -> pd.DataFrame:
    """Читает CSV, JSON и XML и получает единый набор объектов из файлов."""

    csv_frame = pd.read_csv(RAW_DIR / "items.csv", sep=";")

    with (RAW_DIR / "items.json").open(encoding="utf-8") as file:
        json_frame = pd.DataFrame(json.load(file)["items"])

    xml_frame = read_xml_items(RAW_DIR / "items.xml")
    combined = pd.concat([csv_frame, json_frame, xml_frame], ignore_index=True)

    # У трёх файлов одинаковый набор объектов. Для корректного сопоставления с
    # API убираем дубликаты id и учебную строку без идентификатора.
    combined["id"] = pd.to_numeric(combined["id"], errors="coerce")
    combined = combined.dropna(subset=["id"]).drop_duplicates(subset=["id"])
    combined["id"] = combined["id"].astype("Int64")

    return combined


def load_api_data() -> pd.DataFrame:
    """Получает структурированные данные напрямую из официального API."""

    response = requests.get(f"{BASE_URL}/api/items", timeout=10)
    response.raise_for_status()
    return pd.DataFrame(response.json())


def load_selenium_data() -> pd.DataFrame:
    """Запускает браузерный сценарий и возвращает отфильтрованные строки DOM."""

    # Для автоматического сравнения браузер работает без окна. В stage D
    # HEADLESS остаётся False, поэтому при отдельном запуске Chrome виден.
    previous_headless = selenium_client.HEADLESS
    selenium_client.HEADLESS = True

    try:
        return selenium_client.main()
    finally:
        selenium_client.HEADLESS = previous_headless


def measure_method(name: str, loader: Callable[[], pd.DataFrame]) -> Dict[str, Any]:
    """Замеряет способ получения данных и превращает ошибку в строку отчёта."""

    started_at = time.perf_counter()

    try:
        dataframe = loader()
        duration = time.perf_counter() - started_at

        if "id" not in dataframe.columns:
            raise ValueError("В полученных данных отсутствует столбец id")

        return {
            "Способ": name,
            "Количество записей": len(dataframe),
            "Уникальных id": dataframe["id"].nunique(dropna=True),
            "Время, с": round(duration, 4),
            "Есть ошибки": "Нет",
        }

    except Exception as error:
        duration = time.perf_counter() - started_at

        return {
            "Способ": name,
            "Количество записей": 0,
            "Уникальных id": 0,
            "Время, с": round(duration, 4),
            "Есть ошибки": f"Да: {type(error).__name__}: {error}",
        }


def write_report(comparison: pd.DataFrame) -> None:
    """Создаёт короткий отчёт для переноса вывода этапа E в лабораторную."""

    # DataFrame.to_markdown требует стороннюю библиотеку tabulate. Простая
    # генерация Markdown здесь делает лабораторную самодостаточной.
    headers = comparison.columns.tolist()
    markdown_lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]

    for row in comparison.itertuples(index=False, name=None):
        cells = [str(value).replace("|", "\\|").replace("\n", " ") for value in row]
        markdown_lines.append("| " + " | ".join(cells) + " |")

    markdown_table = "\n".join(markdown_lines)
    report = f"""# Этап E Сравнение способов получения данных

{markdown_table}

## Вывод

Официальный REST API предпочтительнее браузерной автоматизации, когда он
доступен: API возвращает структурированные данные напрямую, не требует запуска
браузера и ожидания DOM, обычно работает быстрее и устойчивее к изменениям
разметки страницы. Selenium оправдан для динамических сайтов, когда API
отсутствует или нужно воспроизвести действия пользователя в браузере.

В строке Selenium число записей может быть меньше, поскольку сценарий этапа D
намеренно применяет фильтр категории «Электроника» и собирает только видимые
строки таблицы.
"""
    COMPARISON_REPORT_PATH.write_text(report, encoding="utf-8")


def main() -> None:
    """Запускает сравнение и сохраняет таблицу с итогами этапа E."""

    results: List[Dict[str, Any]] = [
        measure_method("CSV/XML/JSON", load_file_data),
        measure_method("REST API", load_api_data),
        measure_method("Selenium", load_selenium_data),
    ]

    comparison = pd.DataFrame(results)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    comparison.to_csv(COMPARISON_CSV_PATH, index=False, encoding="utf-8-sig")
    write_report(comparison)

    print(comparison.to_string(index=False))
    print(f"Таблица сохранена: {COMPARISON_CSV_PATH}")
    print(f"Вывод сохранён: {COMPARISON_REPORT_PATH}")


if __name__ == "__main__":
    main()
