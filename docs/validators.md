# Validation

## Decorator API

The decorator API allows for concise, Pythonic expression of validation conditions.
Modification of the error handling behavior happens through class fields on the `APIErrorResponse` exception class.

To log a message when an `APIErrorResponse` exception is being handled, set `APIErrorResponse.DECORATOR_LOGGER` to a `logging.Logger` or a callable that takes a single string.

Using all of the decorators will also catch `APIErrorResponse` if raised from inside the handler (i.e., if you make your own subclass).
If you want this functionality but are not using any of the decorators, you can use `@APIErrorResponse.decorator(format_version)`.

```python
APIErrorResponse.DECORATOR_LOGGER = print

@event_format_version(API_GW_20)
@method("POST")
@path("/my/path")
@headers(values={"x-api-key": API_KEY})
@content_type("application/json")
@query_parameters(keys=["my_param"])
@json_body(schema=SCHEMA)
def handler(event, context):
    # code...
```

## Function API

The function API allows for more control over the error handling and the returned response.
Each function returns the validated data.
You must enclose calls to validation functions with a try-except block that catches `APIErrorResponse`.
You can then inspect the exception, log it, etc., and then return `e.get_response()` or a response of your own making.

Each validation function takes the event and some other parameters.

```python
try:
    validate_event_version(event, API_GW_20)
    validate_method(event, "POST")
    validate_path(event, "/my/path")
    validate_headers(event, values={"x-api-key": API_KEY})
    validate_content_type(event, "application/json")
    query_parameters = validate_query_parameters(event, keys=["my_param"])
    my_param = query_parameters["my_param"]
    payload = get_json_body(event, schema=SCHEMA)
except APIErrorResponse as e:
    print(type(e), e.internal_message) # log the message
    response = e.get_response(event=event) # all the inputs to get_response() are available
    return response
```

## Validators

### Event format

Validate the event format with the `@event_format_version` decorator or the `validate_event_format_version()` function.

This takes one of the package fields `API_GW_10` for the API Gateway Lambda proxy event format 1.0, and `API_GW_20` for version 2.0.
`validate_event_format_version()` returns the validated event format version.

By default, if the incoming event's format version does not match, a `TypeError` will be raised, since essentially the API Gateway is invoking the Lambda with the wrong type.
This will cause an error in the Lambda function, which will cause API Gateway to return an error (typically status 500) to the caller.

To instead raise an `FormatVersionError` (that is, to have the Lambda complete successfully), set `use_error_response=True`.
The response will have status 500, error code `InternalServiceError` and message `An error occurred.`, as no details need be exposed to the client.
The `internal_message` describes the expected and received event format versions.

```python
@event_format_version(API_GW_20)
def handler(event, context):
    # code...
```

```python
def handler(event, context):
    try:
        validate_event_format_version(event, API_GW_20)
    except APIErrorResponse as e:
        return e.get_response(event=event)
    # code...
```

### HTTP request method

Validate the HTTP request method with the `@method` decorator or the `validate_method()` function.

This takes a single HTTP method or a list of methods.
`validate_method()` returns the validated HTTP request method from the event.

If the method does not match, the `validate_method()` function raises `UnsupportedMethodError`.

The error response is status 415 (Unsupported Method), the error code is `UnsupportedMethod`, and the error message says the method is not allowed.
The `internal_message` describes the received HTTP method and the allowed values.

### Path (static string)

Validate the URL path against a static string with the `@path` decorator or the `validate_path()` function.

This takes a single path or a list of paths.
`validate_path()` returns the validated path and the path parameters (as provided in the event).

By default, the stage component of the path is removed from the path before validation; set `disable_stage_removal=True` to disable this.

If the path does not match, the `validate_path()` function raises `PathNotFoundError`.

The error response is status 404 (Not Found), the error code is `PathNotFound`, and the error message says the path was not found.
The `internal_message` describes the received path and the allowed values.

### Path (regular expression)

Validate the URL path against a regular expression with the `@path_regex` decorator or the `validate_path_regex()` function.

This takes a single regular expression as a string or a `re.Pattern` object.
`validate_path_regex()` returns the validated path and the path parameters, as provided in the event and overlaid with named groups from the regular expression match.

By default, the stage component of the path is removed from the path before validation; set `disable_stage_removal=True` to disable this.

If the path does not match, the `validate_path_regex()` function raises `PathNotFoundError`.

The error response is status 404 (Not Found), the error code is `PathNotFound`, and the error message says the path was not found.
The `internal_message` describes the received path and the regex.

### Path parameters

Validate the path parameters with the `@path_parameters` decorator or the `validate_path_parameters()` function.

This takes `keys`, a list of path parameters that are required to exist, `values`, a dict of parameter names that are required to have the given values, and `value_patterns`, a dict of parameter names that are required to match the given regular expressions.
`validate_path_parameters()` returns the path and the path parameters.

By default, the stage component of the path is removed from the path before validation; set `disable_stage_removal=True` to disable this.

If the event is missing path parameters listed in `keys`, the path parameters in `values` are missing or do not match the given values, or the path parameters in `value_patterns` are missing or do not match the given patterns, the `validate_path_parameters()` function raises `PathParameterError`.

The error response is status 404 (Not Found), the error code is `PathNotFound`, and the error message says the path was not found.
The `internal_message` describes the missing and invalid path parameters.

### Headers

Validate the existence and values of headers with the `@headers` decorator or the `validate_headers()` function.

This takes `keys`, a list of headers that are required to exist, `values`, a dict of header names that are required to have the given values, and `value_patterns`, a dict of header names that are required to match the given regular expressions.
`validate_headers()` returns the headers as a `dict` with string values, in the API Gateway Lambda proxy version 2.0 format (that is, with multi-value headers as comma-separated strings).

If the event is missing headers listed in `keys`, the headers in `values` are missing or do not match the given values, or the headers in `value_patterns` are missing or do not match the given patterns, the `validate_headers()` function raises `HeaderError`.

The error response is status 400, the error code is `InvalidRequest`, and the error message lists the missing or invalid header names.
The `internal_message` describes the missing and invalid headers.

### Content type

Validate the `Content-Type` header with the `@content_type` decorator or the `validate_content_type()` function.
This is a specialization of the header validation listed above.

This takes a single content type or list of content types.
`validate_content_type()` returns the validated content type.

If the content type does not match, `validate_content_type()` raises `ContentTypeError`.

The error response is 415 (Unsupported Media Type), the error code is `InvalidContentType`, and the error message lists the valid content types.
The error response will also have an `Accept` header added with the valid content types.
The `internal_message` describes the received or missing content type and the valid values.

### Query parameters

Validate the existence and values of query parameters with the `@query parameters` decorator or the `validate_query_parameters()` function.

This takes `keys`, a list of query parameters that are required to exist, `values`, a dict of query parameter names that are required to have the given values, and `value_patterns`, a dict of query parameter names that are required to match the given regular expressions.
`validate_query_parameters()` returns the query parameters as a `dict` with string values, in the API Gateway Lambda proxy version 2.0 format (that is, with multi-value query parameters as comma-separated strings).

If the event is missing query parameters listed in `keys`, the query parameters in `values` are missing or do not match the given values, or the query parameters in `value_patterns` are missing or do not match the given patterns, the `validate_query_parameters()` function raises `QueryParameterError`.

The error response is status 400, the error code is `InvalidRequest`, and the error message lists the missing or invalid query parameter names.
The `internal_message` describes the missing and invalid query parameters.
