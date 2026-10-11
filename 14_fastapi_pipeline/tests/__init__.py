# Marks `tests` as a package so pytest discovers it as one, and so test
# modules can import each other via `from tests.x import y` if ever needed.
# Empty intentionally — no fixtures or helpers live at the package level.
