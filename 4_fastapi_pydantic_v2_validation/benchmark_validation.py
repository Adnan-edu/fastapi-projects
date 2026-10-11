"""Benchmark: BaseModel.model_validate vs TypeAdapter.validate_python for batch validation."""

import timeit

from app.schemas.user import UserRegister, user_register_adapter

SAMPLE_DATA = {
    "username": "benchuser",
    "email": "bench@example.com",
    "password": "Str0ng!Pass",
    "confirm_password": "Str0ng!Pass",
    "first_name": "Bench",
    "last_name": "User",
}

BATCH_SIZE = 1000
ITERATIONS = 50


def benchmark_single_model_validate():
    for _ in range(BATCH_SIZE):
        UserRegister.model_validate(SAMPLE_DATA)


def benchmark_single_type_adapter():
    batch = [SAMPLE_DATA] * 1
    for _ in range(BATCH_SIZE):
        user_register_adapter.validate_python(batch)


def benchmark_batch_type_adapter():
    batch = [SAMPLE_DATA] * BATCH_SIZE
    user_register_adapter.validate_python(batch)


def main():
    print(f"Pydantic v2 Validation Benchmark (batch_size={BATCH_SIZE}, iterations={ITERATIONS})")
    print("-" * 60)

    t_model = timeit.timeit(benchmark_single_model_validate, number=ITERATIONS)
    print(f"BaseModel.model_validate (single x{BATCH_SIZE}): {t_model:.3f}s")

    t_adapter = timeit.timeit(benchmark_single_type_adapter, number=ITERATIONS)
    print(f"TypeAdapter.validate_python (1-item list x{BATCH_SIZE}): {t_adapter:.3f}s")

    t_batch = timeit.timeit(benchmark_batch_type_adapter, number=ITERATIONS)
    print(f"TypeAdapter.validate_python (batch {BATCH_SIZE}): {t_batch:.3f}s")

    print("-" * 60)
    if t_batch > 0:
        ratio = t_model / t_batch
        print(f"Single iterations vs batch ratio (single/batch): {ratio:.2f}x")
    print("Note: TypeAdapter excels at validating non-BaseModel types (Unions, lists, etc.)")


if __name__ == "__main__":
    main()