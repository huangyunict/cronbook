import pytest
from assertpy import assert_that

from cronbook.main import main, parse_args


def test_parse_args_returns_dict():
    assert_that(parse_args([])).is_empty()


def test_main_returns_zero():
    assert_that(main([])).is_equal_to(0)


def test_help_exits_zero():
    with pytest.raises(SystemExit) as excinfo:
        parse_args(["--help"])
    assert_that(excinfo.value.code).is_equal_to(0)
