#!/bin/bash

echo "======================================"
echo "   🚀 ATTENDANCE TRACKER SERVER"
echo "======================================"
echo
echo "Starting server accessible from all office devices..."
echo
echo "Server URLs:"
echo "  Local:    http://localhost:8000"
echo "  Network:  http://$(hostname -I | awk '{print $1}'):8000"
echo
echo "Press Ctrl+C to stop the server"
echo "======================================"
echo

# Get the directory where the script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Change to the project directory
cd "$DIR"

# Start the Django server
python3 manage.py runserver 0.0.0.0:8000
