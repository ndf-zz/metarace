"""Telegraph - MQTT backed message exchange service.

 Configuration via metarace system config metarace.json, keys:

  host : (string) hostname or IP of MQTT server, or None to disable
  usetls : (bool) if True, connect to server over TLS
  debug : (bool) if True, enable logging in MQTT library
  username : (string) username or None to disable
  password : (string) password or None to disable
  deftopic : (string) a default publish topic or None to disable
  qos : (int) QOS to use for topic subscriptions

"""

import threading
import queue
import logging
import json
import paho.mqtt.client as mqtt
import metarace
from metarace import strops

QUEUE_TIMEOUT = 2

# module logger
LOG = logging.getLogger('metarace.telegraph')
LOG.setLevel(logging.DEBUG)


def defcallback(topic=None, msg=None):
    """Default message receive callback function."""
    LOG.debug('RCV %r: %r', topic, msg)


class telegraph(threading.Thread):
    """Metarace telegraph server thread."""

    def subscribe(self, topic=None, qos=None):
        """Add topic to the set of subscriptions."""
        if topic:
            self.__subscriptions[topic] = qos
            if self.__connected:
                self.__queue.put_nowait(('SUBSCRIBE', topic, qos))

    def unsubscribe(self, topic=None):
        """Remove topic from the set of subscriptions."""
        if topic and topic in self.__subscriptions:
            del self.__subscriptions[topic]
            if self.__connected:
                self.__queue.put_nowait(('UNSUBSCRIBE', topic))

    def setcb(self, func=None):
        """Set the message receive callback function."""
        if func is not None:
            self.__cb = func
        else:
            self.__cb = defcallback

    def set_deftopic(self, topic=None):
        """Set or clear the default publish topic."""
        if isinstance(topic, str) and topic:
            self.__deftopic = topic
        else:
            self.__deftopic = None
        LOG.debug('Default publish topic set to: %r', self.__deftopic)

    def set_clientid(self, clientid=None):
        """Set or clear the MQTT Client ID."""
        if isinstance(clientid, str) and clientid:
            self.__client._client_id = clientid
        else:
            self.__client.__client_id = ''
        LOG.debug('MQTT client ID set to: %r', self.__client._client_id)
        if self.__connected:
            self.reconnect()

    def connected(self):
        """Return true if connected."""
        return self.__connected

    def reconnect(self):
        """Request re-connection to relay."""
        self.__queue.put_nowait(('RECONNECT', True))

    def exit(self, msg=None):
        """Request thread termination."""
        self.__running = False
        self.__queue.put_nowait(('EXIT', msg))

    def wait(self):
        """Suspend calling thread until command queue is processed."""
        self.__queue.join()

    def publish(self, msg=None, topic=None, qos=None, retain=False):
        """Publish the provided msg to topic or deftopic if None."""
        self.__queue.put_nowait(('PUBLISH', topic, msg, qos, retain))

    def publish_json(self, obj=None, topic=None, qos=None, retain=False):
        """Pack the provided object into JSON and publish to topic."""
        try:
            self.publish(json.dumps(obj), topic, qos, retain)
        except Exception as e:
            LOG.error('Error publishing object %r: %s', obj, e)

    def __init__(self):
        """Constructor."""
        threading.Thread.__init__(self, daemon=True)
        self.__queue = queue.Queue()
        self.__cb = defcallback
        self.__subscriptions = {}
        self.__curov = None
        self.__deftopic = None
        self.__connected = False
        self.__connect_pending = False
        self.__host = '127.0.0.1'
        self.__port = 1883
        self.__qos = 0
        self.__doreconnect = False

        # check system config for overrides
        if metarace.sysconf.has_option('telegraph', 'host'):
            self.__host = metarace.sysconf.get('telegraph', 'host')
        if metarace.sysconf.has_option('telegraph', 'deftopic'):
            # note: this may be overidden by application
            self.__deftopic = metarace.sysconf.get('telegraph', 'deftopic')
        if metarace.sysconf.has_option('telegraph', 'qos'):
            self.__qos = strops.confopt_posint(
                metarace.sysconf.get('telegraph', 'qos'), 0)
            if self.__qos > 2:
                LOG.info('Invalid QOS %r set to %r', self.__qos, 2)
                self.__qos = 2

        # create mqtt client
        self.__client = mqtt.Client()
        if metarace.sysconf.has_option('telegraph', 'debug'):
            if strops.confopt_bool(metarace.sysconf.get('telegraph', 'debug')):
                LOG.debug('Enabling mqtt/paho debug')
                mqlog = logging.getLogger('metarace.telegraph.mqtt')
                mqlog.setLevel(logging.DEBUG)
                self.__client.enable_logger(mqlog)
        if metarace.sysconf.has_option('telegraph', 'usetls'):
            if strops.confopt_bool(metarace.sysconf.get('telegraph',
                                                        'usetls')):
                LOG.debug('Enabling TLS connection')
                self.__port = 8883
                self.__client.tls_set()
        username = None
        password = None
        if metarace.sysconf.has_option('telegraph', 'username'):
            username = metarace.sysconf.get('telegraph', 'username')
        if metarace.sysconf.has_option('telegraph', 'password'):
            password = metarace.sysconf.get('telegraph', 'password')
        if username and password:
            self.__client.username_pw_set(username, password)
        # override automatic port selection if provided
        if metarace.sysconf.has_option('telegraph', 'port'):
            np = strops.confopt_posint(metarace.sysconf.get('telegraph', 'port'))
            if np is not None:
                self.__port = np
                LOG.debug('Set port to %r', self.__port)
        self.__client.reconnect_delay_set(2, 16)
        self.__client.on_message = self.__on_message
        self.__client.on_connect = self.__on_connect
        self.__client.on_disconnect = self.__on_disconnect
        if self.__host:
            self.__doreconnect = True
        self.__running = False

    def __reconnect(self):
        if not self.__connect_pending:
            if self.__connected:
                LOG.debug('Disconnecting client')
                self.__client.disconnect()
                self.__client.loop_stop()
            if self.__host:
                LOG.debug('Connecting to %s:%d', self.__host, self.__port)
                self.__connect_pending = True
                self.__client.connect_async(self.__host, self.__port)
                self.__client.loop_start()

    # PAHO methods
    def __on_connect(self, client, userdata, flags, rc):
        LOG.debug('Connect %r: %r/%r', client._client_id, flags, rc)
        s = []
        for t in self.__subscriptions:
            nqos = self.__subscriptions[t]
            if nqos is None:
                nqos = self.__qos
            s.append((t, nqos))
        if len(s) > 0:
            LOG.debug('Subscribe: %r', s)
            self.__client.subscribe(s)
        self.__connect_pending = False
        self.__connected = True

    def __on_disconnect(self, client, userdata, rc):
        LOG.debug('Disconnect %r: %r', client._client_id, rc)
        self.__connected = False
        # Note: PAHO lib will attempt re-connection automatically

    def __on_message(self, client, userdata, message):
        #LOG.debug(u'Message from %r: %r', client._client_id, message)
        self.__cb(message.topic, message.payload.decode('utf-8'))

    def run(self):
        """Called via threading.Thread.start()."""
        self.__running = True
        if self.__host:
            LOG.debug('Starting')
        else:
            LOG.debug('Not connected')
        while self.__running:
            try:
                # Check connection status
                if self.__host and self.__doreconnect:
                    self.__doreconnect = False
                    if not self.__connect_pending:
                        self.__reconnect()
                # Process command queue
                while True:
                    m = self.__queue.get(timeout=QUEUE_TIMEOUT)
                    self.__queue.task_done()
                    if m[0] == 'PUBLISH':
                        ntopic = self.__deftopic
                        if m[1] is not None:  # topic is set
                            ntopic = m[1]
                        nqos = m[3]
                        if nqos is None:
                            nqos = self.__qos
                        if ntopic:
                            msg = None
                            if m[2] is not None:
                                msg = m[2].encode('utf-8')
                            self.__client.publish(ntopic, msg, nqos, m[4])
                        else:
                            #LOG.debug(u'No topic, msg ignored: %r', m[1])
                            pass
                    elif m[0] == 'SUBSCRIBE':
                        LOG.debug('Subscribe topic: %r q=%r', m[1], m[2])
                        nqos = m[2]
                        if nqos is None:
                            nqos = self.__qos
                        self.__client.subscribe(m[1], nqos)
                    elif m[0] == 'UNSUBSCRIBE':
                        LOG.debug('Un-subscribe topic: %r', m[1])
                        self.__client.unsubscribe(m[1])
                    elif m[0] == 'RECONNECT':
                        self.__connect_pending = False
                        self.__doreconnect = True
                    elif m[0] == 'EXIT':
                        LOG.debug('Request to close: %r', m[1])
                        self.__running = False
            except queue.Empty:
                pass
            except Exception as e:
                LOG.error('%s: %s', e.__class__.__name__, e)
                self.__connect_pending = False
                self.__doreconnect = False
        self.__client.disconnect()
        self.__client.loop_stop()
        LOG.info('Exiting')
