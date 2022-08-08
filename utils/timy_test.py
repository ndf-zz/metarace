#!/usr/bin/python3

import logging
from time import sleep
import metarace
from metarace import timy

logging.basicConfig(level=logging.DEBUG)
metarace.init()


def timercb(impulse):
    print(repr(impulse))


t = timy.timy()
t.setport('/dev/ttyS0')
t.setcb(timercb)
t.start()
t.sane()
try:
    while True:
        sleep(2)
        t.arm('C0')
finally:
    t.exit()
    t.join()
