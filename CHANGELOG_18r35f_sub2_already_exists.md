# CHANGELOG 18r35f — Sub2API "SSO already exists" idempotent success

Date: 2026-07-20

## Problem
Post-process / pending Sub2API import logged failures like:
`failed.error=SSO already exists; not overwritten`
and retried 3x, counted as pending fill fail — even though account is already in pool.

## Fix
In `sub2api_client.py` SSO→OAuth path: if failed[] detail contains
already exists / not overwritten / duplicate → return ok=True (idempotent success).

## Note
Reload watcher previously killed pending_sso_recovery that resume started in the
same second as cell end; next pending run after stable 8092 reload.
