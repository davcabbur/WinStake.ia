import os
import time
import tempfile
import pytest

from src.cache import APICache


@pytest.fixture
def cache():
    tmpdir = tempfile.mkdtemp()
    c = APICache(cache_dir=tmpdir)
    yield c
    # Cleanup
    for f in os.listdir(tmpdir):
        os.remove(os.path.join(tmpdir, f))
    os.rmdir(tmpdir)


def test_set_and_get(cache):
    """Guardar y recuperar datos del cache."""
    cache.set("test_key", {"value": 42})
    result = cache.get("test_key", ttl_seconds=3600)
    assert result == {"value": 42}


def test_get_missing_key(cache):
    """Key inexistente retorna None."""
    result = cache.get("nonexistent", ttl_seconds=3600)
    assert result is None


def test_ttl_expiration(cache):
    """Datos expirados retornan None."""
    cache.set("expire_me", [1, 2, 3])
    # Forzar expiración poniendo TTL=0
    result = cache.get("expire_me", ttl_seconds=0)
    assert result is None


def test_ttl_valid(cache):
    """Datos dentro del TTL se recuperan."""
    cache.set("fresh", "data")
    result = cache.get("fresh", ttl_seconds=3600)
    assert result == "data"


def test_invalidate(cache):
    """Invalidar elimina la entrada."""
    cache.set("to_delete", "bye")
    assert cache.invalidate("to_delete") is True
    assert cache.get("to_delete", ttl_seconds=3600) is None


def test_invalidate_nonexistent(cache):
    """Invalidar key inexistente retorna False."""
    assert cache.invalidate("ghost") is False


def test_clear_all(cache):
    """Limpiar cache elimina todos los archivos."""
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    count = cache.clear_all()
    assert count == 3
    assert cache.get("a", ttl_seconds=3600) is None


def test_stats_tracking(cache):
    """Estadísticas de hits/misses se actualizan."""
    cache.set("tracked", "value")
    cache.get("tracked", ttl_seconds=3600)   # hit
    cache.get("tracked", ttl_seconds=3600)   # hit
    cache.get("missing", ttl_seconds=3600)   # miss

    stats = cache.get_stats()
    assert stats["hits"] == 2
    assert stats["misses"] == 1
    assert stats["saves"] == 1
    assert stats["hit_rate"] == pytest.approx(66.7, abs=0.1)


def test_complex_data_types(cache):
    """Cache maneja listas, dicts anidados, floats."""
    data = {
        "teams": [{"name": "Barcelona", "xg": 2.45}],
        "total": 78,
        "rate": 0.923,
    }
    cache.set("complex", data)
    result = cache.get("complex", ttl_seconds=3600)
    assert result["teams"][0]["name"] == "Barcelona"
    assert result["rate"] == 0.923
