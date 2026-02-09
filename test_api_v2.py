from test_services_v2 import UserService, PostService


def get_user_api(name: str):
    """Get user by name using UserService."""
    user_service = UserService()
    return user_service.get_user(name)


def create_post_api(title: str, content: str, author: str):
    """Create a new post using PostService."""
    post_service = PostService()
    return post_service.create_post(title, content, author)
