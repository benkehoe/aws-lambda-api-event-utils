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
import copy

from aws_lambda_api_event_utils import *

from tests.events import *
from tests.stack.test_stack import rand_str


def test_validate_path():
    for integration_type in IntegrationType:
        event = Event(
            integration_type=integration_type,
            method="POST",
            path=Path(stage="live", path="/my/path", resource="/my/path"),
            body=None,
        )

        path, parameters = validate_path(event.get_event(), "/my/path")
        assert path == "/my/path"
        assert parameters == {}

        path, parameters = validate_path(event.get_event(), ["/my/path"])
        assert path == "/my/path"
        assert parameters == {}

        path, parameters = validate_path(
            event.get_event(), ["/my/path", "/not/the/path"]
        )
        assert path == "/my/path"
        assert parameters == {}

        with pytest.raises(PathNotFoundError):
            path, parameters = validate_path(event.get_event(), "/not/the/path")

        with pytest.raises(PathNotFoundError):
            path, parameters = validate_path(event.get_event(), ["/not/the/path"])

        with pytest.raises(PathNotFoundError):
            path, parameters = validate_path(
                event.get_event(), ["/not/the/path", "/also/not/the/path"]
            )


def test_path_decorator():
    for integration_type in IntegrationType:
        event = Event(
            integration_type=integration_type,
            method="POST",
            path=Path(stage="live", path="/my/path", resource="/my/path"),
            body=None,
        )

        path, parameters = validate_path(event.get_event(), "/my/path")
        assert path == "/my/path"
        assert parameters == {}

        path, parameters = validate_path(event.get_event(), ["/my/path"])
        assert path == "/my/path"
        assert parameters == {}

        path, parameters = validate_path(
            event.get_event(), ["/my/path", "/not/the/path"]
        )
        assert path == "/my/path"
        assert parameters == {}

        with pytest.raises(PathNotFoundError):
            path, parameters = validate_path(event.get_event(), "/not/the/path")

        with pytest.raises(PathNotFoundError):
            path, parameters = validate_path(event.get_event(), ["/not/the/path"])

        with pytest.raises(PathNotFoundError):
            path, parameters = validate_path(
                event.get_event(), ["/not/the/path", "/also/not/the/path"]
            )


def test_validate_path_regex():
    for integration_type in IntegrationType:
        base_event = Event(
            integration_type=integration_type,
            method="POST",
            path=Path(stage="live", path="/my/path", resource="/my/path"),
            body=None,
        )

        def assert_path_params_empty(event):
            if integration_type in [
                IntegrationType.APIGW_REST,
                IntegrationType.APIGW_HTTP_10,
            ]:
                assert event["pathParameters"] is None
            elif integration_type == IntegrationType.APIGW_HTTP_20:
                assert "pathParameters" not in event
            else:
                raise NotImplementedError

        event = base_event.get_event()
        path, parameters = validate_path_regex(event, r"^/my/path$")
        assert path == "/my/path"
        assert parameters == {}
        assert_path_params_empty(event)

        event = base_event.get_event()
        path, parameters = validate_path_regex(event, r"^/my/(?P<component>\w+)")
        assert path == "/my/path"
        assert parameters == {"component": "path"}
        assert_path_params_empty(event)

        event = base_event.get_event()
        path, parameters = validate_path_regex(event, r"^/my/path$", update_event=True)
        assert path == "/my/path"
        assert parameters == {}
        if integration_type in [
            IntegrationType.APIGW_REST,
            IntegrationType.APIGW_HTTP_10,
        ]:
            assert event["pathParameters"] is None
        elif integration_type == IntegrationType.APIGW_HTTP_20:
            assert "pathParameters" not in event
        else:
            raise NotImplementedError

        event = base_event.get_event()
        path, parameters = validate_path_regex(
            event, r"^/my/(?P<component>\w+)", update_event=True
        )
        assert path == "/my/path"
        assert parameters == {"component": "path"}
        assert event["pathParameters"] == {"component": "path"}

        event = base_event.get_event()
        path, parameters = validate_path_regex(
            event, r"^/my/path(?P<component>/\w+)?", update_event=True
        )
        assert path == "/my/path"
        assert parameters == {"component": None}
        assert event["pathParameters"] == {"component": None}

        event = base_event.get_event()
        path, parameters = validate_path_regex(event, r"^/my/path", update_event=True)
        assert path == "/my/path"
        assert parameters == {}
        assert_path_params_empty(event)

        # check we're not using re.match
        path, parameters = validate_path_regex(base_event.get_event(), r"/path")
        assert path == "/my/path"
        assert parameters == {}

        with pytest.raises(PathNotFoundError):
            path, parameters = validate_path_regex(base_event.get_event(), r"^/path")


def test_path_regex_decorator():
    for integration_type in IntegrationType:
        event = Event(
            integration_type=integration_type,
            method="POST",
            path=Path(stage="live", path="/my/path", resource="/my/path"),
            body=None,
        )

        @path_regex(r"^/my/path$")
        def handler(event, context):
            if integration_type in [
                IntegrationType.APIGW_REST,
                IntegrationType.APIGW_HTTP_10,
            ]:
                assert event["pathParameters"] is None
            elif integration_type == IntegrationType.APIGW_HTTP_20:
                assert "pathParameters" not in event
            else:
                raise NotImplementedError
            return {"statusCode": 200, "body": ""}

        response = handler(event.get_event(), create_context())
        assert response["statusCode"] == 200

        @path_regex(r"^/my/(?P<component>\w+)")
        def handler(event, context):
            assert event["pathParameters"] == {"component": "path"}
            return {"statusCode": 200, "body": ""}

        response = handler(event.get_event(), create_context())
        assert response["statusCode"] == 200

        @path_regex(r"^/my/path(?P<component>/\w+)?")
        def handler(event, context):
            assert event["pathParameters"] == {"component": None}
            return {"statusCode": 200, "body": ""}

        response = handler(event.get_event(), create_context())
        assert response["statusCode"] == 200

        # check we're not using re.match
        @path_regex(r"/path")
        def handler(event, context):
            return {"statusCode": 200, "body": ""}

        response = handler(event.get_event(), create_context())
        assert response["statusCode"] == 200

        @path_regex(r"^/path")
        def handler(event, context):
            return {"statusCode": 200, "body": ""}

        response = handler(event.get_event(), create_context())
        assert response["statusCode"] == 404


def test_validate_path_parameters():
    for integration_type in IntegrationType:
        param_name = rand_str()
        param_value = rand_str()
        param_value_pattern = f"{param_value[-4:]}$"

        parameters = {param_name: param_value}

        resource = f"/my/{param_name}"
        path = f"/my/{param_value}"

        event = Event(
            integration_type=integration_type,
            method="POST",
            path=Path(
                stage="live", path=path, resource=resource, path_parameters=parameters
            ),
            body=None,
        )

        event_path, event_parameters = validate_path_parameters(
            event.get_event(), keys=[param_name]
        )
        assert event_path == f"/my/{param_value}"
        assert event_parameters == parameters

        event_path, event_parameters = validate_path_parameters(
            event.get_event(), values={param_name: param_value}
        )
        assert event_path == f"/my/{param_value}"
        assert event_parameters == parameters

        event_path, event_parameters = validate_path_parameters(
            event.get_event(), value_patterns={param_name: param_value_pattern}
        )
        assert event_path == f"/my/{param_value}"
        assert event_parameters == parameters

        invalid_key = rand_str()
        with pytest.raises(PathParameterError, match=invalid_key):
            event_path, event_parameters = validate_path_parameters(
                event.get_event(), keys=[param_name, invalid_key]
            )

        invalid_key = rand_str()
        invalid_value = rand_str()
        with pytest.raises(PathParameterError) as exc_info:
            event_path, event_parameters = validate_path_parameters(
                event.get_event(),
                keys=[invalid_key],
                values={param_name: invalid_value},
            )
        assert param_name in str(exc_info.value)
        assert invalid_key in str(exc_info.value)


@pytest.mark.xfail(reason="TODO")
def test_path_parameters_decorator():
    assert False, "TODO"

    """

    param_name = rand_str()
    param_value = rand_str()
    param_value_pattern = f"{param_value[-4:]}$"

    parameters = {param_name: param_value}

    event = PATH_PARAMETER_APIGW_10(**parameters)
    event_path, event_parameters = validate_path_parameters(event, keys=[param_name])
    assert event_path == f"/my/{param_value}"
    assert event_parameters == parameters

    event = PATH_PARAMETER_APIGW_10(**parameters)
    event_path, event_parameters = validate_path_parameters(
        event, values={param_name: param_value}
    )
    assert event_path == f"/my/{param_value}"
    assert event_parameters == parameters

    event = PATH_PARAMETER_APIGW_10(**parameters)
    event_path, event_parameters = validate_path_parameters(
        event, value_patterns={param_name: param_value_pattern}
    )
    assert event_path == f"/my/{param_value}"
    assert event_parameters == parameters

    invalid_key = rand_str()
    with pytest.raises(PathParameterError, match=invalid_key):
        event = PATH_PARAMETER_APIGW_10(**parameters)
        event_path, event_parameters = validate_path_parameters(
            event, keys=[param_name, invalid_key]
        )

    invalid_key = rand_str()
    invalid_value = rand_str()
    with pytest.raises(PathParameterError) as exc_info:
        event = PATH_PARAMETER_APIGW_10(**parameters)
        event_path, event_parameters = validate_path_parameters(
            event, keys=[invalid_key], values={param_name: invalid_value}
        )
    assert param_name in str(exc_info.value)
    assert invalid_key in str(exc_info.value)

    ### apigw:2.0 ###

    param_name = rand_str()
    param_value = rand_str()
    param_value_pattern = f"{param_value[-4:]}$"

    parameters = {param_name: param_value}

    event = PATH_PARAMETER_APIGW_20(**parameters)
    event_path, event_parameters = validate_path_parameters(event, keys=[param_name])
    assert event_path == f"/my/{param_value}"
    assert event_parameters == parameters

    event = PATH_PARAMETER_APIGW_20(**parameters)
    event_path, event_parameters = validate_path_parameters(
        event, values={param_name: param_value}
    )
    assert event_path == f"/my/{param_value}"
    assert event_parameters == parameters

    event = PATH_PARAMETER_APIGW_20(**parameters)
    event_path, event_parameters = validate_path_parameters(
        event, value_patterns={param_name: param_value_pattern}
    )
    assert event_path == f"/my/{param_value}"
    assert event_parameters == parameters

    invalid_key = rand_str()
    with pytest.raises(PathParameterError, match=invalid_key):
        event = PATH_PARAMETER_APIGW_20(**parameters)
        event_path, event_parameters = validate_path_parameters(
            event, keys=[param_name, invalid_key]
        )

    invalid_key = rand_str()
    invalid_value = rand_str()
    with pytest.raises(PathParameterError) as exc_info:
        event = PATH_PARAMETER_APIGW_20(**parameters)
        event_path, event_parameters = validate_path_parameters(
            event, keys=[invalid_key], values={param_name: invalid_value}
        )
    assert param_name in str(exc_info.value)
    assert invalid_key in str(exc_info.value)

    """
