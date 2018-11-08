import os
from os.path import expanduser
import sys
import pika
import errno
import base64
import logging
import datetime
import threading
import traceback

from collections import OrderedDict

import click
from click_repl import ExitReplException
from click_repl import repl as repl_base
from prompt_toolkit.history import FileHistory

# for using it as library and as a __main__
try:
    from messages import *
    from event_bus_utils import AmqpListener
    from tabulate import tabulate
except:
    from ..messages import *
    from ..event_bus_utils import AmqpListener
    from ..tabulate import tabulate

logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.WARNING)

COMPONENT_ID = 'ioppytest-cli'

HOME = expanduser("~")

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
WAIT_TIME_FOR_USER_INPUT = 60

DEFAULT_TOPIC_SUBSCRIPTIONS = [
    '#'
]

MESSAGE_TYPES_NOT_ECHOED = [
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

state_lock = threading.RLock()
state = {
    'testcase_id': None,
    'step_id': None,
    'last_message': None,
    'suggested_cmd': None,
    'connection': None,
    'channel': None,
}
profile_choices = {
    'protocol': ['coap', '6lowpan', 'onem2m'],
    'node': ['coap_client', 'coap_server']
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


@click.group()
def cli():
    pass


@cli.command()
def repl():
    """
    Interactive shell, allows user to interact with the ioppytest testing tool
    """

    history_path_file = "{dir}{sep}{comp_name}-history".format(dir=HOME, sep=os.path.sep, comp_name=COMPONENT_ID)
    if not os.path.exists(os.path.dirname(history_path_file)):
        try:
            os.makedirs(os.path.dirname(history_path_file))
        except OSError as exc:  # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise

    prompt_kwargs = {
        'history': FileHistory(history_path_file),
    }
    _echo_log_message('saving CMD history at: {}'.format(history_path_file))

    _echo_welcome_message()
    #_pre_configuration()
    _echo_session_helper("\nYou can press TAB for the available commands at any time \n")

    _echo_session_helper("\nThe command <action [param]> needs to be used for executing the test actions\n")
    _echo_session_helper(
        "\nNote that <action suggested> will help you navigate through the session by executing the "
        "actions the backend normally expects for a standard session flow :)\n")
    _init_action_suggested()

    _set_up_connection()

    repl_base(click.get_current_context(), prompt_kwargs=prompt_kwargs)


@cli.command()
@click.option('-ll', '--lazy-listener',
              is_flag=True,
              default=False,
              help="lazy-listener doest perform conversion to Messages objects")
def connect(lazy_listener):
    """
    Connect to an AMQP session and start consuming messages
    """
    _set_up_connection(lazy_listener=lazy_listener)


@cli.command()
def exit():
    """
    Exits REPL

    """
    _exit()


@cli.command()
@click.option('--destination', default=TEMP_DIR, help='Destination directory.', show_default=True)
def download_network_traces(destination):
    """
    Downloads all networks traces generated during the session
    """
    global state

    _handle_get_testcase_list()
    ls = state['tc_list'].copy()

    for tc_item in ls:
        try:
            tc_id = tc_item['testcase_id']
            msg = MsgSniffingGetCapture(capture_id=tc_id)
            response = _amqp_request(msg, COMPONENT_ID)

            if response.ok:
                _save_file_from_base64(response.filename, response.value, destination)
                _echo_input("downloaded network trace %s , into dir: %s" % (response.filename, destination))
            else:
                raise Exception(response.error_message)

        except Exception as e:
            _echo_error('Error trying to download network traces for testcase : %s' % tc_id)
            _echo_error(e)


@cli.command()
@click.argument('path-to-file', type=click.Path(exists=True))
@click.option('--text-message', default=None, help="Message to be displayed in GUI")
@click.option('--user-id', default='all', help="User ID in case there are several users in session")
def gui_request_file_upload(path_to_file, text_message, user_id):
    """
    Request user to upload a file, saves it in directory (if provided) or else in .tmp
    """
    global state

    msg_request = MsgUiRequestUploadFile()

    msg_request.fields = [
        {
            "name": text_message,
            "type": "file",
        }
    ]

    if user_id:
        msg_request.routing_key = "ui.user.{}.request".format(user_id)
        msg_request.reply_to = "ui.user.{}.reply".format(user_id)

    _echo_input("sending request to {}".format(msg_request.routing_key))
    msg_response = _amqp_request(msg_request, COMPONENT_ID, timeout=WAIT_TIME_FOR_USER_INPUT)
    values_dict = msg_response.fields.pop()  # If there's more than one then GUI fucked up

    value = values_dict['value']
    filename = values_dict['filename']

    _save_file_from_base64(filename, value, path_to_file)
    _echo_input("saved file {} in path {}".format(filename, path_to_file))


@cli.command()
@click.argument('path-to-file', type=click.Path(exists=True))
@click.option('--text-message', default=None, help="Message to be displayed in GUI")
@click.option('--user-id', default='all', help="User ID in case there are several users in session")
def gui_send_file_to_download(path_to_file, text_message, user_id):
    """
    Sends file to user's GUI. Useful for example to enable users to download reports, pcap files, etc..
    """
    global state

    msg_request = MsgUiSendFileToDownload()

    with open(path_to_file, "rb") as file:
        enc = base64.b64encode(file.read())

    msg_request.fields = [
        {
            "name": text_message,
            "type": "data",
            "value": enc.decode("utf-8"),
        }
    ]

    if user_id:
        msg_request.routing_key = "ui.user.{}.display".format(user_id)

    _echo_input("sending file to {}".format(msg_request.routing_key))
    _publish_message(msg_request)


@cli.command()
@click.argument('text-message')
@click.option('--user-id', default='all', help="User ID in case there are several users in session")
def gui_display_message(text_message, user_id):
    """
    Sends message to GUI
    """
    global state

    msg_display = MsgUiDisplay()

    msg_display.fields = [
        {
            "name": text_message,
            "type": "p",
        }
    ]

    if user_id:
        msg_display.routing_key = "ui.user.{}.display".format(user_id)

    _publish_message(msg_display)
    _echo_input("message display sent to {}".format(msg_display.routing_key))


@cli.command()
@click.option('--url', default="https://www.w3schools.com", help="")
def gui_iframe_display(url):
    """
    Sends message to GUI
    """
    global state

    msg = MsgUiDisplayIFrame()

    msg.fields = [
        {
            "value": url,
            "type": "iframe"
        }
    ]

    _publish_message(msg)
    _echo_input("message to GUI: {}".format(msg.routing_key))



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

    _publish_message(msg)


def _handle_get_testcase_list():
    #  requires testing tool to implement GetTestCases feature, see MsgTestSuiteGetTestCases

    request_message = MsgTestSuiteGetTestCases()

    try:
        testcases_list_reponse = _amqp_request(request_message, COMPONENT_ID)
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


def _handle_action_testsuite_start():
    if click.confirm('Do you want START test suite?'):
        msg = MsgTestSuiteStart()
        _publish_message(msg)


def _handle_action_testcase_start():
    if click.confirm('Do you want START test case?'):
        msg = MsgTestCaseStart()  # TODO no testcase id input?
        _publish_message(msg)


def _handle_action_testsuite_abort():
    if click.confirm('Do you want ABORT test suite?'):
        msg = MsgTestSuiteAbort()
        _publish_message(msg)


def _handle_action_testcase_skip():
    if click.confirm('Do you want SKIP current test case?'):
        msg = MsgTestCaseSkip()
        _publish_message(msg)


def _handle_action_testcase_restart():
    if click.confirm('Do you want RESTART current test case?'):
        msg = MsgTestCaseRestart()
        _publish_message(msg)


def _handle_action_stimuli():
    if isinstance(state['last_message'], MsgStepStimuliExecute):
        _echo_session_helper(list_to_str(state['last_message'].description))

    resp = click.confirm('Did you execute last STIMULI step (if any received)?')

    if resp:
        msg = MsgStepStimuliExecuted(
            node=session_profile['node'],
            node_execution_mode="user_assisted"
        )
        _publish_message(msg)

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

    _publish_message(msg)


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


ignorable_message_types = {
    'dissections': [MsgDissectionAutoDissect],
    'packets': [MsgPacketSniffedRaw, MsgPacketInjectRaw],
    'ui': [MsgUiRequestTextInput,
           MsgUiRequestConfirmationButton,
           MsgUiDisplay,
           MsgUiDisplayMarkdownText,
           MsgUiReply]
}


@cli.command()
@click.argument('message_type', type=click.Choice(list(ignorable_message_types.keys())))
def ignore(message_type):
    """
    (REPL only) Do not notify any more on message type
    """
    try:
        for item in ignorable_message_types[message_type]:
            _add_to_ignore_message_list(item)
            _echo_dispatcher('Ignore message category %s: (%s)' % (message_type, str(item)))
    except KeyError as ke:
        _echo_error('Couldnt add to ignored list..')
        _echo_error(ke)


@cli.command()
def enter_debug_context():
    """
    (REPL only) Provides user with some extra debugging commands

    """
    global message_handles_options

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #  this build dinamically a REPL call per each message defined in messages library

    dummy_messages_dict = {k: v for (k, v) in globals().items() if 'Msg' in k}

    def _send_dummy_message():
        ctx = click.get_current_context()
        message_name = ctx.command.name.replace('_send_', '')

        try:
            message_t = dummy_messages_dict[message_name]()
            _echo_input("trying to send message: %s" % repr(message_t))
            _publish_message(message_t)

        except Exception as e:
            _echo_error("Error found: %s" % e)
            return

    for message in list(dummy_messages_dict.keys()):
        name = "_send_%s" % message
        _echo_session_helper('adding cmd: %s' % name)
        c = click.Command(
            name=name,
            callback=_send_dummy_message,
            # params=[
            #     message
            # ],
            short_help="Send dummy %s message to bus." % message
        )

        cli.add_command(c)
        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    @cli.command()
    def _results_store_insert_result():
        tc_results_example = [
            {'verdict': 'pass',
             'description': 'No interoperability error was detected.',
             'testcase_id': 'TD_COAP_CORE_01',
             'partial_verdicts': [
                 ['TD_COAP_CORE_01_step_02', None, 'CHECK step: postponed', ''],
                 ['TD_COAP_CORE_01_step_03', None, 'CHECK step: postponed', ''],
                 ['TD_COAP_CORE_01_step_04', 'pass',
                  'VERIFY step: User informed that the information was displayed correclty on his/her IUT',
                  ''],
                 ['tat_check_1', 'pass',
                  '<Frame   1: [bbbb::1 -> bbbb::2] CoAP [CON 861] GET /test> Match: CoAP(type=0, code=1)'],
                 ['tat_check_2', 'pass',
                  '<Frame   2: [bbbb::2 -> bbbb::1] CoAP [ACK 861] 2.05 Content > Match: CoAP(opt=Opt(CoAPOptionContentFormat()))']]},
            {'verdict': 'pass',
             'description': 'No interoperability error was detected.',
             'testcase_id': 'TD_COAP_CORE_02',
             'partial_verdicts': [
                 ['TD_COAP_CORE_02_step_02', None, 'CHECK step: postponed', ''],
                 ['TD_COAP_CORE_02_step_03', None, 'CHECK step: postponed', ''],
                 ['TD_COAP_CORE_02_step_04', 'pass',
                  'VERIFY step: User informed that the information was displayed correclty on his/her IUT', ''],
                 ['tat_check_1', 'pass',
                  '<Frame   1: [bbbb::1 -> bbbb::2] CoAP [CON 808] DELETE /test> Match: CoAP(type=0, code=4)'],
                 ['tat_check_2', 'pass',
                  "<Frame   2: [bbbb::2 -> bbbb::1] CoAP [ACK 808] 2.02 Deleted > Match: CoAP(code=66, mid=0x0328, tok=b'')"]]},
            {'verdict': 'None', 'description': 'Testcase TD_COAP_CORE_04 was skipped.',
             'testcase_id': 'TD_COAP_CORE_04', 'partial_verdicts': []},
        ]
        m = MsgInsertResultRequest(
            data=tc_results_example
        )
        _publish_message(m)

    @cli.command()
    def _results_store_get_result():
        m = MsgGetResultRequest(
        )
        _publish_message(m)

    @cli.command()
    def _agent_serial_message_inject():
        data = [65, 216, 206, 205, 171, 255, 255, 156, 237, 51, 4, 0, 75, 18, 0, 65, 96, 0, 0, 0, 0, 6, 58, 64, 254,
                128, 0,
                0, 0, 0, 0, 0, 2, 18, 75, 0, 4, 51, 237, 156, 255, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 26, 155, 0,
                40,
                63, 0, 0]
        data_slip = [192, 65, 216, 206, 205, 171, 255, 255, 156, 237, 51, 4, 0, 75, 18, 0, 65, 96, 0, 0, 0, 0, 6, 58,
                     64,
                     254, 128, 0, 0, 0, 0, 0, 0, 2, 18, 75, 0, 4, 51, 237, 156, 255, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                     0,
                     0, 26, 155, 0, 40, 63, 0, 0, 192]
        agent_name = click.prompt('enter agent name (e.g. eut2)', type=str)
        m = MsgPacketInjectRaw(
            timestamp=1488586183.45,
            interface_name='/dev/tun/uruguay_noma',
            data=data,
            data_slip=data_slip
        )
        m.routing_key = m.routing_key.replace('.*.ip.tun.', ".{}.{}.{}.".format(agent_name, '802154', 'serial'))
        _publish_message(m)

    # TODO group cmds
    @cli.command()
    @click.option('-s', '--step-id', default='TD_COAP_CORE_01_step_01', help="step id of the STIMULI")
    @click.option('-ta', '--target-address', default=None, help="taget address")
    @click.option('-n', '--node', default='coap_client', help="Node id (related to the IUT role)")
    def _execute_stimuli_step(step_id, target_address, node):
        """
        Stimuli to be executed by IUT1, targeting IUT2
        """
        _echo_session_helper("Executing test message function %s" % sys._getframe().f_code.co_name)
        msg = MsgStepStimuliExecute(
            node=node,
            step_id=step_id,
            target_address=target_address,
            description="",
            step_type="stimuli",
            step_info=[""],
            testcase_id="",
            testcase_ref="",

        )
        _publish_message(msg)

    @cli.command()
    @click.option('-s', '--step-id', default='TD_COAP_CORE_01_step_04', help="step id of the VERIFY")
    @click.option('-n', '--node', default='coap_client', help="Node id (related to the IUT role)")
    def _execute_verify_step(step_id, node):
        """
        Request IUT to verify a step, normally they respond with a dummy verify ok
        """
        _echo_session_helper("Executing test message function %s" % sys._getframe().f_code.co_name)
        msg = MsgStepVerifyExecute(
            node=node,
            step_id=step_id,
            description="",
            step_type="verify",
            step_info=[""],
            testcase_id="",
            testcase_ref="",

        )
        _publish_message(msg)

    @cli.command()
    @click.option('-tc', '--testcase-id', default=None, help="testcase id")
    def _sniffer_start(testcase_id):
        """
        Sniffer start
        """
        if testcase_id is None:
            testcase_id = 'PCAP_TEST'

        _echo_session_helper("Executing test message function %s" % sys._getframe().f_code.co_name)
        msg = MsgSniffingStart(capture_id=testcase_id,
                               filter_if='tun0',
                               filter_proto='udp')
        _publish_message(msg)

    @cli.command()
    def _sniffer_stop():
        """
        Sniffer stop
        """
        _echo_session_helper("Executing test message function %s" % sys._getframe().f_code.co_name)
        msg = MsgSniffingStop()
        _publish_message(msg)

    @cli.command()
    def _sniffer_get_last_capture():
        """
        Sniffer get last capture
        """
        _echo_session_helper("Executing test message function %s" % sys._getframe().f_code.co_name)
        msg = MsgSniffingGetCaptureLast()
        _publish_message(msg)

    @cli.command()
    def _configure_perf_tt():
        """
        Send example configuration message for perf TT
        """
        _echo_session_helper("Executing test message function %s" % sys._getframe().f_code.co_name)
        from message_examples import PERF_TT_CONFIGURATION
        message = MsgSessionConfiguration(**PERF_TT_CONFIGURATION)  # builds a config for the perf TT
        _publish_message(message)

    @cli.command()
    def _configure_comi_tt():
        """
        Send example configuration message for CoMI TT
        """
        _echo_session_helper("Executing test message function %s" % sys._getframe().f_code.co_name)
        from message_examples import COMI_TT_CONFIGURATION
        message = MsgSessionConfiguration(**COMI_TT_CONFIGURATION)  # builds a config message
        _publish_message(message)

    @cli.command()
    def _configure_6lowpan_tt():
        """
        Send example configuration message for SIXLOWPAN TT
        """
        _echo_session_helper("Executing test message function %s" % sys._getframe().f_code.co_name)
        from message_examples import SIXLOWPAN_TT_CONFIGURATION
        message = MsgSessionConfiguration(**SIXLOWPAN_TT_CONFIGURATION)  # builds a config message
        _publish_message(message)

    @cli.command()
    def _test_tat_analyze_6lowpan():
        """
        Send example 6lowpan tat analysis request
        """
        _echo_session_helper("Executing test message function %s" % sys._getframe().f_code.co_name)
        from message_examples import SIXLOWPAN_TAT_ANALYZE
        message = MsgInteropTestCaseAnalyze(**SIXLOWPAN_TAT_ANALYZE)
        _publish_message(message)

    @cli.command()
    def _configure_coap_tt():
        """
        Send example configuration message for CoAP TT
        """
        _echo_session_helper("Executing test message function %s" % sys._getframe().f_code.co_name)
        from message_examples import COAP_TT_CONFIGURATION
        message = MsgSessionConfiguration(**COAP_TT_CONFIGURATION)  # builds a config message
        _publish_message(message)

    @cli.command()
    def _get_session_configuration_from_ui():
        """
        Get session config from UI
        """
        _echo_session_helper("Executing test message function %s" % sys._getframe().f_code.co_name)
        req = MsgUiRequestSessionConfiguration()
        _publish_message(req)

    @cli.command()
    @click.argument('testcase_id')
    def _testcase_skip(testcase_id):
        """
        Skip a particular testcase
        """
        _echo_session_helper("Executing test message function %s" % sys._getframe().f_code.co_name)

        msg = MsgTestCaseSkip(
            testcase_id=testcase_id
        )
        _publish_message(msg)

    @cli.command()
    @click.argument('text')
    def _ui_display_markdown_text(text):
        """
        Send message to GUI
        """
        _echo_session_helper("Executing test message function %s" % sys._getframe().f_code.co_name)

        msg = MsgUiDisplayMarkdownText()

        _echo_input(text)

        if text:
            fields = [
                {
                    'type': 'p',
                    'value': text
                }
            ]
            msg.fields = fields

        _publish_message(msg)

    @cli.command()
    @click.argument('text')
    def _ui_send_confirmation_button(text):
        """
        Send button to GUI
        """
        _echo_session_helper("Executing test message function %s" % sys._getframe().f_code.co_name)

        msg = MsgUiRequestConfirmationButton()

        _echo_input(text)

        msg.fields = [{
            "name": text,
            "type": "button",
            "value": True
        }]

        _publish_message(msg)

    @cli.command()
    def _ui_send_radio_button():
        """
        Send checkbox example to GUI
        """
        _echo_session_helper("Executing test message function %s" % sys._getframe().f_code.co_name)

        msg = MsgUiRequestQuestionRadio()

        _publish_message(msg)

    _echo_session_helper("Entering debugger context, added extra CMDs, please type --help for more info")


@cli.command()
@click.option('--target-host', default='bbbb::2', help="ICMPv6 destination address")
@click.option('--origin-node', default='coap_client', help="Origin Node id (related to the automated IUT role)")
def _test_automated_iut_reaches_another_other_implementation(target_host, origin_node):
    """
    Request automated IUT to send a ping request to a certain ip destination
    """
    _echo_session_helper("Executing test message function %s" % sys._getframe().f_code.co_name)
    msg = MsgAutomatedIutTestPing(
        node=origin_node,
        target_address=target_host

    )
    resp = _amqp_request(msg, COMPONENT_ID, 15)

    assert resp.ok, '%s cannot reach destination %s' % (origin_node, target_host)


@cli.command()
@click.argument('message', nargs=-1)
def chat(message):
    """
    Send chat message, useful for user-to-user test sessions
    """

    m = ''

    for word in message:
        m += " %s" % word

    c = MsgSessionChat(description=m,
                       user_name=session_profile['user_name'],
                       iut_node=session_profile['node'])
    _publish_message(c)


@cli.command()
def check_connection():
    """
    (REPL only) Check if AMQP connection is active
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
        request_message = MsgTestSuiteGetStatus()

        try:
            status_resp = _amqp_request(request_message, COMPONENT_ID)
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
        list.append(('testcase id', 'testcase ref', 'test case objective', 'testcase status'))
        for tc in tc_states:
            if tc:
                list.append((tc.values()))
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
    d = {}
    d.update(session_profile)
    d.update(state)
    for key, val in d.items():
        table.append((key, list_to_str(str(val))))
    _echo_list_as_table(table)


def _set_up_connection(create_listener=True, lazy_listener=False):
    # conn for repl publisher
    try:
        retries_left = CONNECTION_SETUP_RETRIES
        state_lock.acquire()
        while retries_left > 0:
            try:
                _echo_session_helper("Connecting to %s" % session_profile['amqp_url'])

                state['connection'] = pika.BlockingConnection(pika.URLParameters(session_profile['amqp_url']))
                state['channel'] = state['connection'].channel()
                break
            except pika.exceptions.ConnectionClosed:
                retries_left -= 1
                _echo_session_helper("Couldnt establish connection, retrying .. %s/%s " % (
                    CONNECTION_SETUP_RETRIES - retries_left, CONNECTION_SETUP_RETRIES))

    except pika.exceptions.ProbableAccessDeniedError:
        _echo_error('Probable access denied error. Is provided AMQP_URL correct?')
        state['connection'] = None
        state['channel'] = None
        return

    finally:
        state_lock.release()

    # note we have a separate conn for amqp listener (each pika threads needs a different connection)
    if 'amqp_listener_thread' in state and state['amqp_listener_thread'] is not None:
        _echo_log_message('stopping amqp listener thread')
        th = state['amqp_listener_thread']
        th.stop()
        th.join(2)
        if th.isAlive():
            _echo_log_message('amqp listener thread doesnt want to stop, lets terminate it..')
            th.terminate()

    if create_listener is False:
        return

    # set up listener thread which will call callback each time there's a new message in bus and matches a topic

    if lazy_listener:
        amqp_listener_thread = AmqpListener(
            amqp_url=session_profile['amqp_url'],
            amqp_exchange=session_profile['amqp_exchange'],
            callback=None,
            topics=DEFAULT_TOPIC_SUBSCRIPTIONS,
            use_message_typing=False,
        )
    else:
        amqp_listener_thread = AmqpListener(
            amqp_url=session_profile['amqp_url'],
            amqp_exchange=session_profile['amqp_exchange'],
            callback=_message_handler,
            topics=DEFAULT_TOPIC_SUBSCRIPTIONS,
            use_message_typing=True,
        )

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
    *************************************************************************************
    *   If you experience any problems, or you have any suggestions or feedback         *
    *   don't hesitate to drop me an email at:  federico[dot]sismondi[at]gmail[dot]com  *
    *************************************************************************************
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
    elif isinstance(msg, MsgSessionConfiguration):
        # fixme hanlde extremly long fields in a more generic way
        msg.configuration = ['...ommited fields...']  # this fields is normally monstrously big
        _echo_backend_message(msg)
    elif isinstance(msg, dict):
        click.echo(click.style(repr(msg), fg=COLOR_DEFAULT))
    elif isinstance(msg, (MsgUiDisplay, MsgUiDisplayMarkdownText, MsgUiRequestConfirmationButton)):
        _echo_gui_message(msg)

    # default echo for objects of Message type
    elif isinstance(msg, Message):
        _echo_backend_message(msg)
    else:
        click.echo(click.style(msg, fg=COLOR_DEFAULT))


def _quit_callback():
    click.echo(click.style('Quitting!', fg=COLOR_ERROR_MESSAGE))


def _echo_backend_message(msg):
    assert isinstance(msg, Message)

    try:
        m = "\n[Event bus message] [%s] " % type(msg)
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
        _echo_report_as_table(msg.tc_results)
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


def _echo_report_as_table(tc_report_list):
    try:

        assert type(tc_report_list) is list

        # testcases = [(k, v) for k, v in report_dict.items() if k.lower().startswith('td')]
        testcases = tc_report_list

        for tc_report in testcases:
            table = []
            table.append(("Testcase ID", 'Final verdict', 'Description'))

            tc_id = tc_report['testcase_id'] if 'testcase_id' in tc_report else '???'
            verd = tc_report['verdict'] if 'verdict' in tc_report else '???'
            desc = tc_report['description'] if 'description' in tc_report else '???'

            table.append((tc_id, verd, desc))
            # testcase report
            click.echo()
            click.echo(click.style(tabulate(table, headers="firstrow"), fg=COLOR_TEST_SESSION_HELPER_MESSAGE))
            if 'partial_verdicts' in tc_report:
                click.echo()
                _echo_testcase_partial_verdicts_as_table(tc_report['partial_verdicts'])
            click.echo()

    except Exception as e:
        _echo_error('wrong frame format passed?')
        _echo_error(e)
        _echo_error(traceback.format_exc())
        _echo_error(json.dumps(tc_report_list))


def _echo_frames_as_table(frames):
    assert type(frames) is list

    try:
        for frame in frames:
            table = []
            assert type(frame) is dict
            timestamp = datetime.datetime.fromtimestamp(int(frame['timestamp'])).strftime('%Y-%m-%d %H:%M:%S')
            table.append(('frame id', frame['id']))
            table.append(('frame timestamp', timestamp))
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


def _echo_list_as_table(ls, first_row_is_header=False):
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


def _echo_dict_as_table(d):
    table = []
    for key, value in d.items():
        if type(value) is list:
            temp = [key, list_to_str(value)]
        else:
            temp = [key, value]
        table.append(temp)

    click.echo()  # new line
    click.echo(click.style(tabulate(table), fg=COLOR_TEST_SESSION_HELPER_MESSAGE))


def _echo_session_helper(msg):
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


def _echo_gui_message(msg):
    click.echo(
        click.style("[UI message]\n\tMessage: %s \n\ttags: %s\n\tFields: %s \n\tR_key: %s \n\tcorr_id: %s" %
                    (
                        repr(msg)[:70],
                        str(msg.tags),
                        str(msg.fields)[:70],
                        msg.routing_key,
                        msg.correlation_id if hasattr(msg, 'correlation_id') else ''
                    ),
                    fg=COLOR_SESSION_LOG))


def _echo_log_message(msg):
    if isinstance(msg, MsgSessionLog):
        click.echo(click.style("[log][%s] %s" % (msg.component, list_to_str(msg.message)), fg=COLOR_SESSION_LOG))
    else:
        click.echo(click.style("[%s] %s" % ('log', list_to_str(msg)), fg=COLOR_SESSION_LOG))


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


def _save_file_from_base64(filename, base64_encoded_file, dir=None):
    """
    Returns number of bytes saved.

    :param filename:
    :param base64_encoded_file:
    :return:
    """

    if dir:
        file_path = os.path.join(dir, filename)
    else:
        file_path = os.path.join(os.getcwd(), filename)

    with open(file_path, "wb") as pcap_file:
        nb = pcap_file.write(base64.b64decode(base64_encoded_file))
        return nb


# # # AMQP connection, channel, publish and requests/replies handling # # #

def _amqp_request(request_message, component_id=COMPONENT_ID, timeout=10):
    TIME_WAIT_BETWEEN_POLLS = 0.5
    state_lock.acquire()

    if not _connection_ok():
        _echo_dispatcher('No connection established yet, setting up one..')
        _set_up_connection(create_listener=False)

    channel = state['channel']
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

        retries_left = int(timeout / TIME_WAIT_BETWEEN_POLLS)

        while retries_left > 0:
            time.sleep(TIME_WAIT_BETWEEN_POLLS)
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
                    type(request_message)
                )
            )

    finally:
        # clean up
        channel.queue_delete(reply_queue_name)
        state_lock.release()

    return response


def _publish_message(message):
    if not _connection_ok():
        _echo_dispatcher('No connection established yet, setting up one..')
        _set_up_connection(create_listener=False)

    _echo_dispatcher('Sending message..')

    for i in range(1, 4):
        try:
            state_lock.acquire()
            channel = state['connection'].channel()
            channel.basic_publish(
                exchange=session_profile['amqp_exchange'],
                routing_key=message.routing_key,
                properties=pika.BasicProperties(**message.get_properties()),
                body=message.to_json(),
            )
            channel.close()
            break

        except pika.exceptions.ConnectionClosed as err:
            _echo_error(err)
            _echo_error('Unexpected connection closed, retrying %s/%s' % (i, 4))
            _set_up_connection()

        finally:
            state_lock.acquire()


def main():
    try:
        session_profile.update({'amqp_exchange': str(os.environ['AMQP_EXCHANGE'])})
    except KeyError as e:
        pass  # use default

    try:
        env_url = str(os.environ['AMQP_URL'])
        if 'heartbeat' not in env_url:
            url = '%s?%s&%s&%s&%s&%s' % (
                env_url,
                "heartbeat=600",
                "blocked_connection_timeout=300",
                "retry_delay=1",
                "socket_timeout=1",
                "connection_attempts=3"
            )
        else:
            url = env_url

        session_profile.update({'amqp_url': url})
    except KeyError as e:
        pass  # use default

    try:
        cli()
    except ExitReplException:
        print('Bye!')
        sys.exit(0)
