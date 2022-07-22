#!/usr/bin/python3

import logging
from time import sleep
import metarace
from metarace import telegraph

logging.basicConfig(level=logging.DEBUG)
metarace.init()

def messagecb(topic, msg):
    obj = telegraph.from_json(msg)
    print(repr(obj))    

t = telegraph.telegraph()
t.set_will_json({'example':'error'}, 'thetopic')
t.subscribe('thetopic')
t.setcb(messagecb)
t.start()

# allow connection process to begin before continuing
sleep(1)

count = 0
elist = []
try:
    while True:
        elist.append(count)
        t.publish_json({'example':elist,'count':count}, 'thetopic')
        count += 1
        sleep(5)
finally:
    t.publish_json({'example':'done'}, 'thetopic')
    t.exit()
    t.join()
