import json
import enum
import base64
from dataclasses import dataclass, field as dataclass_field, replace
from collections import defaultdict
from typing import Any, Union, Optional
from unittest.mock import MagicMock

from aws_lambda_api_event_utils.aws_lambda_api_event_utils import (
    FormatVersion,
    EVENT_FORMAT_VERSION_CACHE_KEY,
)


class IntegrationType(enum.Enum):
    """Event format identifiers"""

    APIGW_HTTP_10 = ("API Gateway HTTP 1.0", FormatVersion.APIGW_10)
    APIGW_REST = ("API Gateway REST", FormatVersion.APIGW_10)
    APIGW_HTTP_20 = ("API Gateway HTTP 2.0", FormatVersion.APIGW_20)
    # ALB_10 = "ALB 1.0"

    def __init__(self, description, format_version) -> None:
        self.description = description
        self.format_version = format_version

    def event_with_version(self, *args):
        """For setting the version on test events that don't match the full format spec."""
        event = {}
        for arg in args:
            if arg:
                event.update(arg)
        event[EVENT_FORMAT_VERSION_CACHE_KEY] = self.format_version.name
        return event


def create_context():
    context = MagicMock()
    del context.api_response_headers
    del context.api_response_cookies
    return context


def _merge_dicts(a: dict, b: dict, path: str = "") -> dict:
    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                _merge_dicts(a[key], b[key], f"{path}.{key}")
            elif a[key] == b[key]:
                pass  # same leaf value
            else:
                raise Exception(f"Conflict at {path}.{key}: {a[key]} {b[key]}")
        else:
            a[key] = b[key]
    return a


@dataclass
class Path:
    stage: str
    path: str
    resource: str
    path_parameters: dict = None

    route_method: str = None

    def _get_path_data(self, integration_type: IntegrationType) -> dict:
        path_with_stage = f"/{self.stage}{self.path}"
        path_data = {}
        if integration_type in [
            IntegrationType.APIGW_HTTP_10,
            IntegrationType.APIGW_REST,
        ]:
            path_data["requestContext"] = {}

            path_data["requestContext"]["stage"] = self.stage

            path_data["resource"] = self.resource
            path_data["requestContext"]["resourcePath"] = self.resource

            path_data["path"] = path_with_stage
            path_data["requestContext"]["path"] = path_with_stage

            path_data["pathParameters"] = self.path_parameters
        elif integration_type == IntegrationType.APIGW_HTTP_20:
            path_data["requestContext"] = {"http": {}}

            path_data["requestContext"]["stage"] = self.stage

            # resource

            path_data["rawPath"] = path_with_stage
            path_data["requestContext"]["http"]["path"] = path_with_stage

            if self.path_parameters:
                path_data["pathParameters"] = self.path_parameters

        return path_data


@dataclass
class Body:
    value: str
    is_base64_encoded: bool

    @classmethod
    def from_str(cls, s: str):
        return cls(s, False)

    @classmethod
    def from_bytes(cls, b: str):
        return cls(str(base64.b64encode(b), "ascii"), True)

    @classmethod
    def empty(cls):
        return cls(None, False)

    def _get_body_data(self, integration_type: IntegrationType) -> dict:
        body_data = {}
        if integration_type in [
            IntegrationType.APIGW_HTTP_10,
            IntegrationType.APIGW_REST,
        ]:
            body_data["body"] = self.value
            body_data["isBase64Encoded"] = self.is_base64_encoded
        elif integration_type == IntegrationType.APIGW_HTTP_20:
            if self.value:
                body_data["body"] = self.value
            body_data["isBase64Encoded"] = self.is_base64_encoded
        return body_data


@dataclass
class Event:
    integration_type: IntegrationType
    method: str
    path: Path
    headers: dict = None
    content_type: str = None
    query_params: dict = None
    body: Union[str, bytes, Body] = None

    def to_string(self):
        return json.dumps(self.get_event(), indent=2)

    def with_(
        self,
        integration_type: IntegrationType = None,
        method: str = None,
        path: Path = None,
        headers: dict = None,
        content_type: str = None,
        query_params: dict = None,
        body: Union[str, bytes, Body] = None,
    ):
        kwargs = {}
        for field in [
            "integration_type",
            "method",
            "path",
            "headers",
            "content_type",
            "query_params",
            "body",
        ]:
            if locals()[field] is not None:
                kwargs[field] = locals()[field]
        return replace(self, **kwargs)

    def get_event(self) -> dict:
        event = {}
        for method in [
            self._get_integration_type_data,
            self._get_method_data,
            self._get_headers_data,
            self._get_query_params_data,
        ]:
            data = method()
            _merge_dicts(event, data)

        if self.path is None:
            raise ValueError("path not set")
        if not isinstance(self.path, Path):
            raise TypeError("Path must be path")

        data = self.path._get_path_data(self.integration_type)
        _merge_dicts(event, data)

        body = self.body
        if not body:
            body = Body.empty()
        else:
            if isinstance(body, str):
                body = Body.from_str(body)
            elif isinstance(body, bytes):
                body = Body.from_bytes(body)
            elif not isinstance(body, Body):
                raise TypeError(f"unknown body type {type(body)}")
        data = body._get_body_data(self.integration_type)
        _merge_dicts(event, data)
        return event

    def _get_integration_type_data(self) -> dict:
        if self.integration_type is None:
            raise ValueError("integration_type not set")
        data = {}
        if self.integration_type == IntegrationType.APIGW_REST:
            pass
        elif self.integration_type == IntegrationType.APIGW_HTTP_10:
            data["version"] = "1.0"
        elif self.integration_type == IntegrationType.APIGW_HTTP_20:
            data["version"] = "2.0"
        else:
            raise ValueError(self.integration_type)
        return data

    def _get_method_data(self) -> dict:
        if self.method is None:
            raise ValueError("method not set")
        method_data = {}
        if self.integration_type in [
            IntegrationType.APIGW_HTTP_10,
            IntegrationType.APIGW_REST,
        ]:
            method_data["httpMethod"] = self.method
            method_data["requestContext"] = {"httpMethod": self.method}
        elif self.integration_type == IntegrationType.APIGW_HTTP_20:
            method_data["requestContext"] = {"http": {"method": self.method}}
        else:
            raise ValueError(self.integration_type)
        return method_data

    def _get_headers_data(self) -> dict:
        headers_data = {}
        if self.integration_type in [
            IntegrationType.APIGW_HTTP_10,
            IntegrationType.APIGW_REST,
        ]:
            headers_data["headers"] = {}
            headers_data["multiValueHeaders"] = {}
        elif self.integration_type == IntegrationType.APIGW_HTTP_20:
            headers_data["headers"] = {}
        else:
            raise ValueError(self.integration_type)

        if self.headers:
            for key, value in self.headers.items():
                if self.integration_type in [
                    IntegrationType.APIGW_HTTP_10,
                    IntegrationType.APIGW_REST,
                ]:
                    if not isinstance(value, str):
                        headers_data["headers"][key] = value[-1]
                        headers_data["multiValueHeaders"][key] = value
                    else:
                        headers_data["headers"][key] = value
                        headers_data["multiValueHeaders"][key] = [value]
                elif self.integration_type == IntegrationType.APIGW_HTTP_20:
                    if not isinstance(value, str):
                        headers_data["headers"][key] = ",".join(value)
                    else:
                        headers_data["headers"][key] = value
                else:
                    raise ValueError(self.integration_type)

        if self.content_type:
            if self.integration_type in [
                IntegrationType.APIGW_HTTP_10,
                IntegrationType.APIGW_REST,
            ]:
                headers_data["headers"]["content-type"] = self.content_type
                headers_data["multiValueHeaders"]["content-type"] = [self.content_type]
            elif self.integration_type == IntegrationType.APIGW_HTTP_20:
                headers_data["headers"]["content-type"] = self.content_type
            else:
                raise ValueError(self.integration_type)

        return headers_data

    def _get_query_params_data(self) -> dict:
        query_params_data = {}
        if self.integration_type in [
            IntegrationType.APIGW_HTTP_10,
            IntegrationType.APIGW_REST,
        ]:
            query_params_data["queryStringParameters"] = {}
            query_params_data["multiValueQueryStringParameters"] = {}
        elif self.integration_type == IntegrationType.APIGW_HTTP_20:
            query_params_data["rawQueryString"] = ""

        else:
            raise ValueError(self.integration_type)

        if self.query_params:
            raw_params_data = []
            if self.integration_type == IntegrationType.APIGW_HTTP_20:
                query_params_data["queryStringParameters"] = {}
            for key, value in self.query_params.items():
                if self.integration_type in [
                    IntegrationType.APIGW_HTTP_10,
                    IntegrationType.APIGW_REST,
                ]:
                    if not isinstance(value, str):
                        query_params_data["queryStringParameters"][key] = value[0]
                        query_params_data["multiValueQueryStringParameters"][
                            key
                        ] = value
                    else:
                        query_params_data["queryStringParameters"][key] = value
                        query_params_data["multiValueQueryStringParameters"][key] = [
                            value
                        ]
                elif self.integration_type == IntegrationType.APIGW_HTTP_20:
                    if not isinstance(value, str):
                        raw_params_data.extend((key, v) for v in value)
                        query_params_data["queryStringParameters"][key] = ",".join(
                            value
                        )
                    else:
                        raw_params_data.append((key, value))
                        query_params_data["queryStringParameters"][key] = value
                else:
                    raise ValueError(self.integration_type)
            if self.integration_type == IntegrationType.APIGW_HTTP_20:
                query_params_data["rawQueryString"] = "&".join(
                    f"{k}={v}" for k, v in raw_params_data
                )

        return query_params_data
