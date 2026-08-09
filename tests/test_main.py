import pytest

from cronbook.main import main, parse_args


def test_parse_args_returns_dict():
    assert parse_args([]) == {}


def test_main_returns_zero():
    assert main([]) == 0


def test_help_exits_zero():
    with pytest.raises(SystemExit) as excinfo:
        parse_args(["--help"])
    assert excinfo.value.code == 0
