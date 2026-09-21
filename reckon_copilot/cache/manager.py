from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from reckon_copilot.context.builders import canonical_json


class CacheUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class CacheResult:
    value: Any
    hit: bool
    single_flight_shared: bool = False


class InMemoryCacheBackend:
    def __init__(self):
        self.values: dict[str, tuple[float | None, str]] = {}
        self.lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self.lock:
            entry = self.values.get(key)
            if not entry:
                return None
            expires_at, value = entry
            if expires_at is not None and expires_at <= time.monotonic():
                self.values.pop(key, None)
                return None
            return value

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        expires_at = time.monotonic() + ttl if ttl else None
        with self.lock:
            self.values[key] = (expires_at, value)

    def delete(self, key: str) -> None:
        with self.lock:
            self.values.pop(key, None)


class FrappeCacheBackend:
    def __init__(self, frappe_module=None):
        if frappe_module is None:
            import frappe as frappe_module  # type: ignore
        self.frappe = frappe_module

    def get(self, key: str) -> str | None:
        cache = self.frappe.cache()
        value = cache.get_value(key)
        if value is None:
            return None
        return value.decode("utf-8") if isinstance(value, bytes) else str(value)

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        cache = self.frappe.cache()
        cache.set_value(key, value, expires_in_sec=ttl)

    def delete(self, key: str) -> None:
        self.frappe.cache().delete_value(key)


class SingleFlightLock:
    def __init__(self):
        self._condition = threading.Condition()
        self._running = False
        self.value: Any = None
        self.error: BaseException | None = None


class CacheManager:
    def __init__(self, backend=None, default_ttl: int = 300, lock_timeout: float = 10.0):
        self.backend = backend or InMemoryCacheBackend()
        self.default_ttl = default_ttl
        self.lock_timeout = lock_timeout
        self._single_flights: dict[str, SingleFlightLock] = {}
        self._single_flights_lock = threading.Lock()

    def get_or_compute(
        self,
        key: str,
        compute: Callable[[], Any],
        ttl: int | None = None,
    ) -> CacheResult:
        cached = self._get(key)
        if cached is not None:
            return CacheResult(_decode(cached), hit=True)

        flight, owner = self._flight_for(key)
        if not owner:
            return self._wait_for_flight(key, flight, compute, ttl)

        value = None
        try:
            value = compute()
            self._set(key, _encode(value), ttl if ttl is not None else self.default_ttl)
            return CacheResult(value, hit=False)
        except BaseException as error:
            with flight._condition:
                flight.error = error
                flight._condition.notify_all()
            raise
        finally:
            with flight._condition:
                flight.value = value
                flight._running = False
                flight._condition.notify_all()
            with self._single_flights_lock:
                self._single_flights.pop(key, None)

    def invalidate(self, key: str) -> None:
        self._delete(key)

    def _flight_for(self, key: str) -> tuple[SingleFlightLock, bool]:
        with self._single_flights_lock:
            flight = self._single_flights.get(key)
            if flight:
                return flight, False
            flight = SingleFlightLock()
            flight._running = True
            self._single_flights[key] = flight
            return flight, True

    def _wait_for_flight(
        self,
        key: str,
        flight: SingleFlightLock,
        compute: Callable[[], Any],
        ttl: int | None,
    ) -> CacheResult:
        deadline = time.monotonic() + self.lock_timeout
        with flight._condition:
            while flight._running:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                flight._condition.wait(remaining)
            if not flight._running and flight.error:
                raise flight.error
            if not flight._running:
                cached = self._get(key)
                if cached is not None:
                    return CacheResult(_decode(cached), hit=True, single_flight_shared=True)
                return CacheResult(flight.value, hit=True, single_flight_shared=True)
        value = compute()
        self._set(key, _encode(value), ttl if ttl is not None else self.default_ttl)
        return CacheResult(value, hit=False)

    def _get(self, key: str) -> str | None:
        try:
            return self.backend.get(key)
        except Exception:
            return None

    def _set(self, key: str, value: str, ttl: int | None) -> None:
        try:
            self.backend.set(key, value, ttl)
        except Exception:
            return None

    def _delete(self, key: str) -> None:
        try:
            self.backend.delete(key)
        except Exception:
            return None


def _encode(value: Any) -> str:
    return canonical_json({"value": value})


def _decode(value: str) -> Any:
    import json

    return json.loads(value)["value"]
