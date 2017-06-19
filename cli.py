# -*- coding: utf-8 -*-
# !/usr/bin/env python3

"""
Command line interface

run as
`
cd f-interop-utils
python3 cli.py
`

"""

import six
import pika
import threading
import logging
import time
import json
from datetime import timedelta
import traceback
import uuid
from collections import OrderedDict
import datetime
import os
import signal
from messages import *
from examples_pcap_base64 import *

COMPONENT_ID = 'finterop_CLI'


class NullLogHandler(logging.Handler):
    def emit(self, record):
        pass


class AmqpSniffer(threading.Thread):
    def __init__(self, conn):
        threading.Thread.__init__(self)
        # queues & default exchange declaration
        self.message_count = 0

        self.connection = conn

        self.channel = connection.channel()

        services_queue_name = 'services_queue@%s' % COMPONENT_ID
        self.channel.queue_declare(queue=services_queue_name, auto_delete=True)

        self.channel.queue_bind(exchange=AMQP_EXCHANGE,
                                queue=services_queue_name,
                                routing_key='#')
        # Hello world message
        self.channel.basic_publish(
                body=json.dumps({'_type': 'cli.info', 'value': 'CLI is up!'}),
                routing_key='control.cli.info',
                exchange=AMQP_EXCHANGE,
                properties=pika.BasicProperties(
                        content_type='application/json',
                )
        )

        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(self.on_request, queue=services_queue_name)

    def stop(self):
        self.channel.stop_consuming()

    def on_request(self, ch, method, props, body):
        # obj hook so json.loads respects the order of the fields sent -just for visualization purposeses-
        req_body_dict = json.loads(body.decode('utf-8'), object_pairs_hook=OrderedDict)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        logging.info("Message sniffed: %s, body: %s" % (json.dumps(req_body_dict), str(body)))
        self.message_count += 1

        props_dict = {
            'content_type':     props.content_type,
            'content_encoding': props.content_encoding,
            'headers':          props.headers,
            'delivery_mode':    props.delivery_mode,
            'priority':         props.priority,
            'correlation_id':   props.correlation_id,
            'reply_to':         props.reply_to,
            'expiration':       props.expiration,
            'message_id':       props.message_id,
            'timestamp':        props.timestamp,
            'user_id':          props.user_id,
            'app_id':           props.app_id,
            'cluster_id':       props.cluster_id,
        }
        # let's get rid of values which are empty
        props_dict_only_non_empty_values = {k: v for k, v in props_dict.items() if v is not None}

        print('\n* * * * * * MESSAGE SNIFFED (%s) * * * * * * *' % self.message_count)
        print("TIME: %s" % datetime.datetime.time(datetime.datetime.now()))
        print(" - - - ")
        print("ROUTING_KEY: %s" % method.routing_key)
        print(" - - - ")
        print("PROPS: %s" % json.dumps(props_dict_only_non_empty_values))
        print(" - - - ")
        print('BODY %s' % json.dumps(req_body_dict))
        print(" - - - ")
        # print("ERRORS: %s" % )
        print('* * * * * * * * * * * * * * * * * * * * * \n')

        if props.content_type != "application/json":
            print('* * * * * * API VALIDATION WARNING * * * * * * * ')
            print("props.content_type : " + str(props.content_type))
            print("application/json was expected")
            print('* * * * * * * * * * * * * * * * * * * * *  \n')

        if '_type' not in req_body_dict.keys():
            print('* * * * * * API VALIDATION WARNING * * * * * * * ')
            print("no < _type > field found")
            print('* * * * * * * * * * * * * * * * * * * * *  \n')

    def run(self):
        print("Starting thread listening on the event bus")
        self.channel.start_consuming()
        print('Bye byes!')


class Cli(threading.Thread):
    """
    \brief Thread which handles CLI commands entered by the user.
    """

    CMD_LEVEL_USER = "user"
    CMD_LEVEL_SYSTEM = "system"
    CMD_LEVEL_ALL = [CMD_LEVEL_USER,
                     CMD_LEVEL_SYSTEM]

    def __init__(self, appName, quit_cb=None):
        # initialize parent class
        threading.Thread.__init__(self)

        # slot params
        self.appName = appName
        self.quit_cb = quit_cb

        # local variables
        self.commandLock = threading.Lock()
        self.commands = []
        self.goOn = True

        # logging
        self.log = logging.getLogger(COMPONENT_ID)
        self.log.setLevel(logging.DEBUG)
        self.log.addHandler(NullLogHandler())

        # give this thread a name
        self.name = COMPONENT_ID

        # register system commands (user commands registered by child object)
        self._registerCommand_internal(
                self.CMD_LEVEL_SYSTEM,
                'help',
                'h',
                'print this menu',
                [],
                self._handleHelp)
        self._registerCommand_internal(
                self.CMD_LEVEL_SYSTEM,
                'info',
                'i',
                'information about this application',
                [],
                self._handleInfo)
        self._registerCommand_internal(
                self.CMD_LEVEL_SYSTEM,
                'quit',
                'q',
                'quit this application',
                [],
                self._handleQuit)
        self._registerCommand_internal(
                self.CMD_LEVEL_SYSTEM,
                'uptime',
                'ut',
                'how long this application has been running',
                [],
                self._handleUptime)

        self.startTime = 0.0

    def stop(self):
        cli.goOn = False

    def run(self):
        print('{0} - (c) F-interop\n'.format(self.appName))

        self.startTime = time.time()

        try:
            while self.goOn:

                # CLI stops here each time a user needs to call a command
                params = input('> ')

                # log
                self.log.debug('Following command entered:' + params)

                params = params.split()
                if len(params) < 1:
                    continue

                if len(params) == 2 and params[1] == '?':
                    if not self._printUsageFromName(params[0]):
                        if not self._printUsageFromAlias(params[0]):
                            print(' unknown command or alias \'' + params[0] + '\'')
                    continue

                # find this command
                found = False
                self.commandLock.acquire()
                for command in self.commands:
                    if command['name'] == params[0] or command['alias'] == params[0]:
                        found = True
                        cmdParams = command['params']
                        cmdCallback = command['callback']
                        cmdDontCheckParamsLenth = command['dontCheckParamsLength']
                        break
                self.commandLock.release()

                # call its callback or print error message
                if found:
                    if cmdDontCheckParamsLenth or len(params[1:]) == len(cmdParams):
                        cmdCallback(params[1:])
                    else:
                        if not self._printUsageFromName(params[0]):
                            self._printUsageFromAlias(params[0])
                else:
                    print(' unknown command or alias \'' + params[0] + '\'')

        except Exception as err:
            output = []
            output += ['===== crash in thread {0} ====='.format(self.name)]
            output += ['\nerror:\n']
            output += [str(err)]
            output += ['\ncall stack:\n']
            output += [traceback.format_exc()]
            output = '\n'.join(output)
            print(output)
            self.log.critical(output)
            raise

    # ======================== public ==========================================

    def registerCommand(self, name, alias, description, params, callback, dontCheckParamsLength=False):

        self._registerCommand_internal(self.CMD_LEVEL_USER,
                                       name,
                                       alias,
                                       description,
                                       params,
                                       callback,
                                       dontCheckParamsLength)

    # ======================== private =========================================

    def _registerCommand_internal(self, cmdLevel, name, alias, description, params, callback,
                                  dontCheckParamsLength=False):

        assert cmdLevel in self.CMD_LEVEL_ALL
        assert isinstance(name, str)
        assert isinstance(alias, str)
        assert isinstance(description, str)
        assert isinstance(params, list)
        for p in params:
            assert isinstance(p, str)
        assert callable(callback)
        assert dontCheckParamsLength in [True, False]

        if self._doesCommandExist(name):
            raise SystemError("command {0} already exists".format(name))

        self.commandLock.acquire()
        self.commands.append({
            'cmdLevel':              cmdLevel,
            'name':                  name,
            'alias':                 alias,
            'description':           description,
            'params':                params,
            'callback':              callback,
            'dontCheckParamsLength': dontCheckParamsLength,
        })
        self.commandLock.release()

    def _printUsageFromName(self, commandname):
        return self._printUsage(commandname, 'name')

    def _printUsageFromAlias(self, commandalias):
        return self._printUsage(commandalias, 'alias')

    def _printUsage(self, name, paramType):

        usageString = None

        self.commandLock.acquire()
        for command in self.commands:
            if command[paramType] == name:
                usageString = []
                usageString += ['usage: {0}'.format(name)]
                usageString += [" <{0}>".format(p) for p in command['params']]
                usageString = ''.join(usageString)
        self.commandLock.release()

        if usageString:
            print(usageString)
            return True
        else:
            return False

    def _doesCommandExist(self, cmdName):

        returnVal = False

        self.commandLock.acquire()
        for cmd in self.commands:
            if cmd['name'] == cmdName:
                returnVal = True
        self.commandLock.release()

        return returnVal

    # === command handlers (system commands only, a child object creates more)

    def _handleHelp(self, params):
        output = []
        output += ['Available commands:']

        self.commandLock.acquire()
        for command in self.commands:
            output += [' - {0} ({1}): {2}'.format(command['name'],
                                                  command['alias'],
                                                  command['description'])]
        self.commandLock.release()

        print('\n'.join(output))

    def _handleInfo(self, params):
        output = []
        output += ['General status of the application']
        output += ['']
        output += ['current time: {0}'.format(time.ctime())]
        output += ['']
        output += ['{0} threads running:'.format(threading.activeCount())]
        threadNames = [t.getName() for t in threading.enumerate()]
        threadNames.sort()
        for t in threadNames:
            output += ['- {0}'.format(t)]
        output += ['']
        output += ['This is thread {0}.'.format(threading.currentThread().getName())]

        print('\n'.join(output))

    def _handleQuit(self, params):

        # call the quit callback
        if self.quit_cb:
            self.quit_cb()

        # kill this thread
        self.goOn = False

    def _handleUptime(self, params):

        upTime = timedelta(seconds=time.time() - self.startTime)

        print('Running since {0} ({1} ago)'.format(
                time.strftime("%m/%d/%Y %H:%M:%S", time.localtime(self.startTime)),
                upTime))


        # ======================== helpers =========================================


###############################################################################

if __name__ == '__main__':

    MESSAGE_UI_SELECTOR = 1

    logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.WARNING)

    try:
        AMQP_EXCHANGE = str(os.environ['AMQP_EXCHANGE'])
    except KeyError as e:
        AMQP_EXCHANGE = "default"

    try:
        AMQP_URL = str(os.environ['AMQP_URL'])
        p = six.moves.urllib_parse.urlparse(AMQP_URL)
        AMQP_USER = p.username
        AMQP_SERVER = p.hostname
        logging.info(
            "Env variables imported for AMQP connection, User: {0} @ Server: {1} ".format(AMQP_USER, AMQP_SERVER))
    except KeyError as e:
        print('Cannot retrieve environment variables for AMQP connection. Loading defaults..')
        # load default values
        AMQP_URL = "amqp://{0}:{1}@{2}/{3}".format("guest", "guest", "localhost", "/")

    connection = pika.BlockingConnection(pika.URLParameters(AMQP_URL))
    channel = connection.channel()
    logging.info("AMQP connection established")

    # in case its not declared
    connection.channel().exchange_declare(exchange=AMQP_EXCHANGE,
                                          type='topic',
                                          durable=True,
                                          )


    def quitCallback():
        print("quitting!")


    def echoCallback(params):
        print("echo {0}!".format(params))


    def forgeAmqpMessages(params):

        def publish_message(message):

            properties = pika.BasicProperties(**message.get_properties())

            channel.basic_publish(
                    exchange=AMQP_EXCHANGE,
                    routing_key=message.routing_key,
                    properties=properties,
                    body=message.to_json(),
            )

        # for a typical user input, for a user (coap client) vs automated-iut ( coap server) session type:
        # f 1
        # f 2
        # f 4.a
        # f 4.c
        # =-> there you should get an amqp message saying verdict inconclusive ( due to no traffic on the data plane)

        # re-write each message forged as a unittest? (if not this won't escalate very well)

        events_testcoordination = OrderedDict({
            '1':   MsgTestSuiteStart(),
            '2':   MsgTestCaseStart(),
            '3':   MsgTestCaseRestart(),
            '4.a': MsgStimuliExecuted(),
            '4.b': MsgCheckResponse(),
            '4.c': MsgVerifyResponse(),
            '4.d': MsgVerifyResponse(verify_response=False, description='User indicates that IUT didnt behave '
                                                                        'as expected '),
            # TT should be able to know when the test case was finished based on stimuli, check and verify signals
            '5':   MsgTestCaseFinish(),
            '6':   MsgTestCaseSkip(testcase_id=None),
            '6.a': MsgTestCaseSkip(testcase_id='TD_COAP_CORE_01_v01'),
            '6.b': MsgTestCaseSkip(testcase_id='TD_COAP_CORE_02_v01'),
            '6.c': MsgTestCaseSkip(testcase_id='TD_COAP_CORE_03_v01'),
            '6.d': MsgTestCaseSkip(testcase_id='TD_COAP_CORE_04_v01'),
            '6.e': MsgTestCaseSkip(testcase_id='TD_COAP_CORE_05_v01'),
            '7':   MsgTestCaseSelect(testcase_id='TD_COAP_CORE_02_v01'),
            '8':   MsgTestSuiteAbort(),

        })
        events_orchestrator = OrderedDict({
            'term': MsgTestingToolTerminate(),
            'config':  MsgInteropSessionConfiguration(),
            'config2': MsgInteropSessionConfiguration(
                    tests=[
                        {
                            'testcase_ref': 'TD_COAP_CORE_01_v01',
                            'settings':     {}
                        },
                    ]

            ),
            'config3': MsgInteropSessionConfiguration(
                    tests=[
                        {
                            'testcase_ref': 'someNoneExistantTestCase',
                            'settings':     {}
                        },
                    ]

            ),
        })

        service_testcoordination = OrderedDict({
            'stat0':   MsgTestSuiteGetStatus(),
            'tclist':  MsgTestSuiteGetTestCases(),
        })

        service_sniffing = OrderedDict({
            # start sniffing w/ certain parametrization
            'snif0': MsgSniffingStart(
                    capture_id='TD_COAP_CORE_01',
                    filter_if='tun0',
                    filter_proto='udp port 5683'
            ),
            'snif1': MsgSniffingStop(),
            # get a particular capture file
            'snif2': MsgSniffingGetCapture(capture_id='TD_COAP_CORE_01'),
            # gets last capture
            'snif3': MsgSniffingGetCaptureLast()
        })

        service_tat = OrderedDict({
            'tat0': MsgInteropTestCaseAnalyze(),
            'tat1': MsgInteropTestCaseAnalyze(
                    testcase_id="TD_COAP_CORE_01",
                    testcase_ref="http://f-interop.paris.inria.fr/tests/TD_COAP_CORE_01_v01",
                    file_enc="pcap_base64",
                    filename="TD_COAP_CORE_01.pcap",
                    value=PCAP_empty_base64,
            ),
            'tat2': MsgInteropTestCaseAnalyze(
                    testcase_id="TD_COAP_CORE_01",
                    testcase_ref="http://f-interop.paris.inria.fr/tests/TD_COAP_CORE_01_v01",
                    file_enc="pcap_base64",
                    filename="TD_COAP_CORE_01.pcap",
                    value=PCAP_TC_COAP_01_base64,
            )
        })

        service_dissection = OrderedDict({
            # dissection of empty pcap file
            'dis1': MsgDissectionDissectCapture(),
            # dissection of pcap only coap frames
            'dis2': MsgDissectionDissectCapture(
                    file_enc="pcap_base64",
                    filename="TD_COAP_CORE_01.pcap",
                    protocol_selection='coap',
                    value=PCAP_TC_COAP_01_base64,
            ),
            # complete dissection of pcap
            'dis3': MsgDissectionDissectCapture(
                    file_enc="pcap_base64",
                    filename="TD_COAP_CORE_01.pcap",
                    value=PCAP_TC_COAP_01_base64,
            ),
            # complete dissection of pcap with extra TCP traffic
            'dis4': MsgDissectionDissectCapture(
                    file_enc="pcap_base64",
                    filename="TD_COAP_CORE_01.pcap",
                    value=PCAP_TC_COAP_01_mingled_with_tcp_traffic_base64,
            ),
            # same as dis4 but filtering coap messages
            'dis5': MsgDissectionDissectCapture(
                    file_enc="pcap_base64",
                    filename="TD_COAP_CORE_01.pcap",
                    protocol_selection='coap',
                    value=PCAP_TC_COAP_01_mingled_with_tcp_traffic_base64,
            ),
            # pcap sniffed using AMQP based packet sniffer
            'dis6': MsgDissectionDissectCapture(
                    file_enc="pcap_base64",
                    filename="TD_COAP_CORE_01.pcap",
                    value=PCAP_COAP_GET_OVER_TUN_INTERFACE_base64,
            ),
        })

        testing_tool_emulation = OrderedDict({
            # testing tool is ready to start session
            'tt1': MsgTestingToolReady(),

            # testcase coordination
            'tt10': MsgStepExecute(step_id="TD_COAP_CORE_01_v01_step_01"),
            'tt11': MsgStepExecute(step_id="TD_COAP_CORE_01_v01_step_02"),
            'tt12': MsgStepExecute(step_id="TD_COAP_CORE_01_v01_step_03"),
            'tt13': MsgStepExecute(step_id="TD_COAP_CORE_01_v01_step_04"),
        })

        event_type = params[0]
        print(event_type)

        # dict of all messages
        messages = {
            **events_orchestrator,
            **events_testcoordination,
            **service_testcoordination,
            **service_sniffing,
            **service_tat,
            **service_dissection,
            **testing_tool_emulation,
        }

        # send message
        if event_type in messages.keys():
            publish_message(messages[event_type])
            logging.info("Publishing in the bus: %s" % event_type)
        else:
            msgs_str = ''
            for k in sorted(messages):
                msgs_str += k + ': %s, %s \n' % (messages[k].__class__.__name__, messages[k].__doc__)

            logging.warning('Message type not known. '
                            'The valid ones are: \n %s'
                            % msgs_str
                            )


    cli = Cli("Standalone Sample App", quitCallback)
    cli.registerCommand('echo',
                        'e',
                        'echoes the first param',
                        ['string to echo'],
                        echoCallback)

    cli.registerCommand('forge',
                        'f',
                        'generates forged messages for testing the platform',
                        ['message type or number'],
                        forgeAmqpMessages)

    cli.start()

    # start amqp listener thread
    amqp_listener = AmqpSniffer(connection)
    amqp_listener.start()

    # TODO catch sigint and stop threads gracefully
    cli.join()
    amqp_listener.join()
    connection.close()
