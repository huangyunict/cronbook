# cronbook

Cron job management.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

## Development

```sh
uv sync
uv run cronbook
```

Checks:

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
uv run pytest
```

## License

MIT - see [LICENSE](LICENSE).
