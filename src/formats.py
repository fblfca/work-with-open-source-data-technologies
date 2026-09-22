'''Этап A: чтение, диагностика и нормализация CSV, JSON и XML.

Запуск из корня проекта:
    python src/formats.py
'''

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_DIR / 'data' / 'raw'
PROCESSED_DIR = PROJECT_DIR / 'data' / 'processed'
SOURCE_PRIORITY = {'json': 3, 'xml': 2, 'csv': 1}


def read_csv_items(path: Path) -> pd.DataFrame:
    '''Читает учебный CSV с разделителем ';'.'''

    return pd.read_csv(path, sep=';')


def read_json_items(path: Path) -> pd.DataFrame:
    '''Извлекает список объектов из поля items JSON-документа.'''

    with path.open(encoding='utf-8') as file:
        return pd.DataFrame(json.load(file)['items'])


def read_xml_items(path: Path) -> pd.DataFrame:
    '''Преобразует элементы <item> XML-документа в DataFrame.'''

    root = ET.parse(path).getroot()
    records: List[Dict[str, str]] = []

    for item in root.findall('item'):
        records.append({element.tag: element.text for element in item})

    return pd.DataFrame(records)


def parse_updated_at(value: object) -> pd.Timestamp:
    '''Разбирает все форматы дат учебного набора в единый timestamp.'''

    if pd.isna(value) or str(value).strip() == '':
        return pd.NaT

    value = str(value).strip()
    formats = [
        '%Y-%m-%dT%H:%M:%S%z',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%dT%H:%M:%S',
        '%d.%m.%Y %H:%M:%S',
        '%d.%m.%Y %H:%M',
        '%Y-%m-%d',
        '%d.%m.%Y',
        '%Y/%m/%d',
        '%Y.%m.%d',
        '%d/%m/%Y',
    ]

    for date_format in formats:
        try:
            timestamp = pd.to_datetime(value, format=date_format)

            if timestamp.tzinfo is not None:
                return timestamp.tz_convert('Europe/Moscow').tz_localize(None)

            return timestamp
        except (ValueError, TypeError):
            continue

    return pd.NaT


def normalize_items(dataframe: pd.DataFrame) -> pd.DataFrame:
    '''Приводит набор к единой схеме и удаляет полные дубликаты.'''

    result = dataframe.copy()

    result['id'] = pd.to_numeric(result['id'], errors='coerce').astype('Int64')
    result['name'] = (
        result['name'].astype('string').str.strip().str.replace(r'\s+', ' ', regex=True)
    )
    result['category'] = (
        result['category']
        .astype('string')
        .str.strip()
        .str.replace(r'\s+', ' ', regex=True)
        .str.lower()
        .str.capitalize()
    )

    cleaned_value = (
        result['value']
        .astype('string')
        .str.strip()
        .str.replace(r'\s+', '', regex=True)
        .str.replace(',', '.', regex=False)
    )
    result['value'] = pd.to_numeric(cleaned_value, errors='coerce')
    result['updated_at'] = result['updated_at'].apply(parse_updated_at)

    active_values = {
        'true': True,
        'да': True,
        '1': True,
        'yes': True,
        'false': False,
        'нет': False,
        '0': False,
        'no': False,
    }
    result['active'] = (
        result['active'].astype('string').str.strip().str.lower().map(active_values)
    ).astype('boolean')

    return result.drop_duplicates()


def describe_source(name: str, dataframe: pd.DataFrame) -> None:
    '''Выводит обязательную диагностику каждого исходного формата.'''

    print(f'\n{name}')
    print('Количество записей:', len(dataframe))
    print('Столбцы:', dataframe.columns.tolist())
    print('Типы данных:\n', dataframe.dtypes)
    print('Пропущенные значения:\n', dataframe.isna().sum())
    print('Повторяющиеся id:', dataframe['id'].duplicated().sum())


def build_normalized_dataset() -> pd.DataFrame:
    '''Объединяет источники и выбирает одну валидную запись на каждый id.

    Правило конфликта: наиболее поздний updated_at; при равенстве дат приоритет
    JSON → XML → CSV. Записи без id исключаются из итогового набора, потому что
    их нельзя однозначно объединить и адресовать через REST API.
    '''

    sources = {
        'csv': read_csv_items(RAW_DIR / 'items.csv'),
        'json': read_json_items(RAW_DIR / 'items.json'),
        'xml': read_xml_items(RAW_DIR / 'items.xml'),
    }

    for name, dataframe in sources.items():
        describe_source(name.upper(), dataframe)

    normalized_sources = []
    for name, dataframe in sources.items():
        normalized = normalize_items(dataframe)
        normalized['source'] = name
        normalized_sources.append(normalized)

    combined = pd.concat(normalized_sources, ignore_index=True)
    combined = combined.dropna(subset=['id']).copy()
    combined['source_priority'] = combined['source'].map(SOURCE_PRIORITY)

    combined = combined.sort_values(
        ['id', 'updated_at', 'source_priority'],
        na_position='first',
    )
    final = combined.drop_duplicates(subset=['id'], keep='last')
    final = final.drop(columns=['source', 'source_priority'])
    final = final.sort_values('id').reset_index(drop=True)

    return final


def save_processed_data(dataframe: pd.DataFrame) -> None:
    '''Сохраняет один итоговый набор в трёх требуемых форматах.'''

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(
        PROCESSED_DIR / 'items_normalized.csv',
        sep=';',
        index=False,
        encoding='utf-8',
    )
    dataframe.to_json(
        PROCESSED_DIR / 'items_normalized.json',
        orient='records',
        force_ascii=False,
        date_format='iso',
        indent=2,
    )
    dataframe.to_xml(
        PROCESSED_DIR / 'items_normalized.xml',
        index=False,
        encoding='utf-8',
        # Встроенный xml.etree не требует отдельной зависимости lxml.
        parser='etree',
    )


def main() -> None:
    '''Запускает этап A и показывает итоговые параметры набора.'''

    normalized = build_normalized_dataset()
    save_processed_data(normalized)

    print('\nИтог после нормализации')
    print('Количество записей:', len(normalized))
    print('Уникальных id:', normalized['id'].nunique())
    print('Повторяющиеся id:', normalized['id'].duplicated().sum())


if __name__ == '__main__':
    main()
