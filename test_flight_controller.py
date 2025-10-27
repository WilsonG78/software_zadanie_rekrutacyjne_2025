from flight_controller.flight_controller import MissionContext


if __name__ == "__main__":
    main_controller = MissionContext("simulator_config.yaml")
    main_controller.run()
        