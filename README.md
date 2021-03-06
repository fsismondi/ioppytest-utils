Contact
-------

Federico Sismondi
Contact address: federicosismondi(AT)gmail(DOT)com

Utils
-----

This repo provides some libs and snippets in the form of python modules
used by several ioppytest components and F-Interop components.

Installing CLI, lib and other components
------------------------------------------

`pip install ioppytest-utils`


# Package `event_bus_utils`
---------------------------

(coming soon)

# Package `messages`
--------------------

This packages provides to your code a new abstraction level on
how to interact with the messages in the bus.

Essentially it allows you to:

## 1. manipulate data using the python syntax

```
>>> from messages import *
>>> m = MsgTestCaseSkip(testcase_id = 'some_testcase_id')
>>> m
MsgTestCaseSkip(_api_version = 1.2.15, description = Skip testcase, node = someNode, testcase_id = some_testcase_id, )
>>> m.routing_key
'testsuite.testcase.skip'
>>> m.message_id # doctest: +SKIP
'802012eb-24e3-45c4-9dcc-dc293c584f63'
>>> m.testcase_id
'some_testcase_id'

# also we can modify some of the fields (rewrite the default ones)
>>> m = MsgTestCaseSkip(testcase_id = 'TD_COAP_CORE_03')
>>> m
MsgTestCaseSkip(_api_version = 1.2.15, description = Skip testcase, node = someNode, testcase_id = TD_COAP_CORE_03, )
>>> m.testcase_id
'TD_COAP_CORE_03'

# and even export the message in json format (for example for sending the message though the amqp event bus)
>>> m.to_json()
'{"_api_version": "1.2.15", "description": "Skip testcase", "node": "someNode", "testcase_id": "TD_COAP_CORE_03"}'

# We can use the Message class to import json into Message objects:
>>> m=MsgTestSuiteStart()
>>> m.routing_key
'testsuite.start'
>>> m.to_json()
'{"_api_version": "1.2.15", "description": "Test suite START command"}'
>>> json_message = m.to_json()
>>> obj=Message.load(json_message,'testsuite.start', None )
>>> obj
MsgTestSuiteStart(_api_version = 1.2.15, description = Test suite START command, )
>>> type(obj) # doctest: +SKIP
<class 'messages.MsgTestSuiteStart'>

# We can use the library for generating error responses:
# the request:
>>> m = MsgSniffingStart()
>>>

# the error reply (note that we pass the message of the request to build the reply):
>>> err = MsgErrorReply(m)
>>> err
MsgErrorReply(_api_version = 1.2.15, error_code = None, error_message = None, ok = False, )

# properties of the message are auto-generated:
>>> m.reply_to
'sniffing.start.reply'
>>> err.routing_key
'sniffing.start.reply'
>>> m.correlation_id # doctest: +SKIP
'360b0f67-4455-43e3-a00f-eca91f2e84da'
>>> err.correlation_id # doctest: +SKIP
'360b0f67-4455-43e3-a00f-eca91f2e84da'

# we can get all the AMQP properties also as a dict:
>>> err.get_properties() # doctest: +SKIP
'{'timestamp': 1515172549, 'correlation_id': '16257581-06be-4088-a1f6-5672cc73d8f2', 'message_id': '1ec12c2b-33c7-44ad-97b8-5099c4d52e81', 'content_type': 'application/json'}'

```

## 2. importing/exporting message events from/to json

```
# We can use the Message class to build Message objects from json + rkey:
>>> m=MsgSniffingGetCapture()
>>> m.routing_key
'sniffing.getcapture.request'
>>> m.to_json()
'{"_api_version": "1.2.15", "capture_id": "TD_COAP_CORE_01"}'
>>> json_message = m.to_json()
>>> json_message
'{"_api_version": "1.2.15", "capture_id": "TD_COAP_CORE_01"}'
>>> obj=Message.load(json_message,'testsuite.start', None )
>>> type(obj) # doctest
<class 'messages.MsgTestSuiteStart'>
```


## 3. importing messages from event bus using pika's API

Build a message from a pika's returned values on consume:

```
>>> m = Message.load_from_pika(method, props, body)
>>> m.routing_key
'sniffing.getcapture.request'
>>> m.to_json()
'{"_api_version": "1.2.15", "capture_id": "TD_COAP_CORE_01"}'
```


# Package cli tool: ioppytest-cli
---------------------------------

(used from terminal with entrypoint `ioppytest-cli`)

 ```
(my_venv) ➜  ioppytest-cli
Usage: ioppytest-cli [OPTIONS] COMMAND [ARGS]...

Options:
  --help  Show this message and exit.

Commands:
  action                   Execute interop test action
  chat                     Send chat message, useful for user-to-user...
  check_connection         (REPL only) Check if AMQP connection is...
  clear                    Clear screen
  connect                  Connect to an AMQP session and start...
  download_network_traces  Downloads all networks traces generated...
  enter_debug_context      (REPL only) Provides user with some extra...
  exit                     Exits REPL
  get_session_parameters   Print session state and parameters
  get_session_status       Retrieves status information from testing...
  gui_display_message      Sends message to GUI
  gui_request_file_upload  Request user to upload a file, saves it in...
  ignore                   (REPL only) Do not notify any more on message...
  repl                     Interactive shell, allows user to interact...
```



## 1. REPL mode: `ioppytest-cli repl`

this can be used for example for UI actions:

```
> action ts_start
[User input] ts_start
Do you want START test suite? [y/N]: y
Sending message..

[Event bus message] [<class 'messages.messages.MsgTestSuiteStart'>]

------------  ------------------------
_api_version  1.2.15
description   Test suite START command
------------  ------------------------
```

but also for testing internal services provided by the tools
(`> enter_debug_context` needed):

```
> _send_MsgTestSuiteGetTestCases
[User input] trying to send message: MsgTestSuiteGetTestCases(_api_version = 1.2.15, )
Sending message..

[Event bus message] [<class 'messages.messages.MsgTestSuiteGetTestCases'>]
------------  -----
_api_version  1.2.15
------------  -----

[log][test_coordinator|amqp_connector] RECEIVED request: <class 'ioppytest.utils.messages.messages.MsgTestSuiteGetTestCases'>
[log][test_coordinator|amqp_connector] HANDLING request: <class 'ioppytest.utils.messages.messages.MsgTestSuiteGetTestCases'>
[log][test_coordinator|amqp_connector] PUBLISHING to routing_key: testsuite.testcases.list.reply, msg: MsgReply(_api_version = 1.2.15, ok = True, tc_list = [OrderedDict([('te

[Event bus message] [<class 'messages.messages.MsgTestSuiteGetTestCasesReply'>]

------------  --------------------------------------------------------------------------------------------------------------------
 _api_version    1.2.15
 ok              True
 tc_list         {'testcase_id': 'TD_COAP_CORE_01', 'testcase_ref': 'http://doc.f-interop.eu/tests/TD_COAP_CORE_01', 'state': None}
                  {'testcase_id': 'TD_COAP_CORE_02', 'testcase_ref': 'http://doc.f-interop.eu/tests/TD_COAP_CORE_02', 'state': None}
                  {'testcase_id': 'TD_COAP_CORE_03', 'testcase_ref': 'http://doc.f-interop.eu/tests/TD_COAP_CORE_03', 'state': None}
                  {'testcase_id': 'TD_COAP_CORE_04', 'testcase_ref': 'http://doc.f-interop.eu/tests/TD_COAP_CORE_04', 'state': None}
                  {'testcase_id': 'TD_COAP_CORE_05', 'testcase_ref': 'http://doc.f-interop.eu/tests/TD_COAP_CORE_05', 'state': None}
                  {'testcase_id': 'TD_COAP_CORE_06', 'testcase_ref': 'http://doc.f-interop.eu/tests/TD_COAP_CORE_06', 'state': None}
                  {'testcase_id': 'TD_COAP_CORE_07', 'testcase_ref': 'http://doc.f-interop.eu/tests/TD_COAP_CORE_07', 'state': None}
                  {'testcase_id': 'TD_COAP_CORE_08', 'testcase_ref': 'http://doc.f-interop.eu/tests/TD_COAP_CORE_08', 'state': None}
                  {'testcase_id': 'TD_COAP_CORE_09', 'testcase_ref': 'http://doc.f-interop.eu/tests/TD_COAP_CORE_09', 'state': None}
                  {'testcase_id': 'TD_COAP_CORE_10', 'testcase_ref': 'http://doc.f-interop.eu/tests/TD_COAP_CORE_09', 'state': None}
                  {'testcase_id': 'TD_COAP_CORE_11', 'testcase_ref': 'http://doc.f-interop.eu/tests/TD_COAP_CORE_11', 'state': None}
                  {'testcase_id': 'TD_COAP_CORE_12', 'testcase_ref': 'http://doc.f-interop.eu/tests/TD_COAP_CORE_12', 'state': None}
                  {'testcase_id': 'TD_COAP_CORE_13', 'testcase_ref': 'http://doc.f-interop.eu/tests/TD_COAP_CORE_13', 'state': None}
                  {'testcase_id': 'TD_COAP_CORE_14', 'testcase_ref': 'http://doc.f-interop.eu/tests/TD_COAP_CORE_14', 'state': None}
                  {'testcase_id': 'TD_COAP_CORE_15', 'testcase_ref': 'http://doc.f-interop.eu/tests/TD_COAP_CORE_15', 'state': None}
                  {'testcase_id': 'TD_COAP_CORE_16', 'testcase_ref': 'http://doc.f-interop.eu/tests/TD_COAP_CORE_16', 'state': None}
                  {'testcase_id': 'TD_COAP_CORE_17', 'testcase_ref': 'http://doc.f-interop.eu/tests/TD_COAP_CORE_17', 'state': None}
                  {'testcase_id': 'TD_COAP_CORE_18', 'testcase_ref': 'http://doc.f-interop.eu/tests/TD_COAP_CORE_18', 'state': None}
                  {'testcase_id': 'TD_COAP_CORE_19', 'testcase_ref': 'http://doc.f-interop.eu/tests/TD_COAP_CORE_19', 'state': None}
                  {'testcase_id': 'TD_COAP_CORE_20', 'testcase_ref': 'http://doc.f-interop.eu/tests/TD_COAP_CORE_20', 'state': None}
                  {'testcase_id': 'TD_COAP_CORE_21', 'testcase_ref': 'http://doc.f-interop.eu/tests/TD_COAP_CORE_21', 'state': None}
                  {'testcase_id': 'TD_COAP_CORE_22', 'testcase_ref': 'http://doc.f-interop.eu/tests/TD_COAP_CORE_22', 'state': None}
                  {'testcase_id': 'TD_COAP_CORE_23', 'testcase_ref': 'http://doc.f-interop.eu/tests/TD_COAP_CORE_23', 'state': None}
                  {'testcase_id': 'TD_COAP_CORE_31', 'testcase_ref': 'http://doc.f-interop.eu/tests/TD_COAP_CORE_31', 'state': None}
------------  --------------------------------------------------------------------------------------------------------------------
[log][test_coordinator|amqp_connector] Finished with REQUEST: <class 'ioppytest.utils.messages.messages.MsgTestSuiteGetTestCases'>
```

other example:

```
> _send_MsgAgentTunStart
[User input] trying to send message: MsgAgentTunStart(_api_version = 1.2.15, ipv4_host = None, ipv4_netmask = None, ipv4_network = None, ipv6_host = :3, ipv6_no_forwarding = False, ipv6_prefix = bbbb, name = agent_TT, re_route_packets_host = None, re_route_packets_if = None, re_route_packets_prefix = None, )
Sending message..

[Event bus message] [<class 'messages.messages.MsgAgentTunStart'>]

-----------------------  --------
_api_version             1.2.15
ipv4_host
ipv4_netmask
ipv4_network
ipv6_host                :3
ipv6_no_forwarding       False
ipv6_prefix              bbbb
name                     agent_TT
re_route_packets_host
re_route_packets_if
re_route_packets_prefix
-----------------------  --------
>
```


press TAB for more info:

```
>
   _configure_6lowpan_tt                         Send example configuration message for...
   _configure_coap_tt                            Send example configuration message for CoAP...
   _configure_comi_tt                            Send example configuration message for CoMI...
   _configure_perf_tt                            Send example configuration message for perf...
   _execute_stimuli_step                         Stimuli to be executed by IUT1, targeting...
   _execute_verify_step                          Request IUT to verify a step, normally they...
   _get_session_configuration_from_ui            Get session config from UI
   _send_MsgAgentSerialStart                     Send dummy MsgAgentSerialStart message to bus.
   _send_MsgAgentSerialStarted                   Send dummy MsgAgentSerialStarted message to bus.
   _send_MsgAgentTunStart                        Send dummy MsgAgentTunStart message to bus.
   _send_MsgAgentTunStarted                      Send dummy MsgAgentTunStarted message to bus.
   _send_MsgConfigurationExecute                 Send dummy MsgConfigurationExecute message to bus.
   _send_MsgConfigurationExecuted                Send dummy MsgConfigurationExecuted message to bus.
   _send_MsgDeleteResultReply                    Send dummy MsgDeleteResultReply message to bus.
   _send_MsgDeleteResultRequest                  Send dummy MsgDeleteResultRequest message to bus.
   _send_MsgDissectionAutoDissect                Send dummy MsgDissectionAutoDissect message to bus.
   (...)
```


## sniffing the event bus with: `ioppytest-cli connect`

connects to event bus (amqp vhost), subscribes and consumes any type of
message in the bus, this component tries to import the json messages
and the message properties into Message python objects
(using `messages` package)

```
(my_venv) ➜  ioppytest-cli connect
[Test Assistant] Connecting to amqp://paul:iamthewalrus@f-interop.rennes.inria.fr/session05?heartbeat=600&blocked_connection_timeout=300&retry_delay=1&socket_timeout=1&connection_attempts=3

[Event bus message] [<class 'messages.messages.MsgTestingToolComponentReady'>]

------------  -------------------------------
_api_version  1.2.15
component     amqp_listener_b49d7db4
description   amqp_listener_b49d7db4 is READY
------------  -------------------------------
```


## sniffing w/ lazy listener: `ioppytest-cli connect --ll`

The same as `ioppytest-cli connect` but no import into `messages`
objects. It just echos back the json and some amqp properties like
routing key, message id, correlation id, content type, etc..

No conversion from json to python objects, no data validation

```
(my_venv) ➜  ioppytest_cli connect -ll

[Test Assistant] Connecting to amqp://paul:iamthewalrus@f-interop.rennes.inria.fr/session05?heartbeat=600&blocked_connection_timeout=300&retry_delay=1&socket_timeout=1&connection_attempts=3

------------------------------------------------------------------------------------------------------------------------
routing_key : testsuite.testcases.list.request
------------------------------------------------------------------------------------------------------------------------
{
    "_api_version": "1.2.15",
    "content_type": "application/json",
    "correlation_id": "00393e9e-d255-4309-8a9b-18ec608602f3",
    "message_id": "00393e9e-d255-4309-8a9b-18ec608602f3",
    "reply_to": "testsuite.testcases.list.reply",
    "timestamp": 1527671157
}
------------------------------------------------------------------------------------------------------------------------
routing_key : log.info.test_coordinator|amqp_connector
------------------------------------------------------------------------------------------------------------------------
{
    "_api_version": "1.0.8",
    "component": "test_coordinator|amqp_connector",
    "content_type": "application/json",
    "message": "RECEIVED request: <class 'ioppytest.utils.messages.messages.MsgTestSuiteGetTestCases'>"
}
------------------------------------------------------------------------------------------------------------------------
routing_key : log.info.test_coordinator|amqp_connector
------------------------------------------------------------------------------------------------------------------------
{
    "_api_version": "1.0.8",
    "component": "test_coordinator|amqp_connector",
    "content_type": "application/json",
    "message": "HANDLING request: <class 'ioppytest.utils.messages.messages.MsgTestSuiteGetTestCases'>"
}
------------------------------------------------------------------------------------------------------------------------
routing_key : log.info.test_coordinator|amqp_connector
------------------------------------------------------------------------------------------------------------------------
{
    "_api_version": "1.0.8",
    "component": "test_coordinator|amqp_connector",
    "content_type": "application/json",
    "message": "PUBLISHING to routing_key: testsuite.testcases.list.reply, msg: MsgReply(_api_version = 1.2.15, ok = True, tc_list = [OrderedDict([('te"
}
------------------------------------------------------------------------------------------------------------------------
routing_key : testsuite.testcases.list.reply
------------------------------------------------------------------------------------------------------------------------
{
    "_api_version": "1.2.15",
    "content_type": "application/json",
    "correlation_id": "00393e9e-d255-4309-8a9b-18ec608602f3",
    "message_id": "619283ab-c6a1-4b91-8a65-8697b665e3a1",
    "ok": true,
    "tc_list": [
        {
            "state": null,
            "testcase_id": "TD_COAP_CORE_01",
            "testcase_ref": "http://doc.f-interop.eu/tests/TD_COAP_CORE_01"
        },
        {
            "state": null,
            "testcase_id": "TD_COAP_CORE_02",
            "testcase_ref": "http://doc.f-interop.eu/tests/TD_COAP_CORE_02"
        },
        {
            "state": null,
            "testcase_id": "TD_COAP_CORE_03",
            "testcase_ref": "http://doc.f-interop.eu/tests/TD_COAP_CORE_03"
        },
        {
            "state": null,
            "testcase_id": "TD_COAP_CORE_04",
            "testcase_ref": "http://doc.f-interop.eu/tests/TD_COAP_CORE_04"
        },
        {
            "state": null,
            "testcase_id": "TD_COAP_CORE_05",
            "testcase_ref": "http://doc.f-interop.eu/tests/TD_COAP_CORE_05"
        },
        {
            "state": null,
            "testcase_id": "TD_COAP_CORE_06",
            "testcase_ref": "http://doc.f-interop.eu/tests/TD_COAP_CORE_06"
        },
        {
            "state": null,
            "testcase_id": "TD_COAP_CORE_07",
            "testcase_ref": "http://doc.f-interop.eu/tests/TD_COAP_CORE_07"
        },
        {
            "state": null,
            "testcase_id": "TD_COAP_CORE_08",
            "testcase_ref": "http://doc.f-interop.eu/tests/TD_COAP_CORE_08"
        },
        {
            "state": null,
            "testcase_id": "TD_COAP_CORE_09",
            "testcase_ref": "http://doc.f-interop.eu/tests/TD_COAP_CORE_09"
        },
        {
            "state": null,
            "testcase_id": "TD_COAP_CORE_10",
            "testcase_ref": "http://doc.f-interop.eu/tests/TD_COAP_CORE_09"
        },
        {
            "state": null,
            "testcase_id": "TD_COAP_CORE_11",
            "testcase_ref": "http://doc.f-interop.eu/tests/TD_COAP_CORE_11"
        },
        {
            "state": null,
            "testcase_id": "TD_COAP_CORE_12",
            "testcase_ref": "http://doc.f-interop.eu/tests/TD_COAP_CORE_12"
        },
        {
            "state": null,
            "testcase_id": "TD_COAP_CORE_13",
            "testcase_ref": "http://doc.f-interop.eu/tests/TD_COAP_CORE_13"
        },
        {
            "state": null,
            "testcase_id": "TD_COAP_CORE_14",
            "testcase_ref": "http://doc.f-interop.eu/tests/TD_COAP_CORE_14"
        },
        {
            "state": null,
            "testcase_id": "TD_COAP_CORE_15",
            "testcase_ref": "http://doc.f-interop.eu/tests/TD_COAP_CORE_15"
        },
        {
            "state": null,
            "testcase_id": "TD_COAP_CORE_16",
            "testcase_ref": "http://doc.f-interop.eu/tests/TD_COAP_CORE_16"
        },
        {
            "state": null,
            "testcase_id": "TD_COAP_CORE_17",
            "testcase_ref": "http://doc.f-interop.eu/tests/TD_COAP_CORE_17"
        },
        {
            "state": null,
            "testcase_id": "TD_COAP_CORE_18",
            "testcase_ref": "http://doc.f-interop.eu/tests/TD_COAP_CORE_18"
        },
        {
            "state": null,
            "testcase_id": "TD_COAP_CORE_19",
            "testcase_ref": "http://doc.f-interop.eu/tests/TD_COAP_CORE_19"
        },
        {
            "state": null,
            "testcase_id": "TD_COAP_CORE_20",
            "testcase_ref": "http://doc.f-interop.eu/tests/TD_COAP_CORE_20"
        },
        {
            "state": null,
            "testcase_id": "TD_COAP_CORE_21",
            "testcase_ref": "http://doc.f-interop.eu/tests/TD_COAP_CORE_21"
        },
        {
            "state": null,
            "testcase_id": "TD_COAP_CORE_22",
            "testcase_ref": "http://doc.f-interop.eu/tests/TD_COAP_CORE_22"
        },
        {
            "state": null,
            "testcase_id": "TD_COAP_CORE_23",
            "testcase_ref": "http://doc.f-interop.eu/tests/TD_COAP_CORE_23"
        },
        {
            "state": null,
            "testcase_id": "TD_COAP_CORE_31",
            "testcase_ref": "http://doc.f-interop.eu/tests/TD_COAP_CORE_31"
        }
    ],
    "timestamp": 1527671158
}
------------------------------------------------------------------------------------------------------------------------
routing_key : log.info.test_coordinator|amqp_connector
------------------------------------------------------------------------------------------------------------------------
{
    "_api_version": "1.0.8",
    "component": "test_coordinator|amqp_connector",
    "content_type": "application/json",
    "message": "Finished with REQUEST: <class 'ioppytest.utils.messages.messages.MsgTestSuiteGetTestCases'>"
}
```


For contributing or directly using the source code:
---------------------------------------------------

Libraries in this repo are all self contained what makes it easy to
import.
There are several approaches for doing so:

1. Simply copy & paste the code into your python modules.
Any modification on the libraries must be done into
[utils repo](https://gitlab.f-interop.eu/f-interop-contributors/utils)
Please increase the VERSION number when doing so.

2. Submodule it:
From the top dir of your git repo run:

```
git submodule add https://gitlab.f-interop.eu/f-interop-contributors/utils.git <someSubDir>/utils
```

commit & push

```
git commit -m 'added f-interop's utils git repo as submodule'
```

remember when cloning a project with submodules to use --recursive flag

```
git clone --recursive ...
```

or else, right after cloning you can:

```
git submodule update --init --recursive
```

whenever you find that your utils libraries are not the latests versions
you can 'bring' those last changes from the main utils repo to your project
with:

```
git submodule update --remote --merge
```

after bringing the last changes you can update your project with the last changes by doing:

```
git add <someSubDir>/utils
git commit -m 'updated submodule reference to last commit'
git push
```


TODO:
=====

using ioppytest console file:

```
python3 -i console.py
```

```
>>> AMQP_URL
'amqp://paul:iamthewalrus@f-interop.rennes.inria.fr/session05?heartbeat=0&blocked_connection_timeout=2&retry_delay=1&socket_timeout=5&connection_attempts=3'

Document use of ioppytest_cli interactively with python terminal:

 >>> ioppytest_cli.session_profile.update({'amqp_url': AMQP_URL}))
  File "<stdin>", line 1
    ioppytest_cli.session_profile.update({'amqp_url': AMQP_URL}))
                                                                ^
SyntaxError: invalid syntax
>>> ioppytest_cli.session_profile.update({'amqp_url': AMQP_URL})
>>> ioppytest_cli.session_profile.update({'amqp_url': AMQP_URL})
KeyboardInterrupt
>>> ioppytest_cli.session_profile
OrderedDict([('user_name', 'Walter White'), ('protocol', 'coap'), ('node', 'both'), ('amqp_url', 'amqp://paul:iamthewalrus@f-interop.rennes.inria.fr/session05?heartbeat=0&blocked_connection_timeout=2&retry_delay=1&socket_timeout=5&connection_attempts=3'), ('amqp_exchange', 'amq.topic')])
>>> a=ioppytest_cli._set_up_connection()
[Test Assistant] Connecting to amqp://paul:iamthewalrus@f-interop.rennes.inria.fr/session05?heartbeat=0&blocked_connection_timeout=2&retry_delay=1&socket_timeout=5&connection_attempts=3

[Event bus message] [<class 'messages.MsgTestingToolComponentReady'>]

>>> ------------  -------------------------------
_api_version  1.2.15
component     amqp_listener_47607736
description   amqp_listener_47607736 is READY
------------  -------------------------------

>>> ioppytest_cli.download_network_traces()

[Event bus message] [<class 'messages.MsgTestSuiteGetTestCases'>]

------------  -----
_api_version  1.2.15
------------  -----
[Error] Is testing tool up?
[Error] Response timeout! rkey: testsuite.testcases.list.request , request type: <class 'messages.MsgTestSuiteGetTestCases'>
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
  File "/Library/Frameworks/Python.framework/Versions/3.6/lib/python3.6/site-packages/click/core.py", line 722, in __call__
    return self.main(*args, **kwargs)
  File "/Library/Frameworks/Python.framework/Versions/3.6/lib/python3.6/site-packages/click/core.py", line 697, in main
    rv = self.invoke(ctx)
  File "/Library/Frameworks/Python.framework/Versions/3.6/lib/python3.6/site-packages/click/core.py", line 895, in invoke
    return ctx.invoke(self.callback, **ctx.params)
  File "/Library/Frameworks/Python.framework/Versions/3.6/lib/python3.6/site-packages/click/core.py", line 535, in invoke
    return callback(*args, **kwargs)
  File "/Library/Frameworks/Python.framework/Versions/3.6/lib/python3.6/site-packages/ioppytest_cli/ioppytest_cli.py", line 164, in download_network_traces
    ls = state['tc_list'].copy()
KeyError: 'tc_list'
>>>

```

if ioppytest testing tool is running on a certain AMQP vhost,
and test case 20 and 21 have been executed.
Then using ioppytest console provides nice features like ask the
testing tool for all the pcap files and create a local copy of those:

```
python3 -i console.py
```

```
Project dir: /Users/fsismondi/dev/ioppytest
ENVIRONMENT VAR not found, using defaulte: INTERACTIVE_SESSION=True
Env vars for AMQP connection succesfully imported
URL: amqp://paul:iamthewalrus@f-interop.rennes.inria.fr/session05
AMQP_EXCHANGE: amq.topic
Welcome to ttproto console.
- run as: python3 -i console.py
- Use [tab] to complete
- Use help(object) to print help messages.
- Quit using ctrl+d
>>> # use AMQP event bus instance where a testing tool is listening to:
...
>>>
KeyboardInterrupt
>>> AMQP_URL='amqp://5JFKMADK:M49Y8NQZ@mq.f-interop.eu:443/750bcce8-c1e3-4d9a-ba39-efd12d9da7a4'
>>> ioppytest_cli
<module 'ioppytest_cli.ioppytest_cli' from '/Library/Frameworks/Python.framework/Versions/3.6/lib/python3.6/site-packages/ioppytest_cli/ioppytest_cli.py'>

>>> ioppytest_cli.session_profile.update({'amqp_url': AMQP_URL})
>>> ioppytest_cli.download_network_traces()

No connection established yet, setting up one..

[Test Assistant] Connecting to amqp://5JFKMADK:M49Y8NQZ@mq.f-interop.eu:443/750bcce8-c1e3-4d9a-ba39-efd12d9da7a4
testcase_id      testcase_ref                                   objective                                                                                                             state
---------------  ---------------------------------------------  --------------------------------------------------------------------------------------------------------------------  -----------
TD_COAP_CORE_01  http://doc.f-interop.eu/tests/TD_COAP_CORE_01  Perform GET transaction(CON mode)                                                                                     skipped
TD_COAP_CORE_02  http://doc.f-interop.eu/tests/TD_COAP_CORE_02  Perform DELETE transaction (CON mode)                                                                                 skipped
TD_COAP_CORE_03  http://doc.f-interop.eu/tests/TD_COAP_CORE_03  Perform PUT transaction (CON mode)                                                                                    skipped
TD_COAP_CORE_04  http://doc.f-interop.eu/tests/TD_COAP_CORE_04  Perform POST transaction (CON mode)                                                                                   skipped
TD_COAP_CORE_05  http://doc.f-interop.eu/tests/TD_COAP_CORE_05  Perform GET transaction (NON mode)                                                                                    skipped
TD_COAP_CORE_06  http://doc.f-interop.eu/tests/TD_COAP_CORE_06  Perform DELETE transaction (NON mode)                                                                                 skipped
TD_COAP_CORE_07  http://doc.f-interop.eu/tests/TD_COAP_CORE_07  Perform PUT transaction (NON mode)                                                                                    skipped
TD_COAP_CORE_08  http://doc.f-interop.eu/tests/TD_COAP_CORE_08  Perform POST transaction (NON mode)                                                                                   skipped
TD_COAP_CORE_09  http://doc.f-interop.eu/tests/TD_COAP_CORE_09  Perform GET transaction with separate response(CON mode, no piggyback)                                                skipped
TD_COAP_CORE_10  http://doc.f-interop.eu/tests/TD_COAP_CORE_10  Perform GET transaction containing non-empty Token (CON mode)                                                         skipped
TD_COAP_CORE_11  http://doc.f-interop.eu/tests/TD_COAP_CORE_11  Perform GET transaction containing non-empty Token with a separate response (CON mode)                                skipped
TD_COAP_CORE_12  http://doc.f-interop.eu/tests/TD_COAP_CORE_12  Perform GET transaction using empty Token (CON mode)                                                                  skipped
TD_COAP_CORE_13  http://doc.f-interop.eu/tests/TD_COAP_CORE_13  Perform GET transaction containing several URI-Path options (CON mode)                                                skipped
TD_COAP_CORE_14  http://doc.f-interop.eu/tests/TD_COAP_CORE_14  Perform GET transaction containing several URI-Query options (CON mode)                                               skipped
TD_COAP_CORE_15  http://doc.f-interop.eu/tests/TD_COAP_CORE_15  Perform GET transaction (CON mode, piggybacked response) in a lossy context                                           skipped
TD_COAP_CORE_16  http://doc.f-interop.eu/tests/TD_COAP_CORE_16  Perform GET transaction (CON mode, delayed response) in a lossy context                                               skipped
TD_COAP_CORE_17  http://doc.f-interop.eu/tests/TD_COAP_CORE_17  Perform GET transaction with a separate response(NON mode)                                                            skipped
TD_COAP_CORE_18  http://doc.f-interop.eu/tests/TD_COAP_CORE_18  Perform POST transaction with responses containing several Location-Path option(CON mode)                             skipped
TD_COAP_CORE_19  http://doc.f-interop.eu/tests/TD_COAP_CORE_19  Perform POST transaction with responses containing several Location-Query option(CON mode)                            skipped
TD_COAP_CORE_20  http://doc.f-interop.eu/tests/TD_COAP_CORE_20  Perform GET transaction containing the Accept option (CON mode)                                                       finished
TD_COAP_CORE_21  http://doc.f-interop.eu/tests/TD_COAP_CORE_21  Perform GET transaction containing the Etag option (CON mode)                                                         finished
TD_COAP_CORE_22  http://doc.f-interop.eu/tests/TD_COAP_CORE_22  Perform GET transaction with responses containing the ETag option requests containing the If-Match option (CON mode)  configuring
TD_COAP_CORE_23  http://doc.f-interop.eu/tests/TD_COAP_CORE_23  Perform PUT transaction containing the If-None-Match option (CON mode)                                                None
TD_COAP_CORE_31  http://doc.f-interop.eu/tests/TD_COAP_CORE_31  Perform CoAP Ping (CON mode)                                                                                          skipped

[User input] downloaded network trace TD_COAP_CORE_20.pcap , into dir: tmp
[User input] downloaded network trace TD_COAP_CORE_21.pcap , into dir: tmp



```


```
ls tmp/*.pcap
myrepl-history
TD_COAP_CORE_20.pcap
TD_COAP_CORE_21.pcap
```

