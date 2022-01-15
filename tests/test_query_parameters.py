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

from aws_lambda_api_event_utils import *

from tests.events import *

rand_str = lambda: uuid.uuid4().hex[:8]


def test_validate_query_parameters():
    for integration_type in IntegrationType:
        event = Event(
            integration_type=integration_type,
            method="POST",
            path=Path(stage="live", path="/foo", resource="/foo"),
            body=None,
            query_params={"parameter1": ["value1", "value2"], "parameter2": "value"},
        )

        query_parameters = validate_query_parameters(
            event.get_event(), keys=["parameter1"]
        )
        assert query_parameters == {
            "parameter1": "value1,value2",
            "parameter2": "value",
        }

        parameter_name = rand_str()
        with pytest.raises(QueryParameterError, match=parameter_name):
            validate_query_parameters(event.get_event(), keys=[parameter_name])

        query_parameters = validate_query_parameters(
            event.get_event(), values={"parameter1": "value1,value2"}
        )

        query_parameters = validate_query_parameters(
            event.get_event(), values={"parameter2": "value"}
        )

        parameter_value = rand_str()
        with pytest.raises(QueryParameterError, match=f"parameter1=value1,value2"):
            validate_query_parameters(
                event.get_event(), values={"parameter1": parameter_value}
            )

        parameter_name = rand_str()
        parameter_value = rand_str()
        with pytest.raises(QueryParameterError, match=f"{parameter_name}"):
            validate_query_parameters(
                event.get_event(), values={parameter_name: parameter_value}
            )

        value_pattern = "ue$"
        validate_query_parameters(
            event.get_event(), value_patterns={"parameter2": value_pattern}
        )

        value_pattern = "ue2$"
        validate_query_parameters(
            event.get_event(), value_patterns={"parameter1": value_pattern}
        )

        with pytest.raises(QueryParameterError, match="parameter1"):
            value_pattern = "ue1$"
            validate_query_parameters(
                event.get_event(), value_patterns={"parameter1": value_pattern}
            )

        value_pattern = "ue1(,|$)"
        validate_query_parameters(
            event.get_event(), value_patterns={"parameter1": value_pattern}
        )


def test_query_parameters_decorator():
    for integration_type in IntegrationType:
        event = Event(
            integration_type=integration_type,
            method="POST",
            path=Path(stage="live", path="/foo", resource="/foo"),
            body=None,
            query_params={"parameter1": ["value1", "value2"], "parameter2": "value"},
        )

        def validate_event(event):
            if integration_type in [
                IntegrationType.APIGW_REST,
                IntegrationType.APIGW_HTTP_10,
            ]:
                assert event["queryStringParameters"] == {
                    "parameter1": "value1",
                    "parameter2": "value",
                }
                assert event["multiValueQueryStringParameters"] == {
                    "parameter1": [
                        "value1",
                        "value2",
                    ],
                    "parameter2": [
                        "value",
                    ],
                }
            elif integration_type == IntegrationType.APIGW_HTTP_20:
                assert event["queryStringParameters"] == {
                    "parameter1": "value1,value2",
                    "parameter2": "value",
                }
            else:
                raise NotImplementedError

        @query_parameters(keys=["parameter1"])
        def handler(event, context):
            validate_event(event)
            return {"statusCode": 200, "body": ""}

        response = handler(event.get_event(), None)
        assert response["statusCode"] == 200

        parameter_name = rand_str()

        @query_parameters(keys=[parameter_name])
        def handler(event, context):
            return {"statusCode": 200, "body": ""}

        response = handler(event.get_event(), None)
        assert response["statusCode"] == 400
        assert json.loads(response["body"])["Error"]["Code"] == "InvalidRequest"

        @query_parameters(values={"parameter1": "value1,value2"})
        def handler(event, context):
            validate_event(event)
            return {"statusCode": 200, "body": ""}

        response = handler(event.get_event(), None)
        assert response["statusCode"] == 200

        @query_parameters(values={"parameter2": "value"})
        def handler(event, context):
            validate_event(event)
            return {"statusCode": 200, "body": ""}

        response = handler(event.get_event(), None)
        assert response["statusCode"] == 200

        parameter_value = rand_str()

        @query_parameters(values={"parameter1": parameter_value})
        def handler(event, context):
            return {"statusCode": 200, "body": ""}

        response = handler(event.get_event(), None)
        assert response["statusCode"] == 400

        parameter_name = rand_str()
        parameter_value = rand_str()

        @query_parameters(values={parameter_name: parameter_value})
        def handler(event, context):
            return {"statusCode": 200, "body": ""}

        response = handler(event.get_event(), None)
        assert response["statusCode"] == 400
