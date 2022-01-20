# Changelog

`aws-lambda-api-event-utils` uses [monotonic versioning](blog.appliedcompscilab.com/monotonic_versioning_manifesto/).

# v0.3
* Add [CORS support](README.md#CORS) with `CORSConfig` ([#1](https://github.com/benkehoe/aws-lambda-api-event-utils/issues/1)).
* Add support for [`fastjsonschema`](https://horejsek.github.io/python-fastjsonschema/) ([#2](https://github.com/benkehoe/aws-lambda-api-event-utils/issues/2)).
    * Install with the `fastjsonschema` extra.
    * If both `fastjsonschema` and `jsonschema` are installed, `fastjsonschema` is used.
    * `CompiledFastJSONSchema` class for compiled schemas.
* Rename `JSONSerializationOptions` to `JSONSerializationConfig` and `DatetimeSerializationOptions` to `DatetimeSerializationConfig`.
* Add `APIErrorResponse.from_exception()` replacing `APIErrorResponse.re_raise_as()`.
* Context object consolidated in a `DecoratorApiResponseConfig` object at `context.api_response`
* Add `get_default_headers()` method to `APIErrorResponse` for subclasses to override.

# v0.2
* If a keyword argument named `error_message` is provided to the `APIErrorResponse` constructor, that will be used for the error message in the default `get_error_message()` method.
    * All subclasses of `APIErrorResponse` in this package that override `get_error_message()` also use this behavior.
* Use better error message for JSON schema validation errors.

# v0.1

Initial release.
