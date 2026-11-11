import asyncio
import logging

from starlette.requests import Request
from app.exceptions.handlers import general_exception_handler
from app.models import User, ProviderEnum
from app.schemas import TaskCreate
from app.services.task import TaskService


def test_service_logs_do_not_include_task_content(test_db, caplog):
    test_db.add(User(id='logs', provider=ProviderEnum.google,
                     provider_sub='logs', email='logs@example.com'))
    test_db.commit()
    with caplog.at_level(logging.DEBUG):
        TaskService(test_db).create_task(TaskCreate(
            title='CONFIDENTIAL_TITLE', description='CONFIDENTIAL_DESCRIPTION'), 'logs')
    assert 'CONFIDENTIAL' not in caplog.text


def test_unhandled_errors_do_not_log_payload_or_traceback(caplog):
    request = Request({'type': 'http', 'path': '/api/v1/tasks', 'method': 'GET'})
    with caplog.at_level(logging.ERROR):
        response = asyncio.run(general_exception_handler(
            request, RuntimeError('et_pat_PRIVATE_SQL_PARAMETERS')))
    assert response.status_code == 500
    assert 'PRIVATE' not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
