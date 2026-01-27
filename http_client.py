"""HTTP client base class for making HTTP requests.

This module provides an abstract base class that defines the interface for
HTTP client implementations. It supports:
- GET requests with custom headers
- POST requests with data and headers
- Context manager for session management
- Proper type hints and documentation
"""

from abc import ABC, abstractmethod
from types import TracebackType
from typing import Any


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
