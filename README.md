# aws-lambda-api-event-utils

There are many other libraries, in Python and in other languages, for handling HTTP events in Lambda.
So why this library?

All the libraries I have seen are oriented towards providing traditional HTTP response handling, in the web server style, for Lambda functions.
They are often based on an actual web framework, generally provide routing, etc.

This library does none of that.

It is intended to be used in the serverless native style, where routing and validation logic is pushed into API Gateway whenever possible.
It is intended to make API handlers more Pythonic and less webserver-like, while retaining the use of proxy integrations with API Gateway.

The functionality in this library can be put into two categories:
* More Pythonic handlers: interact less with the raw proxy request and response objects, deal with client errors by raising Python exceptions, make JSON payloads easier.
* Request validation: while as much validation as possible should be done at the API Gateway layer, there are situations where you may need to validate the request in the Lambda function instead. The code in your function should be able to rely on the request being validated.

Note that REST APIs using the Lambda proxy integration does not fully validate request payloads ([read details here](https://rboyd.dev/089999bf-b973-42ed-9796-6167539269b8)), and HTTP APIs do not do any validation.

# Examples

```python
from aws_lambda_api_event_utils import *

import datetime
import decimal

# When an APIErrorResponse is caught by a decorator, it's turned into an
# API response that by default has a payload of the form:
# {
#   "Error": {
#     "Code": <error_code>,
#     "Message": <error_message>
#   }
# }

@api_event_handler
def handler(event, context):
    try:
        # some code
    except SomePayloadError:
        # this will re-raise as an APIErrorResponse so that it can be caught by
        # the decorator and converted to a response to API Gateway using the
        # given status code and a JSON response body with an error code set to
        # the exception class name and an error message set to the
        # stringified exception
        APIErrorResponse.re_raise_as(400)

    try:
        # some code
    except SomeOtherPayloadError:
        # To expose fewer internal details, use this standard exception
        # which results in a status 400, a generic error code,
        # and the given error message
        # There's also APIErrorResponse.from_status_code() to create generic
        # exceptions for other status codes
        raise InvalidRequestError("Something's wrong with the request.")

    try:
        # some code
    except SomeServiceError:
        # In general, server-side problems should be raised as regular exceptions
        # causing the Lambda function to error out. This automatically
        # means API Gateway will return 500 and you'll see these errors in your
        # Lambda function metrics
        raise

    # more code

    # The decorator will convert this to a response with status code 200,
    # like the HTTP API Lambda proxy integration does automatically
    # but it works with REST APIs too, and it does more:
    # - JSON serialization of datetimes and decimals is provided
    # - returning a string will be converted to a text/plain response
    # - returning bytes will be converted to an application/octet-stream response
    return {
        "my_field": "my_value",
        "timestamp": datetime.datetime.now(datetime.timezone.utc),
        "dynamodb_number": decimal.Decimal("8.1")
    }
```

```python
from aws_lambda_api_event_utils import *

# Make subclasses of APIErrorResponse for your own purposes
# The error code is the class name by default
# The error message can be static or a template
# The template can use any fields of the exception
# or any keywords passed to the constructor
class FailedProcessing(APIErrorResponse):
    STATUS_CODE = 400
    ERROR_MESSAGE_TEMPLATE = "Failed during {step}."

# ApiErrorResponses caught by the decorator will log the internal message
# using this callable or logging.Logger
APIErrorResponse.DECORATOR_LOGGER = print

@api_event_handler
def handler(event, context):
    try:
        # some code
    except SomeInputError as e:
        # This will be caught by the decorator and converted to a response
        # You must provide an internal message suitable for logging
        # even if APIErrorResponse.DECORATOR_LOGGER is not set
        # keyword arguments are stored and can be referenced in
        # ERROR_MESSAGE_TEMPLATE
        raise MyError(f"Processing failed: {e}.", step="step 1")

    try:
        # some code
    except SomeOtherInputError as e:
        # You can also override the error message if it's using the default
        # constructor or kwargs are passed to the APIErrorResponse constructor
        raise MyError(f"Processing failed: {e}.", step="step 2",
            error_message="This error message overrides the template.")

    # return some other status code (or a fully-customized response)
    # with make_response()
    # format version can be provided implicitly as the Lambda function
    # input event rather than having to provide it explicitly
    return make_response(201, {"status": "created"}, format_version=event)
```

```python
from aws_lambda_api_event_utils import *

@api_event_handler
def handler(event, context):
    # set response headers and cookies through the Lambda context object
    # this works for both returning a value and raising an APIErrorResponse
    context.api_response_headers = {"my_header_key": "my_header_value"}
    return {"my_field": "my_value"}
```

```python
# JSON schema validation requires the jsonschema package
# it is not required by this package by default
# install it separately or install this package with the
# jsonschema extra as:
# aws-lambda-api-event-utils[jsonschema]
from aws_lambda_api_event_utils import *

SCHEMA = {
    "type": "object",
    "properties": {
        "some_field": {
            "type": "string",
        }
    },
    "required": ["some_field"]
}

# any decorator from the package provides the base functionality
# of @api_event_handler
# Invalid JSON and JSON that violates the schema will generate
# an error response
@json_body(SCHEMA)
def handler(event, context):
    payload = event["body"] # parsed and validated JSON

    try:
        # some code
    except SomeError:
        APIErrorResponse.re_raise_as(400)

    return {"status": "success"}
```

```python
from aws_lambda_api_event_utils import *

# @api_event_handler is the "no-validation" decorator
# using any decorator provides the APIErrorResponse and
# handler-return-value processing
@event_format_version(API_GW_20)
@method("POST")
@path("/my/path")
@headers(keys=["x-api-key"])
@query_parameters(keys=["my_param"])
@json_body(enforce_content_type=True) # require Content-Type: application/json header
def handler(event, context):
    my_param = event["queryStringParameters"]["my_param"]
    payload = event["body"] # parsed and validated JSON

    # do work with my_param and payload

    return {"status": "success"}
```

```python
import os, http, boto3
from aws_lambda_api_event_utils import *

S3_BUCKET_NAME = os.environ["S3_BUCKET_NAME"]

# why use a session? read an explainer:
# https://ben11kehoe.medium.com/boto3-sessions-and-why-you-should-use-them-9b094eb5ca8e
BOTO3_SESSION = boto3.Session()
S3_CLIENT = BOTO3_SESSION.client("s3")

# maybe this route is /obj/{param}
# the regex can constrain it further
# and capturing groups become path parameters
@method("GET")
@path_regex("/data/obj-(?P<s3_key>\w+)")
@headers(keys=["x-api-key"])
def handler(event, context):
    api_key = event["headers"]["x-api-key"]
    s3_key = event["pathParameters"]["s3_key"]

    if not is_authorized(api_key, s3_key):
        # generic errors for all HTTP 4XX and 5XX status codes
        raise APIErrorResponse.from_status_code(http.HTTPStatus.FORBIDDEN)

    presigned_url = S3_CLIENT.generate_presigned_url("get_object",
        Params={
            "Bucket": S3_BUCKET_NAME,
            "Key": s3_key
        },
        ExpiresIn=30
    )

    # create an appropriate redirect response
    # format version can be provided implicitly as the Lambda function
    # input event rather than having to provide it explicitly
    return make_redirect(
        http.HTTPStatus.TEMPORARY_REDIRECT,
        presigned_url,
        format_version=event
    )
```

# Installation

```
pip install aws-lambda-api-utils

# with jsonschema validation support
pip install aws-lambda-api-utils[jsonschema]
```

# API event formats

AWS does not define a global event format convention.
API Gateway Lambda proxy events, which are the focus of this library, come in three styles: the REST API format and HTTP API format version 1.0, which are essentially the same, and HTTP API format version 2.0.

This library defines the `FormatVersion` enum, which represents these as two formats: `FormatVersion.APIGW_10` and `FormatVersion.APIGW_20`.

The `get_event_format_version()` function takes an event and returns the event format version, or `None` if the event format version cannot be determined.
By default, the event format version is cached within the event (the key used for this is available in the `EVENT_FORMAT_VERSION_CACHE_KEY` module field) to speed up multiple calls to `get_event_format_version()` (e.g., across multiple validations).
This can be disabled in this function by setting `disable_cache=True`; it cannot be disabled when using validation functions or decorators.

# Decorators

Using at least one decorator from this package is required to get the `APIErrorResponse` and handler return value processing described below.
Using one or more validation decorators is sufficient; if no validation decorators are needed, `@api_event_handler` provides this functionality as a standalone decorator.

# Request body processing

To retrieve the body from the event, use the `get_body()` function.
This returns the body value as-is if it has already been parsed into an object (e.g., by the `@json_body` decorator), as `bytes` if `isBase64` is set to `True` in the event, or as a string otherwise.
To validate that the event contains a binary body or not, set the `type` parameter to `BodyType.str` or `BodyType.bytes`, which will cause `PayloadBinaryTypeError` to be raised if it doesn't match.

To parse the body as JSON and optionally validate the JSON, use the `@json_body` decorator or the `get_json_body()` function.

This takes an optional JSON schema, which will only work if the package has been installed with the `jsonschema` extra, or the `jsonschema` package has been installed separately.
`get_json_body()` returns the parsed and validated JSON body; it does not modify the event.
`@json_body` replaces the body in the event with the parsed and validated JSON body; it can be retrieved directly or with the `get_body()` function.

Without a schema, the decorator can be used with or without parentheses.

If the body cannot be parsed as JSON, `get_json_body()` raises `PayloadJSONDecodeError`.
The exception will have an `internal_message` that includes the `json.JSONDecodeError`.
The error response is status 400, the error code is `InvalidPayload`, and the error message says the payload must be JSON.

By default, HTTP methods that are not expected to have request bodies, like GET, do not cause an error.
Set `enforce_on_optional_methods=True` to enforce that any request has a valid JSON body.

For convenience, you can enforce that the `Content-Type` header is set to `application/json` by setting `enforce_on_optional_methods=True`.
This uses the [`validate_content_type()` function](docs/validators.md#Content-type).

If the body can be parsed as JSON, but does not validate against the provided schema, `get_json_body()` raises `PayloadSchemaViolationError`.
The exception will have an `internal_message` that includes the schema error.
The error response is status 400, the error code is `InvalidPayload`, and the error message provides the schema error.

# Handler return value processing

When a decorator is used on the Lambda function handler, the return value from the handler is inspected.
If it is a `dict` containing a `"statusCode"` field, it is considered to be a response and returned intact.

Otherwise, it constructs a response using `make_response()`, with the following logic:
* The status code is 200.
* If the return value is of type `bytes`, it will be base64-encoded and a default content-type of `application/octet-stream` will be applied.
* If the return value is of type `str`, it will be used as-is and a default content-type of `text/plain` will be applied.
* Otherwise, the return value will be JSON-serialized and a default content-type of `application/json` will be applied.

When serializing to JSON, objects of `datetime.datetime`, `datetime.date`, and `datetime.time` and `decimal.Decimal` classes are handled.
By default, the `datetime` classes are serialized with their `isoformat()` methods and UTC timezones are converted from using an `+00:00` offset to the plain `Z` suffix.
By default, `decimal.Decimal` is serialized as a float.
This can be changed with the `set_default_json_serialization_options()` function, and also `make_response()` can be provided with a `JSONSerializationOptions` override directly.

Headers and cookies can be set in the `api_response_headers` and `api_response_cookies` fields on the Lambda context object (the decorator creates these fields).

# Redirects

A redirect response can be generated using the `make_redirect()` function, which takes a 3XX status code and a URL to redirect to.

# `APIErrorResponse`
The requirement of the handler returing a structured value when an error occurs is not particularly Pythonic; instead, we should raise an exception and it should cauase the right thing to happen.
This functionality is provided by the `APIErrorResponse` exception class.
An `APIErrorResponse` subclass has a status code, and knows how to create the response to return to API Gateway through the `get_response()` method.

The most basic usage is when you catch an exception that should cause an error to be returned to the client, you can call `APIErrorResponse.re_raise_as()` in the `except` block, providing the status code for the response.
This will pick up the active exception and use it for the response body ([see below](#Error-response-body) for error response body details): the error code will be the exception class name, and the error message will be the stringified exception.
You can provide an internal message for logging ([see below](#Error-logging)), or it will default to a string containing the error code and error message.

You can create your own subclasses of `APIErrorResponse` to make exceptions that will be caught by the decorators and turned into error responses as defined by the subclass.
This package also provides a generic `InvalidRequestError` exception (an `APIErrorResponse` subclass), which has a status code of 400 and an error code of `InvalidRequest`, and an error message you provide.
You can additionally call `APIErrorResponse.from_status_code()` to generate a generic exception instance for a given 4XX or 5XX status code.

Validators in this package raise subclasses of `APIErrorResponse` for validation failures; see the docs for each validator for more information.

When using a decorator to catch `APIErrorResponse` exceptions, headers and cookies for the response can be set from within the handler using the `api_response_headers` and `api_response_cookies` fields on the Lambda context object (the decorator creates these fields).

## Error logging

To log `APIErrorResponse` exceptions caught in a decorator, you can set `APIErrorResponse.DECORATOR_LOGGER` to a callable (e.g., `print`) or a `logging.Logger` object.
This will log the `internal_message` field of the `APIErrorResponse` exception.
By default, this does not include a traceback; set `APIErrorResponse.DECORATOR_LOGGER_TRACEBACK` to `True` to include one.

## Response generation

To generate a response directly, use the `get_response()` method (this is only necessary if you're catching `APIErrorResponse`/subclasses yourself, rather than using a decorator).
This method must be provided an `format_version` to determine the format of the response; this can either be a format version directly, or the Lambda function input event (to determine the format version from).
It can optionally take a `body`, `headers`, and `cookies` to pass to the class methods that determine those values for the response.

By default, the response body generated for an `APIErrorResponse` looks like the following:

```json
{
    "Error": {
        "Code": "<error code>",
        "Message": "<error message>"
    }
}
```

These field names can be changed by altering the `ERROR_PARENT_FIELD`, `ERROR_CODE_FIELD`, and `ERROR_MESSAGE_FIELD` class fields on `APIErrorResponse`; if `ERROR_PARENT_FIELD` is set to `None`, the error code and error message will be put at the top level.

## Subclassing `APIErrorResponse`

Create your own subclasses of `APIErrorResponse` to represent your own error conditions and how they should be mapped into an API response.

The minimal subclass looks like this:
```python
class MyError(APIErrorResponse):
    STATUS_CODE = 400 # the status code for the response

    ERROR_MESSAGE = "My error message." # static message

# usage:
# APIErrorResponse requires an internal message be provided to its constructor.
raise MyError("This is the internal error message for logging")

# Providing a keyword argument named error_message will override the error message
raise MyError("This is the internal error message for logging",
    error_message="Override error message.")
```

The error code defaults to the class name, but can be set explicitly with the `ERROR_CODE` class field.

The error message can be a string template using the `ERROR_MESSAGE_TEMPLATE` field, rather than a static value.
The template uses the standard `str.format()` method.
It can reference any instance fields.
For convenience, any keyword arguments provided to the `APIErrorResponse` constructor are stored and can also be referenced in the template, meaning you don't need to define your own constructor.

```python
class MyError(APIErrorResponse):
    STATUS_CODE = 400 # the status code for the response

    ERROR_MESSAGE_TEMPLATE = "My error message: {msg}." # static message

# usage:
raise MyError("This is the internal error message for logging.",
    msg="value for the error message template")

# Providing a keyword argument named error_message will override the error message
raise MyError("This is the internal error message for logging.",
    error_message="Override error message.")
```

You can provide your own constructor to take more detailed information, and then construct the internal message there.
You can override `get_error_message()` to include more logic.

```python
class MyError(APIErrorResponse):
    STATUS_CODE = 400 # the status code for the response

    # taking kwargs and passing them to APIErrorResponse to allow
    # overriding the error message like normal
    def __init__(self, bad_param, **kwargs):
        self.bad_param = bad_param
        if "internal_message" not in kwargs:
            kwargs["internal_message"] = f"Bad param: {bad_param}"
        super().__init__(**kwargs)

    def get_error_message(self):
        # allow overriding error message
        # self.kwargs are kwargs to APIErrorResponse
        if "error_message" in self.kwargs:
            return self.kwargs["error_message"]
        if self.bad_param == "secret":
            return "Bad parameter."
        else:
            return f"Bad parameter: {self.bad_param}."


# usage:
raise MyError("param1")

# Providing a keyword argument named error_message will override the error message
raise MyError("secret", error_message="Bad secret.")
```

### Headers and cookies
Override the `get_headers()` and `get_cookies()` methods to set the headers and cookies in the response.
They each take the value provided to `get_response()` as input.

### Error response body
The response body is constructed in the `get_body()` method; the default implementation uses the `get_error_code()` and `get_error_message()` fields with the `make_error_body()` class method.

The `get_error_code()` method has a default implementation that uses the `ERROR_CODE` class field if it is set, falling back to the exception class name.

The `get_error_message()` method has a default implementation that uses the `error_message` keyword argument to the `APIErrorResponse` constructor if it was given, otherwise using the following class fields.
`ERROR_MESSAGE` class field if it is set, otherwise using the `ERROR_MESSAGE_TEMPLATE` class field if it is set, calling the string `format()` method with `vars(self)` as inputs (that is, you can reference fields from the exception in the template).
If neither `ERROR_MESSAGE` or `ERROR_MESSAGE_TEMPLATE` are set, the message `An error occurred.` is used.

The `make_error_body()` class method constructs a body of the following form, taking the error code and message as input:
```json
{
  "Error": {
    "Code": "MyErrorCode",
    "Message": "My error message."
  }
}
```
You can change the error code field name with the `ERROR_CODE_FIELD` class field, and the error message field name with the `ERROR_MESSAGE_FIELD` class field.
You can change the top-level field name by setting the `ERROR_PARENT_FIELD` class field, or by setting it to `None` the error code and message fields will be set at the top level.

# Validators

Validation is provided with both a decorator API and a functional API.
See the full documenation on validators [here](docs/validators.md).

# Creating responses directly

The `make_response()` function formats a response for the function according to a given format version.
The format version must be specified, but can be given implicitly by setting `format_version` to the Lambda function input event.

If the `body` arugment is not a string or bytes, it will be serialized to JSON, and a `Content-Type` header of `application/json` will be added.

The function signature is as follows:
```python
make_response(
    status_code: Union[int, http.HTTPStatus],
    body: Optional[Any],
    *,
    format_version: Union[FormatVersion, Dict],
    headers: Optional[Dict[str, Union[str, List[str]]]] = None,
    cookies: Optional[List[str]] = None,
    json_serialization_options: Optional[JSONSerializationOptions] = None,
) -> Dict:
```

When your function raises an exception that should be turned into a response, but you can't or don't want to modify the code to make that exception an `APIErrorResponse` subclass ([see above](#subclassing-errorresponse) for details), you can use the `APIErrorResponse.make_response_from_exception()` class method.
This takes a status code and exception, and creates the error response with the error code set to the exception class name and the error message set to the stringified exception.
If the exception is an `APIErrorResponse` subclass, the result will be a call to its `get_response()` method, but it will raise an error if the status codes don't match.
The method signature is as follows:

```python
APIErrorResponse.make_response_from_exception(
    status_code: Union[int, http.HTTPStatus],
    exception: Exception,
    *,
    format_version: Union[FormatVersion, Dict],
    headers: Optional[Dict[str, Union[str, List[str]]]] = None,
    cookies: Optional[List[str]] = None,
) -> Dict:
```
