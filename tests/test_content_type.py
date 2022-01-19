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

from aws_lambda_api_event_utils import *

from tests.events import *

rand_str = lambda: uuid.uuid4().hex[:8]


def test_validate_content_type():
    for integration_type in IntegrationType:
        base_event = Event(
            integration_type=integration_type,
            method="POST",
            path=Path(stage="live", path="/foo", resource="/foo"),
            body=None,
        )

        event = lambda ct: base_event.with_(content_type=ct).get_event()

        with pytest.raises(ContentTypeError, match="Content-Type is missing") as exc:
            validate_content_type(base_event.get_event(), "application/json")

        content_type = validate_content_type(
            event("application/json"), "application/json"
        )
        assert content_type == "application/json"

        content_type = validate_content_type(
            event("application/json"), ["application/json"]
        )
        assert content_type == "application/json"

        content_type = validate_content_type(
            event("application/json"), ["text/plain", "application/json"]
        )
        assert content_type == "application/json"

        with pytest.raises(ContentTypeError, match="application/json.*text/plain"):
            validate_content_type(event("application/json"), "text/plain")

        content_type = validate_content_type(event("application/json"), "*/*")
        assert content_type == "application/json"

        content_type = validate_content_type(event("application/json"), "application/*")
        assert content_type == "application/json"

        content_type = validate_content_type(
            event("text/html; charset=UTF-8"), "text/html"
        )
        assert content_type == "text/html; charset=UTF-8"


def validate_content_type_decorator():
    for integration_type in IntegrationType:
        base_event = Event(
            integration_type=integration_type,
            method="POST",
            path=Path(stage="live", path="/foo", resource="/foo"),
            body=None,
        )

        event = lambda ct: base_event.with_(content_type=ct).get_event()

        @content_type("application/json")
        def handler(event, context):
            return {"statusCode": 200, "body": ""}

        response = handler(base_event.get_event(), None)
        assert response["statusCode"] == 415
        assert response["Error"]["Code"] == "InvalidContentType"

        @content_type(["text/plain", "application/json"])
        def handler(event, context):
            return {"statusCode": 200, "body": ""}

        response = handler(base_event.get_event(), None)
        assert response["statusCode"] == 415
        assert response["Error"]["Code"] == "InvalidContentType"
        assert (
            response["Error"]["Message"]
            == "Content type must be one of: text/plain, application/json"
        )
        # assert response["headers"]["accept"] == "text/plain; application/json"

        @content_type("application/json")
        def handler(event, context):
            return {"statusCode": 200, "body": ""}

        response = handler(event("application/json"), None)
        assert response["statusCode"] == 200

        @content_type(["application/json"])
        def handler(event, context):
            return {"statusCode": 200, "body": ""}

        response = handler(event("application/json"), None)
        assert response["statusCode"] == 200

        @content_type(["text/plain", "application/json"])
        def handler(event, context):
            return {"statusCode": 200, "body": ""}

        response = handler(event("application/json"), None)
        assert response["statusCode"] == 200

        @content_type("text/plain")
        def handler(event, context):
            return {"statusCode": 200, "body": ""}

        response = handler(event("application/json"), None)
        assert response["statusCode"] == 415
        assert response["Error"]["Code"] == "InvalidContentType"
