from dataclasses import dataclass


@dataclass
class User:
    name: str
    email: str


@dataclass
class Post:
    title: str
    content: str
    author: str
