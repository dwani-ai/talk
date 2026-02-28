# Changelog

All notable changes to this project are documented here.

## Unreleased

- Production hardening:
  - Optional API-key auth for `talk-server` and `agents`.
  - Redis-backed session persistence support for `talk-server`.
  - Structured JSON logging support and `/metrics` endpoints.
  - Optional OpenTelemetry tracing hooks.
  - Compose healthchecks, resource limits, and image tag pinning support.
  - Frontend refactor with shared API/session modules and error boundary.
  - Added runbook and release documentation.
