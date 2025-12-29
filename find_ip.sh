#!/bin/bash

echo "=========================================="
echo "   🔍 ATTENDANCE TRACKER - IP FINDER"
echo "=========================================="
echo
echo "Your server IP addresses:"
echo

# Get all IP addresses
echo "Available IP addresses:"
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | while read ip; do
        if [[ $ip =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            echo "  🌐 $ip"
            echo "     Access URL: http://$ip:8000"
            echo
        fi
    done
else
    # Linux
    hostname -I | tr ' ' '\n' | while read ip; do
        if [[ $ip =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            echo "  🌐 $ip"
            echo "     Access URL: http://$ip:8000"
            echo
        fi
    done
fi

echo "=========================================="
echo "Share the IP address above with your team!"
echo "They can access: http://[IP_ADDRESS]:8000"
echo "=========================================="
