# Taste
- When presented with a code-review finding list, wants ALL findings addressed — including nit-severity items, not just critical ones. Confidence: 0.65
- Gives terse, high-trust sign-offs (a bare "go") and expects the agent to proceed autonomously, picking the recommended option and making open design calls itself rather than asking again. Confidence: 0.5
- Prefers running the agent with permissions skipped (`--yolo` / `--dangerously-skip-permissions`) rather than approving prompts interactively. Confidence: 0.5
- Prefers user-supplied data be captured once and stored, then automatically reused for future orders/updates rather than re-prompted for repeatedly. Confidence: 0.5
- Expects changes to be deployed to the live service (restart/reload the running bot) AND pushed to the remote repo — not left as local commits. Confidence: 0.5
- Keeps runtime configuration and secrets in a live `.env` file (with `.env.example` documenting the keys); deployment/config changes are expected to flow through `.env`. Confidence: 0.4
- Prefers self-maintaining/automatic metadata over hand-maintained artifacts when given a choice (e.g. chose an auto-derived deployed revision over a manually curated changelog). Confidence: 0.4
- Wants operational events (e.g. a new deployment/revision going live) pushed to the admin proactively as a Telegram message, rather than only being available on demand behind a command like `/health`. Confidence: 0.45
