"""
Resilience utilities: retry with exponential backoff, circuit breaker.
Usage:
    from .resilience import retry, CircuitBreaker

    @retry(max_attempts=3, backoff=1.0)
    def call_razorpay():
        ...

    wa_circuit = CircuitBreaker(name="whatsapp_bridge", failure_threshold=5)
    wa_circuit.call(lambda: httpx.post(...))
"""
import time, logging, functools
from typing import Callable, TypeVar, Any
from dataclasses import dataclass, field

logger = logging.getLogger("d2cflow.resilience")
T = TypeVar("T")

def retry(max_attempts: int = 3, backoff: float = 0.5, exceptions=(Exception,)):
    """Decorator: retry with exponential backoff on specified exceptions."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    wait = backoff * (2 ** (attempt - 1))
                    logger.warning("Retry %d/%d for %s: %s (wait=%.1fs)", attempt, max_attempts, fn.__name__, e, wait)
                    if attempt < max_attempts:
                        time.sleep(wait)
            raise last_exc
        return wrapper
    return decorator


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    _failures: int = field(default=0, init=False)
    _state: str = field(default="closed", init=False)  # closed | open | half-open
    _opened_at: float = field(default=0.0, init=False)

    def call(self, fn: Callable[[], T]) -> T:
        if self._state == "open":
            if time.time() - self._opened_at > self.recovery_timeout:
                self._state = "half-open"
                logger.info("CircuitBreaker[%s] entering half-open", self.name)
            else:
                raise RuntimeError(f"CircuitBreaker[{self.name}] is OPEN — {self.name} unavailable")
        try:
            result = fn()
            if self._state == "half-open":
                self._state = "closed"
                self._failures = 0
                logger.info("CircuitBreaker[%s] recovered → closed", self.name)
            return result
        except Exception as e:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._state = "open"
                self._opened_at = time.time()
                logger.error("CircuitBreaker[%s] OPENED after %d failures", self.name, self._failures)
            raise


# Pre-built circuit breakers for external services
whatsapp_cb = CircuitBreaker(name="whatsapp_bridge", failure_threshold=5, recovery_timeout=30)
razorpay_cb = CircuitBreaker(name="razorpay", failure_threshold=3, recovery_timeout=60)
shiprocket_cb = CircuitBreaker(name="shiprocket", failure_threshold=3, recovery_timeout=60)
