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
import http

from aws_lambda_api_event_utils import *

rand_str = lambda: uuid.uuid4().hex[:8]


def test_make_response_invalid_format_version():
    with pytest.raises(TypeError, match="Unknown format version"):
        make_response(200, "body", format_version={"foo": "bar"})


def test_make_response_apigw10_body():
    response = make_response(
        status_code=200, body=None, format_version=FormatVersion.APIGW_10
    )
    assert response["statusCode"] == 200
    assert response["body"] == ""
    assert "headers" not in response

    response = make_response(200, body=None, format_version=FormatVersion.APIGW_10)
    assert response["statusCode"] == 200
    assert response["body"] == ""
    assert "headers" not in response

    body = rand_str()

    response = make_response(
        status_code=200, body=body, format_version=FormatVersion.APIGW_10
    )
    print(json.dumps(response, indent=2))
    assert response["statusCode"] == 200
    assert response["body"] == body
    assert response["headers"]["Content-Type"] == "text/plain"

    response = make_response(
        status_code=http.HTTPStatus.OK, body=body, format_version=FormatVersion.APIGW_10
    )
    assert isinstance(response["statusCode"], int)
    assert response["statusCode"] == 200

    response = make_response(200, body, format_version=FormatVersion.APIGW_10)
    assert response["statusCode"] == 200
    assert response["body"] == body
    assert response["headers"]["Content-Type"] == "text/plain"

    body_bytes = uuid.uuid4().bytes
    body_base64 = str(base64.b64encode(body_bytes), "ascii")

    response = make_response(200, body_bytes, format_version=FormatVersion.APIGW_10)
    assert response["statusCode"] == 200
    assert type(response["body"]) == str
    assert response["body"] == body_base64
    assert response["isBase64Encoded"] == True
    assert response["headers"]["Content-Type"] == "application/octet-stream"

    body = {"foo": "bar"}
    response = make_response(
        status_code=200, body=body, format_version=FormatVersion.APIGW_10
    )
    assert json.loads(response["body"]) == body
    assert response["headers"]["Content-Type"] == "application/json"

    body = ["foo", "bar"]
    response = make_response(
        status_code=200, body=body, format_version=FormatVersion.APIGW_10
    )
    assert json.loads(response["body"]) == body
    assert response["headers"]["Content-Type"] == "application/json"


def test_make_response_apigw20_body():
    response = make_response(
        status_code=200, body=None, format_version=FormatVersion.APIGW_20
    )
    assert response["statusCode"] == 200
    assert response["body"] == ""
    assert "headers" not in response

    response = make_response(200, body=None, format_version=FormatVersion.APIGW_20)
    assert response["statusCode"] == 200
    assert response["body"] == ""
    assert "headers" not in response

    body = rand_str()

    response = make_response(
        status_code=200, body=body, format_version=FormatVersion.APIGW_20
    )
    assert response["statusCode"] == 200
    assert response["body"] == body
    assert response["headers"]["Content-Type"] == "text/plain"

    response = make_response(200, body, format_version=FormatVersion.APIGW_20)
    assert response["statusCode"] == 200
    assert response["body"] == body
    assert response["headers"]["Content-Type"] == "text/plain"

    body_bytes = uuid.uuid4().bytes
    body_base64 = str(base64.b64encode(body_bytes), "ascii")

    response = make_response(200, body_bytes, format_version=FormatVersion.APIGW_20)
    assert response["statusCode"] == 200
    assert type(response["body"]) == str
    assert response["body"] == body_base64
    assert response["isBase64Encoded"] == True
    assert response["headers"]["Content-Type"] == "application/octet-stream"

    body = {"foo": "bar"}
    response = make_response(
        status_code=200, body=body, format_version=FormatVersion.APIGW_20
    )
    assert json.loads(response["body"]) == body
    assert response["headers"]["Content-Type"] == "application/json"

    body = ["foo", "bar"]
    response = make_response(
        status_code=200, body=body, format_version=FormatVersion.APIGW_20
    )
    assert json.loads(response["body"]) == body
    assert response["headers"]["Content-Type"] == "application/json"


def test_make_response_apigw10_headers():
    body = rand_str()

    response = make_response(
        200, body, headers={}, format_version=FormatVersion.APIGW_10
    )
    assert response["statusCode"] == 200
    assert response["body"] == body
    assert response["headers"] == {"Content-Type": "text/plain"}

    response = make_response(
        200, body, headers={"foo": "bar"}, format_version=FormatVersion.APIGW_10
    )
    assert response["statusCode"] == 200
    assert response["body"] == body
    assert response["headers"] == {"foo": "bar", "Content-Type": "text/plain"}

    response = make_response(
        200,
        body,
        headers={"foo": "bar", "a": "b"},
        format_version=FormatVersion.APIGW_10,
    )
    assert response["statusCode"] == 200
    assert response["body"] == body
    assert response["headers"] == {"foo": "bar", "a": "b", "Content-Type": "text/plain"}

    response = make_response(
        200,
        body,
        headers={"foo": "bar", "a": ["b", "c"]},
        format_version=FormatVersion.APIGW_10,
    )
    assert response["statusCode"] == 200
    assert response["body"] == body
    assert response["multiValueHeaders"] == {
        "foo": ["bar"],
        "a": ["b", "c"],
        "Content-Type": ["text/plain"],
    }


def test_make_response_apigw20_headers():
    body = rand_str()

    response = make_response(
        200, body, headers={}, format_version=FormatVersion.APIGW_20
    )
    assert response["statusCode"] == 200
    assert response["body"] == body
    assert response["headers"] == {"Content-Type": "text/plain"}

    response = make_response(
        200, body, headers={"foo": "bar"}, format_version=FormatVersion.APIGW_20
    )
    assert response["statusCode"] == 200
    assert response["body"] == body
    assert response["headers"] == {"foo": "bar", "Content-Type": "text/plain"}

    response = make_response(
        200,
        body,
        headers={"foo": "bar", "a": "b"},
        format_version=FormatVersion.APIGW_20,
    )
    assert response["statusCode"] == 200
    assert response["body"] == body
    assert response["headers"] == {"foo": "bar", "a": "b", "Content-Type": "text/plain"}

    response = make_response(
        200,
        body,
        headers={"foo": "bar", "a": ["b", "c"]},
        format_version=FormatVersion.APIGW_20,
    )
    assert response["statusCode"] == 200
    assert response["body"] == body
    assert response["headers"] == {
        "foo": "bar",
        "a": "b,c",
        "Content-Type": "text/plain",
    }
    assert "multiValueHeaders" not in response


def test_make_response_apigw10_cookies():
    body = rand_str()
    cookie = rand_str()
    with pytest.raises(
        TypeError,
        match=f"Cookies are not supported in format version {FormatVersion.APIGW_10}",
    ):
        make_response(
            200, body, cookies=[cookie], format_version=FormatVersion.APIGW_10
        )


def test_make_response_apigw10_cookies():
    body = rand_str()
    cookie = rand_str()
    response = make_response(
        200, body, cookies=[cookie], format_version=FormatVersion.APIGW_20
    )
    assert response["cookies"] == [cookie]


def test_make_redirect():
    url = f"https://example.com/{rand_str()}"

    response = make_redirect(307, url, format_version=FormatVersion.APIGW_10)
    assert response["statusCode"] == 307
    assert response["headers"]["location"] == url

    response = make_redirect(307, url, format_version=FormatVersion.APIGW_20)
    assert response["statusCode"] == 307
    assert response["headers"]["location"] == url

    with pytest.raises(ValueError, match="3XX"):
        make_redirect(200, url, format_version=FormatVersion.APIGW_10)

    header_key = rand_str()
    header_value = rand_str()

    headers = {header_key: header_value}
    response = make_redirect(
        307, url, headers=headers, format_version=FormatVersion.APIGW_20
    )
    assert response["headers"][header_key] == header_value
    assert response["headers"]["location"] == url

    headers = {"Location": header_value}
    response = make_redirect(
        307, url, headers=headers, format_version=FormatVersion.APIGW_20
    )
    assert response["headers"]["location"] == url
    assert "Location" not in response["headers"]

    headers = {header_key: [header_value]}
    response = make_redirect(
        307, url, headers=headers, format_version=FormatVersion.APIGW_10
    )
    assert response["multiValueHeaders"][header_key] == [header_value]
    assert response["multiValueHeaders"]["location"] == [url]
