import os
import sys
import pika
import base64
import logging
import threading
import traceback
import click
from click_repl import register_repl, ExitReplException

# for using it as library and as a __main__
try:
    from messages import *
    from tabulate import tabulate
except:
    from .messages import *
    from .tabulate import tabulate

logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.WARNING)

COMPONENT_ID = 'cli'

# click colors:: black (might gray) , red, green, yellow (might be an orange), blue, magenta, cyan, white (might gray)
COLOR_DEFAULT = 'white'
COLOR_SESSION_LOG = 'white'
COLOR_COORDINATION_MESSAGE = 'cyan'
COLOR_SESSION_ASSISTANCE = 'cyan'
COLOR_CHAT_MESSAGE = 'green'
COLOR_CHAT_MESSAGE_ECHO = 'green'
COLOR_ERROR_MESSAGE = 'red'
COLOR_TEST_SESSION_HELPER_MESSAGE = 'yellow'

# DIR used for network dumps and other type of tmp files
TEMP_DIR = 'tmp'

DEFAULT_TOPIC_SUBSCRIPTIONS = [
    # 'control.testcoordination',
    # 'control.dissection',
    # 'control.session',
    '#'
]

MESSAGE_TYPES_NOT_ECHOED = [
    MsgPacketInjectRaw,
]

CONNECTION_SETUP_RETRIES = 3

session_profile = OrderedDict(
    {
        'user_name': "Walter White",
        'protocol': "coap",
        'node': "both",
        'amqp_url': "amqp://{0}:{1}@{2}/{3}".format("guest", "guest", "localhost", "/"),
        'amqp_exchange': "amq.topic",
    }
)

state = {
    'testcase_id': None,
    'step_id': None,
    'last_message': None,
    'suggested_cmd': None,
    'connection': None,
    'channel': None,
}
profile_choices = {
    'protocol': ['coap', '6lowpan'],
    'node': ['coap_client', 'coap_server', 'both']
}

# e.g. MsgTestingToolConfigured is normally followed by a test suite start (ts_start)
UI_suggested_actions = {
    MsgTestingToolConfigured: 'ts_start',
    MsgTestCaseReady: 'tc_start',
    MsgStepStimuliExecute: 'stimuli',
    MsgStepVerifyExecute: 'verify',
}


def _init_action_suggested():
    state['suggested_cmd'] = 'ts_start'


class AmqpListener(threading.Thread):
    COMPONENT_ID = 'amqp_listener_%s' % uuid.uuid1()
    DEFAULT_EXCHAGE = 'amq.topic'

    def __init__(self, amqp_url, amqp_exchange, topics, callback):

        threading.Thread.__init__(self)

        if callback is None:
            self.message_dipatcher = print
        else:
            self.message_dipatcher = callback

        try:
            self.connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
            self.channel = self.connection.channel()
        except pika.exceptions.ProbableAccessDeniedError:
            self.message_dipatcher('Probable access denied error. Is provided AMQP_URL correct?')
            self.exit()

        if amqp_exchange:
            self.exchange = amqp_exchange
        else:
            self.exchange = self.DEFAULT_EXCHAGE

        # queues & default exchange declaration
        self.services_queue_name = 'services_queue@%s' % self.COMPONENT_ID
        self.channel.queue_declare(queue=self.services_queue_name,
                                   auto_delete=True,
                                   arguments={'x-max-length': 200})

        if topics:  # subscribe only to passed list
            for t in topics:
                self.channel.queue_bind(exchange=self.exchange,
                                        queue=self.services_queue_name,
                                        routing_key=t)

        else:  # subscribe to all events
            self.channel.queue_bind(exchange=self.exchange,
                                    queue=self.services_queue_name,
                                    routing_key='#')
        # Hello world message
        m = MsgTestingToolComponentReady(
            component=self.COMPONENT_ID,
            description="%s is READY" % self.COMPONENT_ID

        )

        self.channel.basic_publish(
            body=m.to_json(),
            routing_key=m.routing_key,
            exchange=self.exchange,
            properties=pika.BasicProperties(
                content_type='application/json',
            )
        )

        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(self.on_request, queue=self.services_queue_name)

    def stop(self):
        self.channel.queue_delete(self.services_queue_name)
        self.channel.stop_consuming()
        self.connection.close()

    def on_request(self, ch, method, props, body):

        props_dict = {
            'content_type': props.content_type,
            'delivery_mode': props.delivery_mode,
            'correlation_id': props.correlation_id,
            'reply_to': props.reply_to,
            'message_id': props.message_id,
            'timestamp': props.timestamp,
            'user_id': props.user_id,
            'app_id': props.app_id,
        }

        m = None
        try:
            m = Message.from_json(body)
            m.update_properties(**props_dict)
            m.routing_key = method.routing_key
            self.message_dipatcher(m)

        except NonCompliantMessageFormatError as e:
            self.message_dipatcher('%s got a non compliant message error %s' % (self.__class__.__name__, e))

        except Exception as e:
            pass
            # self.message_dipatcher('Error : %s' % str(e))
            # self.message_dipatcher(str(body))

        finally:
            ch.basic_ack(delivery_tag=method.delivery_tag)

    def run(self):
        self.message_dipatcher("Starting thread listening on the event bus..")
        for i in range(1, 4):
            try:
                self.channel.start_consuming()
            except pika.exceptions.ConnectionClosed as err:
                self.message_dipatcher(err)
                self.message_dipatcher('Unexpected connection closed, retrying %s/%s' % (i, 4))

        self.message_dipatcher('Bye byes!')


def amqp_request(channel, request_message, component_id):
    """
    NOTE: channel must be a pika channel
    """
    amqp_exchange = session_profile['amqp_exchange']

    # check first that sender didnt forget about reply to and corr id
    assert request_message.reply_to
    assert request_message.correlation_id

    if amqp_exchange is None:
        amqp_exchange = 'amq.topic'

    response = None

    reply_queue_name = 'amqp_rpc_%s@%s' % (str(uuid.uuid4())[:8], component_id)

    try:

        result = channel.queue_declare(queue=reply_queue_name, auto_delete=True)

        callback_queue = result.method.queue

        # bind and listen to reply_to topic
        channel.queue_bind(
            exchange=amqp_exchange,
            queue=callback_queue,
            routing_key=request_message.reply_to
        )

        channel.basic_publish(
            exchange=amqp_exchange,
            routing_key=request_message.routing_key,
            properties=pika.BasicProperties(**request_message.get_properties()),
            body=request_message.to_json(),
        )

        time.sleep(0.2)
        retries_left = 5

        while retries_left > 0:
            time.sleep(0.5)
            method, props, body = channel.basic_get(reply_queue_name)
            if method:
                channel.basic_ack(method.delivery_tag)
                if hasattr(props, 'correlation_id') and props.correlation_id == request_message.correlation_id:
                    break
            retries_left -= 1

        if retries_left > 0:

            body_dict = json.loads(body.decode('utf-8'), object_pairs_hook=OrderedDict)
            response = MsgReply(request_message, **body_dict)

        else:
            raise Exception(
                "Response timeout! rkey: %s , request type: %s" % (
                    request_message.routing_key,
                    request_message._type
                )
            )

    finally:
        # clean up
        channel.queue_delete(reply_queue_name)

    return response


def publish_message(message):
    if not _connection_ok():
        _echo_dispatcher('No connection established yet')
        return

    _echo_dispatcher('Sending message..')

    for i in range(1, 4):
        try:
            state['channel'].basic_publish(
                exchange=session_profile['amqp_exchange'],
                routing_key=message.routing_key,
                properties=pika.BasicProperties(**message.get_properties()),
                body=message.to_json(),
            )
            break

        except pika.exceptions.ConnectionClosed as err:
            _echo_error(err)
            _echo_error('Unexpected connection closed, retrying %s/%s' % (i, 4))
            _set_up_connection()


@click.group()
def cli():
    pass


@cli.command()
def connect():
    """
    Connect to an AMQP session and start consuming messages
    """
    _set_up_connection()


@cli.command()
def exit():
    """
    Exit test CLI

    """
    _exit()


@cli.command()
def download_network_traces():
    """
    Downloads all networks traces generated during the session
    """
    global state

    _handle_get_testcase_list()
    ls = state['tc_list'].copy()

    try:
        channel = state['connection'].channel()
    except Exception as e:
        _echo_error(e)

    for tc_item in ls:
        try:
            tc_id = tc_item['testcase_id']
            msg = MsgSniffingGetCapture(capture_id=tc_id)
            response = amqp_request(channel, msg, COMPONENT_ID)

            if response.ok:
                save_pcap_from_base64(response.filename, response.value, TEMP_DIR)
                _echo_input("downloaded network trace %s , into dir: %s" % (response.filename, TEMP_DIR))
            else:
                raise Exception(response.error_message)

        except Exception as e:
            _echo_error('Error trying to download network traces for testcase : %s' % tc_id)
            _echo_error(e)


@cli.command()
def clear():
    """
    Clear screen
    """

    click.clear()


def _handle_testcase_select():
    #  requires testing tool to implement GetTestCases feature see MsgTestSuiteGetTestCases
    _handle_get_testcase_list()
    ls = state['tc_list'].copy()

    i = 1
    for tc_item in ls:
        _echo_dispatcher("%s -> %s" % (i, tc_item['testcase_id']))
        i += 1

    resp = click.prompt('Select number of test case to execute from list', type=int)

    try:
        _echo_input("entered %s, corresponding to %s" % (resp, ls[resp - 1]['testcase_id']))
    except Exception as e:
        _echo_error("wrong input \n %s" % e)
        return

    msg = MsgTestCaseSelect(
        testcase_id=ls[resp - 1]['testcase_id']
    )

    publish_message(msg)


def _handle_get_testcase_list():
    #  requires testing tool to implement GetTestCases feature, see MsgTestSuiteGetTestCases
    if _connection_ok():

        temp_channel = state['connection'].channel()
        request_message = MsgTestSuiteGetTestCases()

        try:
            testcases_list_reponse = amqp_request(temp_channel, request_message, COMPONENT_ID)
        except Exception as e:
            _echo_error('Is testing tool up?')
            _echo_error(e)
            return

        try:
            state['tc_list'] = testcases_list_reponse.tc_list
        except Exception as e:
            _echo_error(e)
            return

        _echo_list_of_dicts_as_table(state['tc_list'])
    else:
        _echo_error('No connection established')


def _handle_action_testsuite_start():
    if click.confirm('Do you want START test suite?'):
        msg = MsgTestSuiteStart()
        publish_message(msg)


def _handle_action_testcase_start():
    if click.confirm('Do you want START test case?'):
        msg = MsgTestCaseStart()
        publish_message(msg)


def _handle_action_testsuite_abort():
    if click.confirm('Do you want ABORT test suite?'):
        msg = MsgTestSuiteAbort()
        publish_message(msg)


def _handle_action_testcase_skip():
    if click.confirm('Do you want SKIP current test case?'):
        msg = MsgTestCaseSkip()
        publish_message(msg)


def _handle_action_testcase_restart():
    if click.confirm('Do you want RESTART current test case?'):
        msg = MsgTestCaseRestart()
        publish_message(msg)


def _handle_action_stimuli():
    if isinstance(state['last_message'], MsgStepStimuliExecute):
        _echo_session_helper(list_to_str(state['last_message'].description))

    resp = click.confirm('Did you execute last STIMULI step (if any received)?')

    if resp:
        msg = MsgStepStimuliExecuted(
            node=session_profile['node'],
            node_execution_mode="user_assisted"
        )
        publish_message(msg)

    else:
        _echo_error('Please execute all pending STIMULI steps')


def _handle_action_verify():
    if isinstance(state['last_message'], MsgStepVerifyExecute):
        _echo_session_helper(list_to_str(state['last_message'].description))

    resp = click.prompt("Last verify step was <ok> or not <nok>", type=click.Choice(['ok', 'nok']))

    msg = MsgStepVerifyExecuted(
        response_type="bool",
        verify_response=True if resp == 'ok' else False,
        node=session_profile['node'],
        node_execution_mode="user_assisted"
    )

    publish_message(msg)


message_handles_options = {'ts_start': _handle_action_testsuite_start,
                           'ts_abort': _handle_action_testsuite_abort,
                           'tc_start': _handle_action_testcase_start,
                           'tc_restart': _handle_action_testcase_restart,
                           'tc_skip': _handle_action_testcase_skip,
                           'tc_list': _handle_get_testcase_list,
                           'tc_select': _handle_testcase_select,
                           'verify': _handle_action_verify,
                           'stimuli': _handle_action_stimuli,
                           'suggested': None,
                           }


@cli.command()
@click.argument('api_call', type=click.Choice(message_handles_options.keys()))
def action(api_call):
    """
    Execute interop test action
    """

    _echo_input(api_call)

    if not _connection_ok():
        _echo_dispatcher('No connection established yet')
        return

    if api_call == 'suggested':
        if state['suggested_cmd']:
            _echo_dispatcher("Executing : %s" % state['suggested_cmd'])
            message_handles_options[state['suggested_cmd']]()
            state['suggested_cmd'] = None
            return
        else:
            _echo_error('No suggested message yet.')
            return

    elif api_call in message_handles_options:
        func = message_handles_options[api_call]
        func()

    else:
        _echo_dispatcher('Command <action %s> not accepted' % api_call)


@cli.command()
@click.argument('message_type', type=click.Choice(['dissections']))
def ignore(message_type):
    """
    Do not notify any more on message type
    """
    message_types = {
        'dissections': [MsgDissectionAutoDissect],
        'packets': [MsgPacketSniffedRaw, MsgPacketInjectRaw]
    }

    if message_type in message_types:
        for item in message_types[message_type]:
            _add_to_ignore_message_list(item)
            _echo_dispatcher('Ignore message category %s: (%s)' % (message_type, str(item)))


@cli.command()
def enter_debug_context():
    """
    Provides user with some extra debugging commands

    """
    global message_handles_options
    debug_actions = {
        'send_skip_tc_coap_core_11': send_skip_tescase_coap_core_11,
        'snif1': snif1,
        'snif2': snif2,
        'snif3': snif3,
    }
    message_handles_options.update(debug_actions)

    _echo_session_helper("Entering debugger context, added the following actions: %s" % debug_actions)


@cli.command()
@click.argument('message', nargs=-1)
def chat(message):
    """
    Send chat message, usefull for user-to-user test sessions
    """

    if not _connection_ok():
        _echo_dispatcher('No connection established yet')
        return

    m = ''

    for word in message:
        m += " %s" % word

    c = MsgSessionChat(description=m,
                       user_name=session_profile['user_name'],
                       iut_node=session_profile['node'])
    publish_message(c)


@cli.command()
def check_connection():
    """
    Check if AMQP connection is active
    """
    conn_ok = _connection_ok()
    _echo_dispatcher('connection is %s' % 'OK' if conn_ok else 'not OK')
    return conn_ok


@cli.command()
def get_session_status():
    """
    Retrieves status information from testing tool
    """

    #  requires testing tool to implement GetStatus feature, see MsgTestSuiteGetStatus
    if _connection_ok():
        temp_channel = state['connection'].channel()
        request_message = MsgTestSuiteGetStatus()

        try:
            status_resp = amqp_request(temp_channel, request_message, COMPONENT_ID)
        except Exception as e:
            _echo_error('Is testing tool up?')
            _echo_error(e)
            return

        resp = status_resp.to_dict()
        tc_states = resp['tc_list']
        del resp['tc_list']

        # print general states
        _echo_dict_as_table(resp)

        list = []
        list.append(('testcase id', 'testcase ref', 'testcase status'))
        for tc in tc_states:
            if tc:
                val1, val2, val3, _, _, _ = tc.values()
                list.append((val1, val2, val3))
        # print tc states
        _echo_list_as_table(list, first_row_is_header=True)

    else:
        _echo_error('No connection established')


@cli.command()
def get_session_parameters():
    """
    Print session state and parameters
    """

    _echo_context()


def _connection_ok():
    conn_ok = False
    try:
        conn_ok = state['connection'] is not None and state['connection'].is_open
    except AttributeError as ae:
        pass
    except TypeError as ae:
        pass

    return conn_ok


def _echo_context():
    table = []
    for key, val in {**session_profile, **state}.items():
        table.append((key, list_to_str(val)))
    _echo_list_as_table(table)


def _set_up_connection():
    global state

    # conn for repl publisher
    try:
        retries_left = CONNECTION_SETUP_RETRIES
        while retries_left > 0:
            try:
                state['connection'] = pika.BlockingConnection(pika.URLParameters(session_profile['amqp_url']))
                state['channel'] = state['connection'].channel()
                break
            except pika.exceptions.ConnectionClosed:
                retries_left -= 1
                _echo_session_helper("Couldnt establish connection, retrying .. %s/%s "%(CONNECTION_SETUP_RETRIES-retries_left,CONNECTION_SETUP_RETRIES))

    except pika.exceptions.ProbableAccessDeniedError:
        _echo_error('Probable access denied error. Is provided AMQP_URL correct?')
        state['connection'] = None
        state['channel'] = None
        return

    # note we have a separate conn for amqp listener (each pika threads needs a different connection)
    if 'amqp_listener_thread' in state and state['amqp_listener_thread'] is not None:
        _echo_log_message('stopping amqp listener thread')
        th = state['amqp_listener_thread']
        th.stop()
        th.join(2)
        if th.isAlive():
            _echo_log_message('amqp listener thread doesnt want to stop, lets terminate it..')
            th.terminate()

    amqp_listener_thread = AmqpListener(session_profile['amqp_url'],
                                        session_profile['amqp_exchange'],
                                        DEFAULT_TOPIC_SUBSCRIPTIONS,
                                        _message_handler)
    amqp_listener_thread.start()
    state['amqp_listener_thread'] = amqp_listener_thread


def _pre_configuration():
    global session_profile

    for key, _ in session_profile.items():
        if key in profile_choices.keys():
            selection_type = click.Choice(profile_choices[key])
        else:
            selection_type = str

        value = click.prompt('Please type %s ' % key,
                             type=selection_type,
                             default=session_profile[key])
        _echo_input(value)
        session_profile.update({key: value})


def _add_to_ignore_message_list(msg_type):
    global MESSAGE_TYPES_NOT_ECHOED
    if msg_type.__name__ in globals():
        MESSAGE_TYPES_NOT_ECHOED.append(msg_type)


def _message_handler(msg):
    global state
    """
    This method first prints message into user interface then evaluates if there's any associated action to message.
    :param msg:
    :return:
    """

    if type(msg) in MESSAGE_TYPES_NOT_ECHOED:
        pass  # do not echo
    else:
        # echo
        _echo_dispatcher(msg)

    # process message
    if isinstance(msg, Message):
        state['last_message'] = msg
        if type(msg) in UI_suggested_actions:
            state['suggested_cmd'] = UI_suggested_actions[type(msg)]
            _echo_session_helper(
                'Suggested following action to execute: <action %s> or or <action suggested>' % state['suggested_cmd'])

    elif isinstance(msg, MsgTestCaseVerdict):
        #  Save verdict
        json_file = os.path.join(
            TEMP_DIR,
            msg.testcase_id + '_verdict.json'
        )
        with open(json_file, 'w') as f:
            f.write(msg.to_json())

    elif isinstance(msg, (MsgStepStimuliExecute, MsgStepVerifyExecute)):
        state['step_id'] = msg.step_id

    elif isinstance(msg, MsgTestCaseReady):
        state['testcase_id'] = msg.testcase_id


def _exit():
    _quit_callback()

    if 'amqp_listener_thread' in state and state['amqp_listener_thread'] is not None:
        state['amqp_listener_thread'].stop()
        state['amqp_listener_thread'].join()

    if 'connection' in state and state['connection'] is not None:
        state['connection'].close()

    raise ExitReplException()


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# UI echo functions

def _echo_welcome_message():
    m = """
    Welcome to F-Interop platform!
    The Test assistant will help you go through the interoperability session (messages in cyan).

    """
    _echo_session_helper(m)

    m = """
    *********************************************************************************
    *   If you experience any problems, or you have any suggestions or feedback     *
    *   don't hesitate to drop me an email at:  federico.sismondi@inria.fr          *
    *********************************************************************************
    """
    _echo_session_helper(m)


def _echo_dispatcher(msg):
    """
    :param msg: String, dict or Message object
    :return: echoes using click API
    """

    if type(msg) is str:
        click.echo(click.style(msg, fg=COLOR_DEFAULT))
    elif isinstance(msg, MsgSessionLog):
        _echo_log_message(msg)
    elif isinstance(msg, MsgPacketSniffedRaw):
        _echo_data_message(msg)
    elif isinstance(msg, MsgSessionChat):
        _echo_chat_message(msg)
    elif isinstance(msg, Message):  # default echo for objects of Message type
        _echo_backend_message(msg)
    elif isinstance(msg, dict):
        click.echo(click.style(repr(msg), fg=COLOR_DEFAULT))
    else:
        click.echo(click.style(msg, fg=COLOR_DEFAULT))


def _quit_callback():
    click.echo(click.style('Quitting!', fg=COLOR_ERROR_MESSAGE))


def _echo_backend_message(msg):
    assert isinstance(msg, Message)

    try:
        m = "\n[Session message] [%s] " % msg._type
        if hasattr(m, 'description'):
            m += m.description

        click.echo(click.style(m, fg=COLOR_TEST_SESSION_HELPER_MESSAGE))

    except AttributeError as err:
        _echo_error(err)

    if isinstance(msg, MsgTestCaseReady):
        pass

    elif isinstance(msg, MsgDissectionAutoDissect):
        _echo_frames_as_table(msg.frames)
        return

    elif isinstance(msg, MsgTestCaseVerdict):
        verdict = msg.to_dict()
        partial_verdict = verdict.pop('partial_verdicts')

        _echo_dict_as_table(verdict)
        click.echo()

        if partial_verdict:
            click.echo(click.style("Partial verdicts:", fg=COLOR_TEST_SESSION_HELPER_MESSAGE))
            _echo_testcase_partial_verdicts_as_table(msg.partial_verdicts)
        return

    elif isinstance(msg, MsgTestSuiteReport):
        _echo_report_as_table(msg.to_dict())
        return

    elif isinstance(msg, MsgTestingToolComponentReady):
        pass

    elif isinstance(msg, MsgTestingToolComponentShutdown):
        pass

    _echo_dict_as_table(msg.to_dict())


def _echo_testcase_partial_verdicts_as_table(pvs):
    assert type(pvs) is list

    table = []
    table.append(('Step ID', 'Partial verdict', 'Description'))
    for item in pvs:
        try:
            assert type(item) is list
            cell_1 = item.pop(0)
            cell_2 = item.pop(0)
            cell_3 = list_to_str(item)
            table.append((cell_1, cell_2, cell_3))
        except Exception as e:

            _echo_error(e)
            _echo_error(traceback.format_exc())

    click.echo(click.style(tabulate(table, headers="firstrow"), fg=COLOR_TEST_SESSION_HELPER_MESSAGE))


def _echo_list_of_dicts_as_table(l):
    try:

        assert type(l) is list

        table = []
        first = True

        for d in l:  # for each dict obj in the list
            if d:
                if first:  # adds table header , we assume all dicts have same keys
                    first = False
                    table.append(tuple(d.keys()))
                table.append(tuple(d.values()))

        _echo_list_as_table(table, first_row_is_header=True)

    except Exception as e:
        _echo_error('wrong frame format passed?')
        if l:
            _echo_error(l)
        _echo_error(e)
        _echo_error(traceback.format_exc())


def _echo_report_as_table(report_dict):
    try:

        assert type(report_dict) is dict

        testcases = [(k, v) for k, v in report_dict.items() if k.lower().startswith('td')]

        for tc_name, tc_report in testcases:
            table = []
            if tc_report:
                table.append(("Testcase ID", 'Final verdict', 'Description'))
                table.append((tc_name, tc_report['verdict'], tc_report['description']))

                # testcase report
                click.echo()
                click.echo(click.style(tabulate(table, headers="firstrow"), fg=COLOR_TEST_SESSION_HELPER_MESSAGE))
                click.echo()
                _echo_testcase_partial_verdicts_as_table(tc_report['partial_verdicts'])
                click.echo()
            else:
                _echo_error('No report for testcase %s ' % tc_name)

    except Exception as e:
        _echo_error('wrong frame format passed?')
        _echo_error(e)
        _echo_error(traceback.format_exc())
        _echo_error(json.dumps(report_dict))


def _echo_frames_as_table(frames: list):
    assert type(frames) is list

    try:
        for frame in frames:
            table = []
            assert type(frame) is dict
            table.append(('frame id', frame['id']))
            table.append(('frame timestamp', frame['timestamp']))
            table.append(('frame error', frame['error']))

            # frame header print
            click.echo()  # new line
            click.echo(click.style(tabulate(table), fg=COLOR_TEST_SESSION_HELPER_MESSAGE))

            # print one table per layer
            for layer_as_dict in frame['protocol_stack']:
                assert type(layer_as_dict) is dict
                table = []
                for key, value in layer_as_dict.items():
                    temp = [key, value]
                    table.append(temp)
                click.echo(click.style(tabulate(table), fg=COLOR_TEST_SESSION_HELPER_MESSAGE))

            click.echo()  # new line

    except Exception as e:
        _echo_error('wrong frame format passed?')
        _echo_error(e)
        _echo_error(traceback.format_exc())


def _echo_list_as_table(ls: list, first_row_is_header=False):
    list_flat_items = []
    assert type(ls) is list

    for row in ls:
        assert type(row) is not str
        list_flat_items.append(tuple(list_to_str(item) for item in row))

    if first_row_is_header:
        click.echo(click.style(tabulate(list_flat_items, headers="firstrow"), fg=COLOR_TEST_SESSION_HELPER_MESSAGE))
    else:
        click.echo(click.style(tabulate(list_flat_items), fg=COLOR_TEST_SESSION_HELPER_MESSAGE))

    click.echo()  # new line


def _echo_dict_as_table(d: dict):
    table = []
    for key, value in d.items():
        if type(value) is list:
            temp = [key, list_to_str(value)]
        else:
            temp = [key, value]
        table.append(temp)

    click.echo()  # new line
    click.echo(click.style(tabulate(table), fg=COLOR_TEST_SESSION_HELPER_MESSAGE))


def _echo_session_helper(msg: str):
    click.echo(click.style('[Test Assistant] %s' % msg, fg=COLOR_SESSION_ASSISTANCE))


def _echo_input(msg):
    click.echo(click.style('[User input] %s' % msg, fg=COLOR_DEFAULT))


def _echo_error(msg):
    click.echo(click.style('[Error] %s' % msg, fg=COLOR_ERROR_MESSAGE))


def _echo_chat_message(msg: MsgSessionChat):
    if msg.iut_node == session_profile['node']:  # it's echo message
        click.echo(click.style('[Chat message sent] %s' % list_to_str(msg.description), fg=COLOR_CHAT_MESSAGE_ECHO))
    else:
        click.echo(click.style('[Chat message from %s] %s' % (msg.user_name, list_to_str(msg.description)),
                               fg=COLOR_CHAT_MESSAGE))


def _echo_data_message(msg):
    assert isinstance(msg, (MsgPacketInjectRaw, MsgPacketSniffedRaw))
    click.echo(click.style(
        '[agent] Packet captured on %s. Routing key: %s' % (msg.interface_name, msg.routing_key),
        fg=COLOR_SESSION_LOG)
    )


def _echo_log_message(msg):
    if isinstance(msg, MsgSessionLog):
        click.echo(click.style("[log][%s] %s" % (msg.component, list_to_str(msg.message)), fg=COLOR_SESSION_LOG))
    else:
        click.echo(click.style("[%s] %s" % ('log', list_to_str(msg)), fg=COLOR_SESSION_LOG))


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# debugging actions

def send_skip_tescase_coap_core_11():
    _echo_input("Executing debug message %s" % "send_skip_tescase_coap_core_11")

    msg = MsgTestCaseSkip(
        testcase_id='TD_COAP_CORE_11'
    )
    publish_message(msg)


def snif1():
    _echo_input("Executing debug message %s" % "start sniffing, file name PCAP_TEST.pcap")
    msg = MsgSniffingStart(capture_id='PCAP_TEST',
                           filter_if='tun0',
                           filter_proto='udp')
    publish_message(msg)


def snif2():
    _echo_input("Executing debug message %s" % "stop sniffing")
    msg = MsgSniffingStop()
    publish_message(msg)


def snif3():
    _echo_input("Executing debug message %s" % "get last sniffed file")
    msg = MsgSniffingGetCaptureLast()
    publish_message(msg)


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# some auxiliary functions


def list_to_str(ls):
    """
    flattens a nested list up to two levels of depth

    :param ls: the list, supports str also
    :return: single string with all the items inside the list
    """

    ret = ''

    if ls is None:
        return 'None'

    if type(ls) is str:
        return ls

    try:
        for l in ls:
            if l and isinstance(l, list):
                for sub_l in l:
                    if sub_l and not isinstance(sub_l, list):
                        ret += str(sub_l) + ' \n '
                    else:
                        # I truncate in the second level
                        pass
            else:
                ret += str(l) + ' \n '

    except TypeError as e:
        _echo_error(e)
        return str(ls)

    return ret


def save_pcap_from_base64(filename, pcap_file_base64, dir=None):
    """
    Returns number of bytes saved.

    :param filename:
    :param pcap_file_base64:
    :return:
    """

    if dir:
        file_path = os.path.join(dir, filename)
    else:
        file_path = os.path.join(os.getcwd(), filename)

    with open(file_path, "wb") as pcap_file:
        nb = pcap_file.write(base64.b64decode(pcap_file_base64))
        return nb


if __name__ == "__main__":

    try:
        session_profile.update({'amqp_exchange': str(os.environ['AMQP_EXCHANGE'])})
    except KeyError as e:
        pass  # use default

    try:
        url = '%s?%s&%s' % (
            str(os.environ['AMQP_URL']),
            "heartbeat_interval=600",
            "blocked_connection_timeout=300"
        )
        session_profile.update({'amqp_url': url})
    except KeyError as e:
        pass  # use default

    register_repl(cli)

    _echo_welcome_message()
    _echo_session_helper("\nNow please provide the session setup parameters to the CLI \n")
    _pre_configuration()
    _echo_session_helper(
        "\nPlease type <connect> to connect the CLI to the backend and start running the interop tests! \n")
    _echo_session_helper("\nYou can press TAB for the available commands at any time \n")
    _echo_session_helper("\nThe command <action [param]> needs to be used for executing the test actions\n")
    _echo_session_helper("\nNote that <action suggested> will help you navigate through the session by executing the "
                         "actions the backend normally expects for a standard session flow :)\n")
    _init_action_suggested()

    try:
        cli()
    except ExitReplException:
        sys.exit(0)
        print('Bye!')
