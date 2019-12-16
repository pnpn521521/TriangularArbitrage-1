from abc import ABCMeta, abstractmethod
from threading import Timer, Thread
import time
import queue

class HelloEvent(Thread):
    def __init__(self, string_arg):
        self.string_arg = string_arg
        Thread.__init__(self)

    def run(self):
        print('hello world!')
        time.sleep(3)
        print(self.string_arg)

class AnotherEvent(Thread):
    def __init__(self):
        Thread.__init__(self)
    def run(self):
        print('THIS IS A DIFFERENT KIND OF EVENT!')
