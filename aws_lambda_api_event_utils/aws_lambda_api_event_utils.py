# Copyright 2022 Ben Kehoe
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

__version__ = "0.4.0"  # update here and pyproject.toml

__all__ = (
    "api_event_handler",
    "append_header",
    "append_headers",
    "BodyType",
    "CompiledFastJSONSchema",
    "CORSConfig",
    "DatetimeSerializationConfig",
    "APIErrorResponse",
    "EVENT_FORMAT_VERSION_CACHE_KEY",
    "FormatVersion",
    "get_body",
    "get_default_json_serialization_config",
    "get_event_format_version",
    "get_json_body",
    "InvalidRequestError",
    "json_body",
    "JSONSerializationConfig",
    "make_redirect",
    "make_response",
    "PayloadBinaryTypeError",
    "PayloadJSONDecodeError",
    "PayloadSchemaViolationError",
    "set_default_json_serialization_config",
    "set_header",
    "set_headers",
)

import base64
import json
import functools
import logging
import enum
import sys
import datetime
import decimal
import re
import traceback
import http
from dataclasses import dataclass, field as dataclass_field
from typing import (
    Dict,
    Iterable,
    List,
    Union,
    Optional,
    Any,
    Callable,
    Tuple,
    Type,
    NoReturn,
    ClassVar,
    Callable,
    cast,
)

ApiEventType = Dict[str, Any]
ApiResponseType = Dict[str, Any]

LaxHeadersType = Dict[str, Any]  # Dict[str, Union[str, List[str]]]
StrictHeadersType = Dict[str, str]

EVENT_FORMAT_VERSION_CACHE_KEY = "__event_format_version__"


class FormatVersion(enum.Enum):
    """Event format identifiers"""

    APIGW_10 = "API Gateway HTTP 1.0 and REST"
    APIGW_20 = "API Gateway HTTP 2.0"


@dataclass
class _FormatVersionData:
    version: Optional[Tuple]
    keys: Tuple


_API_GW_10_DATA = _FormatVersionData(
    version=("version", "1.0"),
    keys=(
        "httpMethod",
        "path",
        "pathParameters",
        "headers",
        "multiValueHeaders",
        "queryStringParameters",
        "multiValueQueryStringParameters",
        "body",
        "isBase64Encoded",
    ),
)

# REST APIs don't include a version number
_API_GW_10_REST_DATA = _FormatVersionData(
    version=None,
    keys=(
        "httpMethod",
        "path",
        "pathParameters",
        "headers",
        "multiValueHeaders",
        "queryStringParameters",
        "multiValueQueryStringParameters",
        "body",
        "isBase64Encoded",
    ),
)

_API_GW_20_DATA = _FormatVersionData(
    version=("version", "2.0"),
    keys=(
        ("requestContext", "http", "method"),
        "rawPath",
        # "pathParameters", # may be missing
        "headers",
        # "queryStringParameters", # may be missing
        "rawQueryString",
        # "body", # may be missing
        "isBase64Encoded",
    ),
)


def _get_key(d: Dict, key: Union[str, Iterable[str]]):
    if isinstance(key, str):
        return key in d, d.get(key)
    value = d
    for k in key:
        if k not in value:
            return False, None
        value = value[k]
    return True, value


def _event_matches_format_version(
    event: ApiEventType, format_version_data: _FormatVersionData
):
    if format_version_data.version:
        version_key, version_value = format_version_data.version
        if event.get(version_key) != version_value:
            return False
    for key in format_version_data.keys:
        in_event, _ = _get_key(event, key)
        if not in_event:
            return False
    return True


def get_event_format_version(
    event: ApiEventType, disable_cache: bool = False
) -> Optional[FormatVersion]:
    """Get the format version from the event.

    By default, the format version is cached within the event under the key from
    the EVENT_FORMAT_VERSION_CACHE_KEY module field.

    Args:
        event (dict): The input event for the Lambda function.
        disable_cache (bool): Set to True to leave the event unmodified.

    Returns: The event format version.
    """
    if EVENT_FORMAT_VERSION_CACHE_KEY in event:
        format_version = event[EVENT_FORMAT_VERSION_CACHE_KEY]
        cast(str, format_version)
        return FormatVersion[format_version]  # type: ignore
    event_format_version = None

    if _event_matches_format_version(event, _API_GW_10_DATA):
        event_format_version = FormatVersion.APIGW_10
    elif _event_matches_format_version(event, _API_GW_20_DATA):
        event_format_version = FormatVersion.APIGW_20
    elif _event_matches_format_version(event, _API_GW_10_REST_DATA):
        event_format_version = FormatVersion.APIGW_10

    if event_format_version and not disable_cache:
        event[EVENT_FORMAT_VERSION_CACHE_KEY] = event_format_version.name
    return event_format_version


@dataclass(frozen=True)
class DatetimeSerializationConfig:
    """Options for serializing classes from the datetime package.

    When use_z_format is True (the default), when a UTC datetime or time
    is serialized, if the string ends in "+00:00" it will be replaced with
    "Z"

    The sep and timespec fields allow these arguments to the isoformat() methods
    to be specified.
    """

    use_z_format: bool = True
    sep: Optional[str] = None
    timespec: Optional[str] = None


@dataclass(frozen=True)
class JSONSerializationConfig:
    """Options for serializing classes to JSON.

    The datetime field can be set to True to use the default (serialize
    classes from the datetime package, update datetime and time strings to
    use the "Z" timezone designator for UTC), None or False to disable
    serializing any of these classes, or a DatetimeSerializationConfig object.

    The decimal_type field should be float or str, or None to disable
    serialization of decimal.Decimal objects.
    """

    datetime: Optional[DatetimeSerializationConfig]
    decimal_type: Union[None, Type[float], Type[str]]

    def __post_init__(self):
        if self.datetime is True:
            object.__setattr__(self, "datetime", DatetimeSerializationConfig())
        elif self.datetime is False:
            object.__setattr__(self, "datetime", None)


_DEFAULT_JSON_SERIALIZATION_CONFIG: Optional[
    JSONSerializationConfig
] = JSONSerializationConfig(datetime=DatetimeSerializationConfig(), decimal_type=float)


def set_default_json_serialization_config(config: Optional[JSONSerializationConfig]):
    """Set the default JSON serialization config."""
    global _DEFAULT_JSON_SERIALIZATION_CONFIG
    _DEFAULT_JSON_SERIALIZATION_CONFIG = config


def get_default_json_serialization_config() -> Optional[JSONSerializationConfig]:
    """Get the default JSON serialization config.

    Initializes to serializing classes from the datetime package, including
    updating datetime and time strings to use the "Z" timezone designator for UTC,
    and serializing decimal.Decimal as float.
    """
    global _DEFAULT_JSON_SERIALIZATION_CONFIG
    return _DEFAULT_JSON_SERIALIZATION_CONFIG


def _json_dump_default(obj: Any, config: JSONSerializationConfig):
    if (
        isinstance(obj, (datetime.datetime, datetime.date, datetime.time))
        and config.datetime
    ):
        cast(DatetimeSerializationConfig, config.datetime)
        kwargs = {}
        if (
            isinstance(obj, (datetime.datetime, datetime.time))
            and config.datetime.timespec is not None
        ):
            kwargs["timespec"] = config.datetime.timespec
        if isinstance(obj, datetime.datetime) and config.datetime.sep is not None:
            kwargs["sep"] = config.datetime.sep

        value = obj.isoformat(**kwargs)

        if config.datetime.use_z_format:
            value = re.sub(r"\+00(:?00)?$", "Z", value)

        return value
    if isinstance(obj, decimal.Decimal) and config.decimal_type:
        return config.decimal_type(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


def _json_dump(data: Any, config: Optional[JSONSerializationConfig]):
    dump_kwargs = {}
    if config is not None:
        dump_kwargs["default"] = lambda obj: _json_dump_default(
            obj, cast(JSONSerializationConfig, config)
        )
    return json.dumps(data, **dump_kwargs)  # type: ignore


@dataclass(frozen=True)
class CORSConfig:
    """CORSConfig configuration."""

    CONTENT_TYPE: ClassVar[List[str]] = ["Content-Type", "Accept"]
    AUTHORIZATION: ClassVar[List[str]] = ["Authorization"]
    SIGV4: ClassVar[List[str]] = [
        "Authorization",
        "Content-Type",
        "X-Amz-Date",
        "X-Amz-Security-Token",
    ]
    API_KEY: ClassVar[List[str]] = ["X-Api-Key"]

    @classmethod
    def is_preflight_request(cls, event: ApiEventType) -> bool:
        if _get_method(event) != "OPTIONS":
            return False
        for header in _get_headers(event):
            if header.lower() == "access-control-request-method":
                return True
        return False

    allow_origin: str
    allow_methods: Union[str, List[str], Tuple[str, ...]]
    allow_headers: Union[None, str, List[str], Tuple[str, ...]] = None
    expose_headers: Union[None, str, List[str], Tuple[str, ...]] = None
    max_age: Union[None, int, datetime.timedelta] = None
    allow_credentials: bool = False

    _preflight_headers: Dict[str, str] = dataclass_field(init=False)
    _headers: Dict[str, str] = dataclass_field(init=False)

    def _update_methods(self):
        if isinstance(self.allow_methods, str):
            allow_methods = [self.allow_methods]
        else:
            allow_methods = self.allow_methods
        if "*" in allow_methods:
            allow_methods = ("*",)
        elif "OPTIONS" not in allow_methods:
            allow_methods = ["OPTIONS", *allow_methods]
        object.__setattr__(self, "allow_methods", tuple(allow_methods))

    def _update_header_field(self, field_name: str):
        headers = getattr(self, field_name)
        if not headers:
            return
        if isinstance(headers, str):
            object.__setattr__(self, field_name, (headers,))
            return
        names = set()
        filtered = []
        for name in headers:
            if name == "*":
                object.__setattr__(self, field_name, ("*",))
                return
            if name.lower() in names:
                continue
            filtered.append(name)
            names.add(name.lower())
        object.__setattr__(self, field_name, tuple(filtered))

    def _get_preflight_headers(self) -> Dict[str, str]:
        headers = {
            "Access-Control-Allow-Origin": self.allow_origin,
            "Access-Control-Allow-Methods": ", ".join(self.allow_methods),
        }
        if self.allow_headers:
            headers["Access-Control-Allow-Headers"] = ", ".join(self.allow_headers)
        if self.max_age is not None:
            headers["Access-Control-Max-Age"] = str(int(self.max_age.total_seconds()))  # type: ignore
        if self.allow_credentials is True:
            headers["Access-Control-Allow-Credentials"] = "true"
        return headers

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Access-Control-Allow-Origin": self.allow_origin,
        }
        if self.expose_headers:
            headers["Access-Control-Expose-Headers"] = ", ".join(self.expose_headers)
        if self.allow_credentials is True:
            headers["Access-Control-Allow-Credentials"] = "true"
        return headers

    def __post_init__(self):
        self._update_methods()

        self._update_header_field("allow_headers")

        self._update_header_field("expose_headers")

        if isinstance(self.max_age, int):
            object.__setattr__(
                self, "max_age", datetime.timedelta(seconds=self.max_age)
            )

        object.__setattr__(self, "_preflight_headers", self._get_preflight_headers())
        object.__setattr__(self, "_headers", self._get_headers())

    def make_preflight_response(
        self,
        *,
        format_version: Union[FormatVersion, ApiEventType],
    ) -> ApiResponseType:
        """Generate a preflight CORSConfig response."""

        return make_response(
            204,
            body=None,
            headers=self._preflight_headers,
            format_version=format_version,
        )

    def get_headers(self) -> Dict[str, str]:
        """Get the configured CORSConfig headers."""
        return self._headers


def make_response(
    status_code: Union[int, http.HTTPStatus],
    body: Optional[Any],
    *,
    format_version: Union[FormatVersion, ApiEventType],
    headers: Optional[LaxHeadersType] = None,
    cookies: Optional[List[str]] = None,
    cors_config: Optional[CORSConfig] = None,
    json_serialization_config: Optional[JSONSerializationConfig] = None,
) -> ApiResponseType:
    """Create a response to return from the Lambda function.

    This function requires an event format version; this can be provided
    either directly or as as the input event for the Lambda function to
    extract the format version from.

    Args:
        status_code (int): The status code to use for the response.
        body: The response body as a string, bytes, or JSON-serializable object.
        format_version: The event format version to use for the response, or the
            input event for the Lambda function to extract the format version from.
        headers (dict): The headers, with each value as either a string
            or as a list of strings.
        cookies (list): Cookies to include in the response, which may not be
            supported by all event format versions.
        json_serialization_config (JSONSerializationConfig): Override the default
            JSON serialization settings

    Returns: A dict suitable for returning from the Lambda function.
    """
    if isinstance(status_code, http.HTTPStatus):
        status_code = status_code.value

    if not isinstance(format_version, FormatVersion):
        format_version: Optional[FormatVersion] = get_event_format_version(format_version)  # type: ignore

    if format_version is None:
        raise TypeError("Unknown format version")
    if format_version not in [FormatVersion.APIGW_10, FormatVersion.APIGW_20]:
        raise NotImplementedError(f"Unknown format version {format_version}")

    if cookies is not None and format_version in [FormatVersion.APIGW_10]:
        # TODO: insert into headers?
        raise TypeError(f"Cookies are not supported in format version {format_version}")

    response: Dict[str, Any] = {"statusCode": status_code}

    if body is None:
        response["body"] = ""
    else:
        default_content_type = None
        if isinstance(body, bytes):
            body = str(base64.b64encode(body), "ascii")
            is_base64_encoded = True
            default_content_type = "application/octet-stream"
        elif isinstance(body, str):
            is_base64_encoded = False
            default_content_type = "text/plain"
        else:
            if json_serialization_config is None:
                json_serialization_config = get_default_json_serialization_config()
            body = _json_dump(body, json_serialization_config)
            is_base64_encoded = False
            default_content_type = "application/json"

        if default_content_type:
            headers = _add_single_header(headers, "Content-Type", default_content_type)

        if cors_config:
            headers = _add_headers(headers, cors_config.get_headers())

        response.update(
            {
                "body": body,
                "isBase64Encoded": is_base64_encoded,
            }
        )

    if cookies is not None:
        response["cookies"] = cookies

    if headers is not None:
        if all(isinstance(v, str) for v in headers.values()):
            response["headers"] = headers
        else:
            if format_version == FormatVersion.APIGW_10:
                headers_key = "multiValueHeaders"
                format_str = lambda s: [s]
                format_list = lambda l: l
            else:
                headers_key = "headers"
                format_str = lambda s: s
                format_list = lambda l: ",".join(l)
            response[headers_key] = {}
            for key, value in headers.items():
                if isinstance(value, str):
                    value = format_str(value)
                else:
                    value = format_list(value)
                response[headers_key][key] = value

    return response


def make_redirect(
    status_code: Union[int, http.HTTPStatus],
    url: str,
    *,
    format_version: Union[FormatVersion, ApiEventType],
    headers: Optional[LaxHeadersType] = None,
    cookies: Optional[List[str]] = None,
    cors_config: Optional[CORSConfig] = None,
) -> ApiResponseType:
    """Create a response for a 3XX redirect to return from the Lambda function.

    This function requires an event format version; this can be provided
    either directly or as as the input event for the Lambda function to
    extract the format version from.

    Args:
        status_code (int): The status code to use for the response.
        url (str): The redirect URL, for the Location header.
        format_version (str): The event format version to use for the response,
            or the input event for the Lambda function to extract
            the format version from.
        headers (dict): The headers, with each value as either a string
            or as a list of strings. The Location header will be added to it.
        cookies (list): Cookies to include in the response, which may not be
            supported by all event format versions.

    Returns: A dict suitable for returning from the Lambda function.
    """
    if status_code // 100 != 3:
        raise ValueError(f"Status code {status_code} is not 3XX")
    if headers is None:
        headers = {}
    else:
        headers = {k: v for k, v in headers.items() if k.lower() != "location"}
    headers["location"] = url
    return make_response(
        status_code,
        body=None,
        headers=headers,
        cookies=cookies,
        cors_config=cors_config,
        format_version=format_version,
    )


def api_event_handler(format_version: FormatVersion = None):
    """Process handler responses and catch APIErrorResponse exceptions.

    The return value of the handler is used if it is a dict containing
    a "statusCode" key, otherwise the return value is used as the "body"
    argument to make_response() with a status code of 200.

    APIErrorResponse exceptions are logged and the output of the get_response() method
    is returned from the handler.

    Logging uses logger or callable set in APIErrorResponse.DECORATOR_LOGGER,
    if one has been provided. The log level is ERROR, and the log message
    includes the error code and internal message.
    A traceback will be included if APIErrorResponse.DECORATOR_LOGGER_TRACEBACK
    is set to True.

    This decorator does not validate that the incoming event is in the given
    format version; use the event_format_version decorator for that.
    """
    func = None
    if callable(format_version):
        func = format_version
        format_version = None

    decorator = _get_decorator(
        lambda event: None, response_format_version=format_version
    )

    # deal with bare decorator
    if func:
        return decorator(func)
    else:
        return decorator


class APIErrorResponse(Exception):
    """An exception that can be turned into a Lambda function response.

    The main method for an APIErrorResponse exception is the get_response() method,
    which returns the response as a dict suitable for returning from the Lambda
    function. Additionally, a response can be created directly from any Exception
    using the make_response_from_exception() class method.

    You may catch APIErrorResponse directly, log it and any other desired actions, and
    return the response from get_response(); alternatively, you can decorate the
    Lambda function handler with APIErrorResponse.decorator, which handles catching,
    logging, and returning. If any of the validation decorators from this module are
    used, they also handle this and APIErrorResponse.decorator is not needed.

    When using decorators, logging is handled through the
    APIErrorResponse.DECORATOR_LOGGER class field, which can be set to either a
    logging.Logger or a callable. To include a traceback, set
    APIErrorResponse.DECORATOR_LOGGER_TRACEBACK=True.

    By default, the body of the response is the following:
    {
        "Error": {
            "Code": cls.ERROR_CODE,
            "Message": cls.ERROR_MESSAGE/cls.ERROR_MESSAGE_TEMPLATE
        }
    }
    This body is constructed with the make_error_body() class method, using
    the get_error_code() and get_error_message() instance methods; see the
    documentation for those methods for details on customization.

    Only subclasses may be instantiated. A subclass MUST set the STATUS_CODE
    class field. It MAY set the ERROR_CODE, ERROR_MESSAGE, or ERROR_MESSAGE_TEMPLATE
    class fields, or the various instance methods used to construct the response.

    A subclass MUST provide an internal_message to the superclass constructor, which
    is intended to be used for logging.

    A subclass SHOULD accept **kwargs for its constructor in addition to whatever
    subclass-specific arguments it has, and it SHOULD allow for the internal_message
    to be provided through these kwargs, and it SHOULD pass these kwargs to the
    superclass constructor, where they are stored in the kwargs instance field.
    """

    STATUS_CODE: Union[int, http.HTTPStatus] = NotImplemented

    ERROR_CODE: str = NotImplemented
    ERROR_MESSAGE: str = NotImplemented
    ERROR_MESSAGE_TEMPLATE: str = NotImplemented

    DECORATOR_LOGGER: Union[None, logging.Logger, Callable] = None
    DECORATOR_LOGGER_TRACEBACK: bool = False

    ERROR_PARENT_FIELD: str = "Error"
    ERROR_CODE_FIELD: str = "Code"
    ERROR_MESSAGE_FIELD: str = "Message"

    @classmethod
    def _get_subclass(
        cls,
        *,
        class_name: str,
        status_code: Union[int, http.HTTPStatus],
        error_code: str,
        error_message: str,
        internal_message: str,
    ):
        error_cls = type(
            class_name,
            (APIErrorResponse,),
            {
                "STATUS_CODE": status_code,
                "ERROR_CODE": error_code,
                "ERROR_MESSAGE": error_message,
                "__init__": lambda self: APIErrorResponse.__init__(
                    self, internal_message
                ),
            },
        )
        return error_cls

    @classmethod
    def from_status_code(
        cls,
        status_code: Union[int, http.HTTPStatus],
        *,
        error_message: Optional[str] = None,
        internal_message: Optional[str] = None,
    ) -> "APIErrorResponse":
        """Create an APIErrorResponse exception instance based on the HTTP status code."""
        status_code = http.HTTPStatus(status_code)
        if status_code.value // 100 not in [4, 5]:
            raise ValueError(f"Status code {status_code.value} is not 4XX or 5XX.")

        if status_code == 400:
            if not error_message:
                error_message = "Invalid request."
            return InvalidRequestError(
                error_message=error_message, internal_message=internal_message
            )

        error_code = status_code.phrase.replace(" ", "")
        if error_message is None:
            error_message = f"{status_code.description}."

        if internal_message is None:
            internal_message = f"{error_code}: {error_message}"

        error_class = cls._get_subclass(
            class_name=error_code,
            status_code=status_code,
            error_code=error_code,
            error_message=error_message,
            internal_message=internal_message,
        )
        error_instance = error_class()
        return error_instance

    @classmethod
    def from_exception(
        cls,
        status_code: Union[int, http.HTTPStatus],
        exc: Exception,
        *,
        internal_message: Optional[str] = None,
    ) -> "APIErrorResponse":
        """Create an APIErrorResponse from the given exception.

        This method creates an APIErrorResponse subclass
        with the given status code, the error code set to the exception class name,
        and the error message set to the stringified exception.
        If internal_message is not provided, it is set to a string containing
        the error code and error message.

        If the provided exception is an APIErrorResponse subclass,
        it will be returned as-is
        """
        if isinstance(exc, cls):
            if exc.STATUS_CODE != status_code:
                raise ValueError(
                    f"Status code mismatch: {exc.STATUS_CODE} {status_code}"
                )
            return exc

        error_code = type(exc).__name__
        error_message = str(exc)

        if internal_message is None:
            internal_message = f"{error_code}: {error_message}"
        error_class = cls._get_subclass(
            class_name="AnonymousAPIErrorResponse",
            status_code=status_code,
            error_code=error_code,
            error_message=error_message,
            internal_message=internal_message,
        )
        error_instance = error_class()
        return error_instance

    @classmethod
    def make_error_body(cls, code: str, message: str) -> Dict[str, Any]:
        """Make a response body based on the code and message.

        The result is a dict containing the error code under
        APIErrorResponse.ERROR_CODE_FIELD and the error message under
        APIErrorResponse.ERROR_MESSAGE_FIELD, nested in an outer dict under
        APIErrorResponse.ERROR_PARENT_FIELD, unless that is set to None, in which case
        there is no nesting.

        Args:
            code (str): The error code
            message (str): The error message

        Returns: The response body as a dict.
        """
        body: Dict[str, Any] = {}
        error_dict = body
        if cls.ERROR_PARENT_FIELD:
            error_dict = {}
            body[cls.ERROR_PARENT_FIELD] = error_dict
        error_dict[cls.ERROR_CODE_FIELD] = code
        error_dict[cls.ERROR_MESSAGE_FIELD] = message
        return body

    def __init__(self, internal_message: str, **kwargs) -> None:
        """Args:
        internal_message: A message intended for logging.
        **kwargs: Additional data that will be stored in the kwarg attribute.
        """
        if self.STATUS_CODE is NotImplemented:
            raise NotImplementedError("STATUS_CODE must be set")
        self.internal_message = internal_message
        self.kwargs = kwargs

    def __str__(self) -> str:
        return f"{self.get_error_code()}: {self.internal_message}"

    def __repr__(self) -> str:
        kwargs = vars(self).copy()
        kwargs.pop("kwargs")
        kwargs.update(self.kwargs)
        parts = []
        for key, value in kwargs.items():
            parts.append(f"{key}={value!r}")
        return f"{self.__class__.__name__}({', '.join(parts)})"

    def get_error_code(self) -> str:
        """Get the error code for this exception.

        Returns the ERROR_CODE class field if it is set by the subclass,
        falling back to the class name if it is not.

        Override this in a subclass to implement custom error code logic.
        """
        if self.ERROR_CODE is NotImplemented:
            return self.__class__.__name__
        else:
            return self.ERROR_CODE

    def get_error_message(self) -> str:
        """Get the error message for this exception.

        If a keyword argument named error_message was passed to the APIErrorResponse
        constructor, this is returned. Otherwise it uses class fields.
        Returns the ERROR_MESSAGE class field if it is set by the subclass.
        If it is not, it falls back to the ERROR_MESSAGE_TEMPLATE class field,
        calling the string format() method on it with the exception's instance fields
        as input. If ERROR_MESSAGE_TEMPLATE is also not set, a generic error message
        will be returned.
        """
        if "error_message" in self.kwargs:
            return self.kwargs["error_message"]
        if self.ERROR_MESSAGE is not NotImplemented:
            return self.ERROR_MESSAGE
        if self.ERROR_MESSAGE_TEMPLATE is not NotImplemented:
            template_args = {}
            # add kwargs provided to constructor
            template_args.update(self.kwargs)
            # instance fields should overwrite anything in self.kwargs
            template_args.update(vars(self))
            # remove self.kwargs field
            template_args.pop("kwargs")
            return self.ERROR_MESSAGE_TEMPLATE.format(**template_args)
        return "An error occurred."

    def get_body(self, body: Optional[Any] = None) -> Any:
        """Get the response body for this exception.

        If a body is provided as input, it will be used (this is the behavior
        when a body is provided to get_response()). Otherwise, the body will be
        constructed using the make_error_body() method with get_error_code()
        and get_error_message() as inputs.

        Args:
            body: A string, bytes, or JSON-serializable type.

        Returns: The response body for this exception.
        """
        if body is not None:
            return body
        error_code = self.get_error_code()
        error_message = self.get_error_message()
        return self.make_error_body(error_code, error_message)

    def get_headers(
        self, headers: Optional[LaxHeadersType] = None
    ) -> Optional[LaxHeadersType]:
        """Get the response headers for this exception.

        If headers are provided as input, it will be used (this is the behavior
        when headers are provided to get_response()). Otherwise, returns None.

        Args:
            headers (dict): Headers, the values of which can be a string or
                a list of strings.

        Returns: An optional dictionary of headers, the values of which can be
            a string or a list of strings.
        """
        if headers is not None:
            return headers
        return None

    def get_default_headers(self) -> LaxHeadersType:
        """Get default response headers for this exception.

        These headers will be added to the response headers unless they already
        exist in the headers from get_headers(). This provides a convenient way
        for subclasses to add default headers to the response.

        Returns: A dictionary of headers, the values of which can be
            a string or a list of strings.
        """
        return {}

    def get_cookies(self, cookies: Optional[List[str]] = None) -> Optional[List[str]]:
        """Get the cookies for this exception.

        If cookies are provided as input, it will be used (this is the behavior
        when cookies are provided to get_response()). Otherwise, returns None

        Args:
            cookies (list): An optional list of strings.

        Returns: A list of strings.
        """
        if cookies is not None:
            return cookies
        return None

    def get_response(
        self,
        *,
        format_version: Union[FormatVersion, ApiEventType],
        body: Optional[Any] = None,
        headers: Optional[LaxHeadersType] = None,
        cookies: Optional[List[str]] = None,
        json_serialization_config: Optional[JSONSerializationConfig] = None,
        cors_config: Optional[CORSConfig] = None,
    ) -> ApiResponseType:
        """Get the response for this exception.

        This method requires an event format version; this can be provided
        either directly or as as the input event for the Lambda function to
        extract the format version from.

        Args:
            format_version: The event format version to use for the response, or the
                input event for the Lambda function to extract the format version from.
            body: A response body to use instead of the default get_body() method.
            headers (dict): Headers to use instead of the default get_headers() method.
            cookies (list): Cookies to use instead of the default get_cookies() method.
                Cookies may not be supported by all event format versions.

        Returns: A dict suitable for returning from the Lambda function.
        """
        body = self.get_body(body)

        headers = self.get_headers(headers)
        default_headers = self.get_default_headers()
        if default_headers:
            headers = _add_headers(headers, default_headers)

        cookies = self.get_cookies(cookies)

        return make_response(
            status_code=self.STATUS_CODE,
            body=body,
            headers=headers,
            cookies=cookies,
            cors_config=cors_config,
            json_serialization_config=json_serialization_config,
            format_version=format_version,
        )

    def _decorator_log(self):
        if self.DECORATOR_LOGGER:
            message = str(self)
            if isinstance(self.DECORATOR_LOGGER, logging.Logger):
                self.DECORATOR_LOGGER.error(
                    message, exc_info=self.DECORATOR_LOGGER_TRACEBACK
                )
            else:
                if self.DECORATOR_LOGGER_TRACEBACK:
                    tb = traceback.format_exc()
                    self.DECORATOR_LOGGER(tb)
                self.DECORATOR_LOGGER(message)


class InvalidRequestError(APIErrorResponse):
    """APIErrorResponse for a generic client error.

    The error code and message will be returned to the client,
    and the internal message is used for logging.
    """

    STATUS_CODE = 400
    ERROR_CODE = "InvalidRequest"

    def __init__(
        self,
        error_message: str,
        *,
        internal_message: Optional[str] = None,
        error_code: str = "InvalidRequest",
        **kwargs,
    ) -> None:
        self._error_code = error_code
        self._error_message = error_message
        if internal_message is None:
            internal_message = f"{error_code}: {error_message}"
        super().__init__(internal_message, **kwargs)

    def get_error_code(self) -> str:
        return self._error_code

    def get_error_message(self) -> str:
        return self._error_message


def _process_function_result(
    result: Any,
    *,
    headers: Optional[LaxHeadersType],
    cookies: Optional[List[str]],
    cors_config: Optional[CORSConfig],
    format_version: FormatVersion,
) -> ApiResponseType:
    """Transform non-response results into responses"""
    if isinstance(result, dict) and "statusCode" in result:
        return result
    if not isinstance(format_version, FormatVersion):
        format_version = get_event_format_version(format_version)
    if format_version not in [FormatVersion.APIGW_10, FormatVersion.APIGW_20]:
        raise NotImplementedError(f"Unknown format version {format_version}")
    return make_response(
        status_code=200,
        body=result,
        headers=headers,
        cookies=cookies,
        cors_config=cors_config,
        format_version=format_version,
    )


@dataclass
class DecoratorApiResponseConfig:
    headers: Optional[LaxHeadersType] = None
    cookies: Optional[List[str]] = None
    cors_config: Optional[CORSConfig] = None


def _set_context_field(context):
    """Attempt to add fields to context object"""
    if not hasattr(context, "api_response"):
        try:
            setattr(context, "api_response", DecoratorApiResponseConfig())
        except:
            pass


def _get_context_field(
    context,
) -> DecoratorApiResponseConfig:
    """Attempt to retrieve fields from context object"""
    return getattr(context, "api_response", None) or DecoratorApiResponseConfig()


def _get_decorator(
    validation_func: Callable,
    response_format_version: Optional[FormatVersion] = None,
    **decorator_kwargs,
):
    def decorator(f):
        @functools.wraps(f)
        def handler_wrapper(
            event,
            context,
            *args,
            _response_format_version=response_format_version,
            **kwargs,
        ):
            # Error out on unknown event format version early
            if _response_format_version is None:
                _response_format_version = get_event_format_version(event)
            try:
                validation_func(event, **decorator_kwargs)
                _set_context_field(context)
                result = f(event, context, *args, **kwargs)
                decorator_response_config = _get_context_field(context)
                return _process_function_result(
                    result,
                    headers=decorator_response_config.headers,
                    cookies=decorator_response_config.cookies,
                    cors_config=decorator_response_config.cors_config,
                    format_version=_response_format_version,
                )
            except APIErrorResponse as e:
                e._decorator_log()
                decorator_response_config = _get_context_field(context)
                return e.get_response(
                    headers=decorator_response_config.headers,
                    cookies=decorator_response_config.cookies,
                    cors_config=decorator_response_config.cors_config,
                    format_version=_response_format_version,
                )

        return handler_wrapper

    return decorator


class PayloadBinaryTypeError(APIErrorResponse):
    """APIErrorResponse for a request body that doesn't match the expected binary status.

    The internal_message describes whether the body is binary or not.
    The response will have status 400, error code InvalidPayload and
    message "The request body is invalid."

    Attributes:
        binary_expected: Whether the body was expected to be binary or not.
    """

    STATUS_CODE = 400

    ERROR_CODE = "InvalidPayload"
    ERROR_MESSAGE = "The request body is invalid."

    def __init__(self, *, binary_expected: bool, **kwargs) -> None:
        self.binary_expected = binary_expected

        if "internal_message" not in kwargs:
            if binary_expected:
                kwargs["internal_message"] = "Body was not binary"
            else:
                kwargs["internal_message"] = "Body was binary"
        super().__init__(**kwargs)


class BodyType(enum.Enum):
    str = "text"
    bytes = "binary"


def get_body(event: ApiEventType, *, type: BodyType = None) -> Union[None, str, bytes]:
    """Retrieve the body from the event, decoding base64-encoded binary bodies.

    Args:
        event (dict): The Lambda function input event.
        type (BodyType): Set to BodyType.bytes to require a binary body.
            Set to BodyType.str to require a text body.

    Returns:
        The body, as a string if the raw body is not base64 encoded, as bytes if
        the raw body is base64-encoded, and as the raw body otherwise (this case
        is likely if something else has already parsed the body). An empty body
        is returned as None regardless.

    Raises:
        PayloadBinaryTypeError: If binary is set and the body doesn't match.
        TypeError: If binary is set and the body is not a stringl
    """
    if type is not None and not isinstance(type, BodyType):
        raise TypeError(f"Invalid type {type}, must be BodyType")
    format_version = get_event_format_version(event)
    if format_version in [FormatVersion.APIGW_10, FormatVersion.APIGW_20]:
        body: Any = event.get("body")
        if body is None:
            if type == BodyType.bytes:
                return b""
            elif type == BodyType.str:
                return ""
            else:
                return None
        elif not isinstance(body, str):  # body has already been parsed by something
            # allow type=BodyType.bytes if body is bytes
            if type is not None and not (
                type == BodyType.bytes and isinstance(body, bytes)
            ):
                raise TypeError("Cannot enforce binary status on parsed body")
        elif event.get("isBase64Encoded"):
            if type == BodyType.str:
                raise PayloadBinaryTypeError(binary_expected=False)
            body = base64.b64decode(body)
        else:
            if type == BodyType.bytes:
                raise PayloadBinaryTypeError(binary_expected=True)
        return body
    else:
        raise NotImplementedError


class PayloadJSONDecodeError(APIErrorResponse):
    """APIErrorResponse for a request body that could not be parsed as JSON.

    The internal_message describes the JSON decoding error.
    The response will have status 400, error code InvalidPayload and
    message "Request body must be valid JSON."

    Attributes:
        binary_expected: Whether the body was expected to be binary or not.
    """

    STATUS_CODE = 400
    ERROR_CODE = "InvalidPayload"
    ERROR_MESSAGE = "Request body must be valid JSON."

    def __init__(
        self, *, json_decode_error: Union[str, json.JSONDecodeError], **kwargs
    ) -> None:
        self.json_decode_error = json_decode_error
        if "internal_message" not in kwargs:
            kwargs[
                "internal_message"
            ] = f"Payload is not valid JSON: {json_decode_error}."
        super().__init__(**kwargs)


class PayloadSchemaViolationError(APIErrorResponse):
    """APIErrorResponse for a JSON request body violates the schema.

    The internal_message describes the JSON schema error.
    The response will have status 400, error code InvalidPayload and
    message from the validation error.

    Attributes:
        schema: The JSON schema.
        validation_error: An error message or exception for the schema error.
    """

    STATUS_CODE = 400
    ERROR_CODE = "InvalidPayload"

    def get_error_message(self) -> str:
        if "error_message" in self.kwargs:
            return self.kwargs["error_message"]
        return self.validation_error_message

    def __init__(
        self,
        *,
        schema: Dict,
        validation_error_message: str,
        validation_error: Union["jsonschema.ValidationError", "fastjsonschema.JsonSchemaException"] = None,  # type: ignore
        **kwargs,
    ) -> None:
        self.schema = schema
        self.validation_error_message = validation_error_message
        self.validation_error = validation_error
        if "internal_message" not in kwargs:
            kwargs[
                "internal_message"
            ] = f"Payload violates schema: {validation_error or validation_error_message}"
        super().__init__(**kwargs)


_VALID_JSON_LOADS_TYPES = (str, bytes, bytearray)


@dataclass(frozen=True)
class CompiledFastJSONSchema:
    """Compiled schema validation for fastjsonschema."""

    schema: Dict
    compiled_validator: Callable = dataclass_field(init=False)

    def __post_init__(self):
        try:
            import fastjsonschema
        except ModuleNotFoundError:
            sys.modules["jsonschema"] = None
            msg = (
                "Compiled schema validation requires the fastjsonschema package. "
                + "Install it separately or install the extra as "
                + "aws-lambda-api-event-utils[fastjsonschema]."
            )
            raise ModuleNotFoundError(msg, name="fastjsonschema")

        compiled_validator = fastjsonschema.compile(self.schema)
        object.__setattr__(self, "compiled_validator", compiled_validator)

    def validate(self, payload: Any):
        import fastjsonschema

        try:
            self.compiled_validator(payload)
        except fastjsonschema.JsonSchemaException as e:
            raise PayloadSchemaViolationError(
                validation_error_message=e.message,
                validation_error=e,
                schema=self.schema,
            )


def _validate_fastjsonschema(
    *,
    payload: Any,
    schema: Dict,
):
    import fastjsonschema

    try:
        fastjsonschema.validate(schema, payload)
    except fastjsonschema.JsonSchemaException as e:
        raise PayloadSchemaViolationError(
            validation_error_message=e.message, validation_error=e, schema=schema
        )


def _validate_jsonschema(
    *,
    payload: Any,
    schema: Dict,
):
    import jsonschema

    try:
        jsonschema.validate(payload, schema)
    except jsonschema.ValidationError as e:
        raise PayloadSchemaViolationError(
            validation_error_message=e.message, validation_error=e, schema=schema
        )


def _get_schema_validator() -> Callable:
    try:
        import fastjsonschema

        return _validate_fastjsonschema
    except ModuleNotFoundError:
        sys.modules["fastjsonschema"] = None  # type: ignore
    try:
        import jsonschema

        return _validate_jsonschema
    except ModuleNotFoundError:
        sys.modules["jsonschema"] = None  # type: ignore
        msg = (
            "Schema validation requires either the fastjsonschema or jsonschema packages. "
            + "Install one separately or install the extra as "
            + "aws-lambda-api-event-utils[fastjsonschema] or "
            + "aws-lambda-api-event-utils[jsonschema]."
        )
        raise ModuleNotFoundError(msg, name="fastjsonschema")


def _parse_and_validate_json_body(
    *,
    body: Union[str, bytes, bytearray],
    schema: Union[None, Dict, CompiledFastJSONSchema],
) -> Any:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as e:
        raise PayloadJSONDecodeError(json_decode_error=e)

    # check schema only when body is parsed
    # empty body is allowed by function parameter, not schema
    if schema is None:
        return payload

    if isinstance(schema, CompiledFastJSONSchema):
        schema.validate(payload)
    else:
        validator = _get_schema_validator()
        validator(payload=payload, schema=schema)

    return payload


def _get_json_body(
    event: ApiEventType,
    *,
    schema: Optional[Dict],
    enforce_content_type: bool,
    enforce_on_optional_methods: bool,
    post_parse_hook: Callable = None,
) -> Any:
    if enforce_content_type:
        from .aws_lambda_api_event_validators import validate_content_type

        validate_content_type(event, "application/json")

    body = get_body(event)

    allow_empty_body = False
    if not enforce_on_optional_methods:
        method = _get_method(event)
        allow_empty_body = method in [
            "GET",
            "HEAD",
            "DELETE",
            "CONNECT",
            "OPTIONS",
            "TRACE",
        ]

    # check for unparseable types
    if not body and not allow_empty_body:
        raise PayloadJSONDecodeError(json_decode_error="Request has no body")
    elif body and not isinstance(body, _VALID_JSON_LOADS_TYPES):
        raise TypeError(f"Cannot load JSON from body of type {type(body)}")

    if not body:
        payload = None
    else:
        payload = _parse_and_validate_json_body(body=body, schema=schema)

    if post_parse_hook:
        post_parse_hook(event, payload)

    return payload


def get_json_body(
    event: ApiEventType,
    *,
    schema: Optional[Dict] = None,
    enforce_content_type: bool = False,
    enforce_on_optional_methods: bool = False,
) -> Any:
    """Parse and validate the request body.

    Args:
        event (dict): The Lambda function input event.
        schema (dict): A JSON Schema to use to validate the body.
        enforce_content_type (bool): Check the Content-Type is application/json.
        enforce_on_optional_methods (bool): Disallow empty bodies for HTTP
            methods that normally may not have bodies, e.g., GET and HEAD.

    Returns:
        The parsed and validated body.

    Raises:
        PayloadJSONDecodeError: When the body cannot be parsed.
        PayloadSchemaViolationError: When the body is valid JSON but violates the schema.
    """
    return _get_json_body(
        event=event,
        schema=schema,
        enforce_content_type=enforce_content_type,
        enforce_on_optional_methods=enforce_on_optional_methods,
    )


def _json_body_decorator_post_parse_hook(event: ApiEventType, payload: Any):
    """Update the body in place."""
    format_version = get_event_format_version(event)
    if format_version in [FormatVersion.APIGW_10, FormatVersion.APIGW_20]:
        event["body"] = payload
        event.pop("isBase64Encoded")  # meaningless with parsed body
    else:
        # should not happen as this is checked earlier
        raise NotImplementedError


def json_body(
    schema: Optional[Dict] = None,
    *,
    enforce_content_type: bool = False,
    enforce_on_optional_methods: bool = False,
):
    """Parse and validate the request body.

    This updates the body in-place in the event.

    The following APIErrorResponse subclasses are used:
        PayloadJSONDecodeError: When the body cannot be parsed.
        PayloadSchemaViolationError: When the body is valid JSON but violates the schema.

    Args:
        schema (dict): A JSON Schema to use to validate the body.
        enforce_content_type (bool): Check the Content-Type is application/json.
        enforce_on_optional_methods (bool): Disallow empty bodies for HTTP
            methods that normally may not have bodies, e.g., GET and HEAD.
    """
    # if schema is callable, it's a bare decorator
    func = None
    if callable(schema):
        func = schema
        schema = None

    decorator = _get_decorator(
        _get_json_body,
        schema=schema,
        enforce_content_type=enforce_content_type,
        enforce_on_optional_methods=enforce_on_optional_methods,
        post_parse_hook=_json_body_decorator_post_parse_hook,
    )

    # deal with bare decorator
    if func:
        return decorator(func)
    else:
        return decorator


def _get_method(event: ApiEventType) -> str:
    """Helper function to extract method without validating."""
    format_version = get_event_format_version(event)
    if format_version == FormatVersion.APIGW_10:
        event_method = cast(str, event["httpMethod"])
    elif format_version == FormatVersion.APIGW_20:
        event_method = cast(str, event["requestContext"]["http"]["method"])  # type: ignore
    else:
        raise NotImplementedError
    return event_method


def _get_headers(event: ApiEventType) -> Dict[str, str]:
    format_version = get_event_format_version(event)
    if format_version == FormatVersion.APIGW_10:
        return dict(
            (key.lower(), ",".join(value))
            for key, value in event["multiValueHeaders"].items()  # type: ignore
        )
    elif format_version == FormatVersion.APIGW_20:
        return cast(Dict[str, str], event["headers"])
    else:
        raise NotImplementedError


def _add_single_header(
    headers: Optional[LaxHeadersType], name: str, value: str
) -> LaxHeadersType:
    if headers is None:
        headers = {}
    for key in headers:
        if key.lower() == name.lower():
            break
    else:
        headers[name] = value
    return headers


def _add_headers(
    headers: Optional[LaxHeadersType], headers_to_add: Dict[str, str]
) -> LaxHeadersType:
    if headers is None:
        headers = {}
    header_keys = set(h.lower() for h in headers)
    for name, value in headers_to_add.items():
        if name.lower() not in header_keys:
            headers[name] = value
    return headers


def _append_header_value(
    existing_value: Union[str, List[str]], value_to_append: Union[str, List[str]]
) -> Union[str, List[str]]:
    if isinstance(existing_value, str):
        existing_value = [existing_value]
    if isinstance(value_to_append, str):
        return [*existing_value, value_to_append]
    else:
        return [*existing_value, *value_to_append]


def set_header(
    headers: LaxHeadersType,
    header_name: str,
    header_value: Union[str, List[str]],
    *,
    override: bool,
) -> Optional[bool]:
    """Set the given header.

    Returns True if an existing value was kept.
    Returns False if an existing value was overwritten.
    Returns None if no existing value was found.
    """
    for name in headers.keys():
        if name.lower() == header_name.lower():
            if override:
                headers[name] = header_value
                return False
            return True
    headers[header_name] = header_value
    return None


def set_headers(
    headers: LaxHeadersType, headers_to_set: LaxHeadersType, *, override: bool
):
    """Set the given headers."""
    header_keys = {h.lower(): h for h in headers}
    for header_name, header_value in headers_to_set.items():
        if header_name.lower() not in header_keys:
            headers[header_name] = header_value
        elif override:
            existing_name = header_keys[header_name.lower()]
            headers[existing_name] = header_value


def append_header(
    headers: LaxHeadersType, header_name: str, header_value: Union[str, List[str]]
) -> Optional[bool]:
    """Append the given header.

    Returns True if an existing value was appended to.
    Returns None if no existing value was found.
    """
    for name, value in headers.items():
        if name.lower() == header_name.lower():
            headers[name] = _append_header_value(value, header_value)
            return True
    headers[header_name] = header_value
    return None


def append_headers(headers: LaxHeadersType, headers_to_append: LaxHeadersType):
    """Append the given headers."""
    header_keys = {h.lower(): h for h in headers}
    for header_name, header_value in headers_to_append.items():
        if header_name.lower() in header_keys:
            existing_name = header_keys[header_name.lower()]
            existing_value = headers[existing_name]
            headers[existing_name] = _append_header_value(existing_value, header_value)
        else:
            headers[header_name] = header_value
