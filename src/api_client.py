import json
import time
from pathlib import Path

import pandas as pd
import requests
from typing import Union

BASE_URL = 'http://127.0.0.1:8000'
LOG_PATH = Path('results/api_log.csv')

api_logs = []

def response_to_text(response: requests.Response) -> str:
    '''Возвращает тело ответа в виде строки'''

    content_type = response.headers.get('Content-Type', '')

    if 'application/json' in content_type:
        try:
            return json.dumps(
                response.json(),
                ensure_ascii=False
            )
        except ValueError:
            return response.text

    return response.text

def add_log(
    method: str,
    url: str,
    params: Union[dict, None],
    body: Union[dict, None],
    status_code: Union[int, None],
    content_type: Union[str, None],
    duration_seconds: float,
    response_body: Union[str, None],
    error_type: Union[str, None] = None,
    error_message: Union[str, None] = None,
) -> None:
    '''Добавляет один результат запроса в список логов.'''

    api_logs.append(
        {
            'method': method,
            'url': url,
            'params': json.dumps(params, ensure_ascii=False)
            if params else '',
            'body': json.dumps(body, ensure_ascii=False)
            if body else '',
            'status_code': status_code,
            'content_type': content_type,
            'duration_seconds': round(duration_seconds, 4),
            'response': response_body,
            'error_type': error_type,
            'error_message': error_message,
        }
    )

def send_request(
    method: str,
    endpoint: str,
    *,
    params: Union[dict, None] = None,
    body: Union[dict, None] = None,
    expected_status: Union[int, None] = None
) -> Union[requests.Response, None]:
    '''Выполняет HTTP-запрос, измеряет время и записывает результат в логи
    expected_status используется для ожидаемых ошибок.
    Например, после DELETE повторный GET должен дать 404.'''

    url = f'{BASE_URL}/{endpoint}'
    method = method.upper()

    start_time = time.perf_counter()
    response = None

    try:
        if method == 'GET':
            response = requests.get(
                url=url,
                params=params,
                timeout=10
            )

        elif method == 'POST':
            response = requests.post(
                url=url,
                params=params,
                json=body,
                timeout=10
            )

        elif method == 'PUT':
            response = requests.put(
                url=url,
                params=params,
                json=body,
                timeout=10
            )

        elif method == 'PATCH':
            response = requests.patch(
                url=url,
                params=params,
                json=body,
                timeout=10
            )

        elif method == 'DELETE':
            response = requests.delete(
                url=url,
                params=params,
                json=body,
                timeout=10
            )

        else:
            raise ValueError(f'Не обрабатываемый HTTP-метод: {method}')

        duration = time.perf_counter() - start_time

        if expected_status is not None and response.status_code == expected_status:
            add_log(
                method=method,
                url=url,
                params=params,
                body=body,
                status_code=response.status_code,
                content_type=response.headers.get("Content-Type"),
                duration_seconds=duration,
                response_body=response_to_text(response),
            )

            print(
                f'{method} {endpoint}: '
                f'ожидаемый статус {response.status_code}'
            )
            return response

        response.raise_for_status()

        add_log(
                method=method,
                url=url,
                params=params,
                body=body,
                status_code=response.status_code,
                content_type=response.headers.get("Content-Type"),
                duration_seconds=duration,
                response_body=response_to_text(response),
            )

        print(f"{method} {endpoint}: {response.status_code}")
        return response

    except requests.exceptions.RequestException as error:
        duration = time.perf_counter() - start_time

        response_body = None
        status_code = None
        content_type = None

        if response is not None:
            response_body = response_to_text(response)
            status_code = response.status_code
            content_type = response.headers.get('Content-Type', '')

        add_log(
            method=method,
            url=url,
            params=params,
            body=body,
            status_code=status_code,
            content_type=content_type,
            duration_seconds=duration,
            response_body=response_body,
            error_type=type(error).__name__,
            error_message=str(error),
        )

        print(f'{method} {endpoint}: ошибка {type(error).__name__}')
        return None


def save_logs() -> None:
    '''Сохранение логов'''
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    log_df = pd.DataFrame(api_logs)
    log_df.to_csv(
        LOG_PATH,
        index=False,
        encoding='utf-8'
    )

    print(f'Логи сохранены по пути: {LOG_PATH}')

def test_crud() -> None:
    '''Симуляция работы с беком'''

    test_id = 1111  #id нового объекта

    send_request('get', 'api/items')    #Смотрим, что вообще есть

    #Сам новый объект
    new_item = {
        'id': test_id,
        'name': 'Шоколадка',
        'category': 'Еда',
        'value': '1_000_000',
        'updated_at': '2026-09-16T15:00',
        'active': 'True'
    }

    #Закидываем его на сервер POST
    send_request(
        method='post',
        endpoint='api/items',
        body=new_item
    )

    #Совсем новый объект, которым будем заменять предыдущий
    replacement_item = {
        'name': "Шоколадка 3000: 'Жидкая нуга'",
        'category': 'Гипер-еда',
        'value': '2_000_000',
        'updated_at': '2026-09-16T18:00',
        'active': 'True'
    }

    #Замена прошлого объекта PUT
    send_request(
        method='put',
        endpoint=f'api/items/{test_id}',
        body=replacement_item
    )

    #Заменяемое поле в совсем новом объекте
    patch_data = {
        'active': 'False'
    }

    #Заменяем элемент нового объекта PATCH
    send_request(
        method='patch',
        endpoint=f'api/items/{test_id}',
        body=patch_data
    )

    #Смотрим, что танцы с бубном прошли успешно
    send_request(
        method='get',
        endpoint=f'api/items/{test_id}'
    )

    #Удаляем подопытного кролика
    send_request(
        method='delete',
        endpoint=f'api/items/{test_id}'
    )

    #Пытаемся получить сведения об удаленном объекте -> 
    #-> ждем конкретную ошибку, мол, не нашли, что хотели 404
    send_request(
        method='get',
        endpoint=f'api/items/{test_id}',
        expected_status=404
    )

    #Логируем, понятное дело, куда без этого
    save_logs()

if __name__ == '__main__':
    try:
        test_crud()     #Запускаем шарманку

    finally:
        save_logs()     #Ну вы сами поняли