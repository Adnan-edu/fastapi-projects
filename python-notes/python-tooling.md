# Modern Python Tooling & Robustness Playbook

A structured reference guide covering 9 tools for building reliable, reproducible Python applications.

---

## Quick Navigation

| Tool | Focus Area | When to Use |
| :--- | :--- | :--- |
| [1. uv](#1-uv-dependency-locking) | Dependency & Environment Management | Managing reproducible project environments |
| [2. Ruff](#2-ruff-linting--formatting) | Mechanical Code Quality | Catching dead code, typos, and style issues fast |
| [3. Pydantic](#3-pydantic-boundary-validation) | Runtime Boundary Validation | Rejecting ambiguous data before it enters domain logic |
| [4. Typer](#4-typer-cli-interfaces) | CLI Frontends & Input Verification | Replacing messy `sys.argv` with typed command interfaces |
| [5. HTTPX](#5-httpx-isolated-http-clients) | Deterministic HTTP Requests | Decoupling network requests from network availability |
| [6. Tenacity](#6-tenacity-targeted-retries) | Transient Failure Recovery | Retrying only operations that can actually recover |
| [7. pytest](#7-pytest-regression--cli-testing) | Parameterized & End-to-End Tests | Turning past bug reports into permanent checks |
| [8. Hypothesis](#8-hypothesis-property-based-testing) | Invariant / Edge-Case Discovery | Finding blind spots that example-based tests miss |
| [9. build](#9-build-package-distribution-testing) | Packaging & Distribution Verification | Ensuring installable artifacts work outside the repo |

---

### 1. uv: Dependency Locking

* **Purpose:** Ensures the environment is deterministic, avoiding *"it worked 6 weeks ago"* drift.
* **Core Command:**
  ```bash
  uv sync --locked
  ```
* **Key Mechanisms:**
  * `pyproject.toml` declares intentional requirements.
  * `uv.lock` records exact resolved dependency versions and Python version.
  * `--locked` forces execution to fail if the lockfile is outdated, catching uncommitted or misaligned dependencies before release.
* **Decision Boundary:**
  * **Use:** Repeated environment setup, production pipelines, multi-contributor repos.
  * **Skip:** Single-file standalone scripts without dependencies (native `python` is sufficient) or tiny legacy projects where `venv` + `pip` are already adequate.

---

### 2. Ruff: Linting & Formatting

* **Purpose:** Catches mechanical mistakes (unused imports, undefined variables) automatically without manual review overhead.
* **Core Commands:**
  ```bash
  # Check for issues without modifying files
  uv run --locked ruff check path/to/file.py

  # Preview suggested fixes
  uv run --locked ruff check --diff path/to/file.py
  ```
* **Safe vs. Unsafe Fixes:**
  * Safely removes dead imports (e.g., unused `import json`).
  * Flags undefined variables (e.g., `sum(price)` instead of `sum(prices)`) without guessing what the variable should be.
* **Decision Boundary:**
  * Linters enforce mechanical rules. Keep business logic and semantic validation in tests.

---

### 3. Pydantic: Boundary Validation

* **Purpose:** Enforces strict contracts on data entering your application before it reaches business logic.
* **Pattern:**
  ```python
  from pydantic import BaseModel, ConfigDict, Field

  class Order(BaseModel):
      model_config = ConfigDict(strict=True, extra="forbid")

      sku: str = Field(min_length=1)
      quantity: int = Field(gt=0)
      unit_price_cents: int = Field(ge=0)
  ```
* **Behavior:**
  * `extra="forbid"` rejects unexpected keys (catches misspellings in payloads).
  * `strict=True` rejects coercive types (e.g., string `"2"` or boolean `True` will raise `ValidationError` rather than silently casting to integer `2`).
* **Decision Boundary:**
  * Ideal when parsing JSON payloads, nested structures, or external API contracts.
  * For simple 1–2 argument functions or plain CSV imports (where text parsing is intentional), standard conversions may be sufficient.

---

### 4. Typer: CLI Interfaces

* **Purpose:** Gives scripts structured entry points with built-in path validation, help text, and standardized exit codes.
* **Pattern:**
  ```python
  from pathlib import Path
  from typing import Annotated
  import typer
  from pydantic import TypeAdapter, ValidationError
  from solo_tools.models import Order

  app = typer.Typer()

  @app.command()
  def total(
      path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
  ):
      try:
          orders = TypeAdapter(list[Order]).validate_json(path.read_bytes())
      except (OSError, ValidationError) as exc:
          typer.echo(f"Cannot read orders: {exc}", err=True)
          raise typer.Exit(code=1) from exc

      cents = sum(order.quantity * order.unit_price_cents for order in orders)
      typer.echo(f"{len(orders)} orders, {cents} cents")
  ```
* **Key Details:**
  * Exits with code `2` on invalid argument paths (handled by Typer).
  * Exits with code `1` on invalid payload contents (handled via `typer.Exit(code=1)`).
* **Decision Boundary:**
  * Standard library `argparse` is fine for trivial CLI tasks. Typer shines when interfaces grow and type validation/test runners are needed.

---

### 5. HTTPX: Isolated HTTP Clients

* **Purpose:** Decouples HTTP request logic from network dependencies via dependency injection and mock transports.
* **Pattern:**
  ```python
  import httpx

  # 1. Logic accepts a client instance
  def fetch_stock(client: httpx.Client, sku: str) -> dict:
      response = client.get(f"/stock/{sku}")
      response.raise_for_status()  # Check status BEFORE parsing JSON
      return response.json()

  # 2. Test cleanly without an internet connection using MockTransport
  def fake_api(request):
      if request.url.path == "/stock/BOOK":
          return httpx.Response(200, json={"sku": "BOOK", "available": 7})
      return httpx.Response(404, json={"error": "unknown SKU"})

  with httpx.Client(
      base_url="https://inventory.test",
      transport=httpx.MockTransport(fake_api),
      timeout=httpx.Timeout(5.0, connect=2.0),
      trust_env=False,
  ) as client:
      stock = fetch_stock(client, "BOOK")
  ```
* **Key Details:**
  * Call `response.raise_for_status()` before `.json()` so that upstream HTML 503 pages fail as HTTP errors, not silent JSON decoding errors.
  * Timeouts are granular (connect, read, write, pool).

---

### 6. Tenacity: Targeted Retries

* **Purpose:** Recovers from transient network/service errors without blindly repeating non-recoverable failures.
* **Pattern:**
  ```python
  import httpx
  from tenacity import retry, retry_if_exception, stop_after_attempt, wait_random_exponential

  def retryable(exc: BaseException) -> bool:
      if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout)):
          return True
      return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {502, 503, 504}

  @retry(
      retry=retry_if_exception(retryable),
      stop=stop_after_attempt(3),  # 3 total attempts
      wait=wait_random_exponential(multiplier=0.1, max=1),
      reraise=True,
  )
  def fetch_with_retry(client, sku):
      return fetch_stock(client, sku)
  ```
* **Retry Rules:**
  * **Retry:** `502`, `503`, `504`, connection drops, read timeouts.
  * **Do NOT retry:** `401 Unauthorized`, `404 Not Found`, invalid data/JSON syntax, non-idempotent operations (e.g., payments/orders without idempotency keys).

---

### 7. pytest: Regression & CLI Testing

* **Purpose:** Parameterizes known boundary cases and checks end-to-end integration via temporary files and CLI runners.
* **Pattern:**
  ```python
  import pytest
  from pydantic import ValidationError
  from solo_tools.models import Order

  @pytest.mark.parametrize("quantity", [0, -1, "2", True])
  def test_rejects_invalid_quantity(quantity):
      with pytest.raises(ValidationError) as caught:
          Order(sku="BOOK", quantity=quantity, unit_price_cents=1200)
      assert caught.value.errors()[0]["loc"] == ("quantity",)
  ```
* **Testing Best Practices:**
  * Verify the exact error location (`caught.value.errors()[0]["loc"]`) so unintended validation failures don't pass tests accidentally.
  * Use `tmp_path` fixture for disk-isolated file checks.
  * Use Typer's `CliRunner` to test exit codes alongside output messages.

---

### 8. Hypothesis: Property-Based Testing

* **Purpose:** Discovers unexpected edge cases by evaluating broad invariants rather than hand-picked sample data.
* **Invariant Example (Batching):**
  * *Invariant:* Re-combining all chunks must equal the original sequence in the original order.
* **Pattern:**
  ```python
  from hypothesis import given, settings, strategies as st
  from solo_tools.batches import batches

  @settings(max_examples=200, derandomize=True)
  @given(st.lists(st.integers(), max_size=50), st.integers(min_value=1, max_value=20))
  def test_batches_preserve_every_item(items, size):
      chunks = batches(items, size)
      # Invariant 1: Flattened items match original items exactly
      assert [item for chunk in chunks for item in chunk] == items
      # Invariant 2: No chunk exceeds requested size or is empty
      assert all(0 < len(chunk) <= size for chunk in chunks)
  ```
* **Flaw Detected by Hypothesis:**
  * An implementation with `range(0, len(items) - size + 1, size)` drops final short chunks. Hypothesis caught it using `items = [0], size = 2`.
  * *Fix:* Use `range(0, len(items), size)` with a guard against non-positive sizes.

---

### 9. build: Package Distribution Verification

* **Purpose:** Validates that packaging configurations (`pyproject.toml`, entry points, included files) work when installed as an isolated artifact.
* **Build Command:**
  ```bash
  uv run --locked python -m build --installer uv
  # Or natively: uv build
  ```
* **Verification Workflow:**
  1. Build the distribution wheel (`.whl`) and source distribution (`.tar.gz`).
  2. Install the `.whl` into a clean, empty virtual environment.
  3. Execute the CLI entry point outside of the project repository directory.
* **Why this matters:**
  * Executing directly inside your repository tree uses local files on `PYTHONPATH`, hiding missing files, missing entry points, or undeclared runtime dependencies. Always test the built wheel.