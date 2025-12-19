# Concurrency Analysis

## Problem Statement

The current ninja-cli-mcp implementation has concurrency issues that can lead to conflicts when multiple users or tasks execute simultaneously. This analysis identifies the core problems and proposes solutions.

## Current Design

### Architecture Overview
- Single-process MCP server handling all requests
- Shared `ToolExecutor` instance across all requests
- Tasks execute directly in the repository working directory
- No client/session isolation in the rate limiting system

### Key Components
1. **MCP Server** (`src/ninja_cli_mcp/server.py`)
   - Handles all incoming requests via stdio
   - Uses a singleton `ToolExecutor` instance
   - No per-client tracking or isolation

2. **Tool Executor** (`src/ninja_cli_mcp/tools.py`)
   - Single `ToolExecutor` instance shared across all requests
   - Tasks execute in the same repository directory
   - No request queuing or scheduling mechanism

3. **Security System** (`src/ninja_cli_mcp/security.py`)
   - Rate limiting uses hardcoded "default" client_id
   - No per-user or per-session resource limits
   - Basic resource monitoring but no per-client tracking

## Issues Found

### 1. Shared Rate Limits
All clients share the same rate limit bucket ("default" client_id), meaning one user can exhaust the rate limit for all other users.

### 2. No Request Isolation
Tasks execute in the same working directory without isolation, which can lead to:
- File conflicts when multiple tasks modify the same files
- Race conditions in file operations
- Unpredictable behavior when tasks overlap

### 3. No Client/Session Tracking
The MCP protocol supports session information, but the current implementation doesn't extract or use it for isolation.

### 4. Resource Contention
All tasks compete for the same system resources without any per-client limits or scheduling.

### 5. Working Directory Conflicts
Multiple concurrent tasks operating on the same repository can interfere with each other's file operations.

## Why Tasks "Didn't Make Changes"

The "doorman" task issue likely occurred due to:
1. **Working Directory Confusion**: The task may have executed in a different context than expected
2. **Concurrent Execution Conflicts**: Another task may have modified the same files simultaneously
3. **Path Resolution Issues**: The working directory might have been set incorrectly for that specific execution

## Solutions

### 1. Client/Session Identification
Extract client/session information from the MCP protocol to enable per-client tracking:

