#!/bin/bash
echo "Cleaning up simulation processes..."
tmux kill-session -t sp_sim 2>/dev/null
pkill -9 -f "gz sim" 2>/dev/null
pkill -f nav2 2>/dev/null
pkill -f robot_state_pub 2>/dev/null
pkill -f shoppinkki_core 2>/dev/null
sleep 3
echo "Done."
