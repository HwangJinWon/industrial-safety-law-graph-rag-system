# Workfit Staging Deployment

This is the simplest handoff environment for watch communication development. It uses synthetic data, one always-on API service, HTTPS, and a persistent SQLite disk.

## Recommended prototype hosting

Use a team-owned Render account connected to the team GitHub repository. The included `render.yaml` requests a Starter web service and a 1 GB persistent disk. Check the current price in Render before confirming creation.

## Before deployment

1. Push this project to a private team GitHub repository.
2. Create or sign in to the team-owned Render account.
3. Prepare a random staging API key. Do not commit it to Git.

Generate a key in PowerShell:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Render dashboard steps

1. Select `New` -> `Blueprint`.
2. Connect the private GitHub repository.
3. Select the repository's `render.yaml`.
4. Enter the generated value when asked for `WORKFIT_API_KEY`.
5. Review the displayed monthly price before confirming.
6. Wait for `/healthz` to report healthy.

Render supplies a URL similar to:

```text
https://workfit-staging-api.onrender.com
```

## Verification

Public health check (no key required):

```text
https://workfit-staging-api.onrender.com/healthz
```

API documentation:

```text
https://workfit-staging-api.onrender.com/docs
```

All functional APIs require this header when `WORKFIT_API_KEY` is configured:

```text
X-API-Key: <staging key>
```

Send virtual data from PowerShell without saving the key in code:

```powershell
$env:WORKFIT_API_KEY = "paste-the-key-here"
python scripts/send_virtual_data.py --base-url "https://workfit-staging-api.onrender.com"
Remove-Item Env:WORKFIT_API_KEY
```

## Important limits

- Use synthetic data only.
- This is a shared-key prototype, not production authentication.
- SQLite is suitable for one staging server, not multiple replicas.
- Graph-RAG requires separate Neo4j environment variables and loaded law data.
- Stop/delete the service in the Render dashboard when the development period ends to stop future compute charges.
