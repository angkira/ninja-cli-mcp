"""
Data models module with Person dataclass.

This module provides a Person dataclass with name and age fields,
and a method to convert the dataclass to a dictionary representation.
"""

from dataclasses import dataclass


@dataclass
class Person:
    """
    Represents a person with a name and age.

    Attributes:
        name: The person's name as a string.
        age: The person's age as an integer.

    Examples:
        >>> person = Person(name="Alice", age=30)
        >>> person.name
        'Alice'
        >>> person.age
        30
        >>> person.to_dict()
        {'name': 'Alice', 'age': 30}
    """

    name: str
    age: int

    def to_dict(self) -> dict[str, str | int]:
        """
        Convert the Person instance to a dictionary.

        Returns:
            A dictionary with 'name' and 'age' keys containing
            the person's data.

        Examples:
            >>> person = Person(name="Bob", age=25)
            >>> person.to_dict()
            {'name': 'Bob', 'age': 25}
            >>> isinstance(person.to_dict(), dict)
            True
        """
        return {"name": self.name, "age": self.age}


# ============================================================================
# UNIT TESTS
# ============================================================================


def test_person_creation() -> None:
    """Test that a Person can be created with name and age."""
    person = Person(name="Alice", age=30)
    assert person.name == "Alice"
    assert person.age == 30


def test_person_to_dict() -> None:
    """Test that to_dict() returns the correct dictionary representation."""
    person = Person(name="Bob", age=25)
    result = person.to_dict()

    assert isinstance(result, dict)
    assert result == {"name": "Bob", "age": 25}
    assert "name" in result
    assert "age" in result


def test_person_to_dict_with_empty_name() -> None:
    """Test to_dict() with an empty string name."""
    person = Person(name="", age=0)
    result = person.to_dict()

    assert result == {"name": "", "age": 0}


def test_person_to_dict_with_long_name() -> None:
    """Test to_dict() with a long name string."""
    long_name = "Alexander Christopher Montgomery III"
    person = Person(name=long_name, age=45)
    result = person.to_dict()

    assert result["name"] == long_name
    assert result["age"] == 45


def test_person_to_dict_with_negative_age() -> None:
    """Test to_dict() with a negative age (edge case)."""
    person = Person(name="Charlie", age=-5)
    result = person.to_dict()

    assert result["age"] == -5


def test_person_to_dict_with_large_age() -> None:
    """Test to_dict() with a very large age value."""
    person = Person(name="Diana", age=999999)
    result = person.to_dict()

    assert result["age"] == 999999


def test_person_to_dict_independence() -> None:
    """Test that to_dict() returns a new dict, not a reference."""
    person = Person(name="Eve", age=28)
    dict1 = person.to_dict()
    dict2 = person.to_dict()

    # Modify one dictionary
    dict1["name"] = "Modified"

    # Ensure the other dictionary is unchanged
    assert dict2["name"] == "Eve"
    assert dict1["name"] == "Modified"


def test_person_dataclass_equality() -> None:
    """Test that two Person instances with same data are equal."""
    person1 = Person(name="Frank", age=35)
    person2 = Person(name="Frank", age=35)

    assert person1 == person2


def test_person_dataclass_inequality() -> None:
    """Test that two Person instances with different data are not equal."""
    person1 = Person(name="Grace", age=40)
    person2 = Person(name="Grace", age=41)

    assert person1 != person2


def test_person_repr() -> None:
    """Test the string representation of Person."""
    person = Person(name="Henry", age=50)
    repr_str = repr(person)

    assert "Person" in repr_str
    assert "Henry" in repr_str
    assert "50" in repr_str


def test_multiple_persons_to_dict() -> None:
    """Test creating multiple Person instances and converting to dict."""
    people = [
        Person(name="Alice", age=25),
        Person(name="Bob", age=30),
        Person(name="Charlie", age=35),
    ]

    dicts = [person.to_dict() for person in people]

    assert len(dicts) == 3
    assert dicts[0] == {"name": "Alice", "age": 25}
    assert dicts[1] == {"name": "Bob", "age": 30}
    assert dicts[2] == {"name": "Charlie", "age": 35}


def test_person_to_dict_keys() -> None:
    """Test that to_dict() returns exactly the expected keys."""
    person = Person(name="Ivy", age=22)
    result = person.to_dict()

    assert set(result.keys()) == {"name", "age"}
    assert len(result) == 2


def test_person_to_dict_values_types() -> None:
    """Test that to_dict() returns correct value types."""
    person = Person(name="Jack", age=55)
    result = person.to_dict()

    assert isinstance(result["name"], str)
    assert isinstance(result["age"], int)
