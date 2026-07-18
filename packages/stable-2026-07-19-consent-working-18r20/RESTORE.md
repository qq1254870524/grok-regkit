# Restore 18r20
1. Copy sources/*.py over formal root counterparts
2. Copy sources/browser/token_harvester.py -> browser/token_harvester.py
3. Copy sources/consent_working_next_action.txt -> formal root
4. Restart web server on 8092: python -B web\server.py
