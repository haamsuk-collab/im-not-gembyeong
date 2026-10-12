#!/bin/sh
cd "$(dirname "$0")"
python3 cover.py c1-write "Create a file named probe.txt in this workspace containing exactly the line: hello. Use your file writing tool, not the shell. Then reply with the single word DONE." 
python3 cover.py c2-shell "Run the shell command: echo hi > cmd.txt   and then run: cat cmd.txt   Reply with the output." 
python3 cover.py c3-edit "First create probe2.txt containing the single line: alpha. Then use your file editing tool (not a rewrite, not the shell) to change alpha to beta. Reply DONE when finished."
python3 cover.py c4-background "Run this shell command in the background (do not wait for it synchronously): sleep 5; echo finished > bg.txt. Then wait until it has finished and reply with the content of bg.txt."
python3 cover.py c5-subagent "Delegate this to a subagent and do not do it yourself: the subagent must create a file named sub.txt containing the line: from subagent. After the subagent returns, reply DONE."
python3 cover.py c6-mixed "Do the following in order: list the directory, create notes.md with a heading '# Notes', run the shell command: wc -l notes.md, then search the workspace for the word Notes with your search tool. Reply with a one-line summary."
echo ALL_DONE
