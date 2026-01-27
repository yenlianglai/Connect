---
name: connect-coding-standards
description: Coding standards and refactoring habits for the Connect project. Apply when writing, reviewing, or refactoring code to ensure consistency, maintainability, and clean architecture.
---

# Connect Coding Standards & Refactoring Habits

This skill defines the coding principles and refactoring patterns used throughout the Connect project. Apply these standards when writing new code, reviewing existing code, or refactoring.

## Core Principles

### 1. Separation of Concerns
- **API Endpoints**: Each endpoint should have a single, well-defined responsibility
- **Services**: Business logic separated from API routes and data models
- **Models**: Pure data structures with validation, no business logic
- **Frontend Components**: Single responsibility - one component, one purpose
- **Example**: Topic creation should be a separate endpoint (`/topics/create`), not mixed into chat endpoint (`/chat`)

### 2. Clean Code
- **DRY (Don't Repeat Yourself)**: Extract common patterns into reusable functions
- **SOLID Principles**: Especially Single Responsibility and Dependency Inversion
- **No Magic Numbers/Strings**: Use constants or configuration
- **Explicit over Implicit**: Make intentions clear in code
- **Fail Fast**: Validate inputs early, return errors immediately
- **Expressive naming**: Use expressive function name rather than redundant docstring or comment

### 3. Expressive Naming
- **Functions**: Use verb phrases that describe what they do
  - ✅ `get_relevant_context()` instead of `get_context()`
  - ✅ `create_topic()` instead of `create()`
  - ✅ `merge_nodes()` instead of `merge()`
- **Variables**: Use nouns that describe what they represent
  - ✅ `selectedCategoryIds` instead of `cats`
  - ✅ `memory_context` instead of `ctx`
  - ✅ `isNewSession` instead of `new`
- **Classes**: Use nouns describing the entity
  - ✅ `MemoryRetriever` instead of `Retriever`
  - ✅ `GraphService` instead of `Service`
- **Boolean variables**: Use `is_`, `has_`, `should_`, `can_` prefixes
  - ✅ `isLoading`, `hasPermission`, `shouldCreateCategory`

### 4. Simplicity
- **Avoid Over-Engineering**: Solve the problem at hand, not hypothetical future problems
- **Prefer Simple Solutions**: If a simple approach works, use it
- **Remove Unused Code**: Delete dead code, don't comment it out
- **Minimize Dependencies**: Only add dependencies when necessary
- **Clear Flow**: Code should read like a story from top to bottom

### 5. Generalization vs Specificity
- **General Methods**: Create reusable, parameterized functions when patterns repeat
  - ✅ `update_node_properties(node_id, label, properties)` instead of separate methods for each node type
  - ✅ `get_nodes_by_label(label, filters)` instead of type-specific methods
- **Specific When Needed**: Don't over-generalize - keep it practical
- **Constants for Magic Values**: Extract repeated strings/numbers into class constants
  - ✅ `LABEL_KNOWLEDGE = "Knowledge"` instead of hardcoded strings

### 6. Error Handling
- **Graceful Degradation**: Non-critical operations (like caching) should fail silently with logging
- **Explicit Error Messages**: Provide context in error messages
- **Logging Levels**: Use appropriate levels (debug, info, warning, error)
- **Transaction Safety**: Ensure database operations are atomic where needed

### 7. Code Organization
- **Logical Grouping**: Group related methods together with section comments
  - Example: `# ========== Node Creation ==========`
- **Consistent Patterns**: Use the same patterns throughout the codebase
- **File Structure**: One class per file, related utilities grouped together
- **Import Organization**: Group imports (stdlib, third-party, local)

### 8. Type Safety
- **Type Hints**: Use type hints in Python for clarity
- **Pydantic Models**: Use for data validation and serialization
- **TypeScript**: Use strict types, avoid `any` when possible
- **Optional Types**: Use `| None` or `?` to indicate nullable values

### 9. Documentation
- **Docstrings**: Use for public functions/classes explaining what and why
- **Comments**: Explain "why" not "what" - code should be self-documenting
- **README**: Keep updated with architecture decisions
- **Inline Comments**: Only when code intent isn't obvious

### 10. Testing Considerations
- **Testable Code**: Write code that's easy to test (dependency injection, pure functions)
- **Edge Cases**: Consider edge cases during implementation
- **Integration Tests**: Test full flows, not just units

## Refactoring Patterns

### When Refactoring:
1. **Identify Duplication**: Look for repeated patterns
2. **Extract Common Logic**: Create general helper methods
3. **Simplify Conditionals**: Use early returns, guard clauses
4. **Remove Dead Code**: Delete unused functions/variables
5. **Rename for Clarity**: Improve names to match current understanding
6. **Consolidate Similar Operations**: Merge related functions

### Refactoring Checklist:
- [ ] Are concerns properly separated?
- [ ] Are function/variable names expressive?
- [ ] Is the code simple and readable?
- [ ] Are there any hardcoded values that should be constants?
- [ ] Is there duplication that can be extracted?
- [ ] Are error cases handled gracefully?
- [ ] Is the code organized logically?
- [ ] Are types properly annotated?

## Project-Specific Patterns

### Backend (Python/FastAPI)
- Use `async/await` consistently for I/O operations
- Use dependency injection (`Depends()`) for services
- Group endpoints logically in `main.py`
- Use Pydantic models for request/response validation
- Use `logger` from `logging` module, not `print()`

### Frontend (React/TypeScript)
- Use functional components with hooks
- Extract reusable logic into custom hooks
- Use TypeScript interfaces for props and data structures
- Use TanStack Query for data fetching and caching
- Use Tailwind CSS utility classes, avoid inline styles
- Keep components small and focused

### Database Operations
- Use transactions for multi-step operations
- Handle connection errors gracefully
- Use parameterized queries (prevent SQL injection)
- Batch operations when possible (Redis pipeline, Neo4j batch)

## Anti-Patterns to Avoid

- ❌ Mixing business logic in API endpoints
- ❌ Creating endpoints that do multiple unrelated things
- ❌ Using generic names like `data`, `item`, `result` without context
- ❌ Hardcoding values that might change
- ❌ Creating overly specific methods when a general one would work
- ❌ Ignoring errors silently without logging
- ❌ Premature optimization
- ❌ Over-abstracting simple operations

## Example: Good vs Bad

### Bad:
```python
async def chat(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())
    session = await session_manager.get_session(session_id)
    if not session:
        # Creates topic, creates category, creates sub-categories, etc.
        # 50+ lines of mixed concerns
    # Then handles chat logic
```

### Good:
```python
@app.post("/topics/create")
async def create_topic(request: CreateTopicRequest):
    # Only handles topic creation
    ...

@app.post("/chat")
async def chat(request: ChatRequest):
    # Only handles chat messaging
    ...
```

## When to Use This Skill

- When writing new code - ensure it follows these standards
- When reviewing code - check against these principles
- When refactoring - use these patterns to improve code quality
- When debugging - consider if code organization could be improved
- When adding features - ensure proper separation of concerns

## Instructions

1. **Before Writing Code**: Review relevant sections of this skill
2. **While Coding**: Apply naming conventions, separation of concerns, and simplicity principles
3. **After Coding**: Review against the refactoring checklist
4. **When Refactoring**: Identify patterns, extract common logic, improve names
5. **Ask Questions**: Use the ask questions tool if you need to clarify requirements with the user

## Remember

- **Code is read more than written** - prioritize readability
- **Simple solutions are often the best solutions**
- **Names are the most important form of documentation**
- **Separation of concerns makes code maintainable**
- **Refactor incrementally** - small improvements add up
