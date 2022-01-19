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
import contextlib
from unittest.mock import MagicMock
import logging
import logging.handlers
import io
import sys
import http

from aws_lambda_api_event_utils import *

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


def test_make_response_from_exception():
    msg = rand_str()
    exc = Exception(msg)

    response = APIErrorResponse.from_exception(400, exc).get_response(
        format_version=FormatVersion.APIGW_20
    )
    assert response["statusCode"] == 400
    assert json.loads(response["body"]) == {
        "Error": {"Code": "Exception", "Message": msg}
    }
    assert response["headers"]["Content-Type"] == "application/json"

    with error_response_changes():
        response = APIErrorResponse.from_exception(400, exc).get_response(
            format_version=FormatVersion.APIGW_20
        )
        assert response["headers"]["Content-Type"] == "application/json"

        headers = {"header_name": "header_value"}
        cookies = [rand_str()]
        response = APIErrorResponse.from_exception(400, exc).get_response(
            headers=headers,
            cookies=cookies,
            format_version=FormatVersion.APIGW_20,
        )
        assert response["headers"]["Content-Type"] == "application/json"
        assert response["headers"]["header_name"] == "header_value"
        assert "foo" not in response["headers"]
        assert response["cookies"] == cookies


def test_make_response_from_exception_subclass():
    class TestError(APIErrorResponse):
        STATUS_CODE = 450
        ERROR_CODE = rand_str()
        ERROR_MESSAGE = rand_str()

    exc = TestError("foo")

    response = APIErrorResponse.from_exception(450, exc).get_response(
        format_version=FormatVersion.APIGW_20
    )
    assert response == exc.get_response(format_version=FormatVersion.APIGW_20)

    with pytest.raises(ValueError, match="Status code mismatch"):
        raise APIErrorResponse.from_exception(400, exc)


def test_make_error_body():
    code = rand_str()
    msg = rand_str()

    result = APIErrorResponse.make_error_body(code, msg)
    assert result == {"Error": {"Code": code, "Message": msg}}

    with error_response_changes():
        parent_field = rand_str()
        code_field = rand_str()
        msg_field = rand_str()

        APIErrorResponse.ERROR_PARENT_FIELD = parent_field
        APIErrorResponse.ERROR_CODE_FIELD = code_field
        APIErrorResponse.ERROR_MESSAGE_FIELD = msg_field

        result = APIErrorResponse.make_error_body(code, msg)
        assert result == {parent_field: {code_field: code, msg_field: msg}}

        APIErrorResponse.ERROR_PARENT_FIELD = None
        result = APIErrorResponse.make_error_body(code, msg)
        assert result == {code_field: code, msg_field: msg}


def test_status_code_required():
    class TestError(APIErrorResponse):
        pass

    with pytest.raises(NotImplementedError, match="STATUS_CODE must be set"):
        TestError("foo")


def test_get_error_code():
    internal_msg = rand_str()

    class TestError1(APIErrorResponse):
        STATUS_CODE = 400

    exc = TestError1(internal_msg)
    assert exc.get_error_code() == "TestError1"

    class TestError2(APIErrorResponse):
        STATUS_CODE = 400
        ERROR_CODE = rand_str()

    exc = TestError2(internal_msg)
    assert exc.get_error_code() == TestError2.ERROR_CODE


def test_get_error_message():
    internal_msg = rand_str()

    class TestError1(APIErrorResponse):
        STATUS_CODE = 400

    exc = TestError1(internal_msg)
    assert exc.get_error_message() == "An error occurred."

    error_msg = rand_str()
    exc = TestError1(internal_msg, error_message=error_msg)
    assert exc.get_error_message() == error_msg

    class TestError2(APIErrorResponse):
        STATUS_CODE = 400
        ERROR_MESSAGE = rand_str()

    exc = TestError2(internal_msg)
    assert exc.get_error_message() == TestError2.ERROR_MESSAGE

    error_msg = rand_str()
    exc = TestError2(internal_msg, error_message=error_msg)
    assert exc.get_error_message() == error_msg

    prefix = rand_str()
    param = rand_str()

    class TestError3(APIErrorResponse):
        STATUS_CODE = 400
        ERROR_MESSAGE_TEMPLATE = prefix + " {param}"

        def __init__(self, the_param, internal_message: str, **kwargs):
            self.param = the_param
            super().__init__(internal_message, **kwargs)

    exc = TestError3(param, internal_msg)
    assert exc.get_error_message() == f"{prefix} {param}"

    error_msg = rand_str()
    exc = TestError3(param, internal_msg, error_message=error_msg)
    assert exc.get_error_message() == error_msg


def test_get_body():
    internal_msg = rand_str()

    class TestError1(APIErrorResponse):
        STATUS_CODE = 400

    exc = TestError1(internal_msg)
    body = exc.get_body()
    assert body == {"Error": {"Code": "TestError1", "Message": "An error occurred."}}

    code = rand_str()
    msg = rand_str()

    class TestError2(APIErrorResponse):
        STATUS_CODE = 400

        def get_error_code(self) -> str:
            return code

        def get_error_message(self) -> str:
            return msg

    exc = TestError2(internal_msg)
    body = exc.get_body()
    assert body == {"Error": {"Code": code, "Message": msg}}


def test_get_response():
    body = rand_str()
    headers = {"key": rand_str()}
    cookies = [rand_str()]

    internal_msg = rand_str()

    class TestError1(APIErrorResponse):
        STATUS_CODE = 400

    exc = TestError1(internal_msg)

    response = exc.get_response(format_version=FormatVersion.APIGW_20)
    assert response == {
        "statusCode": 400,
        "body": json.dumps(
            {"Error": {"Code": "TestError1", "Message": "An error occurred."}}
        ),
        "headers": {"Content-Type": "application/json"},
        "isBase64Encoded": False,
    }

    response = exc.get_response(
        body=body,
        headers=headers,
        cookies=cookies,
        format_version=FormatVersion.APIGW_20,
    )
    assert response == {
        "statusCode": 400,
        "body": body,
        "headers": headers,
        "cookies": cookies,
        "isBase64Encoded": False,
    }


@pytest.mark.xfail(reason="TODO")
def test_kwargs():
    # TODO: all the subclasses too?
    assert False


@pytest.mark.xfail(reason="TODO")
def test_invalid_request_error():
    assert False


def test__log():
    error_code = rand_str()
    error_message = rand_str()
    internal_message = rand_str()

    class TestError(APIErrorResponse):
        STATUS_CODE = 400

        ERROR_CODE = error_code
        ERROR_MESSAGE = error_message

        def __init__(self):
            super().__init__(internal_message)

    expected_str = f"{error_code}: {internal_message}"

    with error_response_changes():
        logger = MagicMock()
        APIErrorResponse.DECORATOR_LOGGER = logger

        try:
            raise TestError()
        except TestError as exc:
            exc._decorator_log()

        logger.assert_called_with(expected_str)

    with error_response_changes():
        logger = MagicMock()
        APIErrorResponse.DECORATOR_LOGGER = logger
        APIErrorResponse.DECORATOR_LOGGER_TRACEBACK = True

        try:
            raise TestError()
        except TestError as exc:
            exc._decorator_log()

        assert logger.call_count == 2
        logger.assert_called_with(expected_str)

    with error_response_changes():
        logger = logging.Logger(rand_str())

        str_io = io.StringIO()
        handler = logging.StreamHandler(str_io)

        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        APIErrorResponse.DECORATOR_LOGGER = logger

        try:
            raise TestError()
        except TestError as exc:
            exc._decorator_log()

        assert str_io.getvalue().strip() == expected_str

    with error_response_changes():
        logger = logging.Logger(rand_str())

        str_io = io.StringIO()
        handler = logging.StreamHandler(str_io)

        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        APIErrorResponse.DECORATOR_LOGGER = logger
        APIErrorResponse.DECORATOR_LOGGER_TRACEBACK = True

        try:
            raise TestError()
        except TestError as exc:
            exc._decorator_log()

        lines = str_io.getvalue().splitlines()

        assert len(lines) > 1
        assert lines[0] == expected_str


def test_raise():
    msg = rand_str()
    with pytest.raises(APIErrorResponse) as exc:
        try:
            raise RuntimeError(msg)
        except RuntimeError as e:
            raise APIErrorResponse.from_exception(400, e)
    exc = exc.value
    assert exc.STATUS_CODE == 400
    assert exc.get_error_code() == "RuntimeError"
    assert exc.get_error_message() == msg
    assert exc.internal_message == f"RuntimeError: {msg}"

    msg = rand_str()
    internal_msg = rand_str()
    with pytest.raises(APIErrorResponse) as exc:
        try:
            raise RuntimeError(msg)
        except RuntimeError as e:
            raise APIErrorResponse.from_exception(400, e, internal_message=internal_msg)
    exc = exc.value
    assert exc.STATUS_CODE == 400
    assert exc.get_error_code() == "RuntimeError"
    assert exc.get_error_message() == msg
    assert exc.internal_message == internal_msg

    msg = rand_str()
    with pytest.raises(APIErrorResponse) as exc:
        e = RuntimeError(msg)
        raise APIErrorResponse.from_exception(400, e)
    exc = exc.value
    assert exc.STATUS_CODE == 400
    assert exc.get_error_code() == "RuntimeError"
    assert exc.get_error_message() == msg


def test_from_status_code():
    def test(
        status_code,
        *,
        error_code,
        error_message,
        input_error_message=None,
        input_internal_message=None,
    ):
        try:
            exc = APIErrorResponse.from_status_code(
                status_code,
                error_message=input_error_message,
                internal_message=input_internal_message,
            )
        except APIErrorResponse as exc:
            assert exc.STATUS_CODE == status_code
            assert exc.ERROR_CODE == error_code
            assert exc.ERROR_MESSAGE == error_message

    test(404, error_code="NotFound", error_message="Nothing matches the given URI.")
    test(
        http.HTTPStatus.NOT_FOUND,
        error_code="NotFound",
        error_message="Nothing matches the given URI.",
    )

    test(
        511,
        error_code="NetworkAuthenticationRequired",
        error_message="The client needs to authenticate to gain network access.",
    )

    with pytest.raises(ValueError, match="Status code 200 is not 4XX or 5XX"):
        test(200, error_code="foo", error_message="bar")

    with pytest.raises(ValueError, match="499 is not a valid HTTPStatus"):
        test(499, error_code="foo", error_message="bar")

    exc = APIErrorResponse.from_status_code(
        400,
        error_message="foo",
        internal_message="bar",
    )
    assert isinstance(exc, InvalidRequestError)

    if sys.version_info.minor >= 9:
        # RFC 2324 compliance added in 3.9
        test(418, error_code="ImATeapot", error_message="Teapot cannot brew coffee.")
