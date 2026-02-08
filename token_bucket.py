"""
Single-file Token Bucket Rate Limiter Implementation

Core Algorithm:
  - Token Refill: tokens = min(capacity, last_tokens + floor(time_elapsed * rate))
  - Rate Limit Check: if cost > tokens: rate limited
  - State Storage: tokens, last_refreshed
  - TTL: 2 * (capacity / rate)
"""

import math
import threading
import time
from collections import OrderedDict
from datetime import timedelta
from typing import Any, Dict, Optional, OrderedDict as OrderedDictT, Protocol, Sequence


# =============================================================================
# Type Definitions
# =============================================================================

KeyT = str
StoreValueT = float
StoreDictValueT = Dict[KeyT, StoreValueT]

# TTL State Constants (consistent with original implementation)
STORE_TTL_STATE_NOT_EXIST: int = 0  # Key does not exist
STORE_TTL_STATE_NOT_TTL: int = -1   # Key exists but has no expiration (never expires)


# =============================================================================
# Lock Protocol
# =============================================================================

class LockP(Protocol):
    """Lock Protocol"""

    def acquire(self) -> bool:
        ...

    def release(self) -> None:
        ...

    def __enter__(self) -> "LockP":
        ...

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        ...


# =============================================================================
# Configuration Classes
# =============================================================================

@dataclass
class Rate:
    """Rate represents the rate limit configuration"""

    #: Time period for the rate limit
    period: timedelta

    #: Maximum number of requests allowed in the specified time period
    limit: int


@dataclass
class Quota:
    """Quota represents the quota limit configuration"""

    #: Base rate limit configuration
    rate: Rate

    #: Burst capacity, allows temporarily exceeding rate limit, default equals limit
    burst: int = 0

    #: Computed fields
    period_sec: int = 0
    emission_interval: float = 0.0
    fill_rate: float = 0.0

    def __post_init__(self):
        self.period_sec = int(self.rate.period.total_seconds())
        self.emission_interval = self.period_sec / self.rate.limit
        self.fill_rate = self.rate.limit / self.period_sec


def per_duration(duration: timedelta, limit: int, burst: Optional[int] = None) -> Quota:
    """Create a quota with specified duration and request limit"""
    if burst is None:
        burst = limit
    return Quota(Rate(period=duration, limit=limit), burst=burst)


def per_sec(limit: int, burst: Optional[int] = None) -> Quota:
    """Per-second limit"""
    return per_duration(timedelta(seconds=1), limit, burst)


def per_min(limit: int, burst: Optional[int] = None) -> Quota:
    """Per-minute limit"""
    return per_duration(timedelta(minutes=1), limit, burst)


def per_hour(limit: int, burst: Optional[int] = None) -> Quota:
    """Per-hour limit"""
    return per_duration(timedelta(hours=1), limit, burst)


def per_day(limit: int, burst: Optional[int] = None) -> Quota:
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

    def __init__(self, max_size: int = 1024):
        self.max_size: int = max_size
        self.expire_info: Dict[str, float] = {}
        self.lock: LockP = threading.Lock()
        # Use OrderedDict for LRU
        self._client: OrderedDictT[KeyT, Any] = OrderedDict()

    def exists(self, key: KeyT) -> bool:
        """Check if key exists"""
        return key in self._client

    def has_expired(self, key: KeyT) -> bool:
        """Check if key has expired"""
        return self.ttl(key) == STORE_TTL_STATE_NOT_EXIST

    def ttl(self, key: KeyT) -> int:
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

    def check_and_evict(self, key: KeyT) -> None:
        """Check if storage is full, evict oldest entry if so (LRU strategy)"""
        if len(self._client) >= self.max_size and not self.exists(key):
            # Pop the oldest entry
            pop_key, _ = self._client.popitem(last=False)
            self.expire_info.pop(pop_key, None)

    def expire(self, key: KeyT, timeout: int) -> None:
        """Set expiration time for key"""
        self.expire_info[key] = time.monotonic() + timeout

    def hgetall(self, name: KeyT) -> StoreDictValueT:
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

    def hset(
        self,
        name: KeyT,
        key: Optional[KeyT] = None,
        value: Optional[StoreValueT] = None,
        mapping: Optional[StoreDictValueT] = None,
    ) -> None:
        """Set fields and values in hash table"""
        if key is None and not mapping:
            raise ValueError("hset requires key-value pairs")

        kv: StoreDictValueT = {}
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

    def delete(self, key: KeyT) -> bool:
        """Delete key"""
        try:
            self.expire_info.pop(key, None)
            del self._client[key]
        except KeyError:
            return False
        return True


# =============================================================================
# Result Classes
# =============================================================================

@dataclass
class RateLimitState:
    """RateLimitState represents the current state of rate limiter for a given key"""

    #: Maximum requests allowed in initial state
    limit: int

    #: Maximum requests allowed for given key in current state
    remaining: int

    #: Seconds until rate limiter returns to initial state
    reset_after: float

    #: Seconds to retry request, 0 if request is allowed
    retry_after: float = 0


class RateLimitResult:
    """RateLimitResult represents the result of executing rate limiter for a given key"""

    __slots__ = ("limited", "_state_values", "_state")

    def __init__(self, limited: bool, state_values: tuple):
        self.limited: bool = limited
        self._state_values: tuple = state_values
        self._state: Optional[RateLimitState] = None

    @property
    def state(self) -> RateLimitState:
        if self._state:
            return self._state
        self._state = RateLimitState(*self._state_values)
        return self._state


# =============================================================================
# Atomic Operations
# =============================================================================

class BaseAtomicAction:
    """Base class for atomic operations"""

    TYPE: str = ""
    STORE_TYPE: str = ""

    def __init__(self, backend: MemoryStoreBackend):
        self._backend = backend

    def do(self, keys: Sequence[KeyT], args: Optional[Sequence[StoreValueT]]) -> tuple:
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

    TYPE: str = "limit"
    STORE_TYPE: str = "memory"

    def do(
        self, keys: Sequence[KeyT], args: Optional[Sequence[StoreValueT]]
    ) -> tuple[int, int]:
        """Execute token bucket rate limit operation

        Args:
            keys: Storage key list (first element is bucket key)
            args: [rate, capacity, cost] - rate, capacity, request cost

        Returns:
            (limited, tokens) - whether rate limited, current token count
        """
        # Pure computation outside lock to reduce serialized section
        key: str = keys[0]
        rate: float = args[0]
        capacity: int = args[1]
        cost: int = args[2]
        now: int = int(time.time())

        with self._backend.lock:
            # Get current bucket state
            bucket: StoreDictValueT = self._backend.hgetall(key)
            last_tokens: int = bucket.get("tokens", capacity)
            last_refreshed: int = bucket.get("last_refreshed", now)

            # Calculate elapsed time (seconds)
            time_elapsed: int = max(0, now - last_refreshed)

            # Refill tokens: min(capacity, last_tokens + floor(elapsed * rate))
            # Use floor for consistency with original implementation
            tokens: int = min(capacity, last_tokens + math.floor(time_elapsed * rate))

            # Check if rate limiting is needed
            limited: int = 1 if tokens < cost else 0
            if limited:
                return limited, tokens

            # Consume tokens
            tokens -= cost

            # Update bucket state
            self._backend.hset(key, mapping={"tokens": tokens, "last_refreshed": now})

            # Set expiration to 2x time needed to fill bucket
            fill_time: float = capacity / rate
            self._backend.expire(key, math.ceil(2 * fill_time))

            return limited, tokens


# =============================================================================
# Token Bucket Rate Limiter
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

    KEY_PREFIX: str = "throttled:v1:token_bucket:"

    def __init__(self, quota: Quota, backend: Optional[MemoryStoreBackend] = None):
        """
        Args:
            quota: Quota configuration
            backend: Storage backend, defaults to memory storage
        """
        self.quota = quota
        self._backend = backend or MemoryStoreBackend()
        self._atomic_action = MemoryLimitAtomicAction(self._backend)

    def _prepare_key(self, key: str) -> str:
        """Prepare storage key"""
        return "{}{}".format(self.KEY_PREFIX, key)

    def _refill_sec(self, upper: int, remaining: int) -> int:
        """Calculate seconds needed for bucket to recover to limit"""
        if remaining >= upper:
            return 0
        return math.ceil((upper - remaining) / self.quota.fill_rate)

    def _to_result(
        self, limited: int, cost: int, tokens: int, capacity: int
    ) -> RateLimitResult:
        """Convert rate limit result"""
        reset_after: int = self._refill_sec(capacity, tokens)
        # Can retry when tokens refill to cost
        retry_after: int = self._refill_sec(cost, tokens) if limited else 0

        return RateLimitResult(
            limited=bool(limited),
            state_values=(capacity, tokens, reset_after, retry_after),
        )

    def limit(self, key: str, cost: int = 1) -> RateLimitResult:
        """
        Perform rate limit check on request

        Args:
            key: Unique identifier for rate limit target (e.g., user ID, IP address)
            cost: Number of tokens consumed by request, defaults to 1

        Returns:
            RateLimitResult: Contains whether rate limited and current state
        """
        formatted_key: str = self._prepare_key(key)
        rate: float = self.quota.fill_rate
        capacity: int = self.quota.burst

        limited, tokens = self._atomic_action.do(
            [formatted_key], [rate, capacity, cost]
        )

        return self._to_result(limited, cost, tokens, capacity)

    def peek(self, key: str) -> RateLimitState:
        """
        View current rate limit state without modifying state

        Args:
            key: Unique identifier for rate limit target

        Returns:
            RateLimitState: Current rate limit state
        """
        now: int = int(time.time())
        formatted_key: str = self._prepare_key(key)
        rate: float = self.quota.fill_rate
        capacity: int = self.quota.burst

        # Get current bucket state
        bucket: StoreDictValueT = self._backend.hgetall(formatted_key)
        last_tokens: int = bucket.get("tokens", capacity)
        last_refreshed: int = bucket.get("last_refreshed", now)

        # Calculate elapsed time and refill tokens
        time_elapsed: int = max(0, now - last_refreshed)
        tokens: int = min(capacity, last_tokens + math.floor(time_elapsed * rate))

        # Calculate time to fill bucket
        reset_after: int = math.ceil((capacity - tokens) / rate)

        return RateLimitState(limit=capacity, remaining=tokens, reset_after=reset_after)
