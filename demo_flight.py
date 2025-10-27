#!/usr/bin/env python3
"""
Demo script showing how to use the flight controller with the visualizer
"""

import time
import threading
from flight_controller.flight_controller import MissionContext

def run_demo_mission():
    """Run a demo mission with the flight controller"""
    print("🚀 Starting Demo Flight Mission")
    print("=" * 50)
    
    try:
        # Initialize mission context
        print("Initializing mission context...")
        mission = MissionContext('simulator_config.yaml')
        print("✓ Mission context initialized")
        
        # Start the mission loop
        print("Starting mission loop...")
        print("Note: This will run until manually stopped")
        print("Press Ctrl+C to stop")
        print("=" * 50)
        
        mission_start_time = time.time()
        
        while True:
            try:
                # Process incoming frames
                frame = mission.receive_frame()
                if frame:
                    mission.handle_frame()
                    
                    # Print some status updates
                    if hasattr(mission, '_state'):
                        state_name = mission._state.__class__.__name__
                        elapsed = time.time() - mission_start_time
                        print(f"[{elapsed:6.1f}s] State: {state_name}")
                        
                        # Print sensor data occasionally
                        if elapsed % 5 < 0.1:  # Every 5 seconds
                            sensors = mission.sensors
                            print(f"  Sensors - Altitude: {sensors.get('altitude', 0):.1f}m, "
                                  f"Pressure: {sensors.get('oxidizer_pressure', 0):.1f}bar, "
                                  f"Fuel: {sensors.get('fuel_level', 0):.1f}%")
                
                time.sleep(0.1)  # Small delay
                
            except KeyboardInterrupt:
                print("\n👋 Mission stopped by user")
                break
            except Exception as e:
                print(f"Error in mission loop: {e}")
                time.sleep(1)
                
    except Exception as e:
        print(f"Failed to initialize mission: {e}")
        print("Make sure the simulator is running!")

def main():
    """Main demo function"""
    print("Rocket Flight Controller Demo")
    print("This demo shows the flight controller in action")
    print("For the full visualizer, run: python run_visualizer.py")
    print()
    
    # Check if simulator config exists
    import os
    if not os.path.exists('simulator_config.yaml'):
        print("✗ simulator_config.yaml not found")
        print("Please run this from the project root directory")
        return
    
    print("Starting demo mission...")
    print("Make sure you have:")
    print("1. TCP proxy running: python tcp_proxy.py")
    print("2. Simulator running: python tcp_simulator.py")
    print()
    
    try:
        run_demo_mission()
    except KeyboardInterrupt:
        print("\nDemo stopped")
    except Exception as e:
        print(f"Demo error: {e}")

if __name__ == '__main__':
    main()
