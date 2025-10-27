#!/usr/bin/env python3
"""
Flight Controller Visualization Dashboard
A NiceGUI application for monitoring automated rocket flight
"""

import asyncio
import time
from datetime import datetime
from typing import Dict, List, Optional
import threading
import queue

from nicegui import ui, app
from nicegui.events import ValueChangeEventArguments
import plotly.graph_objects as go

# Import the flight controller
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flight_controller.flight_controller import MissionContext
from communication_library.frame import Frame
from communication_library import ids

class FlightVisualizer:
    def __init__(self):
        self.mission_context: Optional[MissionContext] = None
        self.current_state = "Initializing"
        self.is_connected = False
        self.is_running = False
        self.mission_start_time = None
        self.mission_thread = None
        
        # Data storage for charts
        self.altitude_data = []
        self.pressure_data = []
        self.fuel_level_data = []
        self.oxidizer_level_data = []
        self.timestamps = []
        self.start_time = time.time()
        
        # State tracking
        self.state_history = []
        self.last_update = time.time()
        
        # UI elements (will be initialized in setup_ui)
        self.connection_status = None
        self.state_badge = None
        self.current_state_label = None
        self.mission_time_label = None
        self.connection_label = None
        self.last_update_label = None
        self.fuel_level_progress = None
        self.fuel_level_label = None
        self.oxidizer_level_progress = None
        self.oxidizer_level_label = None
        self.altitude_label = None
        self.pressure_label = None
        self.angle_label = None
        self.altitude_chart = None
        self.pressure_chart = None
        self.combined_chart = None
        self.state_timeline = None
        
        # Control buttons
        self.connect_btn = None
        self.disconnect_btn = None
        self.start_btn = None
        self.stop_btn = None
        
        # Manual control elements
        self.fuel_intake_slider = None
        self.fuel_intake_value = None
        self.oxidizer_intake_slider = None
        self.oxidizer_intake_value = None
        self.fuel_main_slider = None
        self.fuel_main_value = None
        self.oxidizer_main_slider = None
        self.oxidizer_main_value = None
        self.heater_switch = None
        self.igniter_switch = None
        self.parachute_switch = None
        
        # Message queue for thread-safe updates
        self.update_queue = queue.Queue()
        
    def setup_ui(self):
        """Setup the main UI layout"""
        ui.page_title('Rocket Flight Controller Dashboard')
        
        with ui.header().classes('items-center justify-between'):
            ui.label('🚀 Rocket Flight Controller').classes('text-h4 font-bold')
            with ui.row():
                self.connection_status = ui.badge('Disconnected', color='red')
                self.state_badge = ui.badge('Initializing', color='gray')
        
        # Main content area
        with ui.row().classes('w-full gap-4'):
            # Left column - Status and Controls
            with ui.column().classes('w-1/3 gap-4'):
                self.create_status_card()
                self.create_control_panel()
                self.create_sensors_card()
            
            # Right column - Charts and Timeline
            with ui.column().classes('w-2/3 gap-4'):
                self.create_charts()
                self.create_state_timeline()
        
        # Start the update loop
        self.start_update_loop()
    
    def create_status_card(self):
        """Create the mission status card"""
        with ui.card().classes('w-full'):
            ui.label('Mission Status').classes('text-h6 font-bold')
            
            with ui.row().classes('w-full justify-between'):
                ui.label('Current State:')
                self.current_state_label = ui.label('Initializing').classes('font-bold')
            
            with ui.row().classes('w-full justify-between'):
                ui.label('Mission Time:')
                self.mission_time_label = ui.label('00:00:00').classes('font-mono')
            
            with ui.row().classes('w-full justify-between'):
                ui.label('Connection:')
                self.connection_label = ui.label('Disconnected').classes('text-red-500')
            
            with ui.row().classes('w-full justify-between'):
                ui.label('Last Update:')
                self.last_update_label = ui.label('Never').classes('text-sm')
    
    def create_control_panel(self):
        """Create the control panel"""
        with ui.card().classes('w-full'):
            ui.label('Flight Controls').classes('text-h6 font-bold')
            
            with ui.column().classes('w-full gap-2'):
                # Connection controls
                with ui.row().classes('w-full gap-2'):
                    self.connect_btn = ui.button('Connect to Simulator', 
                                              on_click=self.connect_to_simulator).classes('flex-1')
                    self.disconnect_btn = ui.button('Disconnect', 
                                                  on_click=self.disconnect_from_simulator).classes('flex-1')
                    self.disconnect_btn.disable()
                
                # Mission controls
                with ui.row().classes('w-full gap-2'):
                    self.start_btn = ui.button('Start Mission', 
                                             on_click=self.start_mission).classes('flex-1')
                    self.stop_btn = ui.button('Stop Mission', 
                                            on_click=self.stop_mission).classes('flex-1')
                    self.start_btn.disable()
                    self.stop_btn.disable()
                
                # Manual controls
                with ui.expansion('Manual Controls', icon='settings').classes('w-full'):
                    with ui.column().classes('w-full gap-2'):
                        ui.label('Servo Controls').classes('font-bold')
                        
                        # Fuel intake
                        with ui.row().classes('w-full items-center gap-2'):
                            ui.label('Fuel Intake:').classes('w-32')
                            self.fuel_intake_slider = ui.slider(min=0, max=100, value=100)
                            self.fuel_intake_value = ui.label('100%').classes('w-12')
                        self.fuel_intake_slider.on('update:model-value', 
                            lambda e: self.control_servo_handler('fuel_intake', e))
                        
                        # Oxidizer intake
                        with ui.row().classes('w-full items-center gap-2'):
                            ui.label('Oxidizer Intake:').classes('w-32')
                            self.oxidizer_intake_slider = ui.slider(min=0, max=100, value=100)
                            self.oxidizer_intake_value = ui.label('100%').classes('w-12')
                        self.oxidizer_intake_slider.on('update:model-value',
                            lambda e: self.control_servo_handler('oxidizer_intake', e))
                        
                        # Main valves
                        with ui.row().classes('w-full items-center gap-2'):
                            ui.label('Fuel Main:').classes('w-32')
                            self.fuel_main_slider = ui.slider(min=0, max=100, value=100)
                            self.fuel_main_value = ui.label('100%').classes('w-12')
                        self.fuel_main_slider.on('update:model-value',
                            lambda e: self.control_servo_handler('fuel_main', e))
                        
                        with ui.row().classes('w-full items-center gap-2'):
                            ui.label('Oxidizer Main:').classes('w-32')
                            self.oxidizer_main_slider = ui.slider(min=0, max=100, value=100)
                            self.oxidizer_main_value = ui.label('100%').classes('w-12')
                        self.oxidizer_main_slider.on('update:model-value',
                            lambda e: self.control_servo_handler('oxidizer_main', e))
                        
                        ui.label('Relay Controls').classes('font-bold')
                        
                        # Relays
                        with ui.row().classes('w-full items-center gap-2'):
                            ui.label('Oxidizer Heater:').classes('w-32')
                            self.heater_switch = ui.switch()
                        self.heater_switch.on('update:model-value',
                            lambda e: self.control_relay_handler('oxidizer_heater', e))
                        
                        with ui.row().classes('w-full items-center gap-2'):
                            ui.label('Igniter:').classes('w-32')
                            self.igniter_switch = ui.switch()
                        self.igniter_switch.on('update:model-value',
                            lambda e: self.control_relay_handler('igniter', e))
                        
                        with ui.row().classes('w-full items-center gap-2'):
                            ui.label('Parachute:').classes('w-32')
                            self.parachute_switch = ui.switch()
                        self.parachute_switch.on('update:model-value',
                            lambda e: self.control_relay_handler('parachute', e))
    
    def create_sensors_card(self):
        """Create the sensors monitoring card"""
        with ui.card().classes('w-full'):
            ui.label('Sensor Readings').classes('text-h6 font-bold')
            
            # Fuel level
            with ui.row().classes('w-full justify-between items-center'):
                ui.label('Fuel Level:').classes('font-bold')
                self.fuel_level_progress = ui.linear_progress(value=0, show_value=False).classes('flex-1 mx-2')
                self.fuel_level_label = ui.label('0%').classes('w-12')
            
            # Oxidizer level
            with ui.row().classes('w-full justify-between items-center'):
                ui.label('Oxidizer Level:').classes('font-bold')
                self.oxidizer_level_progress = ui.linear_progress(value=0, show_value=False).classes('flex-1 mx-2')
                self.oxidizer_level_label = ui.label('0%').classes('w-12')
            
            # Altitude
            with ui.row().classes('w-full justify-between items-center'):
                ui.label('Altitude:').classes('font-bold')
                self.altitude_label = ui.label('0 m').classes('font-mono')
            
            # Pressure
            with ui.row().classes('w-full justify-between items-center'):
                ui.label('Oxidizer Pressure:').classes('font-bold')
                self.pressure_label = ui.label('0 bar').classes('font-mono')
            
            # Angle
            with ui.row().classes('w-full justify-between items-center'):
                ui.label('Rocket Angle:').classes('font-bold')
                self.angle_label = ui.label('0°').classes('font-mono')
    
    def create_charts(self):
        """Create the data visualization charts"""
        with ui.card().classes('w-full'):
            ui.label('Flight Data').classes('text-h6 font-bold')
            
            with ui.tabs().classes('w-full') as tabs:
                tab1 = ui.tab('Altitude')
                tab2 = ui.tab('Pressure')
                tab3 = ui.tab('Combined')
            
            with ui.tab_panels(tabs, value=tab1).classes('w-full'):
                # Altitude tab
                with ui.tab_panel(tab1):
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=[], y=[], mode='lines', name='Altitude', line=dict(color='blue')))
                    fig.update_layout(
                        title='Altitude Over Time',
                        xaxis_title='Time (s)',
                        yaxis_title='Altitude (m)',
                        height=300
                    )
                    self.altitude_chart = ui.plotly(fig).classes('w-full')
                
                # Pressure tab
                with ui.tab_panel(tab2):
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=[], y=[], mode='lines', name='Oxidizer Pressure', line=dict(color='red')))
                    fig.update_layout(
                        title='Oxidizer Pressure Over Time',
                        xaxis_title='Time (s)',
                        yaxis_title='Pressure (bar)',
                        height=300
                    )
                    self.pressure_chart = ui.plotly(fig).classes('w-full')
                
                # Combined tab
                with ui.tab_panel(tab3):
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=[], y=[], mode='lines', name='Altitude', yaxis='y', line=dict(color='blue')))
                    fig.add_trace(go.Scatter(x=[], y=[], mode='lines', name='Pressure', yaxis='y2', line=dict(color='red')))
                    fig.update_layout(
                        title='Flight Data Overview',
                        xaxis_title='Time (s)',
                        yaxis=dict(title='Altitude (m)', side='left'),
                        yaxis2=dict(title='Pressure (bar)', side='right', overlaying='y'),
                        height=300
                    )
                    self.combined_chart = ui.plotly(fig).classes('w-full')
    
    def create_state_timeline(self):
        """Create the state timeline visualization"""
        with ui.card().classes('w-full'):
            ui.label('Mission Timeline').classes('text-h6 font-bold')
            
            self.state_timeline = ui.column().classes('w-full gap-2')
            
            # Add initial state
            with self.state_timeline:
                with ui.row().classes('w-full items-center gap-2 p-2 bg-gray-100 rounded'):
                    ui.icon('schedule').classes('text-gray-500')
                    ui.label('Initializing').classes('font-bold')
                    ui.label('System startup').classes('text-sm text-gray-600')
    
    def control_servo_handler(self, servo_name: str, e):
        """Handle servo control"""
        if self.mission_context and self.is_connected:
            value = e.args if hasattr(e, 'args') else e
            device_id = self.mission_context.servo_to_id.get(servo_name, 0)
            frame = Frame(
                ids.BoardID.ROCKET,
                ids.PriorityID.HIGH,
                ids.ActionID.SERVICE,
                ids.BoardID.SOFTWARE,
                ids.DeviceID.SERVO,
                device_id,
                ids.DataTypeID.FLOAT,
                ids.OperationID.SERVO.value.POSITION,
                (float(value),)
            )
            self.mission_context.send_frame(frame)
            
            # Update UI
            if servo_name == 'fuel_intake' and self.fuel_intake_value:
                self.fuel_intake_value.set_text(f'{value}%')
            elif servo_name == 'oxidizer_intake' and self.oxidizer_intake_value:
                self.oxidizer_intake_value.set_text(f'{value}%')
            elif servo_name == 'fuel_main' and self.fuel_main_value:
                self.fuel_main_value.set_text(f'{value}%')
            elif servo_name == 'oxidizer_main' and self.oxidizer_main_value:
                self.oxidizer_main_value.set_text(f'{value}%')
    
    def control_relay_handler(self, relay_name: str, e):
        """Handle relay control"""
        if self.mission_context and self.is_connected:
            value = e.args if hasattr(e, 'args') else e
            device_id = self.mission_context.relays_to_id.get(relay_name, 0)
            operation = ids.OperationID.RELAY.value.OPEN if value else ids.OperationID.RELAY.value.CLOSE
            frame = Frame(
                ids.BoardID.ROCKET,
                ids.PriorityID.HIGH,
                ids.ActionID.SERVICE,
                ids.BoardID.SOFTWARE,
                ids.DeviceID.RELAY,
                device_id,
                ids.DataTypeID.FLOAT,
                operation,
                ()
            )
            self.mission_context.send_frame(frame)
    
    def connect_to_simulator(self):
        """Connect to the rocket simulator"""
        try:
            # Try to find config file
            config_paths = ['simulator_config.yaml', 'hardware_config.yaml', 'config.yaml']
            config_file = None
            for path in config_paths:
                if os.path.exists(path):
                    config_file = path
                    break
            
            if not config_file:
                ui.notify('Config file not found. Checked: ' + ', '.join(config_paths), type='negative')
                return
            
            # Create mission context (this connects to TCP automatically)
            self.mission_context = MissionContext(config_file)
            self.is_connected = True
            
            # Update UI
            self.connection_status.set_text('Connected')
            self.connection_status.props('color=green')
            self.connection_label.set_text('Connected')
            self.connection_label.classes(remove='text-red-500', add='text-green-500')
            
            self.connect_btn.disable()
            self.disconnect_btn.enable()
            self.start_btn.enable()
            
            ui.notify(f'Connected to simulator using {config_file}', type='positive')
        except Exception as e:
            ui.notify(f'Failed to connect: {str(e)}', type='negative')
            print(f"Connection error: {e}")
            import traceback
            traceback.print_exc()
    
    def disconnect_from_simulator(self):
        """Disconnect from the simulator"""
        # Stop mission if running
        if self.is_running:
            self.stop_mission()
        
        self.is_connected = False
        self.mission_context = None
        
        self.connection_status.set_text('Disconnected')
        self.connection_status.props('color=red')
        self.connection_label.set_text('Disconnected')
        self.connection_label.classes(remove='text-green-500', add='text-red-500')
        
        self.connect_btn.enable()
        self.disconnect_btn.disable()
        self.start_btn.disable()
        self.stop_btn.disable()
        
        ui.notify('Disconnected from simulator', type='info')
    
    def start_mission(self):
        """Start the automated mission - uses mission_context.run()"""
        if not self.mission_context:
            ui.notify('Not connected to simulator', type='negative')
            return
        
        self.is_running = True
        self.mission_start_time = time.time()
        self.start_btn.disable()
        self.stop_btn.enable()
        
        # Start mission in a separate thread using the run() method
        # This creates a wrapper that can be stopped
        def mission_wrapper():
            """Wrapper around mission.run() that can be stopped"""
            try:
                # Override the while True in run() by using handle_frame directly
                while self.is_running and self.mission_context:
                    self.mission_context.handle_frame()
                    
                    # Queue state updates for UI
                    if hasattr(self.mission_context, '_state'):
                        self.update_queue.put(('state_update', self.mission_context._state))
                    
                    time.sleep(0.01)  # Small delay to prevent CPU overload
                    
            except Exception as e:
                print(f"Mission error: {e}")
                import traceback
                traceback.print_exc()
                self.update_queue.put(('error', str(e)))
        
        self.mission_thread = threading.Thread(target=mission_wrapper, daemon=True)
        self.mission_thread.start()
        
        ui.notify('Mission started - Automated sequence running', type='positive')
    
    def stop_mission(self):
        """Stop the automated mission"""
        self.is_running = False
        
        # Wait for thread to finish
        if self.mission_thread and self.mission_thread.is_alive():
            self.mission_thread.join(timeout=1.0)
        
        self.start_btn.enable()
        self.stop_btn.disable()
        
        ui.notify('Mission stopped', type='info')
    
    def start_update_loop(self):
        """Start the UI update loop"""
        async def update_ui():
            try:
                # Process queued updates
                while not self.update_queue.empty():
                    update_type, data = self.update_queue.get_nowait()
                    self.process_update(update_type, data)
                
                # Update UI elements
                self.update_ui_elements()
                
            except Exception as e:
                print(f"Update loop error: {e}")
        
        # Use NiceGUI timer for thread-safe UI updates
        ui.timer(0.5, update_ui)
    
    def process_update(self, update_type: str, data):
        """Process queued updates"""
        if update_type == 'state_update':
            # State was updated in mission thread
            pass
        elif update_type == 'error':
            ui.notify(f'Mission error: {data}', type='negative')
    
    def update_ui_elements(self):
        """Update UI elements with current data"""
        if not self.mission_context:
            return
        
        # Update current state
        if hasattr(self.mission_context, '_state') and self.mission_context._state:
            state_name = self.mission_context._state.__class__.__name__
            if state_name != self.current_state:
                self.current_state = state_name
                self.current_state_label.set_text(state_name)
                self.add_state_to_timeline(state_name)
                
                # Update state badge color
                state_colors = {
                    'IdleState': 'gray',
                    'LaunchState': 'blue',
                    'FuelState': 'yellow',
                    'HeatingOxidizerState': 'orange',
                    'IgnitationState': 'red',
                    'FlightState': 'green',
                    'LandingState': 'purple',
                    'LandedState': 'green',
                    'AbortState': 'red'
                }
                self.state_badge.set_text(state_name.replace('State', ''))
                self.state_badge.props(f'color={state_colors.get(state_name, "gray")}')
        
        # Update mission time
        if self.is_running and self.mission_start_time:
            mission_time = time.time() - self.mission_start_time
            hours = int(mission_time // 3600)
            minutes = int((mission_time % 3600) // 60)
            seconds = int(mission_time % 60)
            self.mission_time_label.set_text(f'{hours:02d}:{minutes:02d}:{seconds:02d}')
        
        # Update sensor readings
        self.update_sensor_readings()
        
        # Update charts
        self.update_charts()
        
        # Update last update time
        self.last_update_label.set_text(datetime.now().strftime('%H:%M:%S'))
    
    def update_sensor_readings(self):
        """Update sensor reading displays"""
        if not self.mission_context:
            return
        
        sensors = self.mission_context.sensors
        
        # Fuel level
        fuel_level = sensors.get('fuel_level', 0)
        self.fuel_level_progress.set_value(fuel_level / 100)
        self.fuel_level_label.set_text(f'{fuel_level:.1f}%')
        
        # Oxidizer level
        oxidizer_level = sensors.get('oxidizer_level', 0)
        self.oxidizer_level_progress.set_value(oxidizer_level / 100)
        self.oxidizer_level_label.set_text(f'{oxidizer_level:.1f}%')
        
        # Altitude
        altitude = sensors.get('altitude', 0)
        self.altitude_label.set_text(f'{altitude:.1f} m')
        
        # Pressure
        pressure = sensors.get('oxidizer_pressure', 0)
        self.pressure_label.set_text(f'{pressure:.1f} bar')
        
        # Angle
        angle = sensors.get('angle', 0)
        self.angle_label.set_text(f'{angle:.1f}°')
    
    def update_charts(self):
        """Update the data charts"""
        if not self.mission_context:
            return
        
        sensors = self.mission_context.sensors
        current_time = time.time() - self.start_time
        
        # Add new data points
        self.timestamps.append(current_time)
        self.altitude_data.append(sensors.get('altitude', 0))
        self.pressure_data.append(sensors.get('oxidizer_pressure', 0))
        self.fuel_level_data.append(sensors.get('fuel_level', 0))
        self.oxidizer_level_data.append(sensors.get('oxidizer_level', 0))
        
        # Keep only last 100 data points
        max_points = 100
        if len(self.timestamps) > max_points:
            self.timestamps = self.timestamps[-max_points:]
            self.altitude_data = self.altitude_data[-max_points:]
            self.pressure_data = self.pressure_data[-max_points:]
            self.fuel_level_data = self.fuel_level_data[-max_points:]
            self.oxidizer_level_data = self.oxidizer_level_data[-max_points:]
        
        # Update altitude chart
        if self.altitude_chart:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=self.timestamps, y=self.altitude_data, mode='lines', 
                                    name='Altitude', line=dict(color='blue')))
            fig.update_layout(
                title='Altitude Over Time',
                xaxis_title='Time (s)',
                yaxis_title='Altitude (m)',
                height=300
            )
            self.altitude_chart.update_figure(fig)
        
        # Update pressure chart
        if self.pressure_chart:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=self.timestamps, y=self.pressure_data, mode='lines', 
                                    name='Pressure', line=dict(color='red')))
            fig.update_layout(
                title='Oxidizer Pressure Over Time',
                xaxis_title='Time (s)',
                yaxis_title='Pressure (bar)',
                height=300
            )
            self.pressure_chart.update_figure(fig)
        
        # Update combined chart
        if self.combined_chart:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=self.timestamps, y=self.altitude_data, mode='lines', 
                                    name='Altitude', yaxis='y', line=dict(color='blue')))
            fig.add_trace(go.Scatter(x=self.timestamps, y=self.pressure_data, mode='lines', 
                                    name='Pressure', yaxis='y2', line=dict(color='red')))
            fig.update_layout(
                title='Flight Data Overview',
                xaxis_title='Time (s)',
                yaxis=dict(title='Altitude (m)', side='left'),
                yaxis2=dict(title='Pressure (bar)', side='right', overlaying='y'),
                height=300
            )
            self.combined_chart.update_figure(fig)
    
    def add_state_to_timeline(self, state_name: str):
        """Add a new state to the timeline"""
        state_descriptions = {
            'IdleState': 'System idle, checking conditions',
            'LaunchState': 'Starting oxidizer fueling',
            'FuelState': 'Fueling with fuel',
            'HeatingOxidizerState': 'Heating oxidizer to optimal pressure',
            'IgnitationState': 'Executing ignition sequence',
            'FlightState': 'Rocket in flight',
            'LandingState': 'Preparing for landing',
            'LandedState': 'Mission completed successfully',
            'AbortState': 'Mission aborted due to safety conditions'
        }
        
        description = state_descriptions.get(state_name, 'Unknown state')
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        with self.state_timeline:
            with ui.row().classes('w-full items-center gap-2 p-2 bg-blue-50 rounded'):
                ui.icon('rocket_launch').classes('text-blue-500')
                ui.label(state_name.replace('State', '')).classes('font-bold')
                ui.label(description).classes('text-sm text-gray-600')
                ui.label(timestamp).classes('text-xs text-gray-500 ml-auto')


def main():
    """Main application entry point"""
    try:
        # Create and setup the visualizer
        visualizer = FlightVisualizer()
        visualizer.setup_ui()
        
        print("\n" + "="*70)
        print("🚀 ROCKET FLIGHT CONTROLLER DASHBOARD")
        print("="*70)
        print("Dashboard running at http://localhost:8080")
        print("1. Click 'Connect to Simulator' to establish connection")
        print("2. Click 'Start Mission' to begin automated flight sequence")
        print("3. Monitor telemetry and state transitions in real-time")
        print("="*70 + "\n")
        
        # Run the application
        ui.run(title='Rocket Flight Controller Dashboard', port=8080, show=True)
    except Exception as e:
        print(f"Error starting visualizer: {e}")
        print("Make sure all dependencies are installed: pip install nicegui plotly")
        import traceback
        traceback.print_exc()
        raise

if __name__ in {"__main__", "__mp_main__"}:
    main()