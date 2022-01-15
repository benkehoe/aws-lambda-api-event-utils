import pytest

import json
import uuid

"""
https://exzait1shc.execute-api.us-east-2.amazonaws.com

/format-version-10
  /fixed-path
  /param/{path-parameter}
  /proxy/{proxy+}
  /wrong-lambda


"""


rand_str = lambda: uuid.uuid4().hex[:8]


@pytest.mark.xfail(reason="TODO")
def test_http_10():
    assert False


@pytest.mark.xfail(reason="TODO")
def test_http_20():
    assert False


def test_method(config, caller):
    for call_type, path in [
        ("REST", "/format-version-10/fixed-path"),
        ("HTTP", "/format-version-10/fixed-path"),
        ("HTTP", "/format-version-20/fixed-path"),
    ]:

        response = caller.call(
            type=call_type,
            path=path,
            method="POST",
            validation={"validate_method": {"method": "POST"}},
        )
        response.raise_for_status()

        response = caller.call(
            type=call_type,
            path=path,
            method="GET",
            validation={"validate_method": {"method": "GET"}},
        )
        response.raise_for_status()

        response = caller.call(
            type=call_type,
            path=path,
            method="GET",
            validation={"validate_method": {"method": "POST"}},
        )
        assert response.status_code == 405
        assert response.json()["Error"]["Code"] == "UnsupportedMethod"


def test_path_fixed(config, caller):
    for call_type, path in [
        ("REST", "/format-version-10/fixed-path"),
        ("HTTP", "/format-version-10/fixed-path"),
        ("HTTP", "/format-version-20/fixed-path"),
    ]:

        response = caller.call(
            type=call_type,
            path=path,
            method="POST",
            validation={},
        )
        response.raise_for_status()

        response = caller.call(
            type=call_type,
            path=path,
            method="GET",
            validation={},
        )
        response.raise_for_status()

        response = caller.call(
            type=call_type,
            path=path,
            method="GET",
            validation={"validate_path": {"path": path}},
        )
        response.raise_for_status()

        invalid_path = rand_str()
        response = caller.call(
            type=call_type,
            path=path,
            method="GET",
            validation={"validate_path": {"path": invalid_path}},
        )
        assert response.status_code == 404
        assert response.json()["Error"]["Code"] == "PathNotFound"


def test_path_parameter(config, caller):
    for call_type, path_template in [
        ("REST", "/format-version-10/param/{param}"),
        ("HTTP", "/format-version-10/param/{param}"),
        ("HTTP", "/format-version-20/param/{param}"),
    ]:

        path_param_name = "path-param-1"
        path_param_value = rand_str()
        path_param_value_pattern = f"{path_param_value[-4:]}$"

        path = path_template.format(param=path_param_value)

        response = caller.call(
            type=call_type,
            path=path,
            method="GET",
            validation={"validate_path_parameters": {"keys": [path_param_name]}},
        )
        response.raise_for_status()

        response = caller.call(
            type=call_type,
            path=path,
            method="GET",
            validation={
                "validate_path_parameters": {
                    "values": {path_param_name: path_param_value}
                }
            },
        )
        response.raise_for_status()

        response = caller.call(
            type=call_type,
            path=path,
            method="GET",
            validation={
                "validate_path_parameters": {
                    "value_patterns": {path_param_name: path_param_value_pattern}
                }
            },
        )
        response.raise_for_status()

        invalid_parameter_name = rand_str()
        invalid_parameter_value = rand_str()
        invalid_parameter_value_pattern = rand_str()

        response = caller.call(
            type=call_type,
            path=path,
            method="GET",
            validation={
                "validate_path_parameters": {
                    "keys": [path_param_name, invalid_parameter_name]
                }
            },
        )
        assert response.status_code == 404
        assert response.json()["Error"]["Code"] == "PathNotFound"

        response = caller.call(
            type=call_type,
            path=path,
            method="GET",
            validation={
                "validate_path_parameters": {
                    "values": {path_param_name: invalid_parameter_value}
                }
            },
        )
        assert response.status_code == 404
        assert response.json()["Error"]["Code"] == "PathNotFound"

        response = caller.call(
            type=call_type,
            path=path,
            method="GET",
            validation={
                "validate_path_parameters": {
                    "value_patterns": {path_param_name: invalid_parameter_value_pattern}
                }
            },
        )
        assert response.status_code == 404
        assert response.json()["Error"]["Code"] == "PathNotFound"


def test_path_parameter_proxy(config, caller):
    for call_type, path_template in [
        ("REST", "/format-version-10/proxy/{param}"),
        ("HTTP", "/format-version-10/proxy/{param}"),
        ("HTTP", "/format-version-20/proxy/{param}"),
    ]:

        path_param_name = "proxy"
        path_param_value = rand_str() + "/" + rand_str()
        path_param_value_pattern = f"{path_param_value[-4:]}$"

        path = path_template.format(param=path_param_value)

        response = caller.call(
            type=call_type,
            path=path,
            method="GET",
            validation={"validate_path_parameters": {"keys": [path_param_name]}},
        )
        response.raise_for_status()

        response = caller.call(
            type=call_type,
            path=path,
            method="GET",
            validation={
                "validate_path_parameters": {
                    "values": {path_param_name: path_param_value}
                }
            },
        )
        response.raise_for_status()

        response = caller.call(
            type=call_type,
            path=path,
            method="GET",
            validation={
                "validate_path_parameters": {
                    "value_patterns": {path_param_name: path_param_value_pattern}
                }
            },
        )
        response.raise_for_status()

        invalid_parameter_name = rand_str()
        invalid_parameter_value = rand_str()
        invalid_parameter_value_pattern = rand_str()

        response = caller.call(
            type=call_type,
            path=path,
            method="GET",
            validation={
                "validate_path_parameters": {
                    "keys": [path_param_name, invalid_parameter_name]
                }
            },
        )
        assert response.status_code == 404
        assert response.json()["Error"]["Code"] == "PathNotFound"

        response = caller.call(
            type=call_type,
            path=path,
            method="GET",
            validation={
                "validate_path_parameters": {
                    "values": {path_param_name: invalid_parameter_value}
                }
            },
        )
        assert response.status_code == 404
        assert response.json()["Error"]["Code"] == "PathNotFound"

        response = caller.call(
            type=call_type,
            path=path,
            method="GET",
            validation={
                "validate_path_parameters": {
                    "value_patterns": {path_param_name: invalid_parameter_value_pattern}
                }
            },
        )
        assert response.status_code == 404
        assert response.json()["Error"]["Code"] == "PathNotFound"


def test_headers(config, caller):
    for call_type, path in [
        ("REST", "/format-version-10/fixed-path"),
        ("HTTP", "/format-version-10/fixed-path"),
        ("HTTP", "/format-version-20/fixed-path"),
    ]:

        header_key = rand_str()
        header_value = rand_str()

        invalid_header_key = rand_str()
        invalid_header_value = rand_str()

        response = caller.call(
            type=call_type,
            path=path,
            method="POST",
            headers={header_key: header_value},
            validation={"validate_headers": {"keys": [header_key]}},
        )
        response.raise_for_status()

        response = caller.call(
            type=call_type,
            path=path,
            method="POST",
            headers={header_key: header_value},
            validation={"validate_headers": {"values": {header_key: header_value}}},
        )
        response.raise_for_status()

        response = caller.call(
            type=call_type,
            path=path,
            method="POST",
            headers={header_key: header_value},
            validation={"validate_headers": {"keys": [invalid_header_key]}},
        )
        assert response.status_code == 400
        assert response.json()["Error"]["Code"] == "InvalidRequest"

        response = caller.call(
            type=call_type,
            path=path,
            method="POST",
            headers={header_key: header_value},
            validation={
                "validate_headers": {"values": {header_key: invalid_header_value}}
            },
        )
        assert response.status_code == 400
        assert response.json()["Error"]["Code"] == "InvalidRequest"


def test_content_type(config, caller):
    for call_type, path in [
        ("REST", "/format-version-10/fixed-path"),
        ("HTTP", "/format-version-10/fixed-path"),
        ("HTTP", "/format-version-20/fixed-path"),
    ]:

        response = caller.call(
            type=call_type,
            path=path,
            method="POST",
            body={"foo": "bar"},
            validation={"validate_content_type": {"content_type": "application/json"}},
        )

        response = caller.call(
            type=call_type,
            path=path,
            method="GET",
            validation={"validate_content_type": {"content_type": "application/json"}},
        )
        assert response.status_code == 415
        assert response.json()["Error"]["Code"] == "InvalidContentType"

        response = caller.call(
            type=call_type,
            path=path,
            method="POST",
            body={"foo": "bar"},
            validation={"validate_content_type": {"content_type": "text/plain"}},
        )
        assert response.status_code == 415
        assert response.json()["Error"]["Code"] == "InvalidContentType"


@pytest.mark.xfail(reason="TODO")
def test_query_parameters():
    assert False


@pytest.mark.xfail(reason="TODO")
def test_body():
    assert False


def test_json_body(config, caller):
    for call_type, path in [
        ("REST", "/format-version-10/fixed-path"),
        ("HTTP", "/format-version-10/fixed-path"),
        ("HTTP", "/format-version-20/fixed-path"),
    ]:

        body = {"foo": "bar"}
        body_validation = {"json": True}
        response = caller.call(
            type=call_type,
            path=path,
            method="POST",
            body=body,
            body_validation=body_validation,
        )
        assert response.json()["body_validation"] == body_validation

        # TODO: payload not JSON


def test_json_body_schema(config, caller):
    for call_type, path in [
        ("REST", "/format-version-10/fixed-path"),
        ("HTTP", "/format-version-10/fixed-path"),
        ("HTTP", "/format-version-20/fixed-path"),
    ]:

        body = {"foo": "bar"}

        schema = {"type": "object", "properties": {"foo": {"const": "bar"}}}
        body_validation = {"json": True, "schema": schema}
        response = caller.call(
            type=call_type,
            path=path,
            method="POST",
            body=body,
            body_validation=body_validation,
        )
        assert response.json()["body_validation"] == body_validation

        schema = {"type": "object", "additionalProperties": False}
        body_validation = {"json": True, "schema": schema}
        response = caller.call(
            type=call_type,
            path=path,
            method="POST",
            body=body,
            body_validation=body_validation,
        )
        assert response.status_code == 400
        assert response.json()["Error"]["Code"] == "InvalidPayload"
