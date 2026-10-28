# Privacy and public distribution

Examples are fictional and use unrelated retail and travel scenarios. The skill and MCP use neutral identifiers (`career-discovery` and `career_discovery`). No career profile is assumed for new users.

Do not commit `.env`, `profile.json`, databases, generated reports, local installation metadata, personal paths or access credentials. They are excluded by `.gitignore`. Each user supplies their own optional API credentials. Keyless Saramin discovery generates public links without calling an authenticated API or claiming to have collected postings.

The repository owner and commit attribution remain visible on GitHub. This project cannot anonymize the hosting account, erase copies already downloaded by others, or guarantee removal from third-party caches. Rewriting a branch removes old examples from its reachable history but does not guarantee that every old GitHub object or cached URL is immediately deleted.

Maintainers can run `scripts/audit-public-source.py` against tracked files or a reachable ref, with a private dotenv deny-values file and locally chosen identity/background patterns. The scanner reports issue categories and paths without printing matching credential values. This is a focused check, not a guarantee against all forms of inference or all possible secrets.
