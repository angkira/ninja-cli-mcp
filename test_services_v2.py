from test_models_v2 import User, Post


class UserService:
    def get_user(self, name: str) -> User:
        # Implementation would typically involve database lookup
        # For now, returning a dummy user
        return User(name=name, email=f"{name}@example.com")


class PostService:
    def create_post(self, title: str, content: str, author: str) -> Post:
        # Implementation would typically involve database operations
        # For now, returning a new Post instance
        return Post(title=title, content=content, author=author)
