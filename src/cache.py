"""
WinStake.ia — Caché de API Requests
Almacena respuestas de APIs en disco con TTL configurable.
Evita gastar requests innecesarias (500/mes Odds API, 100/día Football API).
"""

import json
import hashlib
import logging
import os
import time
from typing import Optional, Any

logger = logging.getLogger(__name__)

# Directorio de caché
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cache")


class APICache:
    """Caché en disco con TTL para respuestas de API."""

    def __init__(self, cache_dir: str = CACHE_DIR):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self._stats = {"hits": 0, "misses": 0, "saves": 0}

    def get(self, key: str, ttl_seconds: int) -> Optional[Any]:
        """
        Busca una entrada en caché.

        Args:
            key: Identificador único de la request (URL + params)
            ttl_seconds: Tiempo de vida en segundos

        Returns:
            Datos cacheados si son válidos, None si expiró o no existe
        """
        cache_file = self._key_to_path(key)

        if not os.path.exists(cache_file):
            self._stats["misses"] += 1
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)

            cached_at = cached.get("cached_at", 0)
            age_seconds = time.time() - cached_at

            if age_seconds > ttl_seconds:
                self._stats["misses"] += 1
                age_min = int(age_seconds / 60)
                ttl_min = int(ttl_seconds / 60)
                logger.info(f"⏰ Caché expirada para '{key}' (edad: {age_min}min, TTL: {ttl_min}min)")
                return None

            self._stats["hits"] += 1
            age_min = int(age_seconds / 60)
            logger.info(f"💾 Caché HIT para '{key}' (edad: {age_min}min)")
            return cached.get("data")

        except (json.JSONDecodeError, KeyError, OSError) as e:
            logger.warning(f"⚠️ Error leyendo caché para '{key}': {e}")
            self._stats["misses"] += 1
            return None

    def set(self, key: str, data: Any) -> None:
        """Guarda datos en caché."""
        cache_file = self._key_to_path(key)
        try:
            cached = {
                "key": key,
                "cached_at": time.time(),
                "data": data,
            }
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cached, f, ensure_ascii=False, indent=2)

            self._stats["saves"] += 1
            logger.debug(f"💾 Caché guardada para '{key}'")

        except OSError as e:
            logger.warning(f"⚠️ Error guardando caché para '{key}': {e}")

    def invalidate(self, key: str) -> bool:
        """Invalida una entrada específica de caché."""
        cache_file = self._key_to_path(key)
        if os.path.exists(cache_file):
            os.remove(cache_file)
            logger.info(f"🗑️ Caché invalidada para '{key}'")
            return True
        return False

    def clear_all(self) -> int:
        """Limpia toda la caché. Retorna número de archivos eliminados."""
        count = 0
        for filename in os.listdir(self.cache_dir):
            if filename.endswith(".json"):
                os.remove(os.path.join(self.cache_dir, filename))
                count += 1

        logger.info(f"🗑️ Caché limpiada: {count} archivos eliminados")
        return count

    def get_stats(self) -> dict:
        """Retorna estadísticas de uso de la caché."""
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total * 100) if total > 0 else 0
        return {
            **self._stats,
            "total_requests": total,
            "hit_rate": round(hit_rate, 1),
        }

    def _key_to_path(self, key: str) -> str:
        """Convierte un key en una ruta de archivo segura."""
        # Hash del key para nombre de archivo seguro
        key_hash = hashlib.md5(key.encode()).hexdigest()[:12]
        # Nombre legible + hash
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in key[:40])
        filename = f"{safe_name}_{key_hash}.json"
        return os.path.join(self.cache_dir, filename)
