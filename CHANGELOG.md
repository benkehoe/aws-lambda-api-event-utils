# Changelog

# v0.2
* If a keyword argument named `error_message` is provided to the `APIErrorResponse` constructor, that will be used for the error message in the default `get_error_message()` method.
    * All subclasses of `APIErrorResponse` in this package that override `get_error_message()` also use this behavior.
* Use better error message for JSON schema validation errors.

# v0.1

Initial release.
