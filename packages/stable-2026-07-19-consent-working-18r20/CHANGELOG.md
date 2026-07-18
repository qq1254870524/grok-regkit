# 18r20 consent working + incomplete envelope

## Fix
1. consent only finds soft-nav (0071fd...) then fails with 1 Next-Action
   - persist working Next-Action to consent_working_next_action.txt
   - prepend disk working id every round
   - under-discovered (<2 ids) extended JS scan
2. incomplete envelope on register
   - CreateEmail duplicate uses shared first Promise (not AbortError/fake JSON)
3. SignUp 200 sso_len=0
   - one remint+retry after protocol candidates fail

## Verified
- unit tests OK
- live probe: working 404454... returns code, referrer=grok-build, 3.9s
