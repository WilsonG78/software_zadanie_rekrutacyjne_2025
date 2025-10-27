from communication_library.communication_manager import (
    CommunicationManager,
    TransportType,
)
from communication_library.tcp_transport import TcpSettings
from communication_library.frame import Frame
from communication_library import ids
from communication_library.exceptions import (
    TransportTimeoutError,
    TransportError,
    UnregisteredCallbackError,
)
from typing import Callable, List, Dict
from abc import ABC, abstractmethod
import yaml
import time
import threading
import logging
from datetime import datetime


class MissionContext:
    _state: "MissionState"
    communication_manager: CommunicationManager
    action_handler: Dict[ids.ActionID, Callable]
    servos: Dict[str, int]
    servo_to_id: Dict[str, int]
    relays: Dict[str, float]
    relays_to_id: Dict[str, int]
    sensors: Dict[str, int]

    def __init__(self, hardware_config: str):
        # Setup logging
        self.logger = logging.getLogger(f"MissionContext_{id(self)}")
        self.logger.setLevel(logging.INFO)
        
        # Create console handler if not already exists
        if not self.logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
        
        self.logger.info("=== MissionContext Initialization Started ===")
        self.logger.info(f"Hardware config file: {hardware_config}")
        
        self._state = IdleState()
        self.logger.info(f"Initial state set to: {self._state.__class__.__name__}")
        
        self.communication_manager = CommunicationManager()
        self.logger.info("CommunicationManager created")
        
        self.communication_manager.change_transport_type(TransportType.TCP)
        self.logger.info("Transport type changed to TCP")
        
        self.communication_manager.connect(TcpSettings("127.0.0.1",3000))
        self.logger.info(self.communication_manager.is_connected)
        self.logger.info("Connected to TCP server at 127.0.0.1:3000")
        
        self.action_handler = {
            ids.ActionID.FEED: self.handle_feed,
            ids.ActionID.SERVICE: self.handle_service,
            ids.ActionID.ACK: self.handle_ack,
            ids.ActionID.NACK: self.handle_nack,
        }
        self.logger.info("Action handlers registered")

        with open(hardware_config, "r") as config_file:
            self.config = yaml.safe_load(config_file)
        self.logger.info(f"Hardware configuration loaded from {hardware_config}")

        self.servos = {}
        self.servo_to_id = {}
        for servo_name, servo_config in self.config["devices"]["servo"].items():
            self.servos[servo_name] = servo_config["closed_pos"]
            self.servo_to_id[servo_name] = servo_config["device_id"]
        self.logger.info(f"Servos configured: {list(self.servos.keys())}")

        self.relays = {}
        self.relays_to_id = {}
        for relay_name, relay_config in self.config["devices"]["relay"].items():
            self.relays[relay_name] = 0
            self.relays_to_id[relay_name] = relay_config["device_id"]
        self.logger.info(f"Relays configured: {list(self.relays.keys())}")

        self.sensors = {
            "fuel_level": 0.0,
            "oxidizer_level": 0.0,
            "altitude": 0.0,
            "oxidizer_pressure": 0.0,
            "angle": 2.0,
        }
        self.logger.info(f"Sensors initialized: {list(self.sensors.keys())}")
        
        self.logger.info("=== MissionContext Initialization Completed ===")
        print(self._state)
        self._state.context = self
        self._state.on_enter()
        

    def transition_to(self, state):
        old_state = self._state.__class__.__name__ if self._state else "None"
        new_state = state.__class__.__name__
        self.logger.info(f"State transition: {old_state} -> {new_state}")
        self._state = state
        self._state.context = self
        self._state.on_enter()
        self.logger.info(f"State {new_state} entered successfully")

    def handle_frame(self):
        try:
            frame = self.receive_frame()
            if not frame:
                self.logger.debug("No frame received (timeout)")
                return
            self.logger.debug(f"Frame received: {frame.action.name} from device {frame.device_type.name}")
        except TimeoutError as e:
            self.logger.debug(f"Frame receive timeout: {e}")
        except UnregisteredCallbackError as e:
            self.logger.warning(f"Unregistered callback error: {e}")
            handler = self.action_handler.get(e.frame.action)
            if handler:
                self.logger.info(f"Handling frame with registered handler: {e.frame}")
                handler(e.frame)
            else:
                self.logger.error(f"No handler found for frame: {e.frame}")
        except Exception as e:
            self.logger.error(f"Unexpected error in handle_frame: {e}")

    def update_telemetry(self, frame: Frame):
        self.logger.debug("Updating telemetry from frame")
        self.handle_feed(frame)

    def handle_feed(self, frame: Frame):
        self.logger.debug(f"Handling FEED frame: device={frame.device_type}, data={frame.payload}")
        self._state.handle_feed(frame)

    def handle_nack(self, frame: Frame):
        self.logger.warning(f"Handling NACK frame: device={frame.device_type}, error={frame.payload}")
        self._state.handle_nack(frame)

    def handle_ack(self, frame: Frame):
        self.logger.info(f"Handling ACK frame: device={frame.device_type}")
        self._state.handle_ack(frame)

    def handle_service(self, frame: Frame):
        self.logger.info(f"Handling SERVICE frame: device={frame.device_type}, operation={frame.operation}")
        self._state.handle_service(frame)

    def receive_frame(self) -> Frame:
        self.logger.debug("Attempting to receive frame from communication manager")
        frame = self.communication_manager.receive()
        if frame:
            self.logger.debug(f"Frame received successfully: {frame.action}")
        return frame

    def servo_name_to_id(self, name: str):
        return self.servo_to_id[name]

    def send_frame(self, frame: Frame) -> None:
        self.logger.info(f"Sending frame: {frame.action} to device {frame.device_type} (ID: {frame.device_id})")
        self.communication_manager.push(frame)
        self.communication_manager.send()
        self.logger.debug("Frame sent successfully")

    def close_relay(self, relay_id: int):
        self.logger.info(f"Closing relay ID: {relay_id}")
        relay_close_frame = Frame(
            ids.BoardID.ROCKET,
            ids.PriorityID.LOW,
            ids.ActionID.SERVICE,
            ids.BoardID.SOFTWARE,
            ids.DeviceID.RELAY,
            relay_id,
            ids.DataTypeID.FLOAT,
            ids.OperationID.RELAY.value.CLOSE,
            (),
        )
        self.send_frame(relay_close_frame)

    def close_servo(self, servo_id: int):
        self.logger.info(f"Closing servo ID: {servo_id}")
        servo_close_frame = Frame(
            ids.BoardID.ROCKET,
            ids.PriorityID.LOW,
            ids.ActionID.SERVICE,
            ids.BoardID.SOFTWARE,
            ids.DeviceID.SERVO,
            servo_id,
            ids.DataTypeID.FLOAT,
            ids.OperationID.SERVO.value.CLOSE,
            (),
        )
        self.send_frame(servo_close_frame)

    def run(self):
        """Main mission loop"""
        self.logger.info("Starting mission loop")
        try:
            while True:  # ← HERE IS THE WHILE LOOP!
                self.handle_frame()
                time.sleep(0.1)  # Small delay to prevent CPU overload
        except KeyboardInterrupt:
            self.logger.info("Mission interrupted by user")
        except Exception as e:
            self.logger.error(f"Mission loop error: {e}", exc_info=True)

class MissionState(ABC):
    def __init__(self):
        self._context = None

    @property
    def context(self) -> MissionContext:
        return self._context

    @context.setter
    def context(self, context: MissionContext) -> None:
        self._context = context
        if context and hasattr(context, 'logger'):
            context.logger.debug(f"Context set for state: {self.__class__.__name__}")

    @abstractmethod
    def handle_feed(self, frame: Frame):
        device_name = ids.DeviceID(frame.device_type).name
        if self.context and hasattr(self.context, 'logger'):
            self.context.logger.debug(f"Processing FEED data for {device_name}: {frame.payload}")
        match frame.device_type:
            case ids.DeviceID.SENSOR:
                self.context.sensors[device_name] = frame.payload[0]
                if self.context and hasattr(self.context, 'logger'):
                    self.context.logger.debug(f"Sensor {device_name} updated to: {frame.payload[0]}")
            case ids.DeviceID.SERVO:
                self.context.servos[device_name] = frame.payload[0]
                if self.context and hasattr(self.context, 'logger'):
                    self.context.logger.debug(f"Servo {device_name} updated to: {frame.payload[0]}")
            case ids.DeviceID.RELAY:
                self.context.relays[device_name] = frame.payload[0]
                if self.context and hasattr(self.context, 'logger'):
                    self.context.logger.debug(f"Relay {device_name} updated to: {frame.payload[0]}")

    @abstractmethod
    def handle_nack(self, frame: Frame):
        pass

    @abstractmethod
    def handle_ack(self, frame: Frame):
        pass

    @abstractmethod
    def handle_service(self, frame: Frame):
        pass

    @abstractmethod
    def on_enter(self) -> None:
        pass


class IdleState(MissionState):
    def on_enter(self):
        self.context.logger.info("=== IdleState Entered ===")
        self.context.logger.info("Closing all open relays and servos")
        
        for relay in self.context.relays.keys():
            if self.context.relays[relay] == ids.OperationID.RELAY.value.OPEN:
                self.context.logger.info(f"Closing open relay: {relay}")
                self.context.close_relay(self.context.relays_to_id[relay])
        
        for servo in self.context.servos.keys():
            if self.context.servos[servo] == ids.OperationID.SERVO.value.OPEN:
                self.context.logger.info(f"Closing open servo: {servo}")
                self.context.close_servo(self.context.servo_to_id[servo])
        
        self.context.logger.info("IdleState initialization completed")

    def handle_feed(self, frame: Frame):
        device_name = ids.DeviceID(frame.device_type).name
        match frame.device_type:
            case ids.DeviceID.SENSOR:
                self.context.sensors[device_name] = frame.payload[0]
            case ids.DeviceID.SERVO:
                self.context.servos[device_name] = frame.payload[0]
            case ids.DeviceID.RELAY:
                self.context.relays[device_name] = frame.payload[0]

    def handle_nack(self, frame: Frame):
        self.context.send_frame(frame)

    def handle_service(self, frame: Frame):
        pass

    def handle_ack(self, frame: Frame):
        pass

    def transition_condition(self):
        is_good = True
        for relay in self.context.relays.keys():
            if self.context.relays[relay] != ids.OperationID.RELAY.value.CLOSE:
                self.context.close_relay(self.context.relays_to_id[relay])
                is_good = False
        for servo in self.context.servos.keys():
            if self.context.servos[servo] != ids.OperationID.SERVO.value.CLOSE:
                self.context.close_servo(self.context.servo_to_id[servo])
                is_good = False
        if is_good:
            self.context.transition_to(LaunchState)


class LaunchState(MissionState):
    def on_enter(self):
        self.oxidizer_fueling = False
        self.fueling_complete = False
        self.target_pressure = 30.0
        self.target_level = 100.0
        self.open_oxidizer_intake()

    def open_oxidizer_intake(self):
        open_oxidizer_intake = Frame(
            ids.BoardID.ROCKET,
            ids.PriorityID.HIGH,
            ids.ActionID.SERVICE,
            ids.BoardID.SOFTWARE,
            ids.DeviceID.SERVO,
            1,  # oxidizer_intake
            ids.DataTypeID.FLOAT,
            ids.OperationID.SERVO.value.POSITION,
            (0,),  # 0 = open position
        )

        self.context.send_frame(open_oxidizer_intake)
        self.oxidizer_fueling = True

    def close_oxidizer_intake(self):
        close_oxidizer_intake = Frame(
            ids.BoardID.ROCKET,
            ids.PriorityID.HIGH,
            ids.ActionID.SERVICE,
            ids.BoardID.SOFTWARE,
            ids.DeviceID.SERVO,
            1,  # oxidizer_intake
            ids.DataTypeID.FLOAT,
            ids.OperationID.SERVO.value.POSITION,
            (100,),  # 100 = closed position
        )
        self.context.send_frame(close_oxidizer_intake)

    def handle_nack(self, frame):
        """We send our frame once again"""
        new_frame = Frame(
            frame.source,
            ids.PriorityID.HIGH,
            ids.ActionID.SERVICE,
            frame.destination,
            frame.device_type,
            frame.device_id,
            frame.data_type,
            frame.operation,
            (),
        )
        self.context.send_frame(new_frame)

    def handle_ack(self, frame):
        print(f"Action completed {frame}")

    def handle_feed(self, frame):
        device_name = ids.DeviceID(frame.device_type).name
        match frame.device_type:
            case ids.DeviceID.SENSOR:
                self.context.sensors[device_name] = frame.payload[0]
            case ids.DeviceID.SERVO:
                self.context.servos[device_name] = frame.payload[0]
            case ids.DeviceID.RELAY:
                self.context.relays[device_name] = frame.payload[0]
        oxidizer_level = self.context.sensors["oxidizer_level"]
        oxidizer_pressure = self.context.sensors["oxidizer_pressure"]
        if device_name == "oxidizer_level":
            if oxidizer_level >= self.target_level and self.oxidizer_fueling:
                self.close_oxidizer_intake()
        elif device_name == "oxidizer_pressure":
            if (
                self.fueling_complete
                and abs(oxidizer_pressure - self.target_pressure) < 5
            ):
                self.context.transition_to(FuelState)

    def handle_service(self, frame):
        pass


class FuelState(MissionState):
    def on_enter(self):
        self.fueling = False
        self.target_fuel_level = 100
        self.fueling_completed = False
        self.open_fuel_intake()

    def open_fuel_intake(self):
        open_fuel_intake = Frame(
            ids.BoardID.ROCKET,
            ids.PriorityID.HIGH,
            ids.ActionID.SERVICE,
            ids.BoardID.SOFTWARE,
            ids.DeviceID.SERVO,
            0,  # fuel_intake
            ids.DataTypeID.FLOAT,
            ids.OperationID.SERVO.value.POSITION,
            (0,),  # 0 = open position
        )

        self.context.send_frame(open_fuel_intake)
        self.fueling = True

    def handle_nack(self, frame: Frame):
        """We send our frame once again"""
        new_frame = Frame(
            frame.source,
            ids.PriorityID.HIGH,
            ids.ActionID.SERVICE,
            frame.destination,
            frame.device_type,
            frame.device_id,
            frame.data_type,
            frame.operation,
            (),
        )
        self.context.send_frame(new_frame)

    def handle_ack(self, frame: Frame):
        if (
            frame.device_type == ids.DeviceID.SERVO
            and frame.device_id == 0  # fuel_intake device_id
            and frame.operation == ids.OperationID.SERVO.value.POSITION
            and frame.payload[0] == 100  # closed position
        ):
            self.context.transition_to(HeatingOxidizerState)

    def handle_feed(self, frame):
        device_name = ids.DeviceID(frame.device_type).name
        match frame.device_type:
            case ids.DeviceID.SENSOR:
                self.context.sensors[device_name] = frame.payload[0]
            case ids.DeviceID.SERVO:
                self.context.servos[device_name] = frame.payload[0]
            case ids.DeviceID.RELAY:
                self.context.relays[device_name] = frame.payload[0]
        fuel_level = self.context.sensors["fuel_level"]
        if device_name == "fuel_intake":
            if fuel_level >= self.target_fuel_level and self.fueling:
                self.close_fuel_intake()

    def close_fuel_intake(self):
        close_fuel_intake = Frame(
            ids.BoardID.ROCKET,
            ids.PriorityID.HIGH,
            ids.ActionID.SERVICE,
            ids.BoardID.SOFTWARE,
            ids.DeviceID.SERVO,
            0,  # fuel_intake
            ids.DataTypeID.FLOAT,
            ids.OperationID.SERVO.value.POSITION,
            (100,),  # 100 = closed position
        )

        self.context.send_frame(close_fuel_intake)
        self.fueling = False


class HeatingOxidizerState(MissionState):
    def on_enter(self):
        self.heating = False
        self.target_level = 65
        self.turn_on_heater()

    def turn_on_heater(self):
        turn_on_oxidizer_heater = Frame(
            ids.BoardID.ROCKET,
            ids.PriorityID.HIGH,
            ids.ActionID.SERVICE,
            ids.BoardID.SOFTWARE,
            ids.DeviceID.RELAY,
            0,  # oxidizer_heater
            ids.DataTypeID.FLOAT,
            ids.OperationID.RELAY.value.OPEN,
            (),
        )
        self.context.send_frame(turn_on_oxidizer_heater)

    def handle_feed(self, frame):
        device_name = ids.DeviceID(frame.device_type).name
        match frame.device_type:
            case ids.DeviceID.SENSOR:
                self.context.sensors[device_name] = frame.payload[0]
            case ids.DeviceID.SERVO:
                self.context.servos[device_name] = frame.payload[0]
            case ids.DeviceID.RELAY:
                self.context.relays[device_name] = frame.payload[0]
        oxidizer_pressure = self.context.sensors["oxidizer_pressure"]
        if device_name == "oxidizer_pressure":
            if oxidizer_pressure >= self.target_level and self.heating:
                self.turn_off_heater()

    def turn_off_heater(self):
        turn_off_oxidizer_heater = Frame(
            ids.BoardID.ROCKET,
            ids.PriorityID.HIGH,
            ids.ActionID.SERVICE,
            ids.BoardID.SOFTWARE,
            ids.DeviceID.RELAY,
            0,  # oxidizer_heater
            ids.DataTypeID.FLOAT,
            ids.OperationID.RELAY.value.CLOSE,
            (),
        )
        self.context.send_frame(turn_off_oxidizer_heater)

    def handle_nack(self, frame):
        """We send our frame once again we have to change destination to source and source to destination"""
        new_frame = Frame(
            frame.source,
            ids.PriorityID.HIGH,
            ids.ActionID.SERVICE,
            frame.destination,
            frame.device_type,
            frame.device_id,
            frame.data_type,
            frame.operation,
            (),
        )
        self.context.send_frame(new_frame)

    def handle_ack(self, frame):
        if (
            frame.device_type == ids.DeviceID.RELAY
            and frame.device_id == self.context.relays_to_id["oxidizer_heater"]
            and frame.operation == ids.OperationID.RELAY.value.CLOSE
        ):
            self.context.transition_to(IgnitationState)

        if (
            frame.device_type == ids.DeviceID.RELAY
            and frame.device_id == self.context.relays_to_id["oxidizer_heater"]
            and frame.operation == ids.OperationID.RELAY.value.OPEN
        ):
            self.heating = True


class IgnitationState(MissionState):
    def on_enter(self):
        self.valves_opened = False
        self.igniter_on = False
        self.fuel_valve_opened = False
        self.oxidizer_valve_opened = False
        self.ignition_started = False
        self.ignition_successful = False
        
        self.fuel_ack_time = None
        self.oxidizer_ack_time = None
        self.start_time = time.time()
        self.igniter_time = None


        pressure = self.context.sensors.get("oxidizer_pressure", 0)
        if pressure < 40:
            self.context.transition_to(HeatingOxidizerState())
            return
        elif pressure > 65:
            self.context.transition_to(AbortState())
            return
        
        self.open_fuel_main_valve()
        threading.Timer(0.2, self.open_oxidizer_main_valve).start()

        threading.Timer(0.9, self.check_valve_timing).start()
    

    
    def open_fuel_main_valve(self):
        """Open the main fuel valve"""
        fuel_main_frame = Frame(
            ids.BoardID.ROCKET,
            ids.PriorityID.HIGH,
            ids.ActionID.SERVICE,
            ids.BoardID.SOFTWARE,
            ids.DeviceID.SERVO,
            2,  # fuel_main device_id
            ids.DataTypeID.FLOAT,
            ids.OperationID.SERVO.value.POSITION,
            (0,),  # 0 = open position
        )
        self.context.send_frame(fuel_main_frame)
    
    def open_oxidizer_main_valve(self):
        """Open the main oxidizer valve"""
        oxidizer_main_frame = Frame(
            ids.BoardID.ROCKET,
            ids.PriorityID.HIGH,
            ids.ActionID.SERVICE,
            ids.BoardID.SOFTWARE,
            ids.DeviceID.SERVO,
            3,  # oxidizer_main device_id
            ids.DataTypeID.FLOAT,
            ids.OperationID.SERVO.value.POSITION,
            (0,),  # 0 = open position
        )
        self.context.send_frame(oxidizer_main_frame)
    
    def check_valve_timing(self):
        """Checks after 0.9 s if two of intakes are opened in allowed time."""
        if self.fuel_ack_time and self.oxidizer_ack_time:
            delta = abs(self.fuel_ack_time - self.oxidizer_ack_time)
            if delta <= 1.0:
                threading.Timer(0.3, self.activate_igniter).start()
                threading.Timer(1.0, self.check_igniter_timing).start()
            else:
                self.context.transition_to(AbortState())
        else:
            self.context.transition_to(AbortState())




    def activate_igniter(self):
        """Activate the igniter"""
        if self.igniter_on:
            return
        
        igniter_frame = Frame(
            ids.BoardID.ROCKET,
            ids.PriorityID.HIGH,
            ids.ActionID.SERVICE,
            ids.BoardID.SOFTWARE,
            ids.DeviceID.RELAY,
            1,  # igniter device_id
            ids.DataTypeID.FLOAT,
            ids.OperationID.RELAY.value.OPEN,
            (),
        )
        self.context.send_frame(igniter_frame)
       
    def check_igniter_timing(self):
        """Checks if igniter was activated in allowed time."""
        if not self.igniter_on:
            print("[IgnitionState] Igniter not activated in time. Flooding risk! Aborting.")
            self.context.transition_to(AbortState())
        else:
            print("[IgnitionState] Igniter fired successfully, awaiting lift-off...")

    def handle_feed(self, frame: Frame):
        device_name = ids.DeviceID(frame.device_type).name
        match frame.device_type:
            case ids.DeviceID.SENSOR:
                self.context.sensors[device_name] = frame.payload[0]
            case ids.DeviceID.SERVO:
                self.context.servos[device_name] = frame.payload[0]
            case ids.DeviceID.RELAY:
                self.context.relays[device_name] = frame.payload[0]
        
        
       
        
        # Check for successful ignition (altitude increasing)
        if self.igniter_on and not self.ignition_successful:
            altitude = self.context.sensors.get("altitude", 0)
            if altitude > 0:
                self.ignition_successful = True
                
                self.context.transition_to(FlightState)
    
    def handle_nack(self, frame: Frame):
        """Handle NACK responses during ignition"""
        print(f"NACK received during ignition: {frame}")
        # Retry the operation
        new_frame = Frame(
            frame.source,
            ids.PriorityID.HIGH,
            ids.ActionID.SERVICE,
            frame.destination,
            frame.device_type,
            frame.device_id,
            frame.data_type,
            frame.operation,
            frame.payload,
        )
        self.context.send_frame(new_frame)
    
    def handle_ack(self, frame: Frame):
        """Handle ACK responses during ignition"""
        now = time.time()
        device_name = ids.DeviceID(frame.device_type).name
        if frame.device_type == ids.DeviceID.SERVO:
            if frame.device_id == 2:  # fuel_main
                self.fuel_ack_time = now
                self.fuel_valve_opened = True
            elif frame.device_id == 3:  # oxidizer_main
                self.oxidizer_ack_time = now
                self.oxidizer_valve_opened = True
        elif frame.device_type == ids.DeviceID.RELAY:
            if frame.device_id == 1:  # igniter
                self.igniter_on = True
                self.igniter_time = now
    
    def handle_service(self, frame: Frame):
        """Handle service requests during ignition"""
        pass
        




class FlightState(MissionState):
    def on_enter(self):
        pass

    def handle_feed(self, frame: Frame):
        device_name = ids.DeviceID(frame.device_type).name
        if device_name == "altitude":
            if frame.payload[0] < self.context.sensors["altitude"]:
                self.context.sensors["altitude"] = frame.payload[0]
                self.context.transition_to(LandingState())
        match frame.device_type:
            case ids.DeviceID.SENSOR:
                self.context.sensors[device_name] = frame.payload[0]
            case ids.DeviceID.SERVO:
                self.context.servos[device_name] = frame.payload[0]
            case ids.DeviceID.RELAY:
                self.context.relays[device_name] = frame.payload[0]
    def handle_nack(self, frame: Frame):
        pass
    def handle_ack(self, frame: Frame):
        pass
    def handle_service(self, frame: Frame):
        pass

class LandingState(MissionState):
    def on_enter(self):
        self.landing_complete = False
        self.parachute_deployed = False
        self.deploy_parachute()

    def deploy_parachute(self):
        parachute_frame = Frame(
            ids.BoardID.ROCKET,
            ids.PriorityID.HIGH,
            ids.ActionID.SERVICE,
            ids.BoardID.SOFTWARE,
            ids.DeviceID.RELAY,
            2,  # parachute device_id
            ids.DataTypeID.FLOAT,
            ids.OperationID.RELAY.value.OPEN,
            (),
        )
        self.context.send_frame(parachute_frame)
    

    def handle_feed(self, frame: Frame):
        device_name = ids.DeviceID(frame.device_type).name
        match frame.device_type:
            case ids.DeviceID.SENSOR:
                self.context.sensors[device_name] = frame.payload[0]
            case ids.DeviceID.SERVO:
                self.context.servos[device_name] = frame.payload[0]
            case ids.DeviceID.RELAY:
                self.context.relays[device_name] = frame.payload[0]
        if self.context.sensors["altitude"] <= 0:
            self.landing_complete = True
            self.context.transition_to(LandedState())

    def handle_nack(self, frame: Frame):
        """We send our frame once again we have to change destination to source and source to destination"""
        new_frame = Frame(
            frame.source,
            ids.PriorityID.HIGH,
            ids.ActionID.SERVICE,
            frame.destination,
            frame.device_type,
            frame.device_id,
            frame.data_type,
            frame.operation,
            (frame.payload[0],),
        )
        self.context.send_frame(new_frame)

    def handle_ack(self, frame: Frame):
        if frame.device_type == ids.DeviceID.RELAY and frame.device_id == self.context.relays_to_id["parachute"]:
            self.parachute_deployed = True
        

class LandedState(MissionState):
    def on_enter(self):
        print("Landed")

class AbortState(MissionState):
    pass

if __name__ == "__main__":
    main_mision = MissionContext("../simulator_config.yaml")