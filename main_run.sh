#!/bin/bash
# Rocket Flight Controller - Main Run Script
# This script starts both the TCP proxy and simulator simultaneously

echo "Starting Rocket Flight Controller Services"
echo "=============================================="

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    echo "Activating virtual environment..."
    source .venv/Scripts/activate
    echo "Virtual environment activated"
else
    echo " No virtual environment found, using system Python"
fi

# Check if required files exist
if [ ! -f "tcp_proxy.py" ]; then
    echo " Error: tcp_proxy.py not found"
    exit 1
fi

if [ ! -f "tcp_simulator.py" ]; then
    echo "Error: tcp_simulator.py not found"
    exit 1
fi

if [ ! -f "simulator_config.yaml" ]; then
    echo "Error: simulator_config.yaml not found"
    exit 1
fi

echo " All required files found"
echo ""

# Function to cleanup background processes on script exit
cleanup() {
    echo ""
    echo "Shutting down services..."
    kill $PROXY_PID $SIMULATOR_PID 2>/dev/null
    wait $PROXY_PID $SIMULATOR_PID 2>/dev/null
    echo " Services stopped"
    exit 0
}

# Set up signal handlers for cleanup
trap cleanup SIGINT SIGTERM

# Start TCP proxy in background
echo "Starting TCP Proxy..."
python tcp_proxy.py &
PROXY_PID=$!
echo "✓ TCP Proxy started (PID: $PROXY_PID)"

# Wait a moment for proxy to initialize
sleep 2

# Start simulator in background
echo "Starting Rocket Simulator..."
python tcp_simulator.py &
SIMULATOR_PID=$!
echo "✓ Rocket Simulator started (PID: $SIMULATOR_PID)"

echo ""
echo "Both services are running!"
echo "   - TCP Proxy PID: $PROXY_PID"
echo "   - Simulator PID: $SIMULATOR_PID"
echo ""
echo "To start the visualizer, run in another terminal:"
echo "   python flight_visualizer.py"
echo ""
echo "Press Ctrl+C to stop all services"
echo "=============================================="

# Wait for both processes
wait $PROXY_PID $SIMULATOR_PID