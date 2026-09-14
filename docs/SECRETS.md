# Secrets & API keys

How ninja-mcp stores provider credentials and how to manage them.

## TL;DR

- Secrets (API keys) live in an **AES-256-GCM encrypted store**
  (`~/.ninja/credentials.db`), with the **OS keychain/keyring** as the primary
  backend when available.
- Ninja **never writes secrets to `~/.ninja-mcp.env`** and **never exports them
  into the process environment**.
- The store **password** is held in process memory only. For headless runs it is
  supplied via a systemd credential (Linux), a password file (launchd on macOS),
  or the OS keychain — never via an environment variable.
- Manage everything from the config TUI: `ninja-config configure` → **API Keys**.

## Where secrets are stored

| Location | Notes |
|---|---|
| `~/.ninja/credentials.db` | **Primary.** AES-256-GCM encrypted SQLite (PBKDF2-HMAC-SHA256, 100k iters). |
| OS keychain/keyring | Fallback. macOS **Keychain** / Linux Secret Service (libsecret). |
| `~/.ninja-mcp.env` | **Never contains secrets.** Non-secret settings only. |
| Process environment | **Never set by ninja.** See "External CLIs" below. |

Reads and writes go to the encrypted store first, so an out-of-date key in the
keychain can never shadow a newer value in the database.

Secrets are the `*_API_KEY` names (`OPENROUTER_API_KEY`, `OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, `PERPLEXITY_API_KEY`, `ZAI_API_KEY`, `GROQ_API_KEY`,
`DEEPSEEK_API_KEY`, `MISTRAL_API_KEY`, `GOOGLE_API_KEY`, `SERPER_API_KEY`).

Legacy plaintext keys found in `~/.ninja-mcp.env` are migrated into the store on
first run and the plaintext lines are scrubbed (a
`~/.ninja-mcp.env.pre-migration.bak` backup is kept).

## The store password

The encrypted store is unlocked with a password. Resolution order (never env by
default, never written anywhere by ninja):

0. **Passwordless store** — if the database opens with an empty password, it is
   used as-is (machine-bound; no prompt). Set a password to change this.
2. **Inherited fd** — `ninja-mcp daemon start` prompts once and hands each
   forked daemon a pipe fd; only the fd number (not the secret) is in the child
   environment.
3. **systemd credential** — `$CREDENTIALS_DIRECTORY/ninja-store-password`
   (Linux, via `LoadCredential`).
4. **Password file** — `NINJA_STORE_PASSWORD_FILE=/path` (any OS; e.g. launchd).
5. **OS keychain/keyring** — where the TUI's *Set / Change* stores it for
   headless/desktop launches.
6. **`NINJA_CREDENTIAL_PASSWORD`** — read-only fallback for CI only.
7. **Interactive prompt** — when a TTY is available.

## Managing keys (TUI)

`ninja-config configure` → **API Keys**:

- Focus a provider row to reveal its inline editor, type the value, **Save**.
- `↑`/`↓` move between providers.
- **Encrypted store** section at the bottom shows the password source and lets
  you **Set / Change** (re-encrypts existing credentials, persists the password
  to the OS keychain) or **Reset** (deletes `credentials.db`; type `DELETE` to
  confirm).

## Headless: daemons and CI

- **Linux (systemd user service).** Provision an encrypted credential once:
  ```bash
  ./scripts/provision_systemd_credential.sh
  systemctl --user restart ninja-cli-mcp
  ```
  This writes `~/.config/ninja-mcp/store-password.cred` (systemd-encrypted) and a
  drop-in with `LoadCredentialEncrypted=`. No plaintext, no env.
- **macOS (launchd).** Use the OS Keychain (TUI *Set / Change* persists the
  password there) or point `NINJA_STORE_PASSWORD_FILE` at a `0600` file in the
  launchd job.
- **CI.** Set `NINJA_CREDENTIAL_PASSWORD` (and the provider key) as CI secrets;
  ninja reads but never writes them.

If neither is available on a headless host, the encrypted store cannot be
unlocked and ninja falls back to any pre-existing environment variables — which
is why we recommend provisioning the credential instead.

## Key precedence: ninja keys vs operator auth

When ninja spawns a coding CLI it builds a **clean child environment**:

1. **Inherited API keys are stripped** — a stale `OPENROUTER_API_KEY` in your
   shell can neither leak into nor shadow the CLI.
2. **If ninja has a key** in the encrypted store, it is exported to the child
   (`OPENROUTER_API_KEY` + `OPENAI_API_KEY`), so operators that honour the
   environment use it.
3. **If ninja has no key**, nothing is exported and the operator's own auth is
   used — OpenCode `auth.json`, Codex/ChatGPT login, Claude auth. You are not
   prompted and not blocked.
4. **Host-auth operators** (Codex, Claude, Junie) never receive an injected key.

So: *our key if present, otherwise the operator's authorization.* One caveat —
OpenCode prefers its own stored credential over the env value, so keep ninja's
key and OpenCode's `auth.json` in sync (or just rely on OpenCode's auth).

## External CLIs have their own auth

`opencode`, `codex`, `claude`, `gemini` and `aider` keep their **own**
credentials (for example OpenCode: `~/.local/share/opencode/auth.json`; Codex:
ChatGPT login). Ninja's coder runs those CLIs, so a working provider key may live
in the **CLI's** store even when ninja's store has none. The store password only
protects ninja's encrypted database.

Ninja passes the resolved key to the **child CLI process** at launch (some CLIs
read it from the environment); this is ephemeral and never persisted by ninja.

## Resetting / troubleshooting

- **401 / "User not found"** from a provider: the stored key is invalid. Update
  it in the TUI (API Keys) or replace it via `ninja_common.secrets.set_secret`.
- **Password prompt on every start**: persist the password (TUI *Set / Change*,
  or the systemd credential) so it is found automatically.
- **Forgot the password**: **Reset** in the TUI deletes `credentials.db`; re-add
  keys afterwards.
- Verify a key without exposing it:
  ```bash
  curl -sS -o /dev/null -w "%{http_code}\n" \
    https://openrouter.ai/api/v1/key -H "Authorization: Bearer $OPENROUTER_API_KEY"
  ```

## See also

- [CONFIGURATION.md](CONFIGURATION.md) — full configuration reference
- [../SECURITY.md](../SECURITY.md) — security policy
- [RELEASING.md](RELEASING.md) — release process
