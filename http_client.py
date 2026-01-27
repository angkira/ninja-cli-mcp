"""HTTP client base class for making HTTP requests.

This module provides an abstract base class that defines the interface for
HTTP client implementations. It supports:
- GET requests with custom headers
- POST requests with data and headers
- Context manager for session management
- Proper type hints and documentation
"""

import threading
import time
from abc import ABC, abstractmethod
from functools import wraps
from types import TracebackType
from typing import Any, Callable, TypeVar

import requests

# Type variable for generic function type hints
F = TypeVar("F", bound=Callable[..., Any])


def rate_limit(calls_per_second: float) -> Callable[[F], F]:
    """Decorator to limit the rate of function calls per second.

    This decorator ensures that a function is not called more frequently than
    the specified rate. It uses threading.Lock for thread safety, making it
    safe to use in multi-threaded environments.

    Args:
        calls_per_second: Maximum number of calls allowed per second.
            Must be a positive number. For example:
            - 1.0 means one call per second
            - 2.0 means two calls per second (minimum 0.5s between calls)
            - 0.5 means one call every two seconds

    Returns:
        A decorator function that wraps the target function with rate limiting.

    Raises:
        ValueError: If calls_per_second is not positive.

    Thread Safety:
        This decorator is thread-safe. Multiple threads can safely call the
        decorated function concurrently, and the rate limit will be enforced
        across all threads.

    Examples:
        >>> @rate_limit(calls_per_second=2.0)
        ... def api_call():
        ...     return "data"
        >>> # First call executes immediately
        >>> api_call()
        'data'
        >>> # Second call within 0.5s will be delayed
        >>> api_call()  # Waits if called too soon
        'data'

        >>> # Can be used on methods too
        >>> class APIClient:
        ...     @rate_limit(calls_per_second=1.0)
        ...     def fetch_data(self, url: str) -> dict:
        ...         return {"url": url}

    Notes:
        - The rate limit is enforced per decorated function, not globally
        - The first call to a decorated function executes immediately
        - Subsequent calls will sleep if they occur too soon after the last call
        - The decorator tracks time using time.time() with second precision
    """
    if calls_per_second <= 0:
        raise ValueError("calls_per_second must be positive")

    # Calculate minimum time between calls in seconds
    min_interval = 1.0 / calls_per_second

    # Dictionary to store last call time for each function instance
    # Using a dict allows the decorator to work with different function instances
    last_call_times: dict[int, float] = {}
    lock = threading.Lock()

    def decorator(func: F) -> F:
        """Inner decorator that wraps the actual function.

        Args:
            func: The function to be rate limited.

        Returns:
            The wrapped function with rate limiting applied.
        """

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            """Wrapper that enforces rate limiting before calling the function.

            Args:
                *args: Positional arguments to pass to the wrapped function.
                **kwargs: Keyword arguments to pass to the wrapped function.

            Returns:
                The return value of the wrapped function.
            """
            # Get a unique identifier for this function call context
            # Use id(func) as the key since each function has a unique identity
            func_id = id(func)

            with lock:
                current_time = time.time()

                # Get the last call time for this function
                last_call_time = last_call_times.get(func_id, 0.0)

                # Calculate how long since the last call
                time_since_last_call = current_time - last_call_time

                # If not enough time has passed, sleep for the remaining time
                if time_since_last_call < min_interval:
                    sleep_time = min_interval - time_since_last_call
                    time.sleep(sleep_time)
                    # Update current time after sleeping
                    current_time = time.time()

                # Update the last call time
                last_call_times[func_id] = current_time

            # Call the actual function
            return func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator


class HTTPClient(ABC):
    """Abstract base class for HTTP client implementations.

    This class defines the interface that all HTTP client implementations
    must follow. It provides methods for making GET and POST requests, and
    supports context manager protocol for proper session management.

    Subclasses must implement:
    - get(): Make HTTP GET requests
    - post(): Make HTTP POST requests
    - __enter__(): Enter context manager (session setup)
    - __exit__(): Exit context manager (session cleanup)

    Examples:
        >>> class MyHTTPClient(HTTPClient):
        ...     def get(self, url: str, headers: Optional[dict[str, str]] = None) -> dict[str, Any]:
        ...         # Implementation here
        ...         pass
        ...
        ...     def post(
        ...         self, url: str, data: Any, headers: Optional[dict[str, str]] = None
        ...     ) -> dict[str, Any]:
        ...         # Implementation here
        ...         pass
        ...
        ...     def __enter__(self) -> "MyHTTPClient":
        ...         # Setup session
        ...         return self
        ...
        ...     def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        ...         # Cleanup session
        ...         pass
        >>> with MyHTTPClient() as client:
        ...     response = client.get("https://api.example.com/data")
        ...     result = client.post("https://api.example.com/submit", data={"key": "value"})
    """

    @abstractmethod
    def get(self, url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
        """Make an HTTP GET request.

        Args:
            url: The URL to make the GET request to.
            headers: Optional dictionary of HTTP headers to include in the request.

        Returns:
            A dictionary containing the response data. The structure depends on
            the implementation but typically includes status, headers, and body.

        Raises:
            NotImplementedError: This is an abstract method and must be implemented
                by subclasses.
            HTTPError: If the request fails (implementation-specific).
            ValueError: If the URL is invalid (implementation-specific).

        Examples:
            >>> client.get("https://api.example.com/data")
            {'status': 200, 'body': {'data': 'value'}}
            >>> client.get(
            ...     "https://api.example.com/data", headers={"Authorization": "Bearer token"}
            ... )
            {'status': 200, 'body': {'protected': 'data'}}
        """
        raise NotImplementedError("Subclasses must implement get()")

    @abstractmethod
    def post(
        self,
        url: str,
        data: Any,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP POST request.

        Args:
            url: The URL to make the POST request to.
            data: The data to send in the request body. Can be a dictionary,
                string, bytes, or any other type supported by the implementation.
            headers: Optional dictionary of HTTP headers to include in the request.

        Returns:
            A dictionary containing the response data. The structure depends on
            the implementation but typically includes status, headers, and body.

        Raises:
            NotImplementedError: This is an abstract method and must be implemented
                by subclasses.
            HTTPError: If the request fails (implementation-specific).
            ValueError: If the URL or data is invalid (implementation-specific).

        Examples:
            >>> client.post("https://api.example.com/submit", data={"key": "value"})
            {'status': 201, 'body': {'id': 123}}
            >>> client.post(
            ...     "https://api.example.com/submit",
            ...     data={"key": "value"},
            ...     headers={"Content-Type": "application/json"},
            ... )
            {'status': 201, 'body': {'id': 124}}
        """
        raise NotImplementedError("Subclasses must implement post()")

    @abstractmethod
    def __enter__(self) -> "HTTPClient":
        """Enter the context manager and set up the HTTP session.

        This method is called when entering a 'with' statement. Subclasses
        should use this to initialize any resources needed for making HTTP
        requests, such as connection pools or session objects.

        Returns:
            The HTTPClient instance for use within the context.

        Raises:
            NotImplementedError: This is an abstract method and must be implemented
                by subclasses.

        Examples:
            >>> with client as c:
            ...     response = c.get("https://api.example.com/data")
        """
        raise NotImplementedError("Subclasses must implement __enter__()")

    @abstractmethod
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the context manager and clean up the HTTP session.

        This method is called when exiting a 'with' statement. Subclasses
        should use this to clean up any resources that were initialized in
        __enter__(), such as closing connections or releasing resources.

        Args:
            exc_type: The type of exception that occurred, if any.
            exc_val: The exception instance that occurred, if any.
            exc_tb: The traceback of the exception, if any.

        Raises:
            NotImplementedError: This is an abstract method and must be implemented
                by subclasses.

        Examples:
            >>> with client as c:
            ...     response = c.get("https://api.example.com/data")
            # __exit__ is automatically called here
        """
        raise NotImplementedError("Subclasses must implement __exit__()")


class RequestsHTTPClient(HTTPClient):
    """HTTP client implementation using the requests library.

    This implementation provides:
    - Automatic retry logic with exponential backoff
    - Error handling for connection errors, timeouts, and HTTP errors
    - Session management for connection pooling
    - Configurable retry parameters

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        initial_backoff: Initial backoff delay in seconds (default: 1.0)
        max_backoff: Maximum backoff delay in seconds (default: 32.0)
        timeout: Request timeout in seconds (default: 30.0)

    Examples:
        >>> with RequestsHTTPClient() as client:
        ...     response = client.get("https://api.example.com/data")
        ...     print(response["status"])
        200

        >>> # Custom retry configuration
        >>> with RequestsHTTPClient(max_retries=5, initial_backoff=2.0) as client:
        ...     response = client.post("https://api.example.com/submit", data={"key": "value"})
    """

    def __init__(
        self,
        max_retries: int = 3,
        initial_backoff: float = 1.0,
        max_backoff: float = 32.0,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the HTTP client with retry configuration.

        Args:
            max_retries: Maximum number of retry attempts.
            initial_backoff: Initial backoff delay in seconds.
            max_backoff: Maximum backoff delay in seconds.
            timeout: Request timeout in seconds.

        Raises:
            ValueError: If any parameter is invalid (negative or zero values).
        """
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if initial_backoff <= 0:
            raise ValueError("initial_backoff must be positive")
        if max_backoff <= 0:
            raise ValueError("max_backoff must be positive")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if initial_backoff > max_backoff:
            raise ValueError("initial_backoff cannot be greater than max_backoff")

        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.timeout = timeout
        self._session: requests.Session | None = None

    def _should_retry(self, exception: Exception) -> bool:
        """Determine if a request should be retried based on the exception.

        Args:
            exception: The exception that occurred during the request.

        Returns:
            True if the request should be retried, False otherwise.
        """
        # Retry on connection errors and timeouts
        if isinstance(exception, (requests.ConnectionError, requests.Timeout)):
            return True

        # Retry on specific HTTP status codes (server errors)
        if isinstance(exception, requests.HTTPError):
            if exception.response is not None:
                status_code = exception.response.status_code
                # Retry on 5xx server errors and 429 (Too Many Requests)
                return status_code >= 500 or status_code == 429

        return False

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay for a given attempt.

        Args:
            attempt: The current retry attempt number (0-based).

        Returns:
            The backoff delay in seconds, capped at max_backoff.
        """
        backoff = self.initial_backoff * (2**attempt)
        return min(backoff, self.max_backoff)

    def _make_request_with_retry(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        data: Any = None,
    ) -> dict[str, Any]:
        """Make an HTTP request with automatic retry logic.

        Args:
            method: HTTP method (GET, POST, etc.).
            url: The URL to make the request to.
            headers: Optional HTTP headers.
            data: Optional request data (for POST requests).

        Returns:
            A dictionary containing status code, headers, and response body.

        Raises:
            requests.ConnectionError: If connection fails after all retries.
            requests.Timeout: If request times out after all retries.
            requests.HTTPError: If HTTP error occurs after all retries.
            RuntimeError: If session is not initialized.
        """
        if self._session is None:
            raise RuntimeError("Session not initialized. Use context manager.")

        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                # Make the request
                response = self._session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=data if data is not None else None,
                    timeout=self.timeout,
                )

                # Raise HTTPError for bad status codes
                response.raise_for_status()

                # Parse response body
                try:
                    body = response.json()
                except ValueError:
                    # If response is not JSON, return text
                    body = response.text

                return {
                    "status": response.status_code,
                    "headers": dict(response.headers),
                    "body": body,
                }

            except Exception as e:
                last_exception = e

                # Check if we should retry
                if not self._should_retry(e) or attempt >= self.max_retries:
                    # No more retries or non-retryable error
                    raise

                # Calculate backoff and wait
                backoff_delay = self._calculate_backoff(attempt)
                time.sleep(backoff_delay)

        # This should never be reached, but just in case
        if last_exception:
            raise last_exception
        raise RuntimeError("Unexpected error in retry logic")

    def get(self, url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
        """Make an HTTP GET request with automatic retry logic.

        Args:
            url: The URL to make the GET request to.
            headers: Optional dictionary of HTTP headers to include in the request.

        Returns:
            A dictionary containing the response data with keys:
            - status: HTTP status code (int)
            - headers: Response headers (dict)
            - body: Response body (dict if JSON, str otherwise)

        Raises:
            requests.ConnectionError: If connection fails after all retries.
            requests.Timeout: If request times out after all retries.
            requests.HTTPError: If HTTP error occurs after all retries.
            RuntimeError: If session is not initialized.

        Examples:
            >>> with RequestsHTTPClient() as client:
            ...     response = client.get("https://api.example.com/data")
            ...     print(response["status"])
            200
        """
        return self._make_request_with_retry("GET", url, headers=headers)

    def post(
        self,
        url: str,
        data: Any,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP POST request with automatic retry logic.

        Args:
            url: The URL to make the POST request to.
            data: The data to send in the request body (will be JSON-encoded).
            headers: Optional dictionary of HTTP headers to include in the request.

        Returns:
            A dictionary containing the response data with keys:
            - status: HTTP status code (int)
            - headers: Response headers (dict)
            - body: Response body (dict if JSON, str otherwise)

        Raises:
            requests.ConnectionError: If connection fails after all retries.
            requests.Timeout: If request times out after all retries.
            requests.HTTPError: If HTTP error occurs after all retries.
            RuntimeError: If session is not initialized.

        Examples:
            >>> with RequestsHTTPClient() as client:
            ...     response = client.post("https://api.example.com/submit", data={"key": "value"})
            ...     print(response["status"])
            201
        """
        return self._make_request_with_retry("POST", url, headers=headers, data=data)

    def __enter__(self) -> "RequestsHTTPClient":
        """Enter the context manager and set up the HTTP session.

        Returns:
            The RequestsHTTPClient instance with an active session.

        Examples:
            >>> with RequestsHTTPClient() as client:
            ...     response = client.get("https://api.example.com/data")
        """
        self._session = requests.Session()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the context manager and clean up the HTTP session.

        Args:
            exc_type: The type of exception that occurred, if any.
            exc_val: The exception instance that occurred, if any.
            exc_tb: The traceback of the exception, if any.

        Examples:
            >>> with RequestsHTTPClient() as client:
            ...     response = client.get("https://api.example.com/data")
            # Session is automatically closed here
        """
        if self._session is not None:
            self._session.close()
            self._session = None
