from app.services.compute import fibonacci, light_compute, io_simulated


def test_fibonacci_zero():
    assert fibonacci(0) == 0


def test_fibonacci_one():
    assert fibonacci(1) == 1


def test_fibonacci_two():
    assert fibonacci(2) == 1


def test_fibonacci_negative():
    assert fibonacci(-5) == 0


def test_fibonacci_known_values():
    assert fibonacci(10) == 55
    assert fibonacci(20) == 6765
    assert fibonacci(30) == 832040


def test_light_compute_returns_required_keys():
    result = light_compute(100)
    assert "input" in result
    assert "result" in result
    assert "elapsed_seconds" in result


def test_light_compute_input_matches():
    result = light_compute(50)
    assert result["input"] == 50


def test_light_compute_elapsed_non_negative():
    result = light_compute(100)
    assert result["elapsed_seconds"] >= 0