# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅ Yes    |

## Reporting a Vulnerability

We take security seriously. To report a security vulnerability:

1. **Do not open a public GitHub issue.**
2. Email us at [security@angkira.com](mailto:security@angkira.com) with:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Any relevant logs or screenshots
3. We will acknowledge receipt within 48 hours.
4. We aim to provide an initial resolution timeline within 5 business days.
5. We will keep you updated on progress and credit you in the changelog (optional).

### Responsible Disclosure

Please follow responsible disclosure practices. Do not exploit vulnerabilities or access data beyond what is necessary to demonstrate the issue.

## Security Best Practices

- Keep dependencies up-to-date (`uv sync --upgrade`)
- Store API keys securely (e.g., use environment variables)
- Use scoped API keys when possible
- For parallel plan execution, consider using git worktrees for stronger isolation

## Encryption and Secrets

- Never commit API keys or secrets to the repository
- Use `.env` or environment variables locally
- For CI, use GitHub Actions secrets

## Questions?

Contact us at [security@angkira.com](mailto:security@angkira.com).
