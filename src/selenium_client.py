'''Selenium-клиент для этапа D лабораторной работы 1.

Страница /dynamic намеренно получает таблицу JavaScript-запросом после клика.
Поэтому здесь используются только WebDriverWait и ожидаемые условия, без sleep.
'''

import os
from pathlib import Path
from typing import Dict, List

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait


BASE_URL = 'http://127.0.0.1:8000'
OUTPUT_PATH = Path('results/selenium_items.csv')
FILTER_CATEGORY = 'Электроника'
# False позволяет увидеть браузер во время защиты. При необходимости работы
# без окна переключи значение на True.
HEADLESS = False

# Selenium Manager по умолчанию пишет драйвер в пользовательский ~/.cache.
# В учебном окружении эта папка может быть недоступна, поэтому используем
# кэш внутри проекта. При первом запуске Manager подберёт ChromeDriver сюда.
PROJECT_DIR = Path(__file__).resolve().parents[1]
SELENIUM_CACHE_PATH = PROJECT_DIR / '.selenium'
os.environ.setdefault('SE_CACHE_PATH', str(SELENIUM_CACHE_PATH))


def create_driver() -> webdriver.Chrome:
    '''Создаёт Chrome WebDriver. Selenium Manager сам подбирает ChromeDriver.'''

    options = Options()
    options.add_argument('--window-size=1440,900')

    if HEADLESS:
        options.add_argument('--headless=new')

    return webdriver.Chrome(options=options)


def extract_visible_table(driver: webdriver.Chrome) -> pd.DataFrame:
    '''Считывает только строки, которые реально отображены в DOM-таблице.'''

    header_cells = driver.find_elements(By.CSS_SELECTOR, '#items-table thead th')
    columns = [cell.get_attribute('data-field') for cell in header_cells]

    records: List[Dict[str, str]] = []
    rows = driver.find_elements(By.CSS_SELECTOR, '#items-body tr')

    for row in rows:
        cells = row.find_elements(By.TAG_NAME, 'td')
        values = [cell.text for cell in cells]

        if len(values) == len(columns):
            records.append(dict(zip(columns, values)))

    dataframe = pd.DataFrame(records, columns=columns)

    # Браузер возвращает текст. Приведение ниже подчёркивает, что после
    # Selenium-извлечения результат снова становится структурированными данными.
    if not dataframe.empty:
        dataframe['id'] = pd.to_numeric(dataframe['id'], errors='coerce').astype('Int64')
        dataframe['value'] = pd.to_numeric(dataframe['value'], errors='coerce')
        dataframe['updated_at'] = pd.to_datetime(
            dataframe['updated_at'], errors='coerce'
        )
        dataframe['active'] = dataframe['active'].str.lower().map(
            {'true': True, 'false': False}
        ).astype('boolean')

    return dataframe


def main() -> None:
    '''Выполняет полный сценарий этапа D и сохраняет отфильтрованные строки.'''

    driver = create_driver()
    wait = WebDriverWait(driver, 10)

    try:
        driver.get(f'{BASE_URL}/dynamic')

        # 1. Явно ждём кликабельную кнопку, а не используем time.sleep().
        wait.until(EC.element_to_be_clickable((By.ID, 'load-data'))).click()

        # 2. JavaScript завершил fetch('/api/items') и отрисовал строки таблицы.
        wait.until(
            lambda browser: browser.find_element(By.ID, 'status').get_attribute(
                'data-state'
            ) == 'loaded'
        )
        wait.until(
            lambda browser: len(
                browser.find_elements(By.CSS_SELECTOR, '#items-body tr')
            ) > 0
        )

        # 3. Фильтр доступен лишь после динамической загрузки категорий.
        filter_element = wait.until(
            lambda browser: (
                browser.find_element(By.ID, 'category-filter')
                if browser.find_element(By.ID, 'category-filter').is_enabled()
                else False
            )
        )
        Select(filter_element).select_by_visible_text(FILTER_CATEGORY)

        # 4. Дожидаемся применения фильтра: каждая отображённая строка должна
        # принадлежать выбранной категории.
        wait.until(
            lambda browser: (
                len(browser.find_elements(By.CSS_SELECTOR, '#items-body tr')) > 0
                and all(
                    row.find_elements(By.TAG_NAME, 'td')[2].text == FILTER_CATEGORY
                    for row in browser.find_elements(By.CSS_SELECTOR, '#items-body tr')
                )
            )
        )

        dataframe = extract_visible_table(driver)
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        dataframe.to_csv(OUTPUT_PATH, index=False, encoding='utf-8-sig')

        print(f'Категория фильтра: {FILTER_CATEGORY}')
        print(f'Собрано строк: {len(dataframe)}')
        print(f'Результат сохранён: {OUTPUT_PATH}')

    finally:
        # Драйвер всегда закрывается, в том числе при ошибке ожидания или API.
        driver.quit()


if __name__ == '__main__':
    main()
