'''Локальный REST API для лабораторной работы 1.

Сервер загружает итоговые нормализованные данные из CSV при старте и хранит
их в памяти. Поэтому POST, PUT, PATCH и DELETE можно безопасно демонстрировать:
после перезапуска Uvicorn исходный CSV останется неизменным.
'''

import asyncio
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Response, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


app = FastAPI(
    title='Лаба1',
    version='1.0.0'
)


class ItemInput(BaseModel):
    '''Полный набор изменяемых полей объекта без его идентификатора.'''

    name: str
    category: str
    value: Optional[float] = None
    updated_at: Optional[str] = None
    active: Optional[bool] = None


class Item(ItemInput):
    '''Ресурс API. Его id задаётся при POST или берётся из URL при PUT.'''

    id: int


class ItemPatch(BaseModel):
    '''Все поля необязательны: PATCH изменяет только переданные поля.'''

    name: Optional[str] = None
    category: Optional[str] = None
    value: Optional[float] = None
    updated_at: Optional[str] = None
    active: Optional[bool] = None


PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_DIR / 'data' / 'processed' / 'items_normalized.csv'
REQUIRED_COLUMNS = {'id', 'name', 'category', 'value', 'updated_at', 'active'}


def model_to_dict(model: BaseModel, **kwargs) -> dict:
    '''Поддерживает Pydantic 2 и Pydantic 1, если он установлен локально.'''

    if hasattr(model, 'model_dump'):
        return model.model_dump(**kwargs)

    return model.dict(**kwargs)


def optional_string(value: object) -> Optional[str]:
    '''Преобразует pandas NaN/NaT в JSON-совместимое None.'''

    return None if pd.isna(value) else str(value)


def optional_boolean(value: object) -> Optional[bool]:
    '''Безопасно читает булевы значения после выгрузки DataFrame в CSV.'''

    if pd.isna(value):
        return None

    normalized = str(value).strip().lower()

    if normalized in {'true', '1', 'да', 'yes'}:
        return True
    if normalized in {'false', '0', 'нет', 'no'}:
        return False

    return None


def load_items() -> dict[int, Item]:
    '''Загружает один канонический набор данных для API из processed CSV.'''

    if not DATA_PATH.exists():
        raise RuntimeError(
            f'Не найден нормализованный файл: {DATA_PATH}. '
            'Сначала выполните этап нормализации данных.'
        )

    # CSV этапа A сохранён с разделителем ';'.
    dataframe = pd.read_csv(DATA_PATH, sep=';')

    missing_columns = REQUIRED_COLUMNS.difference(dataframe.columns)
    if missing_columns:
        raise RuntimeError(
            'В нормализованном файле отсутствуют колонки: '
            f"{', '.join(sorted(missing_columns))}"
        )

    # Объект без id невозможно адресовать через /api/items/{id}, поэтому
    # намеренно грязная строка с пустым идентификатором не попадает в API.
    dataframe = dataframe.dropna(subset=['id']).copy()
    dataframe['id'] = pd.to_numeric(dataframe['id'], errors='raise').astype(int)

    if dataframe['id'].duplicated().any():
        duplicate_ids = dataframe.loc[
            dataframe['id'].duplicated(keep=False), 'id'
        ].tolist()
        raise RuntimeError(
            'Нормализованный файл содержит повторяющиеся id: '
            f'{duplicate_ids}'
        )

    loaded_items: dict[int, Item] = {}

    for row in dataframe.to_dict(orient='records'):
        item_id = int(row['id'])

        # Переход от pandas-типов к обычным Python-типам нужен, чтобы FastAPI
        # корректно сериализовал пропуски как JSON null, а не как NaN.
        loaded_items[item_id] = Item(
            id=item_id,
            name=str(row['name']),
            category=str(row['category']),
            value=None if pd.isna(row['value']) else float(row['value']),
            updated_at=optional_string(row['updated_at']),
            active=optional_boolean(row['active']),
        )

    return loaded_items


# Хранилище намеренно находится только в памяти. CRUD-сценарий не перезаписывает
# результаты этапа A и каждый запуск сервера начинается с того же processed CSV.
items: dict[int, Item] = load_items()


def get_existing_item(item_id: int) -> Item:
    '''Возвращает ресурс или единообразный HTTP 404.'''

    item = items.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail='Объект не найден')

    return item


@app.get('/api/items', response_model=list[Item])
def get_items() -> list[Item]:
    '''Возвращает все текущие объекты в устойчивом порядке id.'''

    return [items[item_id] for item_id in sorted(items)]


@app.get('/api/items/{item_id}', response_model=Item)
def get_item(item_id: int) -> Item:
    '''GET получает один ресурс по его идентификатору.'''

    return get_existing_item(item_id)


@app.get('/api/test/slow')
async def slow_response(delay: float = 2.0) -> dict:
    """Учебный endpoint для детерминированной проверки Timeout в этапе C."""

    if delay < 0 or delay > 5:
        raise HTTPException(
            status_code=422,
            detail='Параметр delay должен быть в диапазоне от 0 до 5 секунд.',
        )

    # Клиент этапа C запрашивает delay=2 с timeout=0.1, поэтому получает
    # requests.exceptions.Timeout без зависимости от внешних сайтов.
    await asyncio.sleep(delay)
    return {'delay_seconds': delay, 'status': 'completed'}


@app.get('/dynamic', response_class=HTMLResponse)
def dynamic_page() -> str:
    """Возвращает страницу, которую JavaScript заполняет только после клика.

    В исходном HTML нет строк таблицы. Поэтому requests.get('/dynamic') увидит
    только шаблон страницы, а Selenium после выполнения JavaScript — сами данные.
    """

    return """
    <!doctype html>
    <html lang="ru">
    <head>
      <meta charset="utf-8">
      <title>Динамическая таблица объектов</title>
      <style>
        body { font-family: Arial, sans-serif; margin: 2rem; color: #222; }
        button, select { font-size: 1rem; padding: .45rem .7rem; margin-right: .5rem; }
        #status { display: inline-block; margin: .75rem 0; min-height: 1.2rem; }
        table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
        th, td { border: 1px solid #bbb; padding: .5rem; text-align: left; }
        th { background: #f2f2f2; }
      </style>
    </head>
    <body>
      <h1>Объекты из REST API</h1>
      <p>Нажмите кнопку: данные будут загружены JavaScript-запросом к API.</p>

      <button id="load-data" type="button">Загрузить данные</button>
      <label for="category-filter">Категория:</label>
      <select id="category-filter" disabled>
        <option value="">Все категории</option>
      </select>
      <div id="status" data-state="idle">Данные ещё не загружены</div>

      <table id="items-table">
        <thead>
          <tr>
            <th data-field="id">id</th>
            <th data-field="name">name</th>
            <th data-field="category">category</th>
            <th data-field="value">value</th>
            <th data-field="updated_at">updated_at</th>
            <th data-field="active">active</th>
          </tr>
        </thead>
        <tbody id="items-body"></tbody>
      </table>

      <script>
        const loadButton = document.getElementById('load-data');
        const filter = document.getElementById('category-filter');
        const tableBody = document.getElementById('items-body');
        const status = document.getElementById('status');
        let allItems = [];

        function displayValue(value) {
          return value === null || value === undefined ? '' : String(value);
        }

        function renderRows() {
          const selectedCategory = filter.value;
          const visibleItems = selectedCategory
            ? allItems.filter(item => item.category === selectedCategory)
            : allItems;

          tableBody.replaceChildren();

          for (const item of visibleItems) {
            const row = document.createElement('tr');
            for (const field of ['id', 'name', 'category', 'value', 'updated_at', 'active']) {
              const cell = document.createElement('td');
              cell.textContent = displayValue(item[field]);
              row.appendChild(cell);
            }
            tableBody.appendChild(row);
          }

          status.textContent = `Показано записей: ${visibleItems.length}`;
          status.dataset.state = 'loaded';
        }

        function fillCategoryFilter() {
          const categories = [...new Set(allItems.map(item => item.category))].sort();
          filter.replaceChildren(new Option('Все категории', ''));
          for (const category of categories) {
            filter.appendChild(new Option(category, category));
          }
          filter.disabled = false;
        }

        loadButton.addEventListener('click', async () => {
          loadButton.disabled = true;
          status.textContent = 'Загрузка данных...';
          status.dataset.state = 'loading';

          try {
            const response = await fetch('/api/items');
            if (!response.ok) {
              throw new Error(`HTTP ${response.status}`);
            }

            allItems = await response.json();
            fillCategoryFilter();
            renderRows();
          } catch (error) {
            status.textContent = `Ошибка загрузки: ${error.message}`;
            status.dataset.state = 'error';
            loadButton.disabled = false;
          }
        });

        filter.addEventListener('change', renderRows);
      </script>
    </body>
    </html>
    """


@app.post('/api/items', response_model=Item, status_code=status.HTTP_201_CREATED)
def create_item(item: Item) -> Item:
    '''POST создаёт новый объект; существующий id считается конфликтом.'''

    if item.id in items:
        raise HTTPException(
            status_code=409,
            detail='Объект с таким id уже существует',
        )

    items[item.id] = item
    return item


@app.put('/api/items/{item_id}', response_model=Item)
def replace_item(item_id: int, item: ItemInput) -> Item:
    '''PUT заменяет объект целиком, поэтому принимает полный ItemInput.'''

    get_existing_item(item_id)

    replacement = Item(id=item_id, **model_to_dict(item))
    items[item_id] = replacement

    return replacement


@app.patch('/api/items/{item_id}', response_model=Item)
def update_item(item_id: int, patch: ItemPatch) -> Item:
    '''PATCH меняет только поля, присутствующие в теле запроса.'''

    current = get_existing_item(item_id)
    updated_data = model_to_dict(current)

    # exclude_unset сохраняет отличие между «поле не прислали» и
    # «поле прислали со значением null».
    updated_data.update(model_to_dict(patch, exclude_unset=True))

    updated_item = Item(**updated_data)
    items[item_id] = updated_item

    return updated_item


@app.delete('/api/items/{item_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int) -> Response:
    '''DELETE удаляет объект из памяти и возвращает корректный HTTP 204.'''

    get_existing_item(item_id)
    del items[item_id]

    return Response(status_code=status.HTTP_204_NO_CONTENT)
