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

import uuid
import json
import base64

from aws_lambda_api_event_utils.aws_lambda_api_event_validators import _matches


def test__matches():
    assert _matches("foo", "foo")
    assert not _matches("foo", "bar")
    assert _matches("foo", ["foo"])
    assert _matches("foo", ["foo", "bar"])
    assert not _matches("foo", [])
    assert not _matches("foo", ["bar"])
    assert not _matches("foo", ["bar", "baz"])
