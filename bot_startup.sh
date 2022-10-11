#!/bin/bash
# sleep for 30 seconds to avoid stuff not being ready
# sleep 30s
# start the tmux session and run two commands
tmux new-session -s bot -d 
tmux send-keys -t bot "bash" Enter
tmux send-keys -t bot "source /home/pi/.bashrc" Enter
tmux send-keys -t bot "source /home/pi/slashbot/venv/bin/activate" Enter
tmux send-keys -t bot "cd /home/pi/slashbot" Enter
tmux send-keys -t bot "python3 bot.py" Enter
