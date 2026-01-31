"""Comprehensive tests for http_client module.

Tests cover abstract base class behavior, context manager protocol,
method signatures, and concrete implementations.
"""

import threading
import time
from unittest.mock import Mock, patch

import pytest
import requests
from http_client import HTTPClient, RequestsHTTPClient, rate_limit


class TestRateLimitDecorator:
    """Tests for the rate_limit decorator."""

    def test_rate_limit_basic_functionality(self) -> None:
        """Test that rate_limit enforces minimum time between calls."""
        call_times = []

        @rate_limit(calls_per_second=2.0)
        def test_func() -> str:
            call_times.append(time.time())
            return "called"

        # Make three calls
        result1 = test_func()
        result2 = test_func()
        result3 = test_func()

        assert result1 == "called"
        assert result2 == "called"
        assert result3 == "called"
        assert len(call_times) == 3

        # With 2 calls per second, minimum interval is 0.5 seconds
        # Check that there's at least ~0.5s between calls (with small tolerance)
        time_diff_1_2 = call_times[1] - call_times[0]
        time_diff_2_3 = call_times[2] - call_times[1]

        assert time_diff_1_2 >= 0.49  # Allow small tolerance
        assert time_diff_2_3 >= 0.49

    def test_rate_limit_one_call_per_second(self) -> None:
        """Test rate limiting with 1 call per second."""
        call_times = []

        @rate_limit(calls_per_second=1.0)
        def test_func() -> None:
            call_times.append(time.time())

        # Make two calls
        test_func()
        test_func()

        # Should be at least 1 second apart
        time_diff = call_times[1] - call_times[0]
        assert time_diff >= 0.99

    def test_rate_limit_fractional_rate(self) -> None:
        """Test rate limiting with fractional calls per second."""
        call_times = []

        @rate_limit(calls_per_second=0.5)  # One call every 2 seconds
        def test_func() -> None:
            call_times.append(time.time())

        # Make two calls
        test_func()
        test_func()

        # Should be at least 2 seconds apart
        time_diff = call_times[1] - call_times[0]
        assert time_diff >= 1.99

    def test_rate_limit_with_arguments(self) -> None:
        """Test that rate limiting works with function arguments."""
        call_times = []

        @rate_limit(calls_per_second=2.0)
        def test_func(x: int, y: str) -> tuple[int, str]:
            call_times.append(time.time())
            return x, y

        result1 = test_func(1, "a")
        result2 = test_func(2, "b")

        assert result1 == (1, "a")
        assert result2 == (2, "b")
        assert len(call_times) == 2

        time_diff = call_times[1] - call_times[0]
        assert time_diff >= 0.49

    def test_rate_limit_with_kwargs(self) -> None:
        """Test that rate limiting works with keyword arguments."""
        call_times = []

        @rate_limit(calls_per_second=2.0)
        def test_func(x: int, y: str = "default") -> dict:
            call_times.append(time.time())
            return {"x": x, "y": y}

        result1 = test_func(1, y="custom")
        result2 = test_func(2)

        assert result1 == {"x": 1, "y": "custom"}
        assert result2 == {"x": 2, "y": "default"}
        assert len(call_times) == 2

    def test_rate_limit_invalid_rate(self) -> None:
        """Test that invalid rate values raise ValueError."""
        with pytest.raises(ValueError, match="calls_per_second must be positive"):

            @rate_limit(calls_per_second=0)
            def test_func() -> None:
                pass

        with pytest.raises(ValueError, match="calls_per_second must be positive"):

            @rate_limit(calls_per_second=-1.0)
            def test_func2() -> None:
                pass

    def test_rate_limit_on_method(self) -> None:
        """Test that rate limiting works on class methods."""
        call_times = []

        class TestClass:
            @rate_limit(calls_per_second=2.0)
            def method(self) -> str:
                call_times.append(time.time())
                return "method called"

        obj = TestClass()
        result1 = obj.method()
        result2 = obj.method()

        assert result1 == "method called"
        assert result2 == "method called"
        assert len(call_times) == 2

        time_diff = call_times[1] - call_times[0]
        assert time_diff >= 0.49

    def test_rate_limit_thread_safety(self) -> None:
        """Test that rate limiting is thread-safe."""
        call_times = []
        lock = threading.Lock()

        @rate_limit(calls_per_second=2.0)
        def test_func(thread_id: int) -> None:
            with lock:
                call_times.append((time.time(), thread_id))

        # Create multiple threads that call the function
        threads = []
        for i in range(4):
            thread = threading.Thread(target=test_func, args=(i,))
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # All calls should have completed
        assert len(call_times) == 4

        # Sort by time to check intervals
        call_times.sort(key=lambda x: x[0])

        # Check that consecutive calls respect the rate limit
        for i in range(1, len(call_times)):
            time_diff = call_times[i][0] - call_times[i - 1][0]
            # Should be at least ~0.5s between calls
            assert time_diff >= 0.48  # Slightly lower tolerance for threading

    def test_rate_limit_multiple_functions(self) -> None:
        """Test that different functions have independent rate limits."""
        call_times_a = []
        call_times_b = []

        @rate_limit(calls_per_second=1.0)
        def func_a() -> None:
            call_times_a.append(time.time())

        @rate_limit(calls_per_second=2.0)
        def func_b() -> None:
            call_times_b.append(time.time())

        # Call func_a twice
        func_a()
        func_a()

        # Call func_b twice (should be faster)
        func_b()
        func_b()

        # func_a should have ~1s interval
        time_diff_a = call_times_a[1] - call_times_a[0]
        assert time_diff_a >= 0.99

        # func_b should have ~0.5s interval
        time_diff_b = call_times_b[1] - call_times_b[0]
        assert time_diff_b >= 0.49
        assert time_diff_b < 0.7  # Should be significantly less than func_a

    def test_rate_limit_preserves_function_metadata(self) -> None:
        """Test that decorator preserves function name and docstring."""

        @rate_limit(calls_per_second=1.0)
        def test_func() -> None:
            """Test function docstring."""
            pass

        assert test_func.__name__ == "test_func"
        assert test_func.__doc__ == "Test function docstring."

    def test_rate_limit_with_exception(self) -> None:
        """Test that rate limiting still applies when function raises exception."""
        call_times = []

        @rate_limit(calls_per_second=2.0)
        def test_func(should_raise: bool) -> str:
            call_times.append(time.time())
            if should_raise:
                raise ValueError("Test error")
            return "success"

        # First call succeeds
        result = test_func(False)
        assert result == "success"

        # Second call raises exception
        with pytest.raises(ValueError, match="Test error"):
            test_func(True)

        # Third call succeeds and should still be rate limited
        result = test_func(False)
        assert result == "success"

        # Check that rate limiting was enforced
        assert len(call_times) == 3
        time_diff_1 = call_times[1] - call_times[0]
        time_diff_2 = call_times[2] - call_times[1]
        assert time_diff_1 >= 0.49
        assert time_diff_2 >= 0.49

    def test_rate_limit_high_rate(self) -> None:
        """Test rate limiting with very high rate (10 calls per second)."""
        call_times = []

        @rate_limit(calls_per_second=10.0)
        def test_func() -> None:
            call_times.append(time.time())

        # Make 5 calls
        for _ in range(5):
            test_func()

        assert len(call_times) == 5

        # Total time should be at least 0.4 seconds (4 intervals of 0.1s)
        total_time = call_times[-1] - call_times[0]
        assert total_time >= 0.39

    def test_rate_limit_first_call_immediate(self) -> None:
        """Test that the first call to a rate-limited function is immediate."""
        start_time = time.time()

        @rate_limit(calls_per_second=1.0)
        def test_func() -> None:
            pass

        test_func()
        elapsed = time.time() - start_time

        # First call should be essentially immediate (< 0.1s)
        assert elapsed < 0.1

    def test_rate_limit_concurrent_access_different_instances(self) -> None:
        """Test rate limiting with different instances of the same class."""
        call_times = []
        lock = threading.Lock()

        class APIClient:
            @rate_limit(calls_per_second=2.0)
            def call_api(self, client_id: int) -> None:
                with lock:
                    call_times.append((time.time(), client_id))

        # Create two instances
        client1 = APIClient()
        client2 = APIClient()

        # Make calls from both instances
        client1.call_api(1)
        client2.call_api(2)
        client1.call_api(1)
        client2.call_api(2)

        # All calls should be rate limited together
        assert len(call_times) == 4

        # Sort by time
        call_times.sort(key=lambda x: x[0])

        # Check intervals
        for i in range(1, len(call_times)):
            time_diff = call_times[i][0] - call_times[i - 1][0]
            assert time_diff >= 0.48


class TestHTTPClientAbstract:
    """Tests for HTTPClient abstract base class."""

    def test_cannot_instantiate_abstract_class(self) -> None:
        """Test that HTTPClient cannot be instantiated directly."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            HTTPClient()  # type: ignore

    def test_requires_all_abstract_methods(self) -> None:
        """Test that subclass must implement all abstract methods."""

        # Missing all methods
        class IncompleteClient(HTTPClient):
            pass

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteClient()  # type: ignore

        # Missing some methods
        class PartialClient(HTTPClient):
            def get(self, url: str, headers: dict[str, str] | None = None) -> dict:
                return {}

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            PartialClient()  # type: ignore


class TestHTTPClientConcrete:
    """Tests for concrete implementations of HTTPClient."""

    def test_concrete_implementation_valid(self) -> None:
        """Test that a complete concrete implementation can be instantiated."""

        class ConcreteClient(HTTPClient):
            def __init__(self) -> None:
                self.session_active = False

            def get(self, url: str, headers: dict[str, str] | None = None) -> dict:
                return {"status": 200, "body": {}}

            def post(self, url: str, data: dict, headers: dict[str, str] | None = None) -> dict:
                return {"status": 201, "body": {}}

            def __enter__(self) -> "ConcreteClient":
                self.session_active = True
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                self.session_active = False

        # Should instantiate without errors
        client = ConcreteClient()
        assert isinstance(client, HTTPClient)
        assert isinstance(client, ConcreteClient)

    def test_get_method_signature(self) -> None:
        """Test that get method has correct signature and behavior."""

        class TestClient(HTTPClient):
            def __init__(self) -> None:
                self.last_url = None
                self.last_headers = None

            def get(self, url: str, headers: dict[str, str] | None = None) -> dict:
                self.last_url = url
                self.last_headers = headers
                return {"status": 200, "body": {"data": "test"}}

            def post(self, url: str, data: dict, headers: dict[str, str] | None = None) -> dict:
                return {}

            def __enter__(self) -> "TestClient":
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                pass

        client = TestClient()

        # Test basic GET
        response = client.get("https://example.com/api")
        assert response["status"] == 200
        assert client.last_url == "https://example.com/api"
        assert client.last_headers is None

        # Test GET with headers
        headers = {"Authorization": "Bearer token"}
        response = client.get("https://example.com/api", headers=headers)
        assert client.last_headers == headers

    def test_post_method_signature(self) -> None:
        """Test that post method has correct signature and behavior."""

        class TestClient(HTTPClient):
            def __init__(self) -> None:
                self.last_url = None
                self.last_data = None
                self.last_headers = None

            def get(self, url: str, headers: dict[str, str] | None = None) -> dict:
                return {}

            def post(self, url: str, data: dict, headers: dict[str, str] | None = None) -> dict:
                self.last_url = url
                self.last_data = data
                self.last_headers = headers
                return {"status": 201, "body": {"id": 123}}

            def __enter__(self) -> "TestClient":
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                pass

        client = TestClient()

        # Test basic POST
        data = {"key": "value"}
        response = client.post("https://example.com/api", data=data)
        assert response["status"] == 201
        assert client.last_url == "https://example.com/api"
        assert client.last_data == data
        assert client.last_headers is None

        # Test POST with headers
        headers = {"Content-Type": "application/json"}
        response = client.post("https://example.com/api", data=data, headers=headers)
        assert client.last_headers == headers


class TestContextManager:
    """Tests for context manager protocol implementation."""

    def test_context_manager_basic(self) -> None:
        """Test basic context manager usage."""

        class TestClient(HTTPClient):
            def __init__(self) -> None:
                self.entered = False
                self.exited = False

            def get(self, url: str, headers: dict[str, str] | None = None) -> dict:
                return {}

            def post(self, url: str, data: dict, headers: dict[str, str] | None = None) -> dict:
                return {}

            def __enter__(self) -> "TestClient":
                self.entered = True
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                self.exited = True

        client = TestClient()
        assert not client.entered
        assert not client.exited

        with client as c:
            assert client.entered
            assert not client.exited
            assert c is client

        assert client.entered
        assert client.exited

    def test_context_manager_with_operations(self) -> None:
        """Test context manager with HTTP operations inside."""

        class TestClient(HTTPClient):
            def __init__(self) -> None:
                self.session_active = False
                self.requests_made = []

            def get(self, url: str, headers: dict[str, str] | None = None) -> dict:
                if not self.session_active:
                    raise RuntimeError("Session not active")
                self.requests_made.append(("GET", url))
                return {"status": 200}

            def post(self, url: str, data: dict, headers: dict[str, str] | None = None) -> dict:
                if not self.session_active:
                    raise RuntimeError("Session not active")
                self.requests_made.append(("POST", url))
                return {"status": 201}

            def __enter__(self) -> "TestClient":
                self.session_active = True
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                self.session_active = False

        client = TestClient()

        # Should fail outside context
        with pytest.raises(RuntimeError, match="Session not active"):
            client.get("https://example.com")

        # Should work inside context
        with client as c:
            c.get("https://example.com/1")
            c.post("https://example.com/2", data={})

        assert len(client.requests_made) == 2
        assert client.requests_made[0] == ("GET", "https://example.com/1")
        assert client.requests_made[1] == ("POST", "https://example.com/2")

        # Should fail after context
        with pytest.raises(RuntimeError, match="Session not active"):
            client.get("https://example.com")

    def test_context_manager_exception_handling(self) -> None:
        """Test that __exit__ is called even when exception occurs."""

        class TestClient(HTTPClient):
            def __init__(self) -> None:
                self.cleanup_called = False
                self.exception_info: tuple | None = None

            def get(self, url: str, headers: dict[str, str] | None = None) -> dict:
                return {}

            def post(self, url: str, data: dict, headers: dict[str, str] | None = None) -> dict:
                return {}

            def __enter__(self) -> "TestClient":
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                self.cleanup_called = True
                self.exception_info = (exc_type, exc_val, exc_tb)

        client = TestClient()

        # Test with exception
        with pytest.raises(ValueError, match="Test error"):
            with client:
                raise ValueError("Test error")

        assert client.cleanup_called
        assert client.exception_info is not None
        assert client.exception_info[0] is ValueError
        assert str(client.exception_info[1]) == "Test error"

    def test_context_manager_returns_self(self) -> None:
        """Test that __enter__ returns the client instance."""

        class TestClient(HTTPClient):
            def get(self, url: str, headers: dict[str, str] | None = None) -> dict:
                return {}

            def post(self, url: str, data: dict, headers: dict[str, str] | None = None) -> dict:
                return {}

            def __enter__(self) -> "TestClient":
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                pass

        client = TestClient()
        with client as c:
            assert c is client
            assert isinstance(c, TestClient)
            assert isinstance(c, HTTPClient)


class TestDataTypes:
    """Tests for various data types in requests."""

    def test_post_with_dict_data(self) -> None:
        """Test POST with dictionary data."""

        class TestClient(HTTPClient):
            def __init__(self) -> None:
                self.received_data = None

            def get(self, url: str, headers: dict[str, str] | None = None) -> dict:
                return {}

            def post(self, url: str, data: dict, headers: dict[str, str] | None = None) -> dict:
                self.received_data = data
                return {"status": 201}

            def __enter__(self) -> "TestClient":
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                pass

        client = TestClient()
        data = {"key": "value", "number": 42, "nested": {"inner": "data"}}
        client.post("https://example.com", data=data)
        assert client.received_data == data

    def test_get_with_various_headers(self) -> None:
        """Test GET with various header types."""

        class TestClient(HTTPClient):
            def __init__(self) -> None:
                self.received_headers = None

            def get(self, url: str, headers: dict[str, str] | None = None) -> dict:
                self.received_headers = headers
                return {"status": 200}

            def post(self, url: str, data: dict, headers: dict[str, str] | None = None) -> dict:
                return {}

            def __enter__(self) -> "TestClient":
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                pass

        client = TestClient()

        # Test with None headers
        client.get("https://example.com")
        assert client.received_headers is None

        # Test with empty headers
        client.get("https://example.com", headers={})
        assert client.received_headers == {}

        # Test with multiple headers
        headers = {
            "Authorization": "Bearer token",
            "Content-Type": "application/json",
            "User-Agent": "TestClient/1.0",
        }
        client.get("https://example.com", headers=headers)
        assert client.received_headers == headers


class TestInheritance:
    """Tests for inheritance and subclassing behavior."""

    def test_multiple_concrete_implementations(self) -> None:
        """Test that multiple concrete implementations can coexist."""

        class ClientA(HTTPClient):
            def get(self, url: str, headers: dict[str, str] | None = None) -> dict:
                return {"client": "A"}

            def post(self, url: str, data: dict, headers: dict[str, str] | None = None) -> dict:
                return {"client": "A"}

            def __enter__(self) -> "ClientA":
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                pass

        class ClientB(HTTPClient):
            def get(self, url: str, headers: dict[str, str] | None = None) -> dict:
                return {"client": "B"}

            def post(self, url: str, data: dict, headers: dict[str, str] | None = None) -> dict:
                return {"client": "B"}

            def __enter__(self) -> "ClientB":
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                pass

        client_a = ClientA()
        client_b = ClientB()

        assert client_a.get("https://example.com")["client"] == "A"
        assert client_b.get("https://example.com")["client"] == "B"

    def test_isinstance_checks(self) -> None:
        """Test isinstance checks work correctly."""

        class ConcreteClient(HTTPClient):
            def get(self, url: str, headers: dict[str, str] | None = None) -> dict:
                return {}

            def post(self, url: str, data: dict, headers: dict[str, str] | None = None) -> dict:
                return {}

            def __enter__(self) -> "ConcreteClient":
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                pass

        client = ConcreteClient()
        assert isinstance(client, ConcreteClient)
        assert isinstance(client, HTTPClient)
        assert not isinstance(client, str)


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_url(self) -> None:
        """Test handling of empty URLs."""

        class TestClient(HTTPClient):
            def get(self, url: str, headers: dict[str, str] | None = None) -> dict:
                if not url:
                    raise ValueError("URL cannot be empty")
                return {"status": 200}

            def post(self, url: str, data: dict, headers: dict[str, str] | None = None) -> dict:
                if not url:
                    raise ValueError("URL cannot be empty")
                return {"status": 201}

            def __enter__(self) -> "TestClient":
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                pass

        client = TestClient()
        with pytest.raises(ValueError, match="URL cannot be empty"):
            client.get("")

        with pytest.raises(ValueError, match="URL cannot be empty"):
            client.post("", data={})

    def test_none_data_in_post(self) -> None:
        """Test POST with None data."""

        class TestClient(HTTPClient):
            def __init__(self) -> None:
                self.received_data = "not_set"

            def get(self, url: str, headers: dict[str, str] | None = None) -> dict:
                return {}

            def post(self, url: str, data: dict, headers: dict[str, str] | None = None) -> dict:
                self.received_data = data
                return {"status": 201}

            def __enter__(self) -> "TestClient":
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                pass

        client = TestClient()
        client.post("https://example.com", data=None)  # type: ignore
        assert client.received_data is None

    def test_reusable_client(self) -> None:
        """Test that client can be reused multiple times."""

        class TestClient(HTTPClient):
            def __init__(self) -> None:
                self.enter_count = 0
                self.exit_count = 0

            def get(self, url: str, headers: dict[str, str] | None = None) -> dict:
                return {"status": 200}

            def post(self, url: str, data: dict, headers: dict[str, str] | None = None) -> dict:
                return {"status": 201}

            def __enter__(self) -> "TestClient":
                self.enter_count += 1
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                self.exit_count += 1

        client = TestClient()

        # Use multiple times
        with client:
            pass
        assert client.enter_count == 1
        assert client.exit_count == 1

        with client:
            pass
        assert client.enter_count == 2
        assert client.exit_count == 2

        with client:
            pass
        assert client.enter_count == 3
        assert client.exit_count == 3


class TestRequestsHTTPClientInitialization:
    """Tests for RequestsHTTPClient initialization and configuration."""

    def test_default_initialization(self) -> None:
        """Test RequestsHTTPClient with default parameters."""
        client = RequestsHTTPClient()
        assert client.max_retries == 3
        assert client.initial_backoff == 1.0
        assert client.max_backoff == 32.0
        assert client.timeout == 30.0
        assert client._session is None

    def test_custom_initialization(self) -> None:
        """Test RequestsHTTPClient with custom parameters."""
        client = RequestsHTTPClient(
            max_retries=5,
            initial_backoff=2.0,
            max_backoff=64.0,
            timeout=60.0,
        )
        assert client.max_retries == 5
        assert client.initial_backoff == 2.0
        assert client.max_backoff == 64.0
        assert client.timeout == 60.0

    def test_invalid_max_retries(self) -> None:
        """Test that negative max_retries raises ValueError."""
        with pytest.raises(ValueError, match="max_retries must be non-negative"):
            RequestsHTTPClient(max_retries=-1)

    def test_invalid_initial_backoff(self) -> None:
        """Test that non-positive initial_backoff raises ValueError."""
        with pytest.raises(ValueError, match="initial_backoff must be positive"):
            RequestsHTTPClient(initial_backoff=0)
        with pytest.raises(ValueError, match="initial_backoff must be positive"):
            RequestsHTTPClient(initial_backoff=-1.0)

    def test_invalid_max_backoff(self) -> None:
        """Test that non-positive max_backoff raises ValueError."""
        with pytest.raises(ValueError, match="max_backoff must be positive"):
            RequestsHTTPClient(max_backoff=0)
        with pytest.raises(ValueError, match="max_backoff must be positive"):
            RequestsHTTPClient(max_backoff=-1.0)

    def test_invalid_timeout(self) -> None:
        """Test that non-positive timeout raises ValueError."""
        with pytest.raises(ValueError, match="timeout must be positive"):
            RequestsHTTPClient(timeout=0)
        with pytest.raises(ValueError, match="timeout must be positive"):
            RequestsHTTPClient(timeout=-1.0)

    def test_initial_backoff_greater_than_max(self) -> None:
        """Test that initial_backoff > max_backoff raises ValueError."""
        with pytest.raises(ValueError, match="initial_backoff cannot be greater than max_backoff"):
            RequestsHTTPClient(initial_backoff=10.0, max_backoff=5.0)

    def test_is_http_client_instance(self) -> None:
        """Test that RequestsHTTPClient is an instance of HTTPClient."""
        client = RequestsHTTPClient()
        assert isinstance(client, HTTPClient)
        assert isinstance(client, RequestsHTTPClient)


class TestRequestsHTTPClientContextManager:
    """Tests for RequestsHTTPClient context manager functionality."""

    def test_context_manager_creates_session(self) -> None:
        """Test that entering context creates a session."""
        client = RequestsHTTPClient()
        assert client._session is None

        with client:
            assert client._session is not None
            assert isinstance(client._session, requests.Session)

        assert client._session is None

    def test_context_manager_closes_session(self) -> None:
        """Test that exiting context closes the session."""
        client = RequestsHTTPClient()

        with patch("requests.Session") as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session

            with client:
                assert client._session is mock_session

            mock_session.close.assert_called_once()

    def test_context_manager_closes_on_exception(self) -> None:
        """Test that session is closed even when exception occurs."""
        client = RequestsHTTPClient()

        with patch("requests.Session") as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session

            with pytest.raises(ValueError, match="Test error"):
                with client:
                    raise ValueError("Test error")

            mock_session.close.assert_called_once()
            assert client._session is None


class TestRequestsHTTPClientBackoff:
    """Tests for exponential backoff calculation."""

    def test_backoff_calculation(self) -> None:
        """Test exponential backoff calculation."""
        client = RequestsHTTPClient(initial_backoff=1.0, max_backoff=32.0)

        # Test exponential growth
        assert client._calculate_backoff(0) == 1.0
        assert client._calculate_backoff(1) == 2.0
        assert client._calculate_backoff(2) == 4.0
        assert client._calculate_backoff(3) == 8.0
        assert client._calculate_backoff(4) == 16.0
        assert client._calculate_backoff(5) == 32.0

        # Test capping at max_backoff
        assert client._calculate_backoff(6) == 32.0
        assert client._calculate_backoff(10) == 32.0

    def test_custom_backoff_values(self) -> None:
        """Test backoff calculation with custom values."""
        client = RequestsHTTPClient(initial_backoff=2.0, max_backoff=16.0)

        assert client._calculate_backoff(0) == 2.0
        assert client._calculate_backoff(1) == 4.0
        assert client._calculate_backoff(2) == 8.0
        assert client._calculate_backoff(3) == 16.0
        assert client._calculate_backoff(4) == 16.0


class TestRequestsHTTPClientShouldRetry:
    """Tests for retry decision logic."""

    def test_should_retry_connection_error(self) -> None:
        """Test that connection errors trigger retry."""
        client = RequestsHTTPClient()
        assert client._should_retry(requests.ConnectionError("Connection failed"))

    def test_should_retry_timeout(self) -> None:
        """Test that timeout errors trigger retry."""
        client = RequestsHTTPClient()
        assert client._should_retry(requests.Timeout("Request timed out"))

    def test_should_retry_5xx_errors(self) -> None:
        """Test that 5xx HTTP errors trigger retry."""
        client = RequestsHTTPClient()

        for status_code in [500, 502, 503, 504]:
            response = Mock()
            response.status_code = status_code
            error = requests.HTTPError(response=response)
            error.response = response
            assert client._should_retry(error), f"Should retry {status_code}"

    def test_should_retry_429_error(self) -> None:
        """Test that 429 (Too Many Requests) triggers retry."""
        client = RequestsHTTPClient()
        response = Mock()
        response.status_code = 429
        error = requests.HTTPError(response=response)
        error.response = response
        assert client._should_retry(error)

    def test_should_not_retry_4xx_errors(self) -> None:
        """Test that 4xx errors (except 429) do not trigger retry."""
        client = RequestsHTTPClient()

        for status_code in [400, 401, 403, 404]:
            response = Mock()
            response.status_code = status_code
            error = requests.HTTPError(response=response)
            error.response = response
            assert not client._should_retry(error), f"Should not retry {status_code}"

    def test_should_not_retry_other_exceptions(self) -> None:
        """Test that other exceptions do not trigger retry."""
        client = RequestsHTTPClient()
        assert not client._should_retry(ValueError("Some error"))
        assert not client._should_retry(KeyError("Some error"))
        assert not client._should_retry(RuntimeError("Some error"))


class TestRequestsHTTPClientGet:
    """Tests for GET request functionality."""

    def test_get_success(self) -> None:
        """Test successful GET request."""
        client = RequestsHTTPClient()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {"data": "test"}

        with patch("requests.Session") as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            mock_session.request.return_value = mock_response

            with client as c:
                response = c.get("https://api.example.com/data")

            assert response["status"] == 200
            assert response["body"] == {"data": "test"}
            assert response["headers"]["Content-Type"] == "application/json"

            mock_session.request.assert_called_once_with(
                method="GET",
                url="https://api.example.com/data",
                headers=None,
                json=None,
                timeout=30.0,
            )

    def test_get_with_headers(self) -> None:
        """Test GET request with custom headers."""
        client = RequestsHTTPClient()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {}

        with patch("requests.Session") as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            mock_session.request.return_value = mock_response

            headers = {"Authorization": "Bearer token"}
            with client as c:
                c.get("https://api.example.com/data", headers=headers)

            mock_session.request.assert_called_once()
            call_args = mock_session.request.call_args
            assert call_args[1]["headers"] == headers

    def test_get_non_json_response(self) -> None:
        """Test GET request with non-JSON response."""
        client = RequestsHTTPClient()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "text/plain"}
        mock_response.json.side_effect = ValueError("No JSON")
        mock_response.text = "Plain text response"

        with patch("requests.Session") as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            mock_session.request.return_value = mock_response

            with client as c:
                response = c.get("https://api.example.com/data")

            assert response["status"] == 200
            assert response["body"] == "Plain text response"

    def test_get_without_context_manager(self) -> None:
        """Test that GET fails without context manager."""
        client = RequestsHTTPClient()

        with pytest.raises(RuntimeError, match="Session not initialized"):
            client.get("https://api.example.com/data")


class TestRequestsHTTPClientPost:
    """Tests for POST request functionality."""

    def test_post_success(self) -> None:
        """Test successful POST request."""
        client = RequestsHTTPClient()

        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {"id": 123}

        with patch("requests.Session") as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            mock_session.request.return_value = mock_response

            data = {"key": "value"}
            with client as c:
                response = c.post("https://api.example.com/submit", data=data)

            assert response["status"] == 201
            assert response["body"] == {"id": 123}

            mock_session.request.assert_called_once_with(
                method="POST",
                url="https://api.example.com/submit",
                headers=None,
                json=data,
                timeout=30.0,
            )

    def test_post_with_headers(self) -> None:
        """Test POST request with custom headers."""
        client = RequestsHTTPClient()

        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.headers = {}
        mock_response.json.return_value = {}

        with patch("requests.Session") as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            mock_session.request.return_value = mock_response

            headers = {"Content-Type": "application/json"}
            data = {"key": "value"}
            with client as c:
                c.post("https://api.example.com/submit", data=data, headers=headers)

            call_args = mock_session.request.call_args
            assert call_args[1]["headers"] == headers

    def test_post_without_context_manager(self) -> None:
        """Test that POST fails without context manager."""
        client = RequestsHTTPClient()

        with pytest.raises(RuntimeError, match="Session not initialized"):
            client.post("https://api.example.com/submit", data={"key": "value"})


class TestRequestsHTTPClientRetry:
    """Tests for retry logic functionality."""

    @patch("time.sleep")
    def test_retry_on_connection_error(self, mock_sleep: Mock) -> None:
        """Test retry on connection error."""
        client = RequestsHTTPClient(max_retries=2, initial_backoff=1.0)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {"success": True}

        with patch("requests.Session") as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session

            # Fail twice, then succeed
            mock_session.request.side_effect = [
                requests.ConnectionError("Connection failed"),
                requests.ConnectionError("Connection failed"),
                mock_response,
            ]

            with client as c:
                response = c.get("https://api.example.com/data")

            assert response["status"] == 200
            assert response["body"] == {"success": True}
            assert mock_session.request.call_count == 3

            # Verify backoff delays
            assert mock_sleep.call_count == 2
            mock_sleep.assert_any_call(1.0)  # First retry
            mock_sleep.assert_any_call(2.0)  # Second retry

    @patch("time.sleep")
    def test_retry_on_timeout(self, mock_sleep: Mock) -> None:
        """Test retry on timeout error."""
        client = RequestsHTTPClient(max_retries=1, initial_backoff=1.0)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {}

        with patch("requests.Session") as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session

            # Timeout once, then succeed
            mock_session.request.side_effect = [
                requests.Timeout("Request timed out"),
                mock_response,
            ]

            with client as c:
                response = c.get("https://api.example.com/data")

            assert response["status"] == 200
            assert mock_session.request.call_count == 2
            mock_sleep.assert_called_once_with(1.0)

    @patch("time.sleep")
    def test_retry_on_5xx_error(self, mock_sleep: Mock) -> None:
        """Test retry on 5xx server error."""
        client = RequestsHTTPClient(max_retries=1, initial_backoff=1.0)

        error_response = Mock()
        error_response.status_code = 500
        error_response.raise_for_status.side_effect = requests.HTTPError(response=error_response)

        success_response = Mock()
        success_response.status_code = 200
        success_response.headers = {}
        success_response.json.return_value = {}

        with patch("requests.Session") as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session

            # 500 error once, then succeed
            mock_session.request.side_effect = [error_response, success_response]

            with client as c:
                response = c.get("https://api.example.com/data")

            assert response["status"] == 200
            assert mock_session.request.call_count == 2
            mock_sleep.assert_called_once_with(1.0)

    @patch("time.sleep")
    def test_max_retries_exhausted(self, mock_sleep: Mock) -> None:
        """Test that error is raised after max retries exhausted."""
        client = RequestsHTTPClient(max_retries=2, initial_backoff=1.0)

        with patch("requests.Session") as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session

            # Always fail
            mock_session.request.side_effect = requests.ConnectionError("Connection failed")

            with client as c:
                with pytest.raises(requests.ConnectionError, match="Connection failed"):
                    c.get("https://api.example.com/data")

            # Should try max_retries + 1 times (initial + retries)
            assert mock_session.request.call_count == 3
            assert mock_sleep.call_count == 2

    def test_no_retry_on_4xx_error(self) -> None:
        """Test that 4xx errors are not retried."""
        client = RequestsHTTPClient(max_retries=2)

        error_response = Mock()
        error_response.status_code = 404
        http_error = requests.HTTPError(response=error_response)
        http_error.response = error_response
        error_response.raise_for_status.side_effect = http_error

        with patch("requests.Session") as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            mock_session.request.return_value = error_response

            with client as c:
                with pytest.raises(requests.HTTPError):
                    c.get("https://api.example.com/data")

            # Should only try once (no retries for 4xx)
            assert mock_session.request.call_count == 1

    @patch("time.sleep")
    def test_exponential_backoff_timing(self, mock_sleep: Mock) -> None:
        """Test that exponential backoff increases correctly."""
        client = RequestsHTTPClient(max_retries=3, initial_backoff=1.0, max_backoff=32.0)

        with patch("requests.Session") as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            mock_session.request.side_effect = requests.ConnectionError("Connection failed")

            with client as c:
                with pytest.raises(requests.ConnectionError):
                    c.get("https://api.example.com/data")

            # Verify exponential backoff: 1.0, 2.0, 4.0
            assert mock_sleep.call_count == 3
            calls = [call[0][0] for call in mock_sleep.call_args_list]
            assert calls == [1.0, 2.0, 4.0]


class TestRequestsHTTPClientIntegration:
    """Integration tests for complete workflows."""

    def test_multiple_requests_same_session(self) -> None:
        """Test multiple requests using the same session."""
        client = RequestsHTTPClient()

        mock_response1 = Mock()
        mock_response1.status_code = 200
        mock_response1.headers = {}
        mock_response1.json.return_value = {"request": 1}

        mock_response2 = Mock()
        mock_response2.status_code = 201
        mock_response2.headers = {}
        mock_response2.json.return_value = {"request": 2}

        with patch("requests.Session") as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            mock_session.request.side_effect = [mock_response1, mock_response2]

            with client as c:
                response1 = c.get("https://api.example.com/data")
                response2 = c.post("https://api.example.com/submit", data={"key": "value"})

            assert response1["body"] == {"request": 1}
            assert response2["body"] == {"request": 2}
            assert mock_session.request.call_count == 2

    def test_custom_timeout_configuration(self) -> None:
        """Test that custom timeout is applied to requests."""
        client = RequestsHTTPClient(timeout=60.0)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {}

        with patch("requests.Session") as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            mock_session.request.return_value = mock_response

            with client as c:
                c.get("https://api.example.com/data")

            call_args = mock_session.request.call_args
            assert call_args[1]["timeout"] == 60.0
