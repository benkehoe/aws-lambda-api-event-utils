# Copyright 2021 Ben Kehoe
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

import pytest

import copy
import secrets

from aws_lambda_api_event_utils import *

from tests.events import *


def rand_str():
    return secrets.token_hex(4)


rand_str = lambda: secrets.token_hex(4)


def test_validate_headers():
    for integration_type in IntegrationType:
        event = Event(
            integration_type=integration_type,
            method="POST",
            path=Path(stage="live", path="/foo", resource="/foo"),
            body=None,
            headers={"header1": "value1", "header2": ["value1", "value2"]},
        )

        headers = validate_headers(event.get_event(), keys=["header1"])
        assert headers == {"header1": "value1", "header2": "value1,value2"}

        header_name = rand_str()
        with pytest.raises(HeaderError, match=header_name):
            validate_headers(event.get_event(), keys=[header_name])

        headers = validate_headers(event.get_event(), values={"header1": "value1"})

        headers = validate_headers(
            event.get_event(), values={"header2": "value1,value2"}
        )

        header_value = rand_str()
        with pytest.raises(HeaderError, match=f"header1=value1"):
            validate_headers(event.get_event(), values={"header1": header_value})

        header_name = rand_str()
        header_value = rand_str()
        with pytest.raises(HeaderError, match=header_name):
            validate_headers(event.get_event(), values={header_name: header_value})

        value_pattern = "ue1$"
        validate_headers(event.get_event(), value_patterns={"header1": value_pattern})

        value_pattern = "ue2$"
        validate_headers(event.get_event(), value_patterns={"header2": value_pattern})

        with pytest.raises(HeaderError, match="header2"):
            value_pattern = "ue1$"
            validate_headers(
                event.get_event(), value_patterns={"header2": value_pattern}
            )

        value_pattern = "ue1(,|$)"
        validate_headers(event.get_event(), value_patterns={"header2": value_pattern})


def test_headers_decorator():
    for integration_type in IntegrationType:
        event = Event(
            integration_type=integration_type,
            method="POST",
            path=Path(stage="live", path="/foo", resource="/foo"),
            body=None,
            headers={"header1": "value1", "header2": ["value1", "value2"]},
        )

        if integration_type in [
            IntegrationType.APIGW_REST,
            IntegrationType.APIGW_HTTP_10,
        ]:

            def validate_event(event):
                assert event["headers"] == {"header1": "value1", "header2": "value2"}
                assert event["multiValueHeaders"] == {
                    "header1": ["value1"],
                    "header2": ["value1", "value2"],
                }

        elif integration_type == IntegrationType.APIGW_HTTP_20:

            def validate_event(event):
                assert event["headers"] == {
                    "header1": "value1",
                    "header2": "value1,value2",
                }

        else:
            raise NotImplementedError

        @headers(keys=["header1"])
        def handler(event, context):
            validate_event(event)
            return {"statusCode": 200, "body": ""}

        response = handler(event.get_event(), None)
        assert response["statusCode"] == 200

        header_name = rand_str()

        @headers(keys=[header_name])
        def handler(event, context):
            return {"statusCode": 200, "body": ""}

        response = handler(event.get_event(), None)
        assert response["statusCode"] == 400

        @headers(values={"header1": "value1"})
        def handler(event, context):
            validate_event(event)
            return {"statusCode": 200, "body": ""}

        response = handler(event.get_event(), None)
        assert response["statusCode"] == 200

        @headers(values={"header2": "value1,value2"})
        def handler(event, context):
            validate_event(event)
            return {"statusCode": 200, "body": ""}

        response = handler(event.get_event(), None)
        assert response["statusCode"] == 200

        header_value = rand_str()

        @headers(values={"header1": header_value})
        def handler(event, context):
            return {"statusCode": 200, "body": ""}

        response = handler(event.get_event(), None)
        assert response["statusCode"] == 400

        header_name = rand_str()
        header_value = rand_str()

        @headers(values={header_name: header_value})
        def handler(event, context):
            return {"statusCode": 200, "body": ""}

        response = handler(event.get_event(), None)
        assert response["statusCode"] == 400


def test_set_header():
    ex_single = rand_str()
    ex_list = [rand_str(), rand_str()]

    new_single = rand_str()
    new_list = [rand_str(), rand_str()]

    # reuse the same list object
    # append should make new lists
    existing_base = {
        "single_single": ex_single,
        "single_list": ex_single,
        "list_single": ex_list,
        "list_list": ex_list,
    }

    new_base = {
        "SINGLE_SINGLE": new_single,
        "SINGLE_LIST": new_list,
        "LIST_SINGLE": new_single,
        "LIST_LIST": new_list,
    }

    setup = lambda: (copy.deepcopy(existing_base), copy.deepcopy(new_base))

    existing, _ = setup()
    new_key = rand_str()
    new_value = rand_str()
    result = set_header(existing, new_key, new_value, override=True)
    assert existing[new_key] == new_value
    assert result is None

    existing, _ = setup()
    new_key = rand_str()
    new_value = rand_str()
    result = set_header(existing, new_key, new_value, override=False)
    assert existing[new_key] == new_value
    assert result is None

    _, new = setup()
    for key, value in new.items():
        existing, _ = setup()
        result = set_header(existing, key, value, override=True)
        assert result is False
        for ex_key, ex_value in existing.items():
            existing_base_value = existing_base[ex_key]
            if ex_key.lower() == key.lower():
                assert ex_value == value
            else:
                assert ex_value == existing_base_value

    _, new = setup()
    for key, value in new.items():
        existing, _ = setup()
        result = set_header(existing, key, value, override=False)
        assert result is True
        assert existing == existing_base


def test_set_headers():
    ex_single = rand_str()
    ex_list = [rand_str(), rand_str()]

    new_single = rand_str()
    new_list = [rand_str(), rand_str()]

    # reuse the same list object
    # append should make new lists
    existing_base = {
        "single_single": ex_single,
        "single_list": ex_single,
        "list_single": ex_list,
        "list_list": ex_list,
        "single_none": ex_single,
        "list_none": ex_list,
    }

    new_base = {
        "SINGLE_SINGLE": new_single,
        "SINGLE_LIST": new_list,
        "LIST_SINGLE": new_single,
        "LIST_LIST": new_list,
        "NONE_SINGLE": new_single,
        "NONE_LIST": new_list,
    }

    appended = {
        "single_single": [ex_single, new_single],
        "single_list": [ex_single, *new_list],
        "list_single": [*ex_list, new_single],
        "list_list": [*ex_list, *new_list],
    }

    setup = lambda: (copy.deepcopy(existing_base), copy.deepcopy(new_base))

    existing, new = setup()
    set_headers(existing, new, override=True)
    assert existing == {
        "single_single": new_single,
        "single_list": new_list,
        "list_single": new_single,
        "list_list": new_list,
        "single_none": ex_single,
        "list_none": ex_list,
        "NONE_SINGLE": new_single,
        "NONE_LIST": new_list,
    }

    existing, new = setup()
    set_headers(existing, new, override=False)
    assert existing == {
        "single_single": ex_single,
        "single_list": ex_single,
        "list_single": ex_list,
        "list_list": ex_list,
        "single_none": ex_single,
        "list_none": ex_list,
        "NONE_SINGLE": new_single,
        "NONE_LIST": new_list,
    }


def test_append_header():
    ex_single = rand_str()
    ex_list = [rand_str(), rand_str()]

    new_single = rand_str()
    new_list = [rand_str(), rand_str()]

    # reuse the same list object
    # append should make new lists
    existing_base = {
        "single_single": ex_single,
        "single_list": ex_single,
        "list_single": ex_list,
        "list_list": ex_list,
    }

    new_base = {
        "SINGLE_SINGLE": new_single,
        "SINGLE_LIST": new_list,
        "LIST_SINGLE": new_single,
        "LIST_LIST": new_list,
    }

    appended = {
        "single_single": [ex_single, new_single],
        "single_list": [ex_single, *new_list],
        "list_single": [*ex_list, new_single],
        "list_list": [*ex_list, *new_list],
    }

    setup = lambda: (copy.deepcopy(existing_base), copy.deepcopy(new_base))

    existing, _ = setup()
    new_key = rand_str()
    new_value = rand_str()
    result = append_header(existing, new_key, new_value)
    assert existing[new_key] == new_value
    assert result is None

    existing, _ = setup()
    new_key = rand_str()
    new_value = [rand_str(), rand_str()]
    result = append_header(existing, new_key, new_value)
    assert existing[new_key] == new_value
    assert result is None

    _, new = setup()
    for key, value in new.items():
        existing, _ = setup()
        result = append_header(existing, key, value)
        assert result is True
        for ex_key, ex_value in existing.items():
            existing_base_value = existing_base[ex_key]
            if ex_key.lower() == key.lower():
                assert ex_value == appended[ex_key]
            else:
                assert ex_value == existing_base_value


def test_append_headers():
    ex_single = rand_str()
    ex_list = [rand_str(), rand_str()]

    new_single = rand_str()
    new_list = [rand_str(), rand_str()]

    # reuse the same list object
    # append should make new lists
    existing_base = {
        "single_single": ex_single,
        "single_list": ex_single,
        "list_single": ex_list,
        "list_list": ex_list,
        "single_none": ex_single,
        "list_none": ex_list,
    }

    new_base = {
        "SINGLE_SINGLE": new_single,
        "SINGLE_LIST": new_list,
        "LIST_SINGLE": new_single,
        "LIST_LIST": new_list,
        "NONE_SINGLE": new_single,
        "NONE_LIST": new_list,
    }

    setup = lambda: (copy.deepcopy(existing_base), copy.deepcopy(new_base))

    existing, new = setup()
    append_headers(existing, new)
    assert existing == {
        "single_single": [ex_single, new_single],
        "single_list": [ex_single, *new_list],
        "list_single": [*ex_list, new_single],
        "list_list": [*ex_list, *new_list],
        "single_none": ex_single,
        "list_none": ex_list,
        "NONE_SINGLE": new_single,
        "NONE_LIST": new_list,
    }
