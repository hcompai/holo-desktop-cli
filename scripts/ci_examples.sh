#!/usr/bin/env bash
set -euo pipefail

shopt -s nullglob

python_examples=(examples/*/pyproject.toml)
node_examples=(examples/*/package.json)

for pyproject in "${python_examples[@]}"; do
  example_dir="$(dirname "$pyproject")"
  echo "::group::Python example: $example_dir"
  uv sync --directory "$example_dir" --all-groups
  uv run --directory "$example_dir" ruff check .
  uv run --directory "$example_dir" ruff format --check .
  MYPYPATH=src uv run --directory "$example_dir" mypy --explicit-package-bases src
  uv run --directory "$example_dir" pytest
  echo "::endgroup::"
done

for package_json in "${node_examples[@]}"; do
  example_dir="$(dirname "$package_json")"
  echo "::group::Node example: $example_dir"
  npm ci --prefix "$example_dir"
  npm run --prefix "$example_dir" build
  echo "::endgroup::"
done
