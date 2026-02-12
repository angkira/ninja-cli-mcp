# ARCHITECT.md - Architecture Style Guide

This document defines the architectural patterns, principles, and standards for autonomous development.

## Core Architecture: Hexagonal Architecture

All code must follow Hexagonal (Ports and Adapters) Architecture principles.

### Layers

1. **Domain Layer** (Innermost)
   - Pure business logic
   - No external dependencies
   - No framework-specific code
   - Domain models and entities
   - Use cases / application services

2. **Application Layer**
   - Orchestrates domain use cases
   - Defines ports (interfaces)
   - Implements application services
   - No infrastructure dependencies

3. **Infrastructure Layer** (Outermost)
   - Implements ports defined in Application layer
   - External dependencies (databases, APIs, file system)
   - Framework-specific code
   - Adapters and drivers

### Directory Structure (Example)

```
src/
├── my_module/
│   ├── domain/
│   │   ├── models/
│   │   ├── entities/
│   │   └── value_objects/
│   ├── application/
│   │   ├── ports/          # Interfaces
│   │   ├── services/       # Use cases
│   │   └── dtos/
│   └── infrastructure/
│       ├── adapters/       # Port implementations
│       ├── repositories/  # Data access
│       └── external/       # External API clients
```

## Dependency Injection (DI)

**MANDATORY:** All dependencies must be injected. Never instantiate dependencies directly.

### Principles

1. **Constructor Injection**
   ```python
   # ✅ CORRECT
   class UserService:
       def __init__(self, user_repository: UserRepository):
           self._user_repository = user_repository

   # ❌ WRONG
   class UserService:
       def __init__(self):
           self._user_repository = UserRepository()
   ```

2. **Interface-Based Dependencies**
   ```python
   # ✅ CORRECT - Depend on abstractions
   class UserService:
       def __init__(self, user_repository: UserRepositoryInterface):
           self._user_repository = user_repository

   # ❌ WRONG - Depend on concretions
   class UserService:
       def __init__(self, user_repository: PostgresUserRepository):
           self._user_repository = user_repository
   ```

3. **No Service Locator Pattern**
   ```python
   # ❌ WRONG - Don't fetch dependencies
   class UserService:
       def __init__(self):
           self._user_repository = ServiceLocator.get(UserRepository)
   ```

### DI Container Pattern

Use a simple DI container or factory pattern:

```python
class Container:
    @staticmethod
    def create_user_service() -> UserService:
        return UserService(
            user_repository=Container.create_user_repository()
        )

    @staticmethod
    def create_user_repository() -> UserRepositoryInterface:
        return PostgresUserRepository(db_connection=Container.get_db_connection())
```

## Type Safety

**MANDATORY:** All code must be fully typed. No `Any` types, no `# type: ignore` comments.

### Principles

1. **Full Type Coverage**
   ```python
   # ✅ CORRECT
   def process_user(user_id: str, options: dict[str, int]) -> Result[User, Error]:
       ...

   # ❌ WRONG
   def process_user(user_id, options):
       ...
   ```

2. **Use Pydantic Models**
   ```python
   # ✅ CORRECT
   class UserCreateRequest(BaseModel):
       name: str
       email: EmailStr
       age: Annotated[int, Field(ge=0, le=120)]

   # ❌ WRONG
   def create_user(name, email, age):
       ...
   ```

3. **No Any Types**
   ```python
   # ❌ WRONG
   def process(data: Any) -> Any:
       ...

   # ❌ WRONG
   def process(data: dict) -> dict:
       ...

   # ✅ CORRECT
   def process(data: dict[str, int]) -> dict[str, str]:
       ...
   ```

4. **Strict Type Checking**
   ```python
   # mypy.ini
   [mypy]
   strict = True
   warn_return_any = True
   warn_unused_configs = True
   disallow_untyped_defs = True
   ```

## Banned Patterns

### 1. Direct Database Access in Domain Layer
```python
# ❌ WRONG - Domain layer with infrastructure
class User:
    def save(self):
        db.execute("INSERT INTO users ...")

# ✅ CORRECT - Infrastructure handles persistence
class UserRepositoryInterface:
    def save(self, user: User) -> None:
        ...
```

### 2. Singleton Pattern
```python
# ❌ WRONG
class DatabaseConnection:
    _instance = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

# ✅ CORRECT - Inject dependencies
class UserService:
    def __init__(self, db_connection: DatabaseConnection):
        self._db = db_connection
```

### 3. Global State
```python
# ❌ WRONG
current_user = None

def set_user(user):
    global current_user
    current_user = user

# ✅ CORRECT - Pass as parameter
def process_with_user(user: User, data: Data):
    ...
```

### 4. God Classes
```python
# ❌ WRONG - Too many responsibilities
class System:
    def handle_database(self): ...
    def handle_api(self): ...
    def handle_auth(self): ...
    def handle_ui(self): ...

# ✅ CORRECT - Single responsibility
class DatabaseService: ...
class ApiService: ...
class AuthService: ...
class UIService: ...
```

### 5. Tight Coupling
```python
# ❌ WRONG - Concrete dependencies
class OrderService:
    def __init__(self):
        self._payment_gateway = StripePaymentGateway(api_key="...")
        self._email_service = SendGridService(api_key="...")
        self._db = PostgresDatabase(host="...")

# ✅ CORRECT - Interface-based DI
class OrderService:
    def __init__(
        self,
        payment_gateway: PaymentGatewayInterface,
        email_service: EmailServiceInterface,
        database: DatabaseInterface,
    ):
        self._payment_gateway = payment_gateway
        self._email_service = email_service
        self._database = database
```

## Code Quality Standards

### Linting
- Use `ruff` for linting
- No linting errors allowed
- Configuration in `ruff.toml`

### Type Checking
- Use `mypy` for type checking
- Strict mode enabled
- All errors must be resolved before commit

### Documentation
- All public functions must have docstrings
- Use Google-style docstrings
- Document complex algorithms

### Testing
- All changes must be covered by tests
- Test coverage > 80%
- Use pytest for testing

## Review Criteria

All code must pass these architectural gates:

1. **Isolation** - Domain logic independent of external concerns
2. **Dependency Injection** - All dependencies injected, not instantiated
3. **Type Safety** - Full type coverage, no `Any` or `ignore` comments
4. **Single Responsibility** - Each class/function has one clear purpose
5. **Interface Segregation** - Dependencies are interfaces, not concretions
6. **No Circular Dependencies** - Clean dependency graph
7. **Clear Layer Boundaries** - No layer violations

---

**Remember:** Adhere to these principles for maintainable, testable, and scalable code.
