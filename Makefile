.PHONY: setup setup-examples install-dev uninstall-dev lint format typecheck test check ci

setup:
	uv sync --all-groups
	uv run pre-commit install --hook-type pre-commit --hook-type pre-push --install-hooks

# Provision the workspace examples too. Plain `uv sync` only installs the root
# package and uninstalls example-only deps from the shared .venv.
setup-examples:
	uv sync --all-packages --all-groups

install-dev:
	uv tool install --editable . --force

uninstall-dev:
	uv tool uninstall holo-desktop-cli

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy src/

test:
	uv run pytest

check: lint
	uv run ruff format --check .
	$(MAKE) typecheck
	$(MAKE) test

ci: check
	uv run pre-commit run --all-files --hook-stage pre-push
