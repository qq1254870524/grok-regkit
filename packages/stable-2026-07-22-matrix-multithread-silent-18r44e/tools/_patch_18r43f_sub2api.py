from pathlib import Path
p = Path("sub2api_client.py")
t = p.read_text(encoding="utf-8")
old = """            _log(
                self.log_callback,
                f\"[!] Sub2API 可用性验证未通过 account_id={account_id_text} \"
                f\"attempt={attempt}/{max_attempts} detail={last_error}{hint}\",
            )
            if attempt < max_attempts and retry_delay > 0:
                time.sleep(retry_delay)

        return {
            \"ok\": False,
            \"account_id\": account_id,
            \"attempts\": max_attempts,
            \"error\": last_error,
        }"""
new = """            _log(
                self.log_callback,
                f\"[!] Sub2API 可用性验证未通过 account_id={account_id_text} \"
                f\"attempt={attempt}/{max_attempts} detail={last_error}{hint}\",
            )
            # 18r43f: permanent Grok chat/permission denials never become ok by retry;
            # fail-fast so multi post-success workers are not blocked 105s*N each.
            _err_l = str(last_error or \"\").lower()
            if any(
                x in _err_l
                for x in (
                    \"permission-denied\",
                    \"access to the chat endpoint is denied\",
                    \"chat endpoint is denied\",
                    \"not allowed to use\",
                    \"account disabled\",
                    \"account suspended\",
                    \"invalid_sso\",
                    \"sso invalid\",
                )
            ):
                return {
                    \"ok\": False,
                    \"account_id\": account_id,
                    \"attempts\": attempt,
                    \"error\": last_error,
                    \"permanent\": True,
                }
            if attempt < max_attempts and retry_delay > 0:
                time.sleep(retry_delay)

        return {
            \"ok\": False,
            \"account_id\": account_id,
            \"attempts\": max_attempts,
            \"error\": last_error,
        }"""
if old not in t:
    raise SystemExit("anchor not found")
if not t.lstrip().startswith("# 18r43f:"):
    t = "# 18r43f: Sub2API verify fail-fast on permanent permission-denied (drain awaiting_pool)\n" + t
t = t.replace(old, new, 1)
p.write_text(t, encoding="utf-8")
print("patched", p.stat().st_size)
