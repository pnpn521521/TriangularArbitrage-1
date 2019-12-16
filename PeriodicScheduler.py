import queue
from threading import Timer, Thread
from datetime import datetime
import time

class PeriodicScheduler:
    """
    Executes queued threads periodically. Each period, all thread objects in event_queue are started in order.
    """
    def __init__(self, timestep):
        self.timestep = timestep

        self.thread = Timer(self.timestep, self.periodic)

        self.iterations = 0

        self.event_queue = queue.Queue(maxsize=0)

    def start(self):
        self.thread.start()

    def terminate(self):
        self.thread.cancel()

    def periodic(self):
        while not self.event_queue.empty():
            thread = self.event_queue.get()
            thread.start()

        self.thread = Timer(self.timestep, self.periodic)
        self.thread.start()

if __name__ == '__main__':
    trading_system = PeriodicScheduler(1)
    trading_system.start()
