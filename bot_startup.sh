#!/bin/bash
# get stuck in a loop until there is a network connection
n=-1
while ! wget -q --spider https://www.google.co.uk; do
	if [ $n -eq -1 ]; then
		echo -n "waiting for network connection"
	else
		echo -n "."
	fi
	n=$((n+1))
	sleep 2;
done

# add a new line
if [ $n -gt -1 ]; then
	echo ""
fi

# start the tmux session and run two commands
tmux new-session -s bot -d 
tmux send-keys -t bot "bash" Enter
tmux send-keys -t bot "source /home/pi/.bashrc" Enter
tmux send-keys -t bot "source /home/pi/slashbot/venv/bin/activate" Enter
tmux send-keys -t bot "cd /home/pi/slashbot" Enter
tmux send-keys -t bot "python3 bot.py" Enter

