import os
import json

import aws_lambda_api_event_utils as api_utils


def _handler(event, context, event_format_version):
    print("event:", json.dumps(event))

    try:
        api_utils.validate_event_format_version(event, event_format_version)

        validation = json.loads(event["headers"].get("x-validation", "{}"))
        print("validation:", json.dumps(validation))
        for key, value in validation.items():
            if key.startswith("validate_") and hasattr(api_utils, key):
                func = getattr(api_utils, key)
                func(event, **value)
        body_validation = event["headers"].get("x-body-validation")
        if body_validation:
            body_validation = json.loads(body_validation)
            print(
                "body_validation:",
                json.dumps(body_validation),
            )
            if not body_validation.get("json"):
                kwargs = {}
                body_type = body_validation.get("type")
                if body_type:
                    kwargs["type"] = api_utils.BodyType.__members__[body_type]
                api_utils.get_body(event, **kwargs)
            else:
                schema = body_validation.get("schema")
                api_utils.get_json_body(event, schema=schema)

        response = {
            "body_validation": body_validation,
            "validation": validation,
            "event": event,
        }
        response = api_utils.make_response(
            status_code=200,
            body=response,
            format_version=event,
        )
    except api_utils.APIErrorResponse as e:
        print(f"{e.get_error_code()}: {e.internal_message}")
        response = e.get_response(
            format_version=api_utils.FormatVersion.APIGW_10,
            headers={"x-error-message": json.dumps(e.internal_message)},
        )
    print("response:", json.dumps(response))
    return response


def handler10(event, context):
    return _handler(event, context, api_utils.FormatVersion.APIGW_10)


def handler20(event, context):
    return _handler(event, context, api_utils.FormatVersion.APIGW_20)
