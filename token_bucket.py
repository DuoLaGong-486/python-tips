"""
Single-file Token Bucket Rate Limiter Implementation (Python 3.6 Compatible)

Core Algorithm:
  - Token Refill: tokens = min(capacity, last_tokens + floor(time_elapsed * rate))
  - Rate Limit Check: if cost > tokens: rate limited
  - State Storage: tokens, last_refreshed
  - TTL: 2 * (capacity / rate)

Python 3.6 Compatibility Notes:
  - Uses regular classes instead of @dataclass decorator
  - Uses duck typing instead of Protocol
  - Uses type comments for compatibility
"""

import math
import threading
import time
from collections import OrderedDict
from datetime import timedelta


# =============================================================================
# Type Definitions
# =============================================================================

KeyT = str
StoreValueT = float
StoreDictValueT = dict

# TTL State Constants (consistent with original implementation)
STORE_TTL_STATE_NOT_EXIST = 0  # Key does not exist
STORE_TTL_STATE_NOT_TTL = -1   # Key exists but has no expiration (never expires)


# =============================================================================
# Lock Protocol (Duck Typing for Python 3.6)
# =============================================================================

class LockMixin:
    """Lock mixin for Python 3.6 compatibility - duck typing instead of Protocol"""

    def acquire(self):
        # type: () -> bool
        raise NotImplementedError

    def release(self):
        # type: () -> None
        raise NotImplementedError

    def __enter__(self):
        # type: () -> LockMixin
        raise NotImplementedError

    def __exit__(self, exc_type, exc_val, exc_tb):
        # type: (type, type, type) -> None
        raise NotImplementedError


# =============================================================================
# Configuration Classes (Python 3.6 compatible - no dataclass)
# =============================================================================

class Rate:
    """Rate represents the rate limit configuration"""

    def __init__(self, period, limit):
        # type: (timedelta, int) -> None
        self.period = period
        self.limit = limit


class Quota:
    """Quota represents the quota limit configuration"""

    def __init__(self, rate, burst=0):
        # type: (Rate, int) -> None
        self.rate = rate
        self.burst = burst
        # Computed fields
        self.period_sec = 0  # type: int
        self.emission_interval = 0.0  # type: float
        self.fill_rate = 0.0  # type: float
        self._post_init()

    def _post_init(self):
        self.period_sec = int(self.rate.period.total_seconds())
        self.emission_interval = self.period_sec / self.rate.limit
        self.fill_rate = self.rate.limit / self.period_sec


def per_duration(duration, limit, burst=None):
    # type: (timedelta, int, int) -> Quota
    """Create a quota with specified duration and request limit"""
    if burst is None:
        burst = limit
    return Quota(Rate(period=duration, limit=limit), burst=burst)


def per_sec(limit, burst=None):
    # type: (int, int) -> Quota
    """Per-second limit"""
    return per_duration(timedelta(seconds=1), limit, burst)


def per_min(limit, burst=None):
    # type: (int, int) -> Quota
    """Per-minute limit"""
    return per_duration(timedelta(minutes=1), limit, burst)


def per_hour(limit, burst=None):
    # type: (int, int) -> Quota
    """Per-hour limit"""
    return per_duration(timedelta(hours=1), limit, burst)


def per_day(limit, burst=None):
    # type: (int, int) -> Quota
    """Per-day limit"""
    return per_duration(timedelta(days=1), limit, burst)


# =============================================================================
# Storage Backend
# =============================================================================

class MemoryStoreBackend:
    """Memory Storage Backend

    Features:
    - Uses OrderedDict for LRU (Least Recently Used) eviction
    - Supports TTL expiration
    - Thread-safe (protected by lock)
    """

    def __init__(self, max_size=1024):
        # type: (int) -> None
        self.max_size = max_size  # type: int
        self.expire_info = {}  # type: dict
        self.lock = threading.Lock()  # type: threading.Lock
        # Use OrderedDict for LRU
        self._client = OrderedDict()  # type: OrderedDict

    def exists(self, key):
        # type: (KeyT) -> bool
        """Check if key exists"""
        return key in self._client

    def has_expired(self, key):
        # type: (KeyT) -> bool
        """Check if key has expired"""
        return self.ttl(key) == STORE_TTL_STATE_NOT_EXIST

    def ttl(self, key):
        # type: (KeyT) -> int
        """Return TTL status of key"""
        exp = self.expire_info.get(key)
        if exp is None:
            if not self.exists(key):
                return STORE_TTL_STATE_NOT_EXIST  # Return 0: key does not exist
            return STORE_TTL_STATE_NOT_TTL         # Return -1: never expires

        ttl = exp - time.monotonic()
        if ttl <= 0:
            return STORE_TTL_STATE_NOT_EXIST  # Return 0: expired
        return math.ceil(ttl)

    def check_and_evict(self, key):
        # type: (KeyT) -> None
        """Check if storage is full, evict oldest entry if so (LRU strategy)"""
        if len(self._client) >= self.max_size and not self.exists(key):
            # Pop the oldest entry
            pop_key, _ = self._client.popitem(last=False)
            self.expire_info.pop(pop_key, None)

    def expire(self, key, timeout):
        # type: (KeyT, int) -> None
        """Set expiration time for key"""
        self.expire_info[key] = time.monotonic() + timeout

    def hgetall(self, name):
        # type: (KeyT) -> StoreDictValueT
        """Get all fields and values from hash table"""
        # Check expiration and auto-delete
        if self.has_expired(name):
            self.delete(name)
            return {}

        kv = self._client.get(name)
        if not (kv is None or isinstance(kv, dict)):
            raise ValueError("Value must be dict for hgetall")

        # Move to end on access (LRU)
        if kv is not None:
            self._client.move_to_end(name)

        return kv or {}

    def hset(self, name, key=None, value=None, mapping=None):
        # type: (KeyT, Optional[KeyT], Optional[StoreValueT], Optional[StoreDictValueT]) -> None
        """Set fields and values in hash table"""
        if key is None and not mapping:
            raise ValueError("hset requires key-value pairs")

        kv = {}  # type: StoreDictValueT
        if key is not None:
            kv[key] = value
        if mapping:
            kv.update(mapping)

        origin = self._client.get(name)
        if origin is not None:
            if not isinstance(origin, dict):
                raise ValueError("origin must be dict")
            origin.update(kv)
        else:
            # Check space and evict before inserting
            self.check_and_evict(name)
            self._client[name] = kv

        # Move to end on write (LRU)
        self._client.move_to_end(name)

    def delete(self, key):
        # type: (KeyT) -> bool
        """Delete key"""
        try:
            self.expire_info.pop(key, None)
            del self._client[key]
        except KeyError:
            return False
        return True


# =============================================================================
# Result Classes (Python 3.6 compatible - no dataclass)
# =============================================================================

class RateLimitState:
    """RateLimitState represents the current state of rate limiter for a given key"""

    __slots__ = ("limit", "remaining", "reset_after", "retry_after")

    def __init__(self, limit, remaining, reset_after, retry_after=0):
        # type: (int, int, float, float) -> None
        #: Maximum requests allowed in initial state
        self.limit = limit
        #: Maximum requests allowed for given key in current state
        self.remaining = remaining
        #: Seconds until rate limiter returns to initial state
        self.reset_after = reset_after
        #: Seconds to retry request, 0 if request is allowed
        self.retry_after = retry_after


class RateLimitResult:
    """RateLimitResult represents the result of executing rate limiter for a given key"""

    __slots__ = ("limited", "_state_values", "_state")

    def __init__(self, limited, state_values):
        # type: (bool, tuple) -> None
        self.limited = limited  # type: bool
        self._state_values = state_values  # type: tuple
        self._state = None  # type: Optional[RateLimitState]

    @property
    def state(self):
        # type: () -> RateLimitState
        """Get rate limit state"""
        if self._state:
            return self._state
        self._state = RateLimitState(*self._state_values)
        return self._state


# =============================================================================
# Atomic Operations
# =============================================================================

class BaseAtomicAction:
    """Base class for atomic operations"""

    TYPE = ""  # type: str
    STORE_TYPE = ""  # type: str

    def __init__(self, backend):
        # type: (MemoryStoreBackend) -> None
        self._backend = backend

    def do(self, keys, args):
        # type: (list, Optional[list]) -> tuple
        """Execute atomic operation"""
        raise NotImplementedError


class MemoryLimitAtomicAction(BaseAtomicAction):
    """Rate limit atomic operation for memory implementation

    Core Algorithm (consistent with throttled/token_bucket.py):
    1. Get current bucket state (tokens, last_refreshed)
    2. Calculate elapsed time and refill tokens
    3. Check if rate limiting is needed
    4. If not limited, consume tokens and update state
    """

    TYPE = "limit"  # type: str
    STORE_TYPE = "memory"  # type: str

    def do(self, keys, args):
        # type: (list, Optional[list]) -> tuple
        """Execute token bucket rate limit operation

        Args:
            keys: Storage key list (first element is bucket key)
            args: [rate, capacity, cost] - rate, capacity, request cost

        Returns:
            (limited, tokens) - whether rate limited, current token count
        """
        # Pure computation outside lock to reduce serialized section
        key = keys[0]  # type: str
        rate = args[0]  # type: float
        capacity = args[1]  # type: int
        cost = args[2]  # type: int
        now = int(time.time())  # type: int

        with self._backend.lock:
            # Get current bucket state
            bucket = self._backend.hgetall(key)  # type: StoreDictValueT
            last_tokens = bucket.get("tokens", capacity)  # type: int
            last_refreshed = bucket.get("last_refreshed", now)  # type: int

            # Calculate elapsed time (seconds)
            time_elapsed = max(0, now - last_refreshed)  # type: int

            # Refill tokens: min(capacity, last_tokens + floor(elapsed * rate))
            # Use floor for consistency with original implementation
            tokens = min(capacity, last_tokens + math.floor(time_elapsed * rate))  # type: int

            # Check if rate limiting is needed
            limited = 1 if tokens < cost else 0  # type: int
            if limited:
                return limited, tokens

            # Consume tokens
            tokens -= cost

            # Update bucket state
            self._backend.hset(key, mapping={"tokens": tokens, "last_refreshed": now})

            # Set expiration to 2x time needed to fill bucket
            fill_time = capacity / rate  # type: float
            self._backend.expire(key, math.ceil(2 * fill_time))

            return limited, tokens


# =============================================================================
# Token Bucket Rate Limiter (Python 3.6 compatible)
# =============================================================================

class TokenBucketRateLimiter:
    """Token Bucket Rate Limiter

    Core Features:
    - Supports burst traffic: allows up to burst requests to pass instantly
    - Smooth rate limiting: continuously refills tokens at rate
    - Thread-safe: protects shared state with lock
    - Auto-expiration: no manual cleanup of expired buckets
    - LRU eviction: uses OrderedDict for least recently used strategy
    """

    KEY_PREFIX = "throttled:v1:token_bucket:"  # type: str

    def __init__(self, quota, backend=None):
        # type: (Quota, Optional[MemoryStoreBackend]) -> None
        """
        Args:
            quota: Quota configuration
            backend: Storage backend, defaults to memory storage
        """
        self.quota = quota
        self._backend = backend if backend is not None else MemoryStoreBackend()
        self._atomic_action = MemoryLimitAtomicAction(self._backend)

    def _prepare_key(self, key):
        # type: (str) -> str
        """Prepare storage key"""
        return "{}{}".format(self.KEY_PREFIX, key)

    def _refill_sec(self, upper, remaining):
        # type: (int, int) -> int
        """Calculate seconds needed for bucket to recover to limit"""
        if remaining >= upper:
            return 0
        return math.ceil((upper - remaining) / self.quota.fill_rate)

    def _to_result(self, limited, cost, tokens, capacity):
        # type: (int, int, int, int) -> RateLimitResult
        """Convert rate limit result"""
        reset_after = self._refill_sec(capacity, tokens)  # type: int
        # Can retry when tokens refill to cost
        retry_after = self._refill_sec(cost, tokens) if limited else 0  # type: int

        return RateLimitResult(
            limited=bool(limited),
            state_values=(capacity, tokens, reset_after, retry_after),
        )

    def limit(self, key, cost=1):
        # type: (str, int) -> RateLimitResult
        """
        Perform rate limit check on request

        Args:
            key: Unique identifier for rate limit target (e.g., user ID, IP address)
            cost: Number of tokens consumed by request, defaults to 1

        Returns:
            RateLimitResult: Contains whether rate limited and current state
        """
        formatted_key = self._prepare_key(key)  # type: str
        rate = self.quota.fill_rate  # type: float
        capacity = self.quota.burst  # type: int

        limited, tokens = self._atomic_action.do(
            [formatted_key], [rate, capacity, cost]
        )

        return self._to_result(limited, cost, tokens, capacity)

    def peek(self, key):
        # type: (str) -> RateLimitState
        """
        View current rate limit state without modifying state

        Args:
            key: Unique identifier for rate limit target

        Returns:
            RateLimitState: Current rate limit state
        """
        now = int(time.time())  # type: int
        formatted_key = self._prepare_key(key)  # type: str
        rate = self.quota.fill_rate  # type: float
        capacity = self.quota.burst  # type: int

        # Get current bucket state
        bucket = self._backend.hgetall(formatted_key)  # type: StoreDictValueT
        last_tokens = bucket.get("tokens", capacity)  # type: int
        last_refreshed = bucket.get("last_refreshed", now)  # type: int

        # Calculate elapsed time and refill tokens
        time_elapsed = max(0, now - last_refreshed)  # type: int
        tokens = min(capacity, last_tokens + math.floor(time_elapsed * rate))  # type: int

        # Calculate time to fill bucket
        reset_after = math.ceil((capacity - tokens) / rate)  # type: int

        return RateLimitState(limit=capacity, remaining=tokens, reset_after=reset_after)
