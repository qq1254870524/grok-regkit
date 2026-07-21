# 18r35c CreateEmail rate-limit hardfix

## Symptom
browser×socks5×outlook workers=10 hit `验证码过多` on many distinct mailboxes.
18r35b detect worked (fail-fast) but MT raised from fill_email outside fill_code try,
so no mailbox switch; slots hard-failed.

## Causes
1. Simultaneous CreateEmail from 10 workers → proxy/IP rate limit as per-email UI.
2. MT path did not catch fill_email rate-limit → no retry.
3. Limited mailboxes not always burned before next acquire.

## Fix
1. `_wait_create_email_gate` (~2.8s) serializes CreateEmail clicks globally.
2. MT/serial wrap fill_email → handle_create_email_rate_limited → switch mailbox.
3. Code-stage also burns on rate-limit keywords.

## Reload
Restart registration job (or web server) so Python reloads grok_register_ttk.
