# RUN_SUMMARY — 2026-07-18 pending-18r3

## Pass
- bad_password → re-register hybrid → immediate SSO → G2A/Sub2API/CPA (success 1)
- auth_error detection + re-register branch triggered
- G2A grok-4.5 chat OK
- services 8010/8080/8317/8318 stayed up

## Notes
- Historical pending accounts often invalid (password wrong / An error occurred); correct behavior is re-register, not silent drop.
- Primary hybrid path with live next-action produced sso wrapper then session sso in one run.
