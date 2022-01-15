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


def test_validate_headers():
    for integration_type in IntegrationType:
        event = Event(
            integration_type=integration_type,
            method="POST",
            path=Path(stage="live", path="/foo", resource="/foo"),
            body=None,
            headers={"header1": "value1", "header2": ["value1", "value2"]},
        )

        headers = validate_headers(event.get_event(), keys=["header1"])
        assert headers == {"header1": "value1", "header2": "value1,value2"}

        header_name = rand_str()
        with pytest.raises(HeaderError, match=header_name):
            validate_headers(event.get_event(), keys=[header_name])

        headers = validate_headers(event.get_event(), values={"header1": "value1"})

        headers = validate_headers(
            event.get_event(), values={"header2": "value1,value2"}
        )

        header_value = rand_str()
        with pytest.raises(HeaderError, match=f"header1=value1"):
            validate_headers(event.get_event(), values={"header1": header_value})

        header_name = rand_str()
        header_value = rand_str()
        with pytest.raises(HeaderError, match=header_name):
            validate_headers(event.get_event(), values={header_name: header_value})

        value_pattern = "ue1$"
        validate_headers(event.get_event(), value_patterns={"header1": value_pattern})

        value_pattern = "ue2$"
        validate_headers(event.get_event(), value_patterns={"header2": value_pattern})

        with pytest.raises(HeaderError, match="header2"):
            value_pattern = "ue1$"
            validate_headers(
                event.get_event(), value_patterns={"header2": value_pattern}
            )

        value_pattern = "ue1(,|$)"
        validate_headers(event.get_event(), value_patterns={"header2": value_pattern})


def test_headers_decorator():
    for integration_type in IntegrationType:
        event = Event(
            integration_type=integration_type,
            method="POST",
            path=Path(stage="live", path="/foo", resource="/foo"),
            body=None,
            headers={"header1": "value1", "header2": ["value1", "value2"]},
        )

        if integration_type in [
            IntegrationType.APIGW_REST,
            IntegrationType.APIGW_HTTP_10,
        ]:

            def validate_event(event):
                assert event["headers"] == {"header1": "value1", "header2": "value2"}
                assert event["multiValueHeaders"] == {
                    "header1": ["value1"],
                    "header2": ["value1", "value2"],
                }

        elif integration_type == IntegrationType.APIGW_HTTP_20:

            def validate_event(event):
                assert event["headers"] == {
                    "header1": "value1",
                    "header2": "value1,value2",
                }

        else:
            raise NotImplementedError

        @headers(keys=["header1"])
        def handler(event, context):
            validate_event(event)
            return {"statusCode": 200, "body": ""}

        response = handler(event.get_event(), None)
        assert response["statusCode"] == 200

        header_name = rand_str()

        @headers(keys=[header_name])
        def handler(event, context):
            return {"statusCode": 200, "body": ""}

        response = handler(event.get_event(), None)
        assert response["statusCode"] == 400

        @headers(values={"header1": "value1"})
        def handler(event, context):
            validate_event(event)
            return {"statusCode": 200, "body": ""}

        response = handler(event.get_event(), None)
        assert response["statusCode"] == 200

        @headers(values={"header2": "value1,value2"})
        def handler(event, context):
            validate_event(event)
            return {"statusCode": 200, "body": ""}

        response = handler(event.get_event(), None)
        assert response["statusCode"] == 200

        header_value = rand_str()

        @headers(values={"header1": header_value})
        def handler(event, context):
            return {"statusCode": 200, "body": ""}

        response = handler(event.get_event(), None)
        assert response["statusCode"] == 400

        header_name = rand_str()
        header_value = rand_str()

        @headers(values={header_name: header_value})
        def handler(event, context):
            return {"statusCode": 200, "body": ""}

        response = handler(event.get_event(), None)
        assert response["statusCode"] == 400
