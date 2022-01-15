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
from dataclasses import dataclass
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
)

__version__ = "0.1.0"  # update here and pyproject.toml

__all__ = (
    "api_event_handler",
    "BodyType",
    "DatetimeSerializationOptions",
    "APIErrorResponse",
    "EVENT_FORMAT_VERSION_CACHE_KEY",
    "FormatVersion",
    "get_body",
    "get_default_json_serialization_options",
    "get_event_format_version",
    "get_json_body",
    "InvalidRequestError",
    "json_body",
    "JSONSerializationOptions",
    "make_redirect",
    "make_response",
    "PayloadBinaryTypeError",
    "PayloadJSONDecodeError",
    "PayloadSchemaViolationError",
    "set_default_json_serialization_options",
)

EVENT_FORMAT_VERSION_CACHE_KEY = "__event_format_version__"


class FormatVersion(enum.Enum):
    """Event format identifiers"""

    APIGW_10 = "API Gateway HTTP 1.0 and REST"
    APIGW_20 = "API Gateway HTTP 2.0"
    # ALB_10 = "ALB 1.0"


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

_ALB_10_DATA = _FormatVersionData(
    version=None,
    keys=(
        "httpMethod",
        "path",
        "headers",
        "queryStringParameters",
        "body",
        "isBase64Encoded",
    ),
)


def _get_key(d: str, key: Union[str, Iterable[str]]):
    if isinstance(key, str):
        return key in d, d.get(key)
    value = d
    for k in key:
        if k not in value:
            return False, None
        value = value[k]
    return True, value


def _event_matches_format_version(event: Dict, format_version_data: _FormatVersionData):
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
    event: Dict, disable_cache: bool = False
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
        return FormatVersion[event[EVENT_FORMAT_VERSION_CACHE_KEY]]
    event_format_version = None

    if _event_matches_format_version(event, _API_GW_10_DATA):
        event_format_version = FormatVersion.APIGW_10
    elif _event_matches_format_version(event, _API_GW_20_DATA):
        event_format_version = FormatVersion.APIGW_20
    elif _event_matches_format_version(event, _API_GW_10_REST_DATA):
        event_format_version = FormatVersion.APIGW_10
    # elif _event_matches_format_version(event, _ALB_10_DATA):
    #     event_format_version = FormatVersion.ALB_10

    if event_format_version and not disable_cache:
        event[EVENT_FORMAT_VERSION_CACHE_KEY] = event_format_version.name
    return event_format_version


@dataclass(frozen=True)
class DatetimeSerializationOptions:
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
class JSONSerializationOptions:
    """Options for serializing classes to JSON.

    The datetime field can be set to True to use the default (serialize
    classes from the datetime package, update datetime and time strings to
    use the "Z" timezone designator for UTC), None or False to disable
    serializing any of these classes, or a DatetimeSerializationOptions object.

    The decimal_type field should be float or str, or None to disable
    serialization of decimal.Decimal objects.
    """

    datetime: Optional[Union[bool, DatetimeSerializationOptions]]
    decimal_type: Optional[Union[Type[float], Type[str]]]

    def __post_init__(self):
        if self.datetime is True:
            object.__setattr__(self, "datetime", DatetimeSerializationOptions())
        elif self.datetime is False:
            object.__setattr__(self, "datetime", None)


_DEFAULT_JSON_SERIALIZATION_OPTIONS = JSONSerializationOptions(
    datetime=True, decimal_type=float
)


def set_default_json_serialization_options(options: Optional[JSONSerializationOptions]):
    """Set the default JSON serialization options."""
    global _DEFAULT_JSON_SERIALIZATION_OPTIONS
    _DEFAULT_JSON_SERIALIZATION_OPTIONS = options


def get_default_json_serialization_options() -> JSONSerializationOptions:
    """Get the default JSON serialization options.

    Initializes to serializing classes from the datetime package, including
    updating datetime and time strings to use the "Z" timezone designator for UTC,
    and serializing decimal.Decimal as float.
    """
    global _DEFAULT_JSON_SERIALIZATION_OPTIONS
    return _DEFAULT_JSON_SERIALIZATION_OPTIONS


def _json_dump_default(obj: Any, options: JSONSerializationOptions):
    if (
        isinstance(obj, (datetime.datetime, datetime.date, datetime.time))
        and options.datetime
    ):
        kwargs = {}
        if (
            isinstance(obj, (datetime.datetime, datetime.time))
            and options.datetime.timespec is not None
        ):
            kwargs["timespec"] = options.datetime.timespec
        if isinstance(obj, datetime.datetime) and options.datetime.sep is not None:
            kwargs["sep"] = options.datetime.sep

        value = obj.isoformat(**kwargs)

        if options.datetime.use_z_format:
            value = re.sub(r"\+00(:?00)?$", "Z", value)

        return value
    if isinstance(obj, decimal.Decimal) and options.decimal_type:
        return options.decimal_type(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


def _json_dump(data: Any, options: JSONSerializationOptions):
    dump_kwargs = {}
    if options:
        dump_kwargs["default"] = lambda obj: _json_dump_default(obj, options)
    return json.dumps(data, **dump_kwargs)


def make_response(
    status_code: Union[int, http.HTTPStatus],
    body: Optional[Any],
    *,
    format_version: Union[FormatVersion, Dict],
    headers: Optional[Dict[str, Union[str, List[str]]]] = None,
    cookies: Optional[List[str]] = None,
    json_serialization_options: Optional[JSONSerializationOptions] = None,
) -> Dict:
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
        json_serialization_options (JSONSerializationOptions): Override the default
            JSON serialization settings

    Returns: A dict suitable for returning from the Lambda function.
    """
    if isinstance(status_code, http.HTTPStatus):
        status_code = status_code.value

    if not isinstance(format_version, FormatVersion):
        format_version = get_event_format_version(format_version)

    if format_version is None:
        raise TypeError("Unknown format version")
    if format_version not in [FormatVersion.APIGW_10, FormatVersion.APIGW_20]:
        raise NotImplementedError(f"Unknown format version {format_version}")

    if cookies is not None and format_version in [FormatVersion.APIGW_10]:
        # TODO: insert into headers?
        raise TypeError(f"Cookies are not supported in format version {format_version}")

    response = {"statusCode": status_code}

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
            if json_serialization_options is None:
                json_serialization_options = get_default_json_serialization_options()
            body = _json_dump(body, json_serialization_options)
            is_base64_encoded = False
            default_content_type = "application/json"

        if default_content_type:
            if headers is None:
                headers = {}
            for key in headers:
                if key.lower() == "content-type":
                    break
            else:
                headers["content-type"] = default_content_type

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
    format_version: Union[FormatVersion, Dict],
    headers: Optional[Dict[str, Union[str, List[str]]]] = None,
    cookies: Optional[List[str]] = None,
) -> Dict:
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
        format_version=format_version,
        headers=headers,
        cookies=cookies,
    )


def api_event_handler(format_version: str = None):
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

    DECORATOR_LOGGER: Optional[Union[logging.Logger, Callable]] = None
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
    def re_raise_as(
        cls,
        status_code: Union[int, http.HTTPStatus],
        *,
        internal_message: Optional[str] = None,
        exc: Optional[Exception] = None,
    ) -> NoReturn:
        """Raise an APIErrorResponse using the currently-active or given exception.

        This can be used in an except block without explicitly providing the
        exception; it will get it from sys.exc_info().

        This method creates and raises an APIErrorResponse subclass
        with the given status code, the error code set to the exception class name,
        and the error message set to the stringified exception.
        If internal_message is not provided, it is set to a string containing
        the error code and error message.
        """
        if exc is None:
            exc_info = sys.exc_info()
            if not exc_info[1]:
                raise RuntimeError(
                    "APIErrorResponse.re_raise_as() used without an exception outside an except block"
                )
            exc = exc_info[1]
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
        raise error_instance

    @classmethod
    def make_response_from_exception(
        cls,
        status_code: Union[int, http.HTTPStatus],
        exception: Exception,
        *,
        format_version: Union[FormatVersion, Dict],
        headers: Optional[Dict[str, Union[str, List[str]]]] = None,
        cookies: Optional[List[str]] = None,
    ) -> Dict:
        """Create a response based on any Exception.

        If the provided exception is an APIErrorResponse subclass, it must match
        the provided status code, and the response will come from the
        get_response() method.

        For all other exceptions, the response body will use the exception type name
        as the error code, and the stringified exception as the error message.
        """
        if isinstance(exception, cls):
            if exception.STATUS_CODE != status_code:
                raise ValueError(
                    f"Status code mismatch: {exception.STATUS_CODE} {status_code}"
                )
            return exception.get_response(
                headers=headers,
                cookies=cookies,
                format_version=format_version,
            )
        body = cls.make_error_body(
            code=type(exception).__name__,
            message=str(exception),
        )
        return make_response(
            status_code=status_code,
            body=body,
            headers=headers,
            cookies=cookies,
            format_version=format_version,
        )

    @classmethod
    def make_error_body(cls, code: str, message: str) -> Dict:
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
        body = {}
        error_dict = body
        if cls.ERROR_PARENT_FIELD:
            error_dict = {}
            body[cls.ERROR_PARENT_FIELD] = error_dict
        error_dict[cls.ERROR_CODE_FIELD] = code
        error_dict[cls.ERROR_MESSAGE_FIELD] = message
        return body

    def __init__(self, internal_message: str, **kwargs):
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

        Returns the ERROR_MESSAGE class field if it is set by the subclass.
        If it is not, it falls back to the ERROR_MESSAGE_TEMPLATE class field,
        calling the string format() method on it with the exception's instance fields
        as input. If ERROR_MESSAGE_TEMPLATE is also not set, a generic error message
        will be returned.
        """
        if self.ERROR_MESSAGE is NotImplemented:
            if self.ERROR_MESSAGE_TEMPLATE is NotImplemented:
                return "An error occurred."
            else:
                template_args = {}
                # add kwargs provided to constructor
                template_args.update(self.kwargs)
                # instance fields should overwrite anything in self.kwargs
                template_args.update(vars(self))
                # remove self.kwargs field
                template_args.pop("kwargs")
                return self.ERROR_MESSAGE_TEMPLATE.format(**template_args)
        else:
            return self.ERROR_MESSAGE

    def get_body(self, body: Optional[Any] = None) -> Dict:
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
        self, headers: Optional[Dict[str, Union[str, List[str]]]] = None
    ) -> Optional[Dict[str, Union[str, List[str]]]]:
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
        format_version: Union[FormatVersion, Dict],
        body: Optional[Any] = None,
        headers: Optional[Dict[str, Union[str, List[str]]]] = None,
        cookies: Optional[List[str]] = None,
        json_serialization_options: Optional[JSONSerializationOptions] = None,
    ) -> Dict:
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
        cookies = self.get_cookies(cookies)
        return make_response(
            status_code=self.STATUS_CODE,
            body=body,
            headers=headers,
            cookies=cookies,
            format_version=format_version,
            json_serialization_options=json_serialization_options,
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
    ):
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
    headers: Optional[Dict[str, Union[str, List[str]]]],
    cookies: Optional[List[str]],
    format_version: str,
) -> Dict:
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
        format_version=format_version,
    )


def _set_context_fields(context):
    """Attempt to add fields to context object"""
    if not hasattr(context, "api_response_headers"):
        try:
            setattr(context, "api_response_headers", None)
        except:
            pass

    if not hasattr(context, "api_response_cookies"):
        try:
            setattr(context, "api_response_cookies", None)
        except:
            pass


def _get_context_fields(context):
    """Attempt to retrieve fields from context object"""
    headers = getattr(context, "api_response_headers", None)
    cookies = getattr(context, "api_response_cookies", None)
    return headers, cookies


def _get_decorator(
    validation_func: Callable,
    response_format_version: Optional[str] = None,
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
                _set_context_fields(context)
                result = f(event, context, *args, **kwargs)
                headers, cookies = _get_context_fields(context)
                return _process_function_result(
                    result,
                    headers=headers,
                    cookies=cookies,
                    format_version=_response_format_version,
                )
            except APIErrorResponse as e:
                e._decorator_log()
                headers, cookies = _get_context_fields(context)
                return e.get_response(
                    headers=headers,
                    cookies=cookies,
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

    def __init__(self, *, binary_expected: bool, **kwargs):
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


def get_body(event: Dict, *, type: BodyType = None) -> Union[str, bytes]:
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
        body = event.get("body")
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
    ):
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
        return str(self.validation_error)

    def __init__(
        self,
        *,
        schema: Dict,
        validation_error: Union[str, "jsonschema.ValidationError"],  # type: ignore
        **kwargs,
    ):
        self.schema = schema
        self.validation_error = validation_error
        if "internal_message" not in kwargs:
            kwargs["internal_message"] = f"Payload violates schema: {validation_error}"
        super().__init__(**kwargs)


_VALID_JSON_LOADS_TYPES = (str, bytes, bytearray)


def _parse_and_validate_json_body(
    *,
    body: Union[str, bytes, bytearray],
    schema: Optional[Dict],
) -> Any:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as e:
        raise PayloadJSONDecodeError(json_decode_error=e)

    # check schema only when body is parsed
    # empty body is allowed by function parameter, not schema
    if schema is not None:
        try:
            import jsonschema
        except ModuleNotFoundError:
            msg = (
                "Schema validation requires the jsonschema package. "
                + "It can be installed separately or by installing aws-lambda-api-event-utils[jsonschema]."
            )
            raise ModuleNotFoundError(msg, name="jsonschema")

        try:
            jsonschema.validate(payload, schema)
        except jsonschema.ValidationError as e:
            raise PayloadSchemaViolationError(validation_error=e, schema=schema)

    return payload


def _get_json_body(
    event: Dict,
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
    event: Dict,
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


def _json_body_decorator_post_parse_hook(event: Dict, payload: Any):
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


def _get_method(event: Dict) -> str:
    """Helper function to extract method without validating."""
    format_version = get_event_format_version(event)
    if format_version == FormatVersion.APIGW_10:
        event_method = event["httpMethod"]
    elif format_version == FormatVersion.APIGW_20:
        event_method = event["requestContext"]["http"]["method"]
    else:
        return NotImplementedError
    return event_method
