from __future__ import annotations

import functools
from abc import ABC, abstractmethod

from deprecated.sphinx import versionadded

from limits import errors
from limits.storage.registry import StorageRegistry
from limits.typing import (
    Any,
    Awaitable,
    Callable,
    Optional,
    P,
    R,
    Type,
    Union,
    cast,
)
from limits.util import LazyDependency


def _wrap_errors(
    storage: Storage,
    fn: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[R]]:
    @functools.wraps(fn)
    async def inner(*args: P.args, **kwargs: P.kwargs) -> R:  # type: ignore[misc]
        try:
            return await fn(*args, **kwargs)
        except storage.base_exceptions as exc:
            if storage.wrap_exceptions:
                raise errors.StorageError(exc) from exc
            raise

    return inner


@versionadded(version="2.1")
class Storage(LazyDependency, metaclass=StorageRegistry):
    """
    Base class to extend when implementing an async storage backend.
    """

    STORAGE_SCHEME: Optional[list[str]]
    """The storage schemes to register against this implementation"""

    def __new__(cls, *args: Any, **kwargs: Any) -> Storage:  # type: ignore[explicit-any]
        inst = super().__new__(cls)

        for method in {
            "incr",
            "get",
            "get_expiry",
            "check",
            "reset",
            "clear",
        }:
            setattr(inst, method, _wrap_errors(inst, getattr(inst, method)))

        return inst

    def __init__(
        self,
        uri: Optional[str] = None,
        wrap_exceptions: bool = False,
        **options: Union[float, str, bool],
    ) -> None:
        """
        :param wrap_exceptions: Whether to wrap storage exceptions in
         :exc:`limits.errors.StorageError` before raising it.
        """
        super().__init__()
        self.wrap_exceptions = wrap_exceptions

    @property
    @abstractmethod
    def base_exceptions(self) -> Union[Type[Exception], tuple[Type[Exception], ...]]:
        raise NotImplementedError

    @abstractmethod
    async def incr(
        self, key: str, expiry: int, elastic_expiry: bool = False, amount: int = 1
    ) -> int:
        """
        increments the counter for a given rate limit key

        :param key: the key to increment
        :param expiry: amount in seconds for the key to expire in
        :param elastic_expiry: whether to keep extending the rate limit
         window every hit.
        :param amount: the number to increment by
        """
        raise NotImplementedError

    @abstractmethod
    async def get(self, key: str) -> int:
        """
        :param key: the key to get the counter value for
        """
        raise NotImplementedError

    @abstractmethod
    async def get_expiry(self, key: str) -> float:
        """
        :param key: the key to get the expiry for
        """
        raise NotImplementedError

    @abstractmethod
    async def check(self) -> bool:
        """
        check if storage is healthy
        """
        raise NotImplementedError

    @abstractmethod
    async def reset(self) -> Optional[int]:
        """
        reset storage to clear limits
        """
        raise NotImplementedError

    @abstractmethod
    async def clear(self, key: str) -> None:
        """
        resets the rate limit key

        :param key: the key to clear rate limits for
        """
        raise NotImplementedError


class MovingWindowSupport(ABC):
    """
    Abstract base class for async storages that support
    the :ref:`strategies:moving window` strategy
    """

    def __new__(cls, *args: Any, **kwargs: Any) -> MovingWindowSupport:  # type: ignore[explicit-any]
        inst = super().__new__(cls)

        for method in {
            "acquire_entry",
            "get_moving_window",
        }:
            setattr(
                inst,
                method,
                _wrap_errors(cast(Storage, inst), getattr(inst, method)),
            )

        return inst

    @abstractmethod
    async def acquire_entry(
        self, key: str, limit: int, expiry: int, amount: int = 1
    ) -> bool:
        """
        :param key: rate limit key to acquire an entry in
        :param limit: amount of entries allowed
        :param expiry: expiry of the entry
        :param amount: the number of entries to acquire
        """
        raise NotImplementedError

    @abstractmethod
    async def get_moving_window(
        self, key: str, limit: int, expiry: int
    ) -> tuple[float, int]:
        """
        returns the starting point and the number of entries in the moving
        window

        :param key: rate limit key
        :param expiry: expiry of entry
        :return: (start of window, number of acquired entries)
        """
        raise NotImplementedError


class SlidingWindowCounterSupport(ABC):
    """
    Abstract base class for async storages that support
    the :ref:`strategies:sliding window counter` strategy
    """

    def __new__(cls, *args: Any, **kwargs: Any) -> SlidingWindowCounterSupport:  # type: ignore[explicit-any]
        inst = super().__new__(cls)

        for method in {"acquire_sliding_window_entry", "get_sliding_window"}:
            setattr(
                inst,
                method,
                _wrap_errors(cast(Storage, inst), getattr(inst, method)),
            )

        return inst

    @abstractmethod
    async def acquire_sliding_window_entry(
        self,
        key: str,
        limit: int,
        expiry: int,
        amount: int = 1,
    ) -> bool:
        """
        Acquire an entry. Shift the current window to the previous window if it expired.

        :param current_window_key: current window key
        :param previous_window_key: previous window key
        :param limit: amount of entries allowed
        :param expiry: expiry of the entry
        :param amount: the number of entries to acquire
        """
        raise NotImplementedError

    @abstractmethod
    async def get_sliding_window(
        self, key: str, expiry: int
    ) -> tuple[int, float, int, float]:
        """
        Return the previous and current window information.

        :param key: the rate limit key
        :param expiry: the rate limit expiry, needed to compute the key in some implementations
        :return: a tuple of (int, float, int, float) with the following information:
          - previous window counter
          - previous window TTL
          - current window counter
          - current window TTL
        """
        raise NotImplementedError
