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

import re
import operator as op
from typing import Dict, List, Tuple, Union, Optional

from .aws_lambda_api_event_utils import (
    __version__,
    FormatVersion,
    APIErrorResponse,
    get_event_format_version,
    _get_decorator,
    _get_method,
)

__all__ = (
    "FormatVersionError",
    "validate_event_format_version",
    "event_format_version",
    "UnsupportedMethodError",
    "validate_method",
    "method",
    "PathNotFoundError",
    "validate_path",
    "path",
    "validate_path_regex",
    "path_regex",
    "PathParameterError",
    "validate_path_parameters",
    "path_parameters",
    "HeaderError",
    "validate_headers",
    "headers",
    "InvalidContentType",
    "validate_content_type",
    "content_type",
    "QueryParameterError",
    "validate_query_parameters",
    "query_parameters",
)


def _get_stage(event: Dict):
    format_version = get_event_format_version(event)
    if format_version in [FormatVersion.APIGW_10, FormatVersion.APIGW_20]:
        return event["requestContext"]["stage"]
    else:
        raise NotImplementedError


def _matches(
    string: str,
    string_or_string_list: Union[str, List[str]],
    *,
    matcher=(op.eq, op.contains),
) -> bool:
    if isinstance(string_or_string_list, str):
        return matcher[0](string, string_or_string_list)
    else:
        return matcher[1](string_or_string_list, string)


class FormatVersionError(APIErrorResponse):
    """APIErrorResponse for an invalid event format version.

    The internal_message describes the expected and received event format versions.
    The response will have status 500, error code InternalServiceError and
    message "An error occurred.", as no details need be exposed to the client.

    Attributes:
        expected_version: The format version required by the validation.
        actual_version: The format version of the event.
    """

    STATUS_CODE = 500
    ERROR_CODE = "InternalServerError"
    ERROR_MESSAGE = "An error occurred."

    def __init__(
        self,
        *,
        expected_version: FormatVersion,
        actual_version: FormatVersion,
        **kwargs,
    ):
        self.expected_version = expected_version
        self.actual_version = actual_version
        if "internal_message" not in kwargs:
            if actual_version is None:
                kwargs[
                    "internal_message"
                ] = f"Expected event version {expected_version}, but received an unknown event"
            else:
                kwargs[
                    "internal_message"
                ] = f"Expected event version {expected_version}, but received {actual_version}"
        super().__init__(**kwargs)


def validate_event_format_version(
    event: Dict, format_version: FormatVersion, *, use_error_response: bool = False
) -> FormatVersion:
    """Validate the event uses the given format version.

    By default, this raises TypeError, because a correct event format version is
    expected to determined at deployment time. To raise FormatVersionError
    instead, set use_error_response=True.

    Args:
        event (dict): The Lambda function input event.
        format_version (FormatVersion): The expected format version.
        use_error_response (bool): Raise FormatVersionError
            instead of TypeError.

    Returns:
        The event format version.

    Raises:
        TypeError: When the format version doesn't match
            and use_error_response=False
        FormatVersionError: When the format version doesn't match
            and use_error_response=True
    """
    actual_version = get_event_format_version(event)
    if isinstance(format_version, str):
        format_version = FormatVersion[format_version]
    if actual_version != format_version:
        error = FormatVersionError(
            expected_version=format_version, actual_version=actual_version
        )
        if not use_error_response:
            error = TypeError(error.internal_message)
        raise error
    return actual_version


def event_format_version(
    format_version: FormatVersion, *, use_error_response: bool = False
):
    """Validate the event uses the given format version.

    By default, this raises TypeError, because a correct event format version is
    expected to determined at deployment time. To raise FormatVersionError
    instead, set use_error_response=True.

    The following APIErrorResponse subclasses are used:
        TypeError: When the format version doesn't match
            and use_error_response=False
        FormatVersionError: When the format version doesn't match
            and use_error_response=True

    Args:
        format_version (FormatVersion): The expected format version.
        use_error_response (bool): Raise FormatVersionError
            instead of TypeError.

    Raises:
        TypeError: When the format version doesn't match
            and use_error_response=False
    """
    return _get_decorator(
        validate_event_format_version,
        response_format_version=format_version,
        format_version=format_version,
        use_error_response=use_error_response,
    )


class UnsupportedMethodError(APIErrorResponse):
    """APIErrorResponse for an invalid HTTP request method.

    The internal_message describes the allowed and received methods.
    The response will have status 405, error code UnsupportedMethodError and
    an error message listing the allowed methods.

    The response also has the Allow header set as required by RFC7231.

    Attributes:
        event_method: The method in the event.
        valid_methods: The allowed methods.
    """

    STATUS_CODE = 405
    ERROR_CODE = "UnsupportedMethod"

    def __init__(
        self, *, event_method: str, valid_methods: Union[str, List[str]], **kwargs
    ):

        if isinstance(valid_methods, str):
            valid_methods = [valid_methods]

        self.event_method = event_method
        self.valid_methods = valid_methods

        if "internal_message" not in kwargs:
            kwargs[
                "internal_message"
            ] = f"Method {event_method} not in valid set {{{', '.join(valid_methods)}}}."

        super().__init__(**kwargs)

    def get_error_message(self) -> str:
        """Include allowed methods in the error message.

        The allowed methods are in the response headers anyway,
        as required by RFC7231.
        """
        return f"{self.event_method} is not a valid HTTP method. Valid methods are {' '.join(self.valid_methods)}"

    def get_headers(
        self, headers: Optional[Dict[str, Union[str, List[str]]]] = None
    ) -> Optional[Dict[str, Union[str, List[str]]]]:
        """Include Allow header as required by RFC7231."""
        headers = super().get_headers(headers=headers)
        if not headers:
            headers = {}
        else:
            headers = headers.copy()
        headers["allow"] = ", ".join(self.valid_methods)


def validate_method(event: Dict, method: Union[str, List[str]]) -> str:
    """Validate the method in the event against the given method(s).

    Args:
        event (dict): The Lambda function input event.
        method: A method or list of methods to validate against.

    Returns:
        The validated method.

    Raises:
        UnsupportedMethodError: When the method doesn't match.
    """
    event_method = _get_method(event)
    if not _matches(event_method, method):
        raise UnsupportedMethodError(event_method=event_method, valid_methods=method)
    return event_method


def method(method: Union[str, List[str]]):
    """Validate the method in the event against the given method(s).

    The following APIErrorResponse subclasses are used:
        UnsupportedMethodError: When the method doesn't match.

    Args:
        event (dict): The Lambda function input event.
        method: A method or list of methods to validate against.
    """
    return _get_decorator(validate_method, method=method)


class PathNotFoundError(APIErrorResponse):
    """APIErrorResponse for an invalid HTTP request method.

    The internal_message describes the allowed and received methods.
    The response will have status 404, error code PathNotFoundError and
    an error message that the path was not found.

    Attributes:
        event_path: The path in the event.
        valid_paths: The allowed paths, either path literals or regular expressions.
        is_regex: Whether valid_paths contains path literals or regular expressions.
    """

    STATUS_CODE = 404
    ERROR_CODE = "PathNotFound"
    ERROR_MESSAGE_TEMPLATE = "Path {event_path} not found."

    def __init__(
        self,
        *,
        event_path: str,
        valid_paths: Union[str, re.Pattern, List[Union[str, re.Pattern]]],
        is_regex: bool = False,
        **kwargs,
    ):
        proc = lambda v: v.pattern if isinstance(v, re.Pattern) else v
        if isinstance(valid_paths, (str, re.Pattern)):
            valid_paths = proc(valid_paths)
        else:
            valid_paths = list(proc(v) for v in valid_paths)

        if "internal_message" not in kwargs:
            if isinstance(valid_paths, (str, re.Pattern)):
                kwargs[
                    "internal_message"
                ] = f"Path {event_path} does not match {valid_paths}."
            else:
                kwargs[
                    "internal_message"
                ] = f"Path {event_path} not in valid set {{{' '.join(valid_paths)}}}."

        self.event_path = event_path
        self.valid_paths = valid_paths
        self.is_regex = is_regex

        super().__init__(**kwargs)


def _strip_stage(*, path: str, stage: str, format_version: str):
    if not stage:
        return path
    if format_version == FormatVersion.APIGW_20 and stage == "$default":
        return path
    stage_prefix = f"/{stage}"
    if path.startswith(stage_prefix):
        return path[len(stage_prefix) :]
    else:
        return path


def _get_path_and_parameters(
    event: Dict, *, disable_stage_removal: Optional[bool] = False
) -> Tuple[str, Dict[str, str]]:
    """Helper function to extract path and parameters without validating."""
    format_version = get_event_format_version(event)
    if format_version == FormatVersion.APIGW_10:
        event_path = event["path"]
        parameters = event.get("pathParameters") or {}
    elif format_version == FormatVersion.APIGW_20:
        event_path = event["rawPath"]
        # event_path = event["requestContext"]["http"]["path"]
        parameters = event.get("pathParameters") or {}
    else:
        raise NotImplementedError

    if not disable_stage_removal:
        stage = _get_stage(event)
        event_path = _strip_stage(
            path=event_path, stage=stage, format_version=format_version
        )

    return event_path, parameters


def _update_path_parameters(event: Dict, parameters: Dict) -> Dict:
    """Helper method to modify the event's path parameters with the input dict."""
    format_version = get_event_format_version(event)
    if format_version in [FormatVersion.APIGW_10, FormatVersion.APIGW_20]:
        if event.get("pathParameters") is None:
            if not parameters:
                return {}
            event["pathParameters"] = {}
        event["pathParameters"].update(parameters)
        return event["pathParameters"]
    else:
        raise NotImplementedError


def validate_path(
    event: Dict,
    path: Union[str, List[str]],
    *,
    disable_stage_removal: Optional[bool] = False,
) -> Tuple[str, Dict[str, str]]:
    """Validate the path in the event against the given path(s).

    Args:
        event (dict): The Lambda function input event.
        path: A path literal or list of path literals to validate against.
        disable_stage_removal (bool): preserve the original path with stage.

    Returns:
        The validated path and path parameters.

    Raises:
        PathNotFoundError: When the path doesn't match.
    """
    event_path, parameters = _get_path_and_parameters(
        event, disable_stage_removal=disable_stage_removal
    )
    if not _matches(event_path, path):
        raise PathNotFoundError(
            event_path=event_path,
            valid_paths=path,
            is_regex=False,
        )
    return event_path, parameters


def path(path: Union[str, List[str]], *, disable_stage_removal: Optional[bool] = False):
    """Validate the path in the event against the given path(s).

    The following APIErrorResponse subclasses are used:
        PathNotFoundError: When the path doesn't match.

    Args:
        path: A path literal or list of path literals to validate against.
        disable_stage_removal (bool): preserve the original path with stage.
    """
    return _get_decorator(
        validate_path, path=path, disable_stage_removal=disable_stage_removal
    )


def validate_path_regex(
    event: Dict,
    path_regex: Union[str, re.Pattern],
    *,
    disable_stage_removal: Optional[bool] = False,
    update_event: bool = False,
) -> Tuple[str, Dict[str, str]]:
    """Validate the path in the event against the given path pattern.

    Args:
        event (dict): The Lambda function input event.
        path: A regular expression to validate against.
        disable_stage_removal (bool): Preserve the original path with stage.
        update_event (bool): Add regex groups to path parameters in the event.

    Returns:
        The validated path and path parameters.

    Raises:
        PathNotFoundError: When the path doesn't match.
    """
    event_path, parameters = _get_path_and_parameters(
        event, disable_stage_removal=disable_stage_removal
    )
    match = re.search(path_regex, event_path)
    if not match:
        raise PathNotFoundError(
            event_path=event_path, valid_paths=path_regex, is_regex=True
        )
    parameters_from_match = match.groupdict()
    if update_event:
        parameters = _update_path_parameters(event, parameters_from_match)
    else:
        parameters = parameters.copy()
        parameters.update(parameters_from_match)

    return event_path, parameters


def path_regex(
    path_regex: Union[str, re.Pattern], *, disable_stage_removal: Optional[bool] = False
):
    """Validate the path in the event against the given path pattern.

    The following APIErrorResponse subclasses are used:
        PathNotFoundError: When the path doesn't match.

    Args:
        path: A regular expression to validate against.
        disable_stage_removal (bool): Preserve the original path with stage.
    """
    return _get_decorator(
        validate_path_regex,
        path_regex=path_regex,
        disable_stage_removal=disable_stage_removal,
        update_event=True,
    )


class PathParameterError(APIErrorResponse):
    """APIErrorResponse for missing or invalid path parameters.

    The internal_message describes the parameter keys and values in the request
    that do not match the requirements.
    The response will have status 404, error code PathNotFoundError and
    an error message that the path was not found.

    When raised by validate_path_parameters(), the kwargs attribute will
    additionally contain the keys, values, and value_patterns passed to it.

    Attributes:
        event_path: The URL path from the event.
        bad_keys: The required path parameters that are missing from the path.
        bad_values: The required path parameters that are present in the path
            but have an invalid value.
    """

    STATUS_CODE = 404
    ERROR_CODE = "PathNotFound"
    ERROR_MESSAGE_TEMPLATE = "Path {event_path} not found."

    def __init__(self, *, event_path, bad_keys, bad_values, **kwargs):
        self.event_path = event_path
        self.bad_keys = bad_keys
        self.bad_values = bad_values

        if "internal_message" not in kwargs:
            message_parts = []
            if bad_keys:
                message_parts.append(f"missing keys {','.join(bad_keys)}")
            if bad_values:
                s = ",".join(f"{key}={value}" for key, value in bad_values.items())
                message_parts.append("invalid values " + s)
            kwargs[
                "internal_message"
            ] = f"Bad path parameters: {' and '.join(message_parts)}."

        super().__init__(**kwargs)


def validate_path_parameters(
    event: Dict,
    *,
    keys: Optional[List[str]] = None,
    values: Optional[Dict[str, str]] = None,
    value_patterns: Optional[Dict[str, Union[str, re.Pattern]]] = None,
    disable_stage_removal: Optional[bool] = False,
) -> Tuple[str, Dict[str, str]]:
    """Validate the path parameters in the event against the given requirements.

    Args:
        event (dict): The Lambda function input event.
        keys (list): A list of path parameter names that must be present.
        values (dict): A mapping of path parameter names to literal values that
            the parameters must take.
        value_patterns (dict): A mapping of path parameter names to regular
            expression patterns (either strings or re.Pattern objects) that
            the parameters must match.
        disable_stage_removal (bool): Preserve the original path with stage.

    Returns:
        The validated path and path parameters.

    Raises:
        PathParameterError: When the path parameters don't match
            the requirements.
    """
    event_path, parameters = _get_path_and_parameters(
        event, disable_stage_removal=disable_stage_removal
    )

    bad_keys = []
    if keys:
        for key in keys:
            if key not in parameters:
                bad_keys.append(key)

    bad_values = {}
    if values:
        for key, value in values.items():
            if key not in parameters:
                bad_keys.append(key)
            elif parameters[key] != value:
                bad_values[key] = parameters[key]
    if value_patterns:
        for key, value_pattern in value_patterns.items():
            if key not in parameters:
                bad_keys.append(key)
            elif not re.search(value_pattern, parameters[key]):
                bad_values[key] = parameters[key]

    if bad_keys or bad_values:
        raise PathParameterError(
            event_path=event_path,
            bad_keys=bad_keys,
            bad_values=bad_values,
            keys=keys,
            values=values,
            value_patterns=value_patterns,
        )

    return event_path, parameters


def path_parameters(
    *,
    keys: Optional[List[str]] = None,
    values: Optional[Dict[str, str]] = None,
    value_patterns: Optional[Dict[str, Union[str, re.Pattern]]] = None,
):
    """Validate the path parameters in the event against the given requirements.

    The following APIErrorResponse subclasses are used:
        PathParameterError: When the path parameters don't match
            the requirements.

    Args:
        event (dict): The Lambda function input event.
        keys (list): A list of path parameter names that must be present.
        values (dict): A mapping of path parameter names to literal values that
            the parameters must take.
        value_patterns (dict): A mapping of path parameter names to regular
            expression patterns (either strings or re.Pattern objects) that
            the parameters must match.
    """
    return _get_decorator(
        validate_path_parameters,
        keys=keys,
        values=values,
        value_patterns=value_patterns,
    )


class HeaderError(APIErrorResponse):
    """APIErrorResponse for missing or invalid headers.

    The internal_message describes the header keys and values in the request
    that do not match the requirements.
    The response will have status 400, error code InvalidRequestError and
    an error message listing the missing or invalid header keys.

    When raised by validate_headers(), the kwargs attribute will
    additionally contain the keys, values, and value_patterns passed to it.

    Attributes:
        event_headers: The headers from the event.
        bad_keys: The required headers that are missing from the request.
        bad_values: The required headers that are present in the requests
            but have an invalid value.
    """

    STATUS_CODE = 400
    ERROR_CODE = "InvalidRequest"

    def get_error_message(self):
        bad_headers = set()
        if self.bad_keys:
            bad_headers.update(self.bad_keys)
        if self.bad_values:
            bad_headers.update(self.bad_values.keys())
        bad_headers = sorted(bad_headers)
        return f"Missing or invalid headers: {', '.join(bad_headers)}."

    def __init__(
        self,
        *,
        event_headers: Dict[str, str],
        bad_keys: List[str],
        bad_values: Dict[str, str],
        **kwargs,
    ):
        self.event_headers = event_headers
        self.bad_keys = bad_keys
        self.bad_values = bad_values

        if "internal_message" not in kwargs:
            message_parts = []
            if bad_keys:
                message_parts.append(f"missing keys {','.join(bad_keys)}")
            if bad_values:
                s = ",".join(f"{key}={value}" for key, value in bad_values.items())
                message_parts.append("invalid values " + s)
            kwargs["internal_message"] = f"Bad headers: {' and '.join(message_parts)}."

        super().__init__(**kwargs)


def validate_headers(
    event: Dict,
    *,
    keys: Optional[List[str]] = None,
    values: Optional[Dict[str, str]] = None,
    value_patterns: Optional[Dict[str, Union[str, re.Pattern]]] = None,
) -> Dict[str, str]:
    """Validate the headers in the event against the given requirements.

    Args:
        event (dict): The Lambda function input event.
        keys (list): A list of header keys that must be present.
        values (dict): A mapping of header keys to literal values that
            the parameters must take.
        value_patterns (dict): A mapping of header keys to regular
            expression patterns (either strings or re.Pattern objects) that
            the parameters must match.

    Returns:
        The validated headers.

    Raises:
        HeaderError: When the headers don't match
            the requirements.
    """
    format_version = get_event_format_version(event)
    if format_version == FormatVersion.APIGW_10:
        event_headers = dict(
            (key.lower(), ",".join(value))
            for key, value in event["multiValueHeaders"].items()
        )
    elif format_version == FormatVersion.APIGW_20:
        event_headers = event["headers"]
    else:
        raise NotImplementedError

    bad_keys = []
    if keys:
        for key in keys:
            if key not in event_headers:
                bad_keys.append(key)

    bad_values = {}
    if values:
        values = dict((key.lower(), value) for key, value in values.items())
        for key, value in values.items():
            if key not in event_headers:
                bad_keys.append(key)
            elif event_headers[key] != value:
                bad_values[key] = event_headers[key]
    if value_patterns:
        value_patterns = dict(
            (key.lower(), value) for key, value in value_patterns.items()
        )
        for key, value_regex in value_patterns.items():
            if key not in event_headers:
                bad_keys.append(key)
            elif not re.search(value_regex, event_headers[key]):
                bad_values[key] = event_headers[key]

    if bad_keys or bad_values:
        raise HeaderError(
            event_headers=event_headers,
            bad_keys=bad_keys,
            bad_values=bad_values,
            keys=keys,
            values=values,
            value_patterns=value_patterns,
        )

    return event_headers


def headers(
    *,
    keys: Optional[List[str]] = None,
    values: Optional[Dict[str, str]] = None,
    value_patterns: Optional[Dict[str, Union[str, re.Pattern]]] = None,
):
    """Validate the headers in the event against the given requirements.

    The following APIErrorResponse subclasses are used:
        HeaderError: When the headers don't match
            the requirements.

    Args:
        event (dict): The Lambda function input event.
        keys (list): A list of header keys that must be present.
        values (dict): A mapping of header keys to literal values that
            the parameters must take.
        value_patterns (dict): A mapping of header keys to regular
            expression patterns (either strings or re.Pattern objects) that
            the parameters must match.
    """
    return _get_decorator(
        validate_headers, keys=keys, values=values, value_patterns=value_patterns
    )


def _match_content_type_eq(content_type: str, accept: str):
    if accept == "*/*":
        return True
    mime_type = content_type.split(";")[0].strip()
    if accept.endswith("/*"):
        first_part = mime_type.split("/")[0]
        return first_part == accept.split("/")[0]
    return mime_type == accept


def _match_content_type_contains(accept_list: List[str], content_type: str):
    for accept in accept_list:
        if _match_content_type_eq(content_type, accept):
            return True
    return False


_content_type_matcher = (_match_content_type_eq, _match_content_type_contains)


class ContentTypeError(APIErrorResponse):
    STATUS_CODE = 415
    ERROR_CODE = "InvalidContentType"

    def get_error_message(self) -> str:
        if len(self.valid_content_types) == 1:
            return f"Content type must be {self.valid_content_types[0]}."
        return f"Content type must be one of: {', '.join(self.valid_content_types)}."

    # TODO: make this work
    # def get_headers(self, headers: Optional[Dict[str, str]]=None) -> Optional[Dict[str, Union[str, List[str]]]]:
    #     if headers is not None:
    #         headers = headers.copy()
    #     else:
    #         headers = {}
    #         if self.HEADERS:
    #             headers.update(self.HEADERS)
    #     headers["accept-post"] = ", ".join(self.valid_content_types)
    #     return headers

    def __init__(
        self,
        *,
        event_content_type: str,
        valid_content_types: Union[str, List[str]],
        **kwargs,
    ):
        if isinstance(valid_content_types, str):
            valid_content_types = [valid_content_types]
        self.event_content_type = event_content_type
        self.valid_content_types = valid_content_types

        if "internal_message" not in kwargs:
            if event_content_type is None:
                kwargs["internal_message"] = "Content-Type is missing."
            else:
                kwargs[
                    "internal_message"
                ] = f"Content-Type {event_content_type} not in valid set {{{', '.join(valid_content_types)}}}."

        super().__init__(**kwargs)


def validate_content_type(event: Dict, content_type: Union[str, List[str]]) -> str:
    """Validate the content type in the event.

    Args:
        event (dict): The Lambda function input event.
        content_type: A string or list of strings containing content types to match,
            including wildcards.

    Returns:
        The validated content type.

    Raises:
        ContentTypeError: When the content type does not match.
    """
    format_version = get_event_format_version(event)
    if format_version == FormatVersion.APIGW_10:
        event_content_type = None
        for key, value in event["headers"].items():
            if key.lower() == "content-type":
                event_content_type = value
    elif format_version == FormatVersion.APIGW_20:
        event_headers = event["headers"]
        event_content_type = event_headers.get("content-type")
    else:
        raise NotImplementedError
    if not event_content_type:
        raise ContentTypeError(
            event_content_type=None, valid_content_types=content_type
        )
    elif not _matches(event_content_type, content_type, matcher=_content_type_matcher):
        raise ContentTypeError(
            event_content_type=event_content_type, valid_content_types=content_type
        )
    return event_content_type


def content_type(content_type: Union[str, List[str]]):
    """Validate the content type in the event.

    The following APIErrorResponse subclasses are used:
        ContentTypeError: When the content type does not match.

    Args:
        event (dict): The Lambda function input event.
        content_type: A string or list of strings containing content types to match,
            including wildcards.
    """
    return _get_decorator(validate_content_type, content_type=content_type)


class QueryParameterError(APIErrorResponse):
    """APIErrorResponse for missing or invalid query parameters.

    The internal_message describes the query parameters keys and values in
    the request that do not match the requirements.
    The response will have status 400, error code InvalidRequestError and
    an error message listing the missing or invalid query parameter keys.

    When raised by validate_query_parameters(), the kwargs attribute will
    additionally contain the keys, values, and value_patterns passed to it.

    Attributes:
        event_query_parameters: The query parameters from the event.
        bad_keys: The required query parameters that are missing from the request.
        bad_values: The required query parameters that are present in the request
            but have an invalid value.
    """

    STATUS_CODE = 400
    ERROR_CODE = "InvalidRequest"

    def get_error_message(self):
        bad_query_parameters = set()
        if self.bad_keys:
            bad_query_parameters.update(self.bad_keys)
        if self.bad_values:
            bad_query_parameters.update(self.bad_values.keys())
        bad_query_parameters = sorted(bad_query_parameters)
        return f"Invalid query parameters: {', '.join(bad_query_parameters)}."

    def __init__(
        self,
        *,
        event_query_parameters: Dict[str, str],
        bad_keys: List[str],
        bad_values: Dict[str, str],
        **kwargs,
    ):
        self.event_query_parameters = event_query_parameters
        self.bad_keys = bad_keys
        self.bad_values = bad_values

        if "internal_message" not in kwargs:
            message_parts = []
            if bad_keys:
                message_parts.append(f"missing keys {','.join(bad_keys)}")
            if bad_values:
                s = ",".join(f"{key}={value}" for key, value in bad_values.items())
                message_parts.append("invalid values " + s)
            kwargs[
                "internal_message"
            ] = f"Bad parameters: {' and '.join(message_parts)}."

        super().__init__(**kwargs)


def validate_query_parameters(
    event: Dict,
    *,
    keys: Optional[List[str]] = None,
    values: Optional[Dict[str, str]] = None,
    value_patterns: Optional[Dict[str, Union[str, re.Pattern]]] = None,
) -> Dict[str, str]:
    """Validate the query parameters in the event against the given requirements.

    Args:
        event (dict): The Lambda function input event.
        keys (list): A list of query parameter names that must be present.
        values (dict): A mapping of query parameter names to literal values that
            the parameters must take.
        value_patterns (dict): A mapping of query parameter names to regular
            expression patterns (either strings or re.Pattern objects) that
            the parameters must match.

    Returns:
        The validated query parameters.

    Raises:
        QueryParameterError: When the query parameters don't match
            the requirements.
    """
    format_version = get_event_format_version(event)
    if format_version == FormatVersion.APIGW_10:
        event_query_parameters = dict(
            (key, ",".join(value))
            for key, value in event["multiValueQueryStringParameters"].items()
        )
    elif format_version == FormatVersion.APIGW_20:
        if "queryStringParameters" in event:
            event_query_parameters = event["queryStringParameters"]
        else:
            event_query_parameters = {}
    else:
        raise NotImplementedError

    bad_keys = []
    if keys:
        for key in keys:
            if key not in event_query_parameters:
                bad_keys.append(key)

    bad_values = {}
    if values:
        for key, value in values.items():
            if key not in event_query_parameters:
                bad_keys.append(key)
            elif event_query_parameters[key] != value:
                bad_values[key] = event_query_parameters[key]
    if value_patterns:
        for key, value_regex in value_patterns.items():
            if key not in event_query_parameters:
                bad_keys.append(key)
            elif not re.search(value_regex, event_query_parameters[key]):
                bad_values[key] = event_query_parameters[key]

    if bad_keys or bad_values:
        raise QueryParameterError(
            event_query_parameters=event_query_parameters,
            bad_keys=bad_keys,
            bad_values=bad_values,
            keys=keys,
            values=values,
            value_patterns=value_patterns,
        )

    return event_query_parameters


def query_parameters(
    *,
    keys: Optional[List[str]] = None,
    values: Optional[Dict[str, str]] = None,
    value_patterns: Optional[Dict[str, Union[str, re.Pattern]]] = None,
):
    """Validate the query parameters in the event against the given requirements.

    The following APIErrorResponse subclasses are used:
        QueryParameterError: When the query parameters don't match
            the requirements.

    Args:
        event (dict): The Lambda function input event.
        keys (list): A list of query parameter names that must be present.
        values (dict): A mapping of query parameter names to literal values that
            the parameters must take.
        value_patterns (dict): A mapping of query parameter names to regular
            expression patterns (either strings or re.Pattern objects) that
            the parameters must match.
    """
    return _get_decorator(
        validate_query_parameters,
        keys=keys,
        values=values,
        value_patterns=value_patterns,
    )
