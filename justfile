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

run-export:
    uv run traktor-m3u-sync export --config traktor-m3u-sync.toml

check: fmt-check lint type test

lock:
    uv lock
