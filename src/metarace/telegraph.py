# SPDX-License-Identifier: MIT
"""Telegraph

 Telegraph is a thin wrapper over paho.mqtt.client, which provides
 a MQTT pub/sub interface, altered for use with metarace applications.

 Example:

	import metarace
	from metarace import telegraph
	metarace.init()
	
	def messagecb(topic, message):
	    obj = telegraph.from_json(message)
	    ...
	
	t = telegraph.telegraph()
	t.set_will_json({'example':[]}, 'thetopic')
	t.subscribe('thetopic')
	t.setcb(messagecb)
	t.start()
	...
	t.publish_json({'example':[1,2,3]}, 'thetopic')

 Message callback functions receive two named parameters 'topic' and
 'message' which are both unicode strings. The message callback is run in
 the telegraph thread context. Use the convenience function "from_json"
 to convert a message from json into a python object. See defcallback
 for an example.

 Configuration is via metarace system config (metarace.json), under
 section 'telegraph':

  key: (type) Description [default]
  --
  host : (string) MQTT broker, None to disable ['localhost']
  port: (int) MQTT port [1883/8883]
  username : (string) username [None]
  password : (string) password [None]
  usetls : (bool) if True, connect to server over TLS [False]
  persist : (bool) if true, open a persistent connection to broker [False]
  clientid : (string) provide an explicit client id [None]
  qos : (int) default QOS to use for subscribe and publish [0]
  debug : (bool) if True, enable logging in MQTT library [False]
  deftopic : (string) a default publish topic [None]


"""

import threading
import queue
import logging
import json
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from uuid import uuid4
import metarace

_QUEUE_TIMEOUT = 2

# module logger
_log = logging.getLogger('telegraph')
_log.setLevel(logging.DEBUG)

_CONFIG_SCHEMA = {
    'ttype': {
        'prompt': 'MQTT Broker Details',
        'control': 'section'
    },
    'host': {
        'prompt': 'Host:',
        'hint': 'Hostname or IP of MQTT broker',
        'default': 'localhost',
    },
    'port': {
        'prompt': 'Port:',
        'control': 'short',
        'hint': 'TCP port number of MQTT broker',
        'type': 'int',
    },
    'usetls': {
        'prompt': 'Security:',
        'subtext': 'Use TLS?',
        'type': 'bool',
        'control': 'check',
        'hint': 'Connect to MQTT broker using TLS',
        'default': False
    },
    'username': {
        'prompt': 'Username:',
        'hint': 'Username on MQTT broker if required'
    },
    'password': {
        'prompt': 'Password:',
        'hint': 'Password on MQTT broker if required'
    },
    'debug': {
        'prompt': 'Log:',
        'control': 'check',
        'type': 'bool',
        'subtext': 'Debug MQTT connection?',
        'hint': 'Log detailed information on connection to MQTT broken',
        'default': False,
    },
    'ssec': {
        'prompt': 'Session Options',
        'control': 'section',
    },
    'clientid': {
        'prompt': 'Client ID:',
        'hint': 'Specify client id for MQTT connection'
    },
    'persist': {
        'prompt': 'Session:',
        'subtext': 'Persistent?',
        'type': 'bool',
        'control': 'check',
        'hint': 'Request persistent session on broker',
        'default': True,
    },
    'qos': {
        'prompt': 'QoS:',
        'control': 'choice',
        'hint': 'Default message QOS',
        'type': 'int',
        'options': {
            '0': '0 - At most once',
            '1': '1 - At least once',
            '2': '2 - Exactly once'
        },
        'default': 0,
    },
    'deftopic': {
        'prompt': 'Default Topic:',
        'hint': 'Default topic for messages published without one',
    },
}


def from_json(payload=None):
    """Return message payload decoded from json, or None."""
    ret = None
    try:
        ret = json.loads(payload)
    except Exception as e:
        _log.warning('%s decoding JSON payload: %s', e.__class__.__name__, e)
    return ret


def defcallback(topic=None, message=None):
    """Default message receive callback function."""
    ob = from_json(message)
    if ob is not None:
        _log.debug('RCV %r: %r', topic, ob)
    else:
        _log.debug('RCV %r: %r', topic, message)


class telegraph(threading.Thread):
    """Metarace telegraph server thread."""

    def subscribe(self, topic=None, qos=None):
        """Add topic to the set of subscriptions with optional qos."""
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

    def unsubscribe_all(self):
        """Remove all topics from the set of subscriptions."""
        topics = self.__subscriptions
        self.__subscriptions = {}
        for topic in topics:
            if self.__connected:
                self.__queue.put_nowait(('UNSUBSCRIBE', topic))
        topics = None

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
        _log.debug('Default publish topic set to: %r', self.__deftopic)

    def set_will_json(self, obj=None, topic=None, qos=None, retain=False):
        """Pack the provided object into JSON and set as will."""
        try:
            self.set_will(json.dumps(obj), topic, qos, retain)
        except Exception as e:
            _log.error('Error setting will object %r: %s', obj, e)

    def set_will(self, message=None, topic=None, qos=None, retain=False):
        """Set or clear the last will with the broker."""
        if not self.__connect_pending and not self.__connected:
            if topic is not None:
                nqos = qos
                if nqos is None:
                    nqos = self.__qos
                payload = None
                if message is not None:
                    payload = message.encode('utf-8')
                self.__client.will_set(topic, payload, nqos, retain)
                _log.debug('Will set on topic %r', topic)
            else:
                self.__client.will_clear()
                _log.debug('Cleared will')
        else:
            _log.error('Unable to set will, already connected')

    def connected(self):
        """Return true if connected."""
        return self.__connected

    def unsent(self):
        """Return number of queued messages remaining unsent."""
        # _log.debug('Unsent messages: %r', self.__unsent)
        return len(self.__unsent)

    def reconnect(self):
        """Request re-connection to broker."""
        self.__queue.put_nowait(('RECONNECT', True))

    def exit(self, msg=None):
        """Request thread termination."""
        self.__running = False
        self.__queue.put_nowait(('EXIT', msg))

    def wait(self):
        """Suspend calling thread until command queue is processed."""
        self.__queue.join()

    def publish(self,
                message=None,
                topic=None,
                qos=None,
                retain=False,
                timeout=None):
        """Queue provided message for publishing to nominated topic.

        If timeout (float seconds > 0) is provided, telegraph
        will wait up to timeout seconds after publishing for
        completion before re-processing the command queue.

        For QoS == 0, timeout applies to message delivery
        For QoS == 1, timeout applies to PUBACK
        For QoS == 2, timeout applies to PUBCOMP

        This method returns immediately even if timeout set.
        """
        self.__queue.put_nowait(
            ('PUBLISH', topic, message, qos, retain, timeout))

    def publish_json(self,
                     obj=None,
                     topic=None,
                     qos=None,
                     retain=False,
                     cls=None,
                     indent=None,
                     timeout=None):
        """Pack the provided object into JSON and publish to topic."""
        try:
            self.publish(json.dumps(obj, cls=cls, indent=indent), topic, qos,
                         retain, timeout)
        except Exception as e:
            _log.error('Error publishing object %r: %s', obj, e)

    def __init__(self):
        """Constructor."""
        threading.Thread.__init__(self, daemon=True)
        self.__queue = queue.Queue()
        self.__cb = defcallback
        self.__subscriptions = {}
        self.__connected = False
        self.__connect_pending = False
        self.__cid = None
        self.__resub = True
        self.__doreconnect = False
        self.__unsent = set()
        self.__publishLock = threading.Lock()

        metarace.sysconf.add_section('telegraph', _CONFIG_SCHEMA)
        self.__host = metarace.sysconf.get_value('telegraph', 'host')
        self.__port = metarace.sysconf.get_value('telegraph', 'port')
        if self.__port is None:
            self.__port = 1883
        self.__deftopic = metarace.sysconf.get_value('telegraph', 'deftopic')
        self.__qos = metarace.sysconf.get_value('telegraph', 'qos')
        self.__persist = metarace.sysconf.get_value('telegraph', 'persist')
        self.__cid = metarace.sysconf.get_value('telegraph', 'clientid')

        # check values
        if self.__qos > 2:
            _log.info('Invalid QOS %r set to %r', self.__qos, 2)
            self.__qos = 2
        if not self.__cid:
            self.__cid = str(uuid4())
        _log.debug('Using QoS: %r', self.__qos)
        _log.debug('Using client id: %r', self.__cid)
        _log.debug('Persistent connection: %r', self.__persist)

        # create mqtt client
        self.__client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=self.__cid,
            clean_session=not self.__persist)

        if metarace.sysconf.get_value('telegraph', 'debug'):
            _log.debug('Enabling mqtt/paho debug')
            mqlog = logging.getLogger('telegraph.mqtt')
            mqlog.setLevel(logging.DEBUG)
            self.__client.enable_logger(mqlog)

        if metarace.sysconf.get_value('telegraph', 'usetls'):
            _log.debug('Enabling TLS connection')
            if not metarace.sysconf.has_value('telegraph', 'port'):
                # Update port for TLS if not exlicitly set
                self.__port = 8883
                _log.debug('Set port to %r', self.__port)
            self.__client.tls_set()
        username = metarace.sysconf.get_value('telegraph', 'username')
        password = metarace.sysconf.get_value('telegraph', 'password')
        if username and password:
            self.__client.username_pw_set(username, password)

        self.__client.reconnect_delay_set(2, 16)
        self.__client.on_message = self.__on_message
        self.__client.on_connect = self.__on_connect
        self.__client.on_disconnect = self.__on_disconnect
        self.__client.on_publish = self.__on_publish
        if self.__host:
            self.__doreconnect = True
        self.__running = False

    def __reconnect(self):
        if not self.__connect_pending:
            if self.__connected:
                _log.debug('Disconnecting client')
                self.__client.disconnect()
                self.__client.loop_stop()
            if self.__host:
                _log.debug('Connecting to %s:%d', self.__host, self.__port)
                self.__connect_pending = True
                self.__client.connect_async(self.__host, self.__port)
                self.__client.loop_start()

    # PAHO methods - Callback API Version=2
    def __on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            _log.debug('Connect %r: %r/%r', client._client_id, flags,
                       reason_code)
            if not self.__resub and self.__persist and flags.session_present:
                _log.debug('Resumed existing session for %r',
                           client._client_id)
            else:
                _log.debug('Assuming Clean session for %r', client._client_id)
                s = []
                for t in self.__subscriptions:
                    nqos = self.__subscriptions[t]
                    if nqos is None:
                        nqos = self.__qos
                    s.append((t, nqos))
                if len(s) > 0:
                    _log.debug('Subscribe topics: %r', s)
                    self.__client.subscribe(s)
                self.__resub = False
            self.__connected = True
        else:
            _log.info('Connect failed with error %r: %r', reason_code,
                      mqtt.connack_string(reason_code))
            self.__connected = False
        self.__connect_pending = False

    def __on_disconnect(self, client, userdata, flags, reason_code,
                        properties):
        _log.debug('Disconnect %r: %r', client._client_id, reason_code)
        self.__connected = False
        # Note: PAHO lib will attempt re-connection automatically

    def __on_message(self, client, userdata, message):
        #_log.debug('Message from %r: %r', client._client_id, message)
        self.__cb(topic=message.topic, message=message.payload.decode('utf-8'))

    def __on_publish(self, client, userdata, mid, reason_code, properties):
        with self.__publishLock:
            try:
                self.__unsent.remove(mid)
            except Exception as e:
                _log.warning('%s removing published MID=%d: %s',
                             e.__class__.__name__, mid, e)

    def run(self):
        """Called via threading.Thread.start()."""
        self.__running = True
        if self.__host:
            _log.debug('Starting')
        else:
            _log.debug('Not connected')
        while self.__running:
            try:
                # Check connection status
                if self.__host and self.__doreconnect:
                    self.__doreconnect = False
                    if not self.__connect_pending:
                        self.__reconnect()
                # Process command queue
                while self.__running:
                    m = self.__queue.get(timeout=_QUEUE_TIMEOUT)
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

                            with self.__publishLock:
                                mi = self.__client.publish(
                                    ntopic, msg, nqos, m[4])

                                # QoS == 0 when not connected are discarded
                                if nqos != 0 or mi.rc == 0:
                                    self.__unsent.add(mi.mid)

                            # Wait for publish if timeout provided
                            if m[5] is not None and m[5] > 0:
                                if mi.rc == 0:
                                    mi.wait_for_publish(m[5])
                                else:
                                    if nqos == 0:
                                        _log.warning(
                                            'Publish to %r dropped: %r,%r',
                                            ntopic, mi.rc, mi.mid)
                    elif m[0] == 'SUBSCRIBE':
                        _log.debug('Subscribe topic: %r q=%r', m[1], m[2])
                        nqos = m[2]
                        if nqos is None:
                            nqos = self.__qos
                        self.__client.subscribe(m[1], nqos)
                    elif m[0] == 'UNSUBSCRIBE':
                        _log.debug('Un-subscribe topic: %r', m[1])
                        self.__client.unsubscribe(m[1])
                    elif m[0] == 'RECONNECT':
                        self.__connect_pending = False
                        self.__doreconnect = True
                    elif m[0] == 'EXIT':
                        _log.debug('Request to close: %r', m[1])
                        self.__running = False
            except queue.Empty:
                pass
            except Exception as e:
                _log.error('%s: %s', e.__class__.__name__, e)
                self.__connect_pending = False
                self.__doreconnect = False
        if self.__connected:
            self.__client.disconnect()
            self.__client.loop_stop()
        _log.info('Exiting')
