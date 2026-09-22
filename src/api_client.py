"""Клиент REST API для этапов B и C лабораторной работы 1.

Запускать при работающем backend:
    python src/api_client.py
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
import requests


BASE_URL = "http://127.0.0.1:8000"
# На этом порту сервер намеренно не запускается: так проверяется ConnectionError.
UNAVAILABLE_BASE_URL = "http://127.0.0.1:8999"
LOG_PATH = Path("results/api_log.csv")

api_logs: List[Dict[str, Any]] = []


def build_url(base_url: str, endpoint: str) -> str:
    """Собирает URL независимо от наличия '/' на границе частей адреса."""

    return f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"


def json_to_text(value: Optional[Union[dict, list]]) -> str:
    """Сериализует параметры или тело запроса для одной ячейки CSV-лога."""

    if value is None:
        return ""

    return json.dumps(value, ensure_ascii=False)


def response_to_text(response: requests.Response) -> str:
    """Возвращает тело ответа как читаемый JSON либо обычный текст."""

    content_type = response.headers.get("Content-Type", "")

    if "application/json" in content_type:
        try:
            return json.dumps(response.json(), ensure_ascii=False)
        except ValueError:
            pass

    return response.text


def error_category(error: Exception) -> str:
    """Возвращает понятную для отчёта категорию ошибки Requests.

    Requests на разных ОС может выбрасывать более точные подклассы, например
    ConnectTimeout или ReadTimeout. Для этапа C они сводятся к требуемым
    категориям ConnectionError и Timeout, а исходный класс пишется отдельно.
    """

    if isinstance(error, requests.exceptions.ConnectTimeout):
        return "ConnectionError"
    if isinstance(error, requests.exceptions.ConnectionError):
        return "ConnectionError"
    if isinstance(error, requests.exceptions.Timeout):
        return "Timeout"
    if isinstance(error, requests.exceptions.HTTPError):
        return "HTTPError"

    return type(error).__name__


def add_log(
    scenario: str,
    method: str,
    url: str,
    params: Optional[dict],
    body: Optional[dict],
    timeout_seconds: float,
    status_code: Optional[int],
    content_type: Optional[str],
    duration_seconds: float,
    response_body: Optional[str],
    error_type: Optional[str] = None,
    error_detail_type: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    """Добавляет информацию о запросе и его результате в будущий CSV-лог."""

    api_logs.append(
        {
            "scenario": scenario,
            "method": method,
            "url": url,
            "params": json_to_text(params),
            "body": json_to_text(body),
            "timeout_seconds": timeout_seconds,
            "status_code": status_code,
            "content_type": content_type,
            "duration_seconds": round(duration_seconds, 4),
            "response": response_body,
            "error_type": error_type,
            "error_detail_type": error_detail_type,
            "error_message": error_message,
        }
    )


def send_request(
    method: str,
    endpoint: str,
    *,
    scenario: str,
    params: Optional[dict] = None,
    body: Optional[dict] = None,
    timeout: float = 10,
    base_url: Optional[str] = None,
    expected_status: Optional[int] = None,
) -> Optional[requests.Response]:
    """Выполняет запрос, измеряет время и всегда сохраняет результат в лог.

    В том числе обрабатываются ConnectionError, Timeout и HTTPError, поэтому
    учебные ошибочные сценарии не прерывают выполнение программы traceback-ом.
    """

    method = method.upper()
    url = build_url(base_url or BASE_URL, endpoint)
    response: Optional[requests.Response] = None
    start_time = time.perf_counter()

    try:
        # У каждого сетевого запроса есть timeout. Раздельные методы оставлены
        # намеренно: это наглядно показывает использование GET/POST/PUT/PATCH/
        # DELETE из библиотеки requests.
        if method == "GET":
            response = requests.get(url, params=params, timeout=timeout)
        elif method == "POST":
            response = requests.post(url, params=params, json=body, timeout=timeout)
        elif method == "PUT":
            response = requests.put(url, params=params, json=body, timeout=timeout)
        elif method == "PATCH":
            response = requests.patch(url, params=params, json=body, timeout=timeout)
        elif method == "DELETE":
            response = requests.delete(url, params=params, timeout=timeout)
        else:
            raise ValueError(f"Неподдерживаемый HTTP-метод: {method}")

        duration = time.perf_counter() - start_time

        # В этапе B финальный GET после DELETE намеренно получает 404. Такой
        # статус подтверждает удаление и не должен считаться ошибкой сценария.
        if expected_status is not None and response.status_code == expected_status:
            add_log(
                scenario=scenario,
                method=method,
                url=url,
                params=params,
                body=body,
                timeout_seconds=timeout,
                status_code=response.status_code,
                content_type=response.headers.get("Content-Type"),
                duration_seconds=duration,
                response_body=response_to_text(response),
            )
            print(f"{scenario}: {method} {endpoint} -> ожидаемый {response.status_code}")
            return response

        # Превращает 4xx/5xx в HTTPError, который будет пойман ниже и записан.
        response.raise_for_status()

        add_log(
            scenario=scenario,
            method=method,
            url=url,
            params=params,
            body=body,
            timeout_seconds=timeout,
            status_code=response.status_code,
            content_type=response.headers.get("Content-Type"),
            duration_seconds=duration,
            response_body=response_to_text(response),
        )
        print(f"{scenario}: {method} {endpoint} -> {response.status_code}")
        return response

    except (requests.exceptions.RequestException, ValueError) as error:
        duration = time.perf_counter() - start_time

        # При HTTPError объект response существует: сохраняем код и ответ API.
        # При ConnectionError или Timeout ответа нет, поэтому поля остаются пустыми.
        status_code = response.status_code if response is not None else None
        content_type = (
            response.headers.get("Content-Type") if response is not None else None
        )
        response_body = response_to_text(response) if response is not None else None

        add_log(
            scenario=scenario,
            method=method,
            url=url,
            params=params,
            body=body,
            timeout_seconds=timeout,
            status_code=status_code,
            content_type=content_type,
            duration_seconds=duration,
            response_body=response_body,
            error_type=error_category(error),
            error_detail_type=type(error).__name__,
            error_message=str(error),
        )
        print(f"{scenario}: {method} {endpoint} -> {error_category(error)}")
        return None


def run_crud_scenario() -> None:
    """Этап B: полный CRUD над временной тестовой записью."""

    test_id = 1111

    send_request("GET", "api/items", scenario="CRUD")

    new_item = {
        "id": test_id,
        "name": "Шоколадка",
        "category": "Еда",
        "value": 1_000_000.0,
        "updated_at": "2026-09-16T15:00:00",
        "active": True,
    }
    send_request("POST", "api/items", scenario="CRUD", body=new_item)

    # PUT передаёт полную новую версию объекта без id: id задан URL-адресом.
    replacement_item = {
        "name": "Шоколадка 3000 Жидкая нуга",
        "category": "Гипер еда",
        "value": 2_000_000.0,
        "updated_at": "2026-09-16T18:00:00",
        "active": True,
    }
    send_request(
        "PUT", f"api/items/{test_id}", scenario="CRUD", body=replacement_item
    )

    # PATCH содержит только поле, которое необходимо изменить.
    send_request(
        "PATCH", f"api/items/{test_id}", scenario="CRUD", body={"active": False}
    )
    send_request("GET", f"api/items/{test_id}", scenario="CRUD")
    send_request("DELETE", f"api/items/{test_id}", scenario="CRUD")
    send_request(
        "GET",
        f"api/items/{test_id}",
        scenario="CRUD",
        expected_status=404,
    )


def run_error_scenarios() -> None:
    """Этап C: три обязательные ошибки и их запись в results/api_log.csv."""

    # 1. Несуществующий ресурс: API отвечает 404, requests создаёт HTTPError.
    send_request("GET", "api/items/999999", scenario="ERROR nonexistent id")

    # 2. Неработающий порт: соединение не устанавливается, возникает ConnectionError.
    send_request(
        "GET",
        "api/items",
        scenario="ERROR connection",
        base_url=UNAVAILABLE_BASE_URL,
        timeout=2,
    )

    # 3. Локальный endpoint ждёт две секунды, но клиент ждёт только 0.1 секунды.
    # Это воспроизводимо вызывает requests.exceptions.Timeout.
    send_request(
        "GET",
        "api/test/slow",
        scenario="ERROR timeout",
        params={"delay": 2},
        timeout=0.1,
    )


def save_logs() -> None:
    """Сохраняет один общий журнал этапов B и C в UTF-8 для Excel/LibreOffice."""

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(api_logs).to_csv(LOG_PATH, index=False, encoding="utf-8-sig")
    print(f"Лог сохранён: {LOG_PATH}")


def main() -> None:
    """Выполняет все сценарии и сохраняет лог даже при неожиданной ошибке."""

    api_logs.clear()
    try:
        run_crud_scenario()
        run_error_scenarios()
    finally:
        save_logs()


if __name__ == "__main__":
    main()
