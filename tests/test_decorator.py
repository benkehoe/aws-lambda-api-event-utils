# Copyright 2021 Ben Kehoe
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
# https://www.apache.org/licenses/LICENSE-2.0
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.

import pytest

import uuid
import json
import base64
import contextlib
from unittest.mock import MagicMock
import logging
import logging.handlers
import io

from aws_lambda_api_event_utils import *
from aws_lambda_api_event_utils.aws_lambda_api_event_utils import (
    DecoratorApiResponseConfig,
)

from tests.events import *

rand_str = lambda: uuid.uuid4().hex[:8]


@contextlib.contextmanager
def error_response_changes():
    fields = {}
    for field in dir(APIErrorResponse):
        if field.upper() == field:
            fields[field] = getattr(APIErrorResponse, field)

    yield APIErrorResponse

    for field in fields:
        setattr(APIErrorResponse, field, fields[field])


def test_error_handling():
    class TestError(APIErrorResponse):
        STATUS_CODE = 450
        ERROR_CODE = rand_str()
        ERROR_MESSAGE = rand_str()

    internal_message = rand_str()

    exc = TestError(internal_message)

    @api_event_handler(format_version=FormatVersion.APIGW_20)
    def handler(event, context):
        raise exc

    with error_response_changes():
        mock = MagicMock()
        APIErrorResponse.DECORATOR_LOGGER = mock

        response = handler({}, None)
        assert response == exc.get_response(format_version=FormatVersion.APIGW_20)

        mock.assert_called_with(f"{TestError.ERROR_CODE}: {internal_message}")

    with error_response_changes():

        class Handler(logging.Handler):
            def __init__(self) -> None:
                super().__init__(logging.DEBUG)
                self.records = []

            def emit(self, record):
                self.records.append(record)

        logger_handler = Handler()
        logger = logging.getLogger("test")
        logger.addHandler(logger_handler)

        APIErrorResponse.DECORATOR_LOGGER = logger

        response = handler({}, None)
        assert response == exc.get_response(format_version=FormatVersion.APIGW_20)

        assert len(logger_handler.records) == 1
        assert logger_handler.records[0].levelno == logging.ERROR
        assert (
            logger_handler.records[0].getMessage()
            == f"{TestError.ERROR_CODE}: {internal_message}"
        )


def test_context_fields():
    body_key = rand_str()
    body_value = rand_str()

    header_key = rand_str()
    header_value = rand_str()

    cookie = rand_str()

    @api_event_handler(format_version=FormatVersion.APIGW_20)
    def handler(event, context):
        assert hasattr(context, "api_response")
        assert isinstance(context.api_response, DecoratorApiResponseConfig)
        assert context.api_response.headers is None
        assert context.api_response.cookies is None
        assert context.api_response.cors_config is None

        context.api_response.headers = {header_key: header_value}
        context.api_response.cookies = [cookie]

        return {body_key: body_value}

    context = create_context()

    response = handler({}, context)

    assert response["headers"] == {
        header_key: header_value,
        "Content-Type": "application/json",
    }
    assert response["cookies"] == [cookie]

    assert json.loads(response["body"]) == {body_key: body_value}


def test_bare_decorator():
    for integration_type in IntegrationType:

        @api_event_handler
        def handler(event, context):
            return {"status": "success"}

        event = Event(
            integration_type=integration_type,
            method="POST",
            path=Path("live", "/my/path", "/my/path"),
        )

        handler(event.get_event(), create_context())
