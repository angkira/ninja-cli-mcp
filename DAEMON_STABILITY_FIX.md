# Daemon Stability Fix Summary

**Date:** 2025-12-28
**Issue:** MCP daemons failing with "Connection closed" errors and zombie processes
**Status:** ✅ **FIXED**

---

## Problems Identified

### 1. **Proxy Connection Lifecycle** ❌
- **Location:** `src/ninja_common/daemon.py:18-103` (stdio_to_http_proxy)
- **Issue:** Proxy closed entire daemon connection when stdin EOF occurred
- **Impact:** Claude Code sessions would break daemon connections unexpectedly
- **Log Evidence:**
  ```
  {"debug":"UNKNOWN connection closed after 2s (cleanly)"}
  {"error":"Server stderr: Error connecting to daemon:"}
  {"debug":"Tool 'coder_execute_plan_parallel' failed after 0s: MCP error -32000: Connection closed"}
  ```

### 2. **Zombie Processes** 🧟
- **Found:** 27 duplicate server processes from previous daemon starts
- **Impact:** Resource consumption and port conflicts
- **PIDs:** Multiple processes competing for ports 8100-8102

### 3. **No Singleton Enforcement** ⚠️
- **Issue:** No mechanism to prevent multiple daemons per module
- **Impact:** Port conflicts and unpredictable behavior

---

## Solutions Implemented

### ✅ **1. Resilient Proxy Bridge**
**File:** `src/ninja_common/daemon.py:18-161`

**Key Changes:**
- **stdin EOF handling:** Proxy no longer kills daemon when stdin closes
- **Graceful shutdown:** Tasks complete independently without killing each other
- **Error resilience:** BrokenPipeError, ConnectionError handled gracefully
- **Timeout management:** Infinite timeout for SSE connections
- **Better logging:** Debug messages for connection lifecycle

**Architecture:**
```
Multiple Claude Code Sessions
     ↓         ↓         ↓
  Proxy 1  Proxy 2  Proxy 3  ← Each is a bridge (stdin/stdout)
     ↓         ↓         ↓
  ╔═══════════════════════╗
  ║   Singleton Daemon    ║  ← ONE daemon per module
  ║   (Port 8100-8102)    ║
  ╚═══════════════════════╝
```

### ✅ **2. Singleton Daemon Enforcement**
**File:** `src/ninja_common/daemon.py:296-395`

**New Methods:**
- `_is_port_in_use()`: Check if port is listening
- `_find_process_using_port()`: Find PID using port (lsof/ss)
- `_cleanup_zombies()`: Kill zombie processes on port

**Enhanced start() method:**
1. Check PID file + verify process running
2. Check port is in use by correct process
3. Clean up zombies if port conflict
4. Verify daemon started successfully (1s health check)
5. Detach daemon process (`os.setsid()`)

### ✅ **3. Zombie Process Cleanup**
- Killed all 27 zombie processes
- New daemons properly detached from parent session
- PIDs tracked correctly with verification

---

## Test Results

### ✅ **Singleton Enforcement**
```bash
$ uv run ninja-daemon start coder
# (No output - daemon already running)

$ uv run ninja-daemon status
{
  "coder": {
    "running": true,
    "pid": 2000501,
    "port": 8100,
    "url": "http://127.0.0.1:8100/sse"
  }
}
```

### ✅ **Process Count**
```bash
$ ps aux | grep "ninja.*server" | grep -v grep | wc -l
3  # Exactly 3 daemons (was 27 zombies)
```

### ✅ **Port Listening**
```bash
$ lsof -i :8100-8102 | grep LISTEN
python3 2000501 ... TCP localhost:8100 (LISTEN)
python3 2000502 ... TCP localhost:8101 (LISTEN)
python3 2000504 ... TCP localhost:8102 (LISTEN)
```

### ✅ **Proxy Connection**
```bash
$ echo '{"jsonrpc":"2.0","id":1,"method":"initialize",...}' | \
  uv run ninja-daemon connect coder
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05",...}}
# ✅ Connection successful
```

---

## Architecture Overview

### **Before Fix:**
```
Claude Code → Proxy → ❌ Connection breaks → Daemon crashes
Zombie Process 1 (Port 8100) ┐
Zombie Process 2 (Port 8100) ├─ Port conflicts
Zombie Process 3 (Port 8100) ┘
```

### **After Fix:**
```
Claude Code 1 → Proxy 1 ─┐
Claude Code 2 → Proxy 2 ─┼→ Singleton Daemon (Port 8100) ✅
Claude Code 3 → Proxy 3 ─┘

✅ Stable connections
✅ One daemon per module
✅ Resilient to stdin EOF
✅ Proper cleanup
```

---

## Key Improvements

1. **Stability:** Proxies are now stable bridges, not connection owners
2. **Singleton:** Only ONE daemon per module (coder/researcher/secretary)
3. **Cleanup:** Automatic zombie process detection and cleanup
4. **Resilience:** Handles stdin EOF, broken pipes, and connection errors
5. **Verification:** Health checks ensure daemons actually start listening
6. **Logging:** Better debug output for troubleshooting

---

## Files Modified

- `src/ninja_common/daemon.py`:
  - `stdio_to_http_proxy()`: Lines 18-161 (complete rewrite)
  - `DaemonManager._is_port_in_use()`: Lines 226-236 (new)
  - `DaemonManager._find_process_using_port()`: Lines 238-272 (new)
  - `DaemonManager._cleanup_zombies()`: Lines 274-294 (new)
  - `DaemonManager.start()`: Lines 296-395 (enhanced with singleton logic)

---

## Usage

### Start Daemons
```bash
uv run ninja-daemon start          # Start all
uv run ninja-daemon start coder    # Start specific module
```

### Check Status
```bash
uv run ninja-daemon status         # All modules
uv run ninja-daemon status coder   # Specific module
```

### Restart (if needed)
```bash
uv run ninja-daemon restart        # Restart all
```

### Connect (for MCP clients)
```bash
# Claude Code uses this command in .claude.json
uv run ninja-daemon connect coder
```

---

## Expected Behavior

✅ **Multiple proxies can connect** to the same daemon
✅ **Daemon stays alive** when proxies disconnect
✅ **Automatic cleanup** of zombie processes
✅ **No duplicate daemons** - singleton enforcement
✅ **Graceful error handling** - no sudden connection drops

---

## Monitoring

### Check for zombies:
```bash
ps aux | grep "ninja.*server" | grep -v grep
# Should show exactly 3 processes
```

### Check ports:
```bash
lsof -i :8100-8102 | grep LISTEN
# Should show exactly 3 listening sockets
```

### Check logs:
```bash
tail -f ~/.cache/ninja-mcp/logs/coder.log
tail -f ~/.cache/ninja-mcp/logs/researcher.log
tail -f ~/.cache/ninja-mcp/logs/secretary.log
```

---

## Notes

- The daemons are now true singletons - only one per module
- Multiple Claude Code sessions can connect via multiple proxies
- Proxies are ephemeral, daemons are persistent
- Zombie cleanup happens automatically on start
- Health checks verify daemons actually started
