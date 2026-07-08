from traktor_m3u_sync.cli import app


def test_cli_app_exists() -> None:
    assert app is not None
