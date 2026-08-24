from pathlib import Path


def test_caddy_python_match_is_exact_and_legacy_chat_is_not_captured() -> None:
    caddy = (Path(__file__).parents[3] / "Caddyfile").read_text()
    assert caddy.count("path /health/*") == 2
    assert caddy.count("path /api/v1/system/*") == 2
    assert "/api/v1/chat/completions" not in caddy.split("@ima_system", 1)[0]
    assert "@api path /api/*" in caddy
    assert "reverse_proxy {$PYTHON_API_URL}" in caddy
