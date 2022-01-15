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

from aws_lambda_api_event_utils import *

from tests.events import *


def test_get_event_format_version():
    for integration_type in IntegrationType:
        event = Event(
            integration_type=integration_type,
            method="GET",
            path=Path("live", "/foo", "/foo"),
        )
        format_version = get_event_format_version(event.get_event())
        if integration_type == IntegrationType.APIGW_HTTP_20:
            print(json.dumps(event.get_event(), indent=2))
        assert format_version == integration_type.format_version

    ### invalid ###
    assert get_event_format_version({}) is None


def test_validate_event_format_version():
    base_event = Event(
        integration_type=None,
        method="POST",
        path=Path(stage="live", path="/foo", resource="/foo"),
        body=None,
    )
    apigw_http_10_event = base_event.with_(
        integration_type=IntegrationType.APIGW_HTTP_10
    )
    apigw_http_20_event = base_event.with_(
        integration_type=IntegrationType.APIGW_HTTP_20
    )

    version = validate_event_format_version(
        apigw_http_10_event.get_event(), FormatVersion.APIGW_10
    )
    assert version == FormatVersion.APIGW_10

    with pytest.raises(
        TypeError,
        match=f"Expected event version {FormatVersion.APIGW_10}, but received {FormatVersion.APIGW_20}",
    ):
        validate_event_format_version(
            apigw_http_20_event.get_event(), FormatVersion.APIGW_10
        )

    version = validate_event_format_version(
        apigw_http_20_event.get_event(), FormatVersion.APIGW_20
    )
    assert version == FormatVersion.APIGW_20

    with pytest.raises(
        TypeError,
        match=f"Expected event version {FormatVersion.APIGW_20}, but received {FormatVersion.APIGW_10}",
    ):
        validate_event_format_version(
            apigw_http_10_event.get_event(), FormatVersion.APIGW_20
        )

    with pytest.raises(
        TypeError,
        match=f"Expected event version {FormatVersion.APIGW_20}, but received an unknown event",
    ):
        validate_event_format_version({}, FormatVersion.APIGW_20)


def test_validate_event_format_version_use_error_response():
    base_event = Event(
        integration_type=None,
        method="POST",
        path=Path(stage="live", path="/foo", resource="/foo"),
        body=None,
    )
    apigw_http_10_event = base_event.with_(
        integration_type=IntegrationType.APIGW_HTTP_10
    )
    apigw_http_20_event = base_event.with_(
        integration_type=IntegrationType.APIGW_HTTP_20
    )

    version = validate_event_format_version(
        apigw_http_10_event.get_event(), FormatVersion.APIGW_10, use_error_response=True
    )
    assert version == FormatVersion.APIGW_10

    with pytest.raises(FormatVersionError):
        validate_event_format_version(
            apigw_http_20_event.get_event(),
            FormatVersion.APIGW_10,
            use_error_response=True,
        )

    version = validate_event_format_version(
        apigw_http_20_event.get_event(), FormatVersion.APIGW_20, use_error_response=True
    )
    assert version == FormatVersion.APIGW_20

    with pytest.raises(FormatVersionError):
        validate_event_format_version(
            apigw_http_10_event.get_event(),
            FormatVersion.APIGW_20,
            use_error_response=True,
        )

    with pytest.raises(FormatVersionError):
        validate_event_format_version(
            {}, FormatVersion.APIGW_20, use_error_response=True
        )


def test_event_format_version_decorator():
    base_event = Event(
        integration_type=None,
        method="POST",
        path=Path(stage="live", path="/foo", resource="/foo"),
        body=None,
    )
    apigw_http_10_event = base_event.with_(
        integration_type=IntegrationType.APIGW_HTTP_10
    )
    apigw_http_20_event = base_event.with_(
        integration_type=IntegrationType.APIGW_HTTP_20
    )

    @event_format_version(
        FormatVersion.APIGW_10,
    )
    def func_API_GW_10(event, context):
        return {"statusCode": 200, "body": ""}

    @event_format_version(FormatVersion.APIGW_20)
    def func_API_GW_20(event, context):
        return {"statusCode": 200, "body": ""}

    response = func_API_GW_10(apigw_http_10_event.get_event(), None)
    assert response.get("statusCode") == 200

    with pytest.raises(
        TypeError,
        match=f"Expected event version {FormatVersion.APIGW_10}, but received {FormatVersion.APIGW_20}",
    ):
        response = func_API_GW_10(apigw_http_20_event.get_event(), None)

    response = func_API_GW_20(apigw_http_20_event.get_event(), None)
    assert response.get("statusCode") == 200

    with pytest.raises(
        TypeError,
        match=f"Expected event version {FormatVersion.APIGW_20}, but received {FormatVersion.APIGW_10}",
    ):
        response = func_API_GW_20(apigw_http_10_event.get_event(), None)

    with pytest.raises(
        TypeError,
        match=f"Expected event version {FormatVersion.APIGW_20}, but received an unknown event",
    ):
        func_API_GW_20({}, None)


def test_event_format_version_decorator_use_error_response():
    base_event = Event(
        integration_type=None,
        method="POST",
        path=Path(stage="live", path="/foo", resource="/foo"),
        body=None,
    )
    apigw_http_10_event = base_event.with_(
        integration_type=IntegrationType.APIGW_HTTP_10
    )
    apigw_http_20_event = base_event.with_(
        integration_type=IntegrationType.APIGW_HTTP_20
    )

    @event_format_version(FormatVersion.APIGW_10, use_error_response=True)
    def func_API_GW_10(event, context):
        return {"statusCode": 200, "body": ""}

    @event_format_version(FormatVersion.APIGW_20, use_error_response=True)
    def func_API_GW_20(event, context):
        return {"statusCode": 200, "body": ""}

    response = func_API_GW_10(apigw_http_10_event.get_event(), None)
    assert response.get("statusCode") == 200

    response = func_API_GW_10(apigw_http_20_event.get_event(), None)
    assert response.get("statusCode") == 500

    response = func_API_GW_20(apigw_http_20_event.get_event(), None)
    assert response.get("statusCode") == 200

    response = func_API_GW_20(apigw_http_10_event.get_event(), None)
    assert response.get("statusCode") == 500

    response = func_API_GW_20({}, None)
    assert response.get("statusCode") == 500
