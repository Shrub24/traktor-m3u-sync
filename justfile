set shell := ["bash", "-cu"]

default:
    @just --list

setup:
    uv sync --dev
    lefthook install

fmt:
    nix fmt

fmt-check:
    nix flake check

lint:
    uv run ruff check .

type:
    uv run pyright

test:
    uv run pytest

check: fmt-check lint type test

lock:
    uv lock
