.PHONY: lint format typecheck check test install-skills

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy src/ tests/

check: lint
	uv run ruff format --check .
	$(MAKE) typecheck

test:
	uv run pytest

install-skills:
	uv run expense-report-demo install-skills
