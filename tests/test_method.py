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
import json

from aws_lambda_api_event_utils import *

from tests.events import *


def test_validate_method():
    for integration_type in IntegrationType:
        event = Event(
            integration_type=integration_type,
            method="GET",
            path=Path(stage="live", path="/foo", resource="/foo"),
            body=None,
        )

        assert validate_method(event.get_event(), "GET") == "GET"
        assert validate_method(event.get_event(), ["GET"]) == "GET"
        assert validate_method(event.get_event(), ["GET", "POST"]) == "GET"

        with pytest.raises(UnsupportedMethodError):
            validate_method(event.get_event(), "POST")

        with pytest.raises(UnsupportedMethodError):
            validate_method(event.get_event(), ["POST"])


def test_method_decorator():
    for integration_type in IntegrationType:
        event = Event(
            integration_type=integration_type,
            method="GET",
            path=Path(stage="live", path="/foo", resource="/foo"),
            body=None,
        )

        @method("GET")
        def get_only(event, context):
            return make_response(200, body=None, format_version=event)

        response = get_only(event.get_event(), None)
        assert response["statusCode"] == 200

        @method(["GET"])
        def get_list(event, context):
            return make_response(200, body=None, format_version=event)

        response = get_list(event.get_event(), None)
        assert response["statusCode"] == 200

        @method(["GET", "POST"])
        def get_post(event, context):
            return make_response(200, body=None, format_version=event)

        response = get_post(event.get_event(), None)
        assert response["statusCode"] == 200

        @method("POST")
        def post_only(event, context):
            return make_response(200, body=None, format_version=event)

        response = post_only(event.get_event(), None)
        assert response["statusCode"] == 405
        assert json.loads(response["body"])["Error"]["Code"] == "UnsupportedMethod"

        @method(["POST"])
        def post_list(event, context):
            return make_response(200, body=None, format_version=event)

        response = post_list(event.get_event(), None)
        assert response["statusCode"] == 405
        assert json.loads(response["body"])["Error"]["Code"] == "UnsupportedMethod"
