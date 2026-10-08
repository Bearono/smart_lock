"""Start background work after fork, exactly once per device worker."""
backlog = 8


def post_worker_init(worker):
    import os
    from pathlib import Path
    from app import camera, transmitter
    from command_executor import CommandExecutor, UnavailableActuator
    from runtime import CommandWorker, HeartbeatWorker
    actuator = UnavailableActuator()
    state = Path(os.environ.get('DEVICE_STATE_DIR', str(Path(__file__).parent / 'instance')))
    worker.device_commands = CommandWorker(CommandExecutor(transmitter, actuator, state / 'executions.db'))
    worker.device_heartbeat = HeartbeatWorker(transmitter, camera, actuator=actuator)
    worker.device_commands.start()
    worker.device_heartbeat.start()


def worker_exit(server, worker):
    commands = getattr(worker, 'device_commands', None)
    if commands:
        commands.stop()
    heartbeat = getattr(worker, 'device_heartbeat', None)
    if heartbeat:
        heartbeat.stop()
