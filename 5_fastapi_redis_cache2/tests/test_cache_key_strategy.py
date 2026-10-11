import pytest
from fastapi import FastAPI
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_cache.decorator import cache
from starlette.testclient import TestClient

from app.core.cache import city_key_builder


class TestDefaultKeyBuilder:
    def test_city_key_builder_produces_consistent_keys(self):
        key1 = city_key_builder(
            func=None,
            namespace="weather",
            request=None,
            response=None,
            args=(),
            kwargs={"city": "London"},
        )
        key2 = city_key_builder(
            func=None,
            namespace="weather",
            request=None,
            response=None,
            args=(),
            kwargs={"city": "london"},
        )
        assert key1 == key2

    def test_city_key_builder_different_cities(self):
        key1 = city_key_builder(
            func=None,
            namespace="weather",
            request=None,
            response=None,
            args=(),
            kwargs={"city": "London"},
        )
        key2 = city_key_builder(
            func=None,
            namespace="weather",
            request=None,
            response=None,
            args=(),
            kwargs={"city": "Tokyo"},
        )
        assert key1 != key2


class TestNamespaceIsolation:
    def test_different_namespaces_isolate_caches(self):
        @cache(namespace="ns_a", expire=60)
        async def func_a():
            return {"val": "a"}

        @cache(namespace="ns_b", expire=60)
        async def func_b():
            return {"val": "b"}

        key_a = city_key_builder(
            func=func_a,
            namespace="ns_a",
            request=None,
            response=None,
            args=(),
            kwargs={},
        )
        key_b = city_key_builder(
            func=func_b,
            namespace="ns_b",
            request=None,
            response=None,
            args=(),
            kwargs={},
        )
        assert key_a != key_b


class TestCacheKeyWithSpecialCharacters:
    def test_city_with_spaces(self):
        key = city_key_builder(
            func=None,
            namespace="weather",
            request=None,
            response=None,
            args=(),
            kwargs={"city": "New York"},
        )
        assert "new york" in key

    def test_city_with_unicode(self):
        key = city_key_builder(
            func=None,
            namespace="weather",
            request=None,
            response=None,
            args=(),
            kwargs={"city": "M\u00fcnchen"},
        )
        assert "m\u00fcnchen" in key