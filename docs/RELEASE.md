# Release and Versioning

## Versioning

- Use semantic versions for all images:
  - `dwani/talk-server:<major.minor.patch>`
  - `dwani/talk-ux:<major.minor.patch>`
  - `dwani/talk-agents:<major.minor.patch>`
- Keep `latest` for development only.

## Release Process

1. Merge to `main` only after CI is green.
2. Tag release commit: `vX.Y.Z`.
3. Build and push tagged images.
4. Deploy by setting:
   - `DWANI_TALK_SERVER_TAG=X.Y.Z`
   - `DWANI_TALK_UI_TAG=X.Y.Z`
   - `DWANI_TALK_AGENTS_TAG=X.Y.Z`
5. Run smoke tests:
   - `GET /health`
   - `GET /ready`
   - `POST /v1/chat`
6. Monitor error-rate and latency for 30 minutes.

## Rollback Policy

- Rollback by reverting to prior image tags and redeploying compose stack.
- Keep at least the last 3 stable image versions available.
