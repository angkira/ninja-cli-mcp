"""Comprehensive tests for http_client module.

Tests cover abstract base class behavior, context manager protocol,
method signatures, and concrete implementations.
"""

import pytest
from http_client import HTTPClient


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
