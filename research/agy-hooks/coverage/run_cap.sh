#!/bin/sh
cd "$(dirname "$0")"
python3 cap.py k1-inject-toolcall inject_toolcall "If you already know the G1 nonce, reply with only the nonce. Otherwise reply with only UNKNOWN. Do not call any tools."
python3 cap.py k2-inject-ephemeral inject_ephemeral "If you already know the G1 nonce, reply with only the nonce. Otherwise reply with only UNKNOWN. Do not call any tools."
python3 cap.py k3-ask ask "Create a file named out.txt in this workspace containing the single line: ok. Reply DONE only if the file now exists with that content, otherwise reply NOT DONE and one sentence why."
python3 cap.py k4-force-continue force_continue "Reply with the single word OK. Do not call any tools."
echo CAP_DONE
