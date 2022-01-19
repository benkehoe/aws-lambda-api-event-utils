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

import secrets
import dataclasses
import datetime

from aws_lambda_api_event_utils import *

from tests.events import *

rand_str = lambda: secrets.token_hex(4)

# TODO:
# - header dedup
# - * for method and headers


def test_cors_is_preflight_request():
    for integration_type in IntegrationType:
        base_event = Event(
            integration_type=integration_type,
            method="OPTIONS",
            path=Path(stage="live", path="/foo", resource="/foo"),
            body=None,
        )

        assert not CORSConfig.is_preflight_request(base_event.get_event())

        assert CORSConfig.is_preflight_request(
            base_event.with_(
                headers={"Access-Control-Request-Method": "GET"}
            ).get_event()
        )

        assert not CORSConfig.is_preflight_request(
            base_event.with_(
                method="GET", headers={"Access-Control-Request-Method": "GET"}
            ).get_event()
        )


def test_cors_make_preflight_response():
    for integration_type in IntegrationType:
        base_cors_config = CORSConfig(
            allow_origin="https://example.com", allow_methods="GET"
        )

        response = base_cors_config.make_preflight_response(
            format_version=integration_type.format_version
        )
        assert response["statusCode"] == 204
        assert not response.get("body")
        assert (
            response["headers"]["Access-Control-Allow-Origin"] == "https://example.com"
        )
        assert response["headers"]["Access-Control-Allow-Methods"] == "OPTIONS, GET"
        assert "Access-Control-Allow-Headers" not in response["headers"]
        assert "Access-Control-Max-Age" not in response["headers"]
        assert "Access-Control-Credentials" not in response["headers"]
        assert "Access-Control-Expose-Headers" not in response["headers"]

        cors_config = dataclasses.replace(
            base_cors_config, allow_headers=["foo", "bar"]
        )
        response = cors_config.make_preflight_response(
            format_version=integration_type.format_version
        )
        assert response["headers"]["Access-Control-Allow-Headers"] == "foo, bar"

        cors_config = dataclasses.replace(base_cors_config, allow_headers="foo")
        response = cors_config.make_preflight_response(
            format_version=integration_type.format_version
        )
        assert response["headers"]["Access-Control-Allow-Headers"] == "foo"

        cors_config = dataclasses.replace(base_cors_config, max_age=300)
        response = cors_config.make_preflight_response(
            format_version=integration_type.format_version
        )
        assert response["headers"]["Access-Control-Max-Age"] == "300"

        cors_config = dataclasses.replace(
            base_cors_config, max_age=datetime.timedelta(minutes=5)
        )
        response = cors_config.make_preflight_response(
            format_version=integration_type.format_version
        )
        assert response["headers"]["Access-Control-Max-Age"] == "300"

        cors_config = dataclasses.replace(base_cors_config, allow_credentials=True)
        response = cors_config.make_preflight_response(
            format_version=integration_type.format_version
        )
        assert response["headers"]["Access-Control-Allow-Credentials"] == "true"

        cors_config = dataclasses.replace(
            base_cors_config, expose_headers=["foo", "bar"]
        )
        response = cors_config.make_preflight_response(
            format_version=integration_type.format_version
        )
        assert "Access-Control-Expose-Headers" not in response["headers"]


def test_get_headers():
    base_cors_config = CORSConfig(
        allow_origin="https://example.com", allow_methods="GET"
    )

    headers = base_cors_config.get_headers()
    assert headers["Access-Control-Allow-Origin"] == "https://example.com"
    assert "Access-Control-Allow-Methods" not in headers
    assert "Access-Control-Allow-Headers" not in headers
    assert "Access-Control-Max-Age" not in headers
    assert "Access-Control-Credentials" not in headers
    assert "Access-Control-Expose-Headers" not in headers

    cors_config = dataclasses.replace(base_cors_config, allow_headers=["foo", "bar"])
    headers = cors_config.get_headers()
    assert "Access-Control-Allow-Headers" not in headers

    cors_config = dataclasses.replace(
        base_cors_config, max_age=datetime.timedelta(minutes=5)
    )
    headers = cors_config.get_headers()
    assert "Access-Control-Max-Age" not in headers

    cors_config = dataclasses.replace(base_cors_config, allow_credentials=True)
    headers = cors_config.get_headers()
    assert headers["Access-Control-Allow-Credentials"] == "true"

    cors_config = dataclasses.replace(base_cors_config, expose_headers=["foo", "bar"])
    headers = cors_config.get_headers()
    assert headers["Access-Control-Expose-Headers"] == "foo, bar"

    cors_config = dataclasses.replace(base_cors_config, expose_headers="foo")
    headers = cors_config.get_headers()
    assert headers["Access-Control-Expose-Headers"] == "foo"


def test_dedup():
    cors_config = CORSConfig(
        allow_origin="https://example.com",
        allow_methods="GET",
        allow_headers="Accept",
        expose_headers="Content-Type",
    )

    assert cors_config.allow_methods == ("OPTIONS", "GET")
    assert cors_config.allow_headers == ("Accept",)
    assert cors_config.expose_headers == ("Content-Type",)

    cors_config = CORSConfig(
        allow_origin="https://example.com", allow_methods=["GET", "OPTIONS"]
    )
    assert cors_config.allow_methods == ("GET", "OPTIONS")

    cors_config = CORSConfig(
        allow_origin="https://example.com",
        allow_methods="GET",
        allow_headers=["Accept", "Content-Type", "Accept"],
    )
    assert cors_config.allow_headers == ("Accept", "Content-Type")

    cors_config = CORSConfig(
        allow_origin="https://example.com",
        allow_methods="GET",
        allow_headers=["Accept", "*", "Accept"],
    )
    assert cors_config.allow_headers == ("*",)

    cors_config = CORSConfig(
        allow_origin="https://example.com", allow_methods=["*", "GET"]
    )
    assert cors_config.allow_methods == ("*",)
