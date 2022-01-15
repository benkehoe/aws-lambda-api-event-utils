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
import base64
import uuid
import json

from aws_lambda_api_event_utils import *

from tests import events
from tests.events import IntegrationType, Event, Path, Body, create_context

rand_str = lambda: uuid.uuid4().hex[:8]
rand_bytes = lambda: uuid.uuid4().bytes


def test_get_body():
    for integration_type in IntegrationType:
        base_event = Event(
            integration_type=integration_type,
            method="POST",
            path=Path(stage="live", path="/foo", resource="/foo"),
            body=None,
        )

        # basic string body
        body_text = rand_str()
        event = base_event.with_(body=body_text)
        body = get_body(event.get_event())
        assert body == body_text

        # validate string type
        body_text = rand_str()
        event = base_event.with_(body=body_text)
        body = get_body(event.get_event(), type=BodyType.str)
        assert body == body_text

        # validate string type with binary body
        with pytest.raises(PayloadBinaryTypeError) as exc_info:
            body_text = rand_str()
            event = base_event.with_(body=body_text)
            body = get_body(event.get_event(), type=BodyType.bytes)
        assert exc_info.value.binary_expected

        # binary body
        body_bytes = rand_bytes()
        assert type(body_bytes) == bytes
        event = base_event.with_(body=body_bytes)
        event = event.get_event()
        assert type(event["body"]) == str
        assert event["body"][-1] == "="
        body = get_body(event)
        assert body == body_bytes

        # validate bytes type with binary body
        body_bytes = rand_bytes()
        event = base_event.with_(body=body_bytes)
        body = get_body(event.get_event(), type=BodyType.bytes)
        assert body == body_bytes

        # validate bytes type with string body
        with pytest.raises(PayloadBinaryTypeError) as exc_info:
            body_bytes = rand_bytes()
            event = base_event.with_(body=body_bytes)
            body = get_body(event.get_event(), type=BodyType.str)
        assert not exc_info.value.binary_expected

        # already-parsed body
        body_value = {"foo": "bar"}
        event = base_event.with_(
            integration_type=integration_type,
            body=Body(body_value, is_base64_encoded=False),
        )
        body = get_body(event.get_event())
        assert body == body_value

        # already-parsed body
        body_value = {"foo": "bar"}
        event = base_event.with_(
            integration_type=integration_type,
            body=Body(body_value, is_base64_encoded=True),
        )
        body = get_body(event.get_event())
        assert body == body_value

        # already-parsed body can't have type enforced
        with pytest.raises(
            TypeError, match="Cannot enforce binary status on parsed body"
        ):
            body_value = {"foo": "bar"}
            event = base_event.with_(
                integration_type=integration_type,
                body=Body(body_value, is_base64_encoded=True),
            )
            body = get_body(
                event.get_event(),
                type=BodyType.bytes,
            )

        # already-parsed body can't have type enforced
        with pytest.raises(
            TypeError, match="Cannot enforce binary status on parsed body"
        ):
            body_value = {"foo": "bar"}
            event = base_event.with_(
                integration_type=integration_type,
                body=Body(body_value, is_base64_encoded=True),
            )
            body = get_body(
                event.get_event(),
                type=BodyType.str,
            )

        # empty body should stay None
        event = base_event.with_(
            integration_type=integration_type,
            body=Body(None, is_base64_encoded=False),
        )
        body = get_body(
            event.get_event(),
        )
        assert body is None

        # null body with binary type enforced should be empty bytes
        event = base_event.with_(
            integration_type=integration_type,
            body=Body(None, is_base64_encoded=False),
        )
        body = get_body(event.get_event(), type=BodyType.bytes)
        assert body == b""

        # null body with str type enforced should be empty string
        event = base_event.with_(
            integration_type=integration_type,
            body=Body(None, is_base64_encoded=False),
        )
        body = get_body(event.get_event(), type=BodyType.str)
        assert body == ""

        # empty string body with str type enforced should be empty str
        event = base_event.with_(
            integration_type=integration_type,
        )
        input_event = event.get_event()
        input_event["body"] = ""
        body = get_body(
            input_event,
        )
        assert body == ""

        # empty bytes body with bytes type enforced should be empty bytes
        event = base_event.with_(
            integration_type=integration_type,
            body=Body(b"", is_base64_encoded=False),
        )
        body = get_body(
            event.get_event(),
            type=BodyType.bytes,
        )
        assert body == b""


def test_get_json_body():
    for integration_type in IntegrationType:
        base_event = Event(
            integration_type=integration_type,
            method="POST",
            path=Path(stage="live", path="/foo", resource="/foo"),
            body=None,
        )

        body_content = {rand_str(): rand_str()}
        serialized_str = json.dumps(body_content)
        serialized_bytes = json.dumps(body_content).encode("utf-8")

        # body as string
        event = base_event.with_(integration_type=integration_type, body=serialized_str)
        body = get_json_body(event.get_event())
        assert body == body_content

        # body as bytes
        event = base_event.with_(
            integration_type=integration_type, body=serialized_bytes
        )
        body = get_json_body(event.get_event())
        assert body == body_content

        # body isn't JSON
        invalid_body = "<invalid>"
        with pytest.raises(PayloadJSONDecodeError):
            event = base_event.with_(
                integration_type=integration_type, body=invalid_body
            )
            get_json_body(event.get_event())

        # POST without body
        with pytest.raises(PayloadJSONDecodeError, match="Request has no body"):
            event = base_event.with_(
                integration_type=integration_type, body=None, method="POST"
            )
            get_json_body(event.get_event())

        # GET without body
        event = base_event.with_(
            integration_type=integration_type, body=None, method="GET"
        )
        body = get_json_body(event.get_event())
        assert body is None

        # GET without body, enforced parsing
        with pytest.raises(PayloadJSONDecodeError, match="Request has no body"):
            event = base_event.with_(
                integration_type=integration_type, body=None, method="GET"
            )
            get_json_body(
                event.get_event(),
                enforce_on_optional_methods=True,
            )

        # enforce content type when it's missing
        with pytest.raises(ContentTypeError):
            event = base_event.with_(integration_type=integration_type, body=None)
            get_json_body(
                event.get_event(),
                enforce_content_type=True,
            )

        # enforce content type when it's wrong
        with pytest.raises(ContentTypeError):
            event = base_event.with_(
                integration_type=integration_type,
                body=serialized_str,
                content_type="text/plain",
            )
            get_json_body(
                event.get_event(),
                enforce_content_type=True,
            )

        # enforce content type when it's present
        event = base_event.with_(
            integration_type=integration_type,
            body=serialized_str,
            content_type="application/json",
        )
        get_json_body(
            event.get_event(),
            enforce_content_type=True,
        )


def test_json_body_decorator():
    for integration_type in IntegrationType:
        base_event = Event(
            integration_type=integration_type,
            method="POST",
            path=Path(stage="live", path="/foo", resource="/foo"),
            body=None,
        )

        body_content = {rand_str(): rand_str()}
        serialized_str = json.dumps(body_content)

        @json_body  # bare decorator
        def handler(event, context):
            assert event["body"] == body_content
            return {"statusCode": 200, "body": ""}

        event = base_event.with_(integration_type=integration_type, body=serialized_str)
        response = handler(
            event.get_event(),
            create_context(),
        )
        assert response["statusCode"] == 200

        @json_body()  # with parentheses
        def handler(event, context):
            assert event["body"] == body_content
            return {"statusCode": 200, "body": ""}

        event = base_event.with_(integration_type=integration_type, body=serialized_str)
        response = handler(
            event.get_event(),
            create_context(),
        )
        assert response["statusCode"] == 200

        serialized_bytes = json.dumps(body_content).encode("utf-8")

        @json_body
        def handler(event, context):
            assert event["body"] == body_content
            return {"statusCode": 200, "body": ""}

        event = base_event.with_(
            integration_type=integration_type, body=serialized_bytes
        )
        response = handler(
            event.get_event(),
            create_context(),
        )
        assert response["body"] == ""
        assert response["statusCode"] == 200

        invalid_body = "<invalid>"

        @json_body
        def handler(event, context):
            assert event["body"] == body_content
            return {"statusCode": 200, "body": ""}

        event = base_event.with_(integration_type=integration_type, body=invalid_body)
        response = handler(
            event.get_event(),
            create_context(),
        )
        assert response["statusCode"] == 400
        response_body = json.loads(response["body"])
        assert response_body["Error"]["Code"] == "InvalidPayload"
        assert response_body["Error"]["Message"] == "Request body must be valid JSON."

        @json_body
        def handler(event, context):
            assert event["body"] == body_content
            return {"statusCode": 200, "body": ""}

        event = base_event.with_(integration_type=integration_type, body=serialized_str)
        response = handler(event.get_event(), create_context())
        assert response["statusCode"] == 200

        @json_body(enforce_content_type=True)
        def handler(event, context):
            assert event["body"] == body_content
            return {"statusCode": 200, "body": ""}

        event = base_event.with_(
            integration_type=integration_type,
            body=serialized_str,
            content_type="text/plain",
        )
        response = handler(event.get_event(), create_context())
        assert response["statusCode"] == 415
        assert json.loads(response["body"])["Error"]["Code"] == "InvalidContentType"


def test_get_json_body_with_schema():
    for integration_type in IntegrationType:
        base_event = Event(
            integration_type=integration_type,
            method="POST",
            path=Path(stage="live", path="/foo", resource="/foo"),
            body=None,
        )

        schema = {
            "type": "object",
            "properties": {"foo": {"type": "string", "const": "bar"}},
            "additionalProperties": False,
        }

        valid_body_content = {"foo": "bar"}
        valid_body_content_str = json.dumps(valid_body_content)
        valid_body_content_bytes = valid_body_content_str.encode("utf-8")

        invalid_body_content = {"not_foo": "not_bar"}
        invalid_body_content_str = json.dumps(invalid_body_content)
        invalid_body_content_bytes = invalid_body_content_str.encode("utf-8")

        body = get_json_body(
            base_event.with_(body=valid_body_content_str).get_event(),
            schema=schema,
        )
        assert body == valid_body_content

        body = get_json_body(
            base_event.with_(body=valid_body_content_bytes).get_event(),
            schema=schema,
        )
        assert body == valid_body_content

        with pytest.raises(PayloadSchemaViolationError):
            get_json_body(
                base_event.with_(body=invalid_body_content_str).get_event(),
                schema=schema,
            )

        with pytest.raises(PayloadSchemaViolationError):
            get_json_body(
                base_event.with_(body=invalid_body_content_bytes).get_event(),
                schema=schema,
            )


def test_json_body_decorator_with_schema():
    for integration_type in IntegrationType:
        base_event = Event(
            integration_type=integration_type,
            method="POST",
            path=Path(stage="live", path="/foo", resource="/foo"),
            body=None,
        )

        schema = {
            "type": "object",
            "properties": {"foo": {"type": "string", "const": "bar"}},
            "additionalProperties": False,
        }

        valid_body_content = {"foo": "bar"}
        valid_body_content_str = json.dumps(valid_body_content)
        valid_body_content_bytes = valid_body_content_str.encode("utf-8")

        invalid_body_content = {"not_foo": "not_bar"}
        invalid_body_content_str = json.dumps(invalid_body_content)
        invalid_body_content_bytes = invalid_body_content_str.encode("utf-8")

        @json_body(schema=schema)
        def handler(event, context):
            assert event["body"] == valid_body_content
            return {"statusCode": 200, "body": ""}

        response = handler(
            base_event.with_(body=valid_body_content_str).get_event(),
            create_context(),
        )
        assert response["statusCode"] == 200

        response = handler(
            base_event.with_(body=valid_body_content_bytes).get_event(),
            create_context(),
        )
        assert response["statusCode"] == 200

        response = handler(
            base_event.with_(body=invalid_body_content_str).get_event(),
            create_context(),
        )
        assert response["statusCode"] == 400

        response = handler(
            base_event.with_(body=invalid_body_content_bytes).get_event(),
            create_context(),
        )
        assert response["statusCode"] == 400

        @json_body(schema=schema)
        def handler(event, context):
            assert event["body"] == valid_body_content
            return {"statusCode": 200, "body": ""}

        response = handler(
            base_event.with_(body=valid_body_content_str).get_event(), create_context()
        )
        assert response["statusCode"] == 200

        @json_body(schema=schema, enforce_content_type=True)
        def handler(event, context):
            assert event["body"] == valid_body_content
            return {"statusCode": 200, "body": ""}

        response = handler(
            base_event.with_(body=valid_body_content_str).get_event(), create_context()
        )
        assert response["statusCode"] == 415
