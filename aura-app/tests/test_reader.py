import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from serial_reader import _xor, parse_line  # noqa: E402


def make(payload):
    return f"{payload}*{_xor(payload):02X}"


def test_valid_line():
    assert parse_line(make("29.2,70.0,1931,108")) == (29.2, 70.0, 1931.0, 108.0)


def test_dropped_first_character_rejected():
    assert parse_line(make("29.2,70.0,1931,108")[1:]) is None


def test_bad_inputs_rejected():
    for bad in ["", "# DHT read failed | light=1 gas=2", "29.2,70.0,1931,108",
                "29.2,70.0,1931*00", make("1,2,3"), "garbage*ZZ"]:
        assert parse_line(bad) is None
