"""Smoke tests for repository bootstrap."""

def test_import_package() -> None:
    """Import the integration package placeholder."""
    __import__("custom_components.wled_backupservice")
