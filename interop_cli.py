# import click
# from click_repl import repl
# from prompt_toolkit.history import FileHistory
#
# @click.group()
# def cli():
#     pass
#
# @cli.command()
# def myrepl():
#     prompt_kwargs = {
#         'history': FileHistory('/etc/myrepl/myrepl-history'),
#     }
#     repl(click.get_current_context(), prompt_kwargs=prompt_kwargs)

import os
import uuid
import sys
import json
import pika
import logging
import threading
import traceback
from tabulate import tabulate
from collections import OrderedDict
from click.testing import CliRunner
from messages import *

import click
from click_repl import register_repl, ExitReplException

logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.WARNING)

# click colors:: black (might gray) , red, green, yellow (might be an orange), blue, magenta, cyan, white (might gray)
COLOR_DEFAULT = 'white'
COLOR_SESSION_LOG = 'white'
COLOR_COORDINATION_MESSAGE = 'cyan'
COLOR_SESSION_ASSISTANCE = 'cyan'
COLOR_CHAT_MESSAGE = 'green'
COLOR_CHAT_MESSAGE_ECHO = 'green'
COLOR_ERROR_MESSAGE = 'red'
COLOR_TEST_SESSION_HELPER_MESSAGE = 'yellow'

DEFAULT_TOPIC_SUBSCRIPTIONS = [
    # 'control.testcoordination',
    # 'control.dissection',
    # 'control.session',
    '#'
]

MESSAGE_TYPES_NOT_ECHOED = [
    MsgPacketSniffedRaw,
    MsgPacketInjectRaw,
]

TEMP_DIR = 'tmp'


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

UI_suggested_actions = {
    MsgTestingToolConfigured: 'ts_start',
    MsgTestCaseReady: 'tc_start',
    MsgStepStimuliExecute: 'stimuli',
    MsgStepVerifyExecute: 'verify',
}




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
def clear():
    """
    Clear screen
    """

    click.clear()


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
                           'verify': _handle_action_verify,
                           'stimuli': _handle_action_stimuli,
                           'suggested': None,
                           }


@cli.command()
@click.argument('api_call', type=click.Choice(message_handles_options.keys()))
def action(api_call):
    """
    Execute test action
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
    }

    if message_type in message_types:
        for item in message_types[message_type]:
            _add_to_ignore_message_list(item)
            _echo_dispatcher('Ignore message category %s: (%s)' % (message_type, str(item)))


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
def get_session_state():
    """
    Print session state and parameters
    """

    _echo_context()


def _connection_ok():
    conn_ok = False
    try:
        conn_ok = state['connection'] is not None
    except AttributeError as ae:
        pass
    except TypeError as ae:
        pass

    return conn_ok


def _echo_context():
    table = []
    for key, val in {**session_profile, **state}.items():
        #     [  ('Session parameters', session_profile),
        #     #('click context', click.get_current_context()),
        #     ('CLI states', pprint.pformat(state))
        # ]:
        table.append((key, str(val)))
    # click.echo(click.style('%s: \n %s' % (index, val), fg='cyan'))
    _echo_list_as_table(table)


def _set_up_connection():
    global state

    # conn for repl publisher
    try:
        state['connection'] = pika.BlockingConnection(pika.URLParameters(session_profile['amqp_url']))
        state['channel'] = state['connection'].channel()
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


def _echo_welcome_message():
    m = """
    Welcome to F-Interop platform!
    the Test assistant will help you go through the interoperability session (messages in cyan).
    If you experience any problems, or have any suggestions or feedback don't hesitate to drop me an email at:
    federico.sismondi@inria.fr
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

def _init_action_suggested():
    state['suggested_cmd'] = 'ts_start'

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
        _echo_dict_as_table(msg.to_dict())
        if hasattr(msg, 'partial_verdicts') and msg.partial_verdicts is not None:
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



def _echo_report_as_table(report_dict):

    try:

        assert type(report_dict) is OrderedDict

        testcases = [(k, v) for k, v in report_dict.items() if k.lower().startswith('td')]

        for tc_name, tc_report in testcases:
            table = []

            table.append(("Testcase ID", 'Final verdict', 'Description'))
            table.append((tc_name, tc_report['verdict'], tc_report['description']))

            # testcase report
            click.echo()
            click.echo(click.style(tabulate(table,headers="firstrow"), fg=COLOR_TEST_SESSION_HELPER_MESSAGE))
            click.echo()
            _echo_testcase_partial_verdicts_as_table(tc_report['partial_verdicts'])
            click.echo()

    except Exception as e:
        _echo_error('wrong frame format passed?')
        _echo_error(e)
        _echo_error(traceback.format_exc())


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


def _echo_list_as_table(ls: list):
    click.echo()  # new line
    click.echo(click.style(tabulate(ls), fg=COLOR_TEST_SESSION_HELPER_MESSAGE))


def _echo_dict_as_table(d: dict):
    table = []
    for key, value in d.items():
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


def _echo_log_message(msg):
    if isinstance(msg, MsgSessionLog):
        click.echo(click.style(list_to_str(msg.message), fg=COLOR_SESSION_LOG))
    else:
        click.echo(click.style(list_to_str(msg), fg=COLOR_SESSION_LOG))


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# some auxiliary functions


def list_to_str(ls):
    """
    flattens a nested list up to two levels of depth

    :param ls: the list, supports str also
    :return: single string with all the items inside the list
    """

    ret = ''

    if type(ls) is str:
        return ls

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
    return ret


if __name__ == "__main__":


    try:
        session_profile.update({'amqp_exchange': str(os.environ['AMQP_EXCHANGE'])})
    except KeyError as e:
        pass  # use default

    try:
        session_profile.update({'amqp_url': str(os.environ['AMQP_URL'])})
    except KeyError as e:
        pass  # use default

    register_repl(cli)

    _echo_welcome_message()
    _echo_session_helper("\nNow please provide the session setup parameters to the CLI \n")
    _pre_configuration()
    _echo_session_helper(
        "\nPlease type <connect> to connect the CLI to the backend and start running the interop tests! \n")
    _echo_session_helper("\nYou can press TAB for seeing the available commands at any time \n")
    _echo_session_helper("\nThe command <action [param]> needs to be used for executing the test actions,"
                         " note that <action suggested> will help you navigate through the session by executing the "
                         "actions the backend normally expects for a standard session flow :)\n")
    _init_action_suggested()

    try:
        cli()
    except ExitReplException:
        sys.exit(0)
        print('Bye!')
