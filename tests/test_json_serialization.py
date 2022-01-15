from decimal import Decimal
import pytest

import json
from datetime import datetime, time, date, timezone, timedelta
from dataclasses import FrozenInstanceError

from aws_lambda_api_event_utils import *
from aws_lambda_api_event_utils.aws_lambda_api_event_utils import _json_dump


def test_datetime_options():
    options = DatetimeSerializationOptions()
    assert options.sep is None
    assert options.timespec is None
    assert options.use_z_format is True

    with pytest.raises(FrozenInstanceError):
        options.use_z_format = False


def test_json_options():
    options = JSONSerializationOptions(datetime=True, decimal_type=None)
    assert options.datetime == DatetimeSerializationOptions()

    options = JSONSerializationOptions(datetime=False, decimal_type=None)
    assert options.datetime is None


def test_json_dump_decimal():
    num = Decimal("1.1")
    data = {"num": num}

    options = JSONSerializationOptions(decimal_type=None, datetime=None)
    with pytest.raises(TypeError, match="is not JSON serializable"):
        serialized = _json_dump(data, options)

    options = JSONSerializationOptions(decimal_type=float, datetime=None)
    serialized = _json_dump(data, options)
    roundtrip = json.loads(serialized)
    assert roundtrip["num"] == 1.1

    options = JSONSerializationOptions(decimal_type=str, datetime=None)
    serialized = _json_dump(data, options)
    roundtrip = json.loads(serialized)
    assert roundtrip["num"] == "1.1"
    assert Decimal(roundtrip["num"]) == num


def test_json_dump_datetime():
    dt_no_tz = datetime(2022, 1, 15, 10, 22, 30, 759878)
    dt_utc = datetime(2022, 1, 15, 10, 22, 30, 759878, tzinfo=timezone.utc)
    dt_offset = datetime(
        2022, 1, 15, 10, 22, 30, 759878, tzinfo=timezone(timedelta(hours=7))
    )
    data = {
        "datetime_no_tz": dt_no_tz,
        "datetime_utc": dt_utc,
        "datetime_offset": dt_offset,
        "date": dt_utc.date(),
        "time_no_tz": dt_no_tz.timetz(),
        "time_utc": dt_utc.timetz(),
        "time_offset": dt_offset.timetz(),
    }

    options = JSONSerializationOptions(datetime=False, decimal_type=None)
    with pytest.raises(TypeError, match="is not JSON serializable"):
        serialized = _json_dump(data, options)

    options = JSONSerializationOptions(datetime=True, decimal_type=None)
    serialized = _json_dump(data, options)
    roundtrip = json.loads(serialized)
    assert roundtrip["datetime_no_tz"] == "2022-01-15T10:22:30.759878"
    assert roundtrip["datetime_utc"] == "2022-01-15T10:22:30.759878Z"
    assert roundtrip["datetime_offset"] == "2022-01-15T10:22:30.759878+07:00"
    assert roundtrip["date"] == "2022-01-15"
    assert roundtrip["time_no_tz"] == "10:22:30.759878"
    assert roundtrip["time_utc"] == "10:22:30.759878Z"
    assert roundtrip["time_offset"] == "10:22:30.759878+07:00"

    options = JSONSerializationOptions(
        datetime=DatetimeSerializationOptions(timespec="minutes"), decimal_type=None
    )
    serialized = _json_dump(data, options)
    roundtrip = json.loads(serialized)
    assert roundtrip["datetime_no_tz"] == "2022-01-15T10:22"
    assert roundtrip["datetime_utc"] == "2022-01-15T10:22Z"
    assert roundtrip["datetime_offset"] == "2022-01-15T10:22+07:00"
    assert roundtrip["time_no_tz"] == "10:22"
    assert roundtrip["time_utc"] == "10:22Z"
    assert roundtrip["time_offset"] == "10:22+07:00"

    options = JSONSerializationOptions(
        datetime=DatetimeSerializationOptions(sep=" "), decimal_type=None
    )
    serialized = _json_dump(data, options)
    roundtrip = json.loads(serialized)
    assert roundtrip["datetime_no_tz"] == "2022-01-15 10:22:30.759878"
    assert roundtrip["datetime_utc"] == "2022-01-15 10:22:30.759878Z"
    assert roundtrip["datetime_offset"] == "2022-01-15 10:22:30.759878+07:00"

    options = JSONSerializationOptions(
        datetime=DatetimeSerializationOptions(use_z_format=False), decimal_type=None
    )
    serialized = _json_dump(data, options)
    roundtrip = json.loads(serialized)
    assert roundtrip["datetime_no_tz"] == "2022-01-15T10:22:30.759878"
    assert roundtrip["datetime_utc"] == "2022-01-15T10:22:30.759878+00:00"
    assert roundtrip["datetime_offset"] == "2022-01-15T10:22:30.759878+07:00"
    assert roundtrip["date"] == "2022-01-15"
    assert roundtrip["time_no_tz"] == "10:22:30.759878"
    assert roundtrip["time_utc"] == "10:22:30.759878+00:00"
    assert roundtrip["time_offset"] == "10:22:30.759878+07:00"
