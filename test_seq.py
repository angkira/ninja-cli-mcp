[
    'int, float, None] = None) -> None:\n        "',
    '\n        Initialize a Math instance.\n\n        Args:\n            value: An optional initial value. Can be an integer, float, or None.\n                   Defaults to None.\n\n        Examples:\n            >>> m = Math()\n            >>> m.value\n            >>> m = Math(10)\n            >>> m.value\n            10\n            >>> m = Math(3.14)\n            >>> m.value\n            3.14\n        "',
    '\n        self.value = value\n\n    def add(self, a: Union[int, float], b: Union[int, float]) -> Union[int, float]:\n        "',
    '\n        Add two numbers together.\n\n        Args:\n            a: The first number to add (int or float).\n            b: The second number to add (int or float).\n\n        Returns:\n            The sum of a and b. Returns an int if both inputs are ints,\n            otherwise returns a float.\n\n        Examples:\n            >>> m = Math()\n            >>> m.add(2, 3)\n            5\n            >>> m.add(2.5, 3.7)\n            6.2\n            >>> m.add(-1, 5)\n            4\n            >>> m.add(0, 0)\n            0\n        "',
    "\n        return a + b\n\n\nm = Math()\nassert m.add(2, 3) == 5",
]
