import argparse
from typing import Any


def parse_args(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(prog="cronbook", description="Cron job management")
    return vars(parser.parse_args(argv))


def main(argv: list[str] | None = None) -> int:
    parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
