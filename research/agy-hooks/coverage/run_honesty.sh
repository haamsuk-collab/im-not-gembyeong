#!/bin/sh
cd "$(dirname "$0")"
# wait for the coverage runs to finish first
while ! grep -q ALL_DONE run_all.log 2>/dev/null; do sleep 10; done
for i in 1 2 3 4 5 6 7 8; do python3 honesty.py h$i; done
echo HONESTY_DONE
