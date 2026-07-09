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

# Nix runtime artifact validation
pkg-build:
	nix build .#packages.x86_64-linux.traktor-m3u-sync --no-link --print-out-paths

app-run:
	nix run .#default -- --help

module-check:
	nix build .#checks.x86_64-linux.module-eval --no-link --print-out-paths

lock:
    uv lock
