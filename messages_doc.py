"""
Module for building automatically the doc of the API messages in markdown format.
"""
import inspect
import logging
from messages import *

gitlab_url = 'https://gitlab.f-interop.eu/f-interop-contributors/utils/blob/master/messages/messages.py'
doc_parser = 'https://gitlab.f-interop.eu/f-interop-contributors/utils/blob/master/messages_doc.py'
header = """Events (core API)

This section describes the format of the messages used in F-Interop.

This section of the documentation is autogenerated by
[tool](%s)

Check out the messages library
[tool](%s)

Version %s
""" % (doc_parser, gitlab_url, API_VERSION)

services = []
events = []


def message_amqp_section(file, message_instance):
    #file.write("\n\n```amqp")
    file.write("\n\n```")
    try:
        file.write("\n %s" % str(message_instance))
    except Exception as e:
        logging.error("\n FAILED FOR (!) ->  n %s" % repr(message_instance))
        logging.error(e)
    file.write("\n ```")
    return


def message_json_section(file, message_instance):
    #file.write("\n\n```json")
    file.write("\n\n```")
    try:
        file.write("\n %s" % json.dumps(message_instance.to_dict(), indent=4, ))
    except Exception as e:
        logging.error("\n FAILED FOR (!) ->  n %s" % repr(message_instance))
        logging.error(e)
    file.write("\n ```")
    return


def print_doc_tables(services, events):
    """

    expected result (this method cannot do all this, some modifs need to be done manually)

    ### API services

    TBD provides the following services:

    |SERVICES | DESCRIPTION|
    |---| ---|
    |[*testcoordination.testsuite.getstatus*](#testcoordination-testsuite-getstatus) | Message for debugging
    purposes. The coordination component returns the status of the execution |
    |[*testcoordination.testsuite.gettestcases*](#testcoordination-testsuite-gettestcases) | Message for requesting
    the list of test cases included in the test suite.|

    ### API events

    TBD listens and consumes the following messages from the bus:

    |MESSAGES CONSUMED | DESCRIPTION|
    |---| ---|
    |[*testcoordination.testsuite.start*](#testcoordination-testsuite-start) | Message for triggering start of test
    suite. The command is given by one of the users of the session.|
    |[*testcoordination.testsuite.abort*](#testcoordination-testsuite-abort)| Message for aborting the ongoing test
    session.|
    |[*testcoordination.testcase.skip*](#testcoordination-testcase-skip) | Message for skipping a test case.
    Coordinator passes to the next test case if there is any left.|

    Coordinator generates and publishes the following messages:

    |MESSAGES PUBLISHED | DESCRIPTION|
    |---| ---|
    |[*testcoordination.testcase.next*](#testcoordination-testcase-next) | Indicates next testcase to be executed |
    |[*testcoordination.testsuite.finished*](#testcoordination-testsuite-finished) | Indicates there's no more test
    cases to execute |
    |[*testcoordination.error*](#testcoordination-error) | Message used to indicate errors on coordiation component |


    """

    head_1 = """### API services

TBD provides the following services:

|SERVICES | DESCRIPTION|
|---| ---|"""

    head_2 = """### API events

TBD listens and consumes the following messages from the bus:

|MESSAGES CONSUMED | DESCRIPTION|
|---| ---|"""

    head_3 = """TBD generates and publishes the following messages:

|MESSAGES PUBLISHED | DESCRIPTION|
|---| ---|"""

    def table_row(event_type):
        s = ""
        s += "|[*%s*](#%s) | Some description that needs to be writen manually |" \
             % (
                 event_type,
                 event_type.replace('.', '-')
             )
        return s

    print(head_1)
    for s in services:
        print(table_row(s.routing_key))

    print()
    print()
    print(head_2)
    for e in events:
        print(table_row(e.routing_key))

    print()
    print()
    print(head_3)
    for e in events:
        print(table_row(e.routing_key))


def generate_doc_section_into_file(file_to_write, section, list_of_message_classes):
    f = file_to_write
    f.write('\n\n## %s' % (section))

    for msg_class in list_of_message_classes:

        msg_type = msg_class().routing_key
        print('generating doc for %s,%s' % (msg_type, msg_class))

        # Message Type
        f.write('\n\n\n### %s' % (msg_type))

        # Header
        # f.write('\n\n#### Description:\n\n')

        # markdown table header
        f.write("\n| []() | |\n| --- | --- |\n")

        try:
            # add routing key in table
            f.write("|Routing key|{0}|\n".format(msg_class().routing_key))
        except TypeError as te:
            print("No routing key found for %s" % repr(msg_class))

        md_bullet_list = ''
        unknown = ''

        # Message class docstring to table
        for line in msg_class.__doc__.splitlines():
            if line and not line.isspace():

                if "description:" in str(line).lower():
                    sp_line = line.split(':')
                    if len(sp_line) > 1:
                        f.write("|Description:|{0}|\n".format(sp_line[1].strip()))
                    elif len(sp_line) == 1:
                        f.write("|Description:||\n")
                    else:
                        raise NotImplementedError()

                elif '- ' in line:
                    md_bullet_list += "||{0}|\n".format(line.strip())

                elif "Type:" in line:
                    sp_line = line.split(':')
                    f.write('|{0}|{1}|\n'.format(sp_line[0].strip(), sp_line[1].strip()))

                elif "Requirements:" in line:
                    sp_line = line.split(':')
                    f.write('|{0}|{1}|\n'.format(sp_line[0].strip(), sp_line[1].strip()))

                elif "Pub/Sub:" in line or "Typical_use:" in line:
                    sp_line = line.split(':')
                    f.write('|{0}|{1}|\n'.format(sp_line[0].strip(), sp_line[1].strip()))

                else:
                    if md_bullet_list is not '':
                        md_bullet_list += '||{0}|\n'.format(line)
                    else:
                        unknown += '||{0}|\n'.format(line)

        f.write(md_bullet_list)
        f.write(unknown)

        # Message code source:
        line_number = (inspect.findsource(msg_class)[1])
        url = gitlab_url + "#L%s" % line_number
        f.write('\n\nSource code: [%s](%s)\n' % (msg_class.__name__, url))

        msg_instance = None

        # Messages's example AMQP + JSON
        if 'reply' not in msg_class.routing_key:  # Message is not a reply
            msg_instance = msg_class()

        else:  # Message is a reply -> we need to generate it using a request (messages.py library API requierement)

            reply_routing_key = msg_class.routing_key
            request_routing_key = reply_routing_key.replace("reply", "request")
            # get message class of request
            request_class = rk_pattern_to_message_type_map.get_message_type(request_routing_key)
            if request_class is None:
                raise Exception('cannot process message event: %s' % msg_type)
            # create request
            request_instance = request_class()
            # create reply
            msg_instance = msg_class(request_message=request_instance)

        # add the amqo + json section
        message_amqp_section(f, msg_instance)
        message_json_section(f, msg_instance)

        try:
            if 'request' in msg_instance.routing_key:
                services.append(msg_instance)
            else:
                events.append(msg_instance)
        except TypeError as te:
            print("error found trying to document %s, \nerror %s" % (msg_instance, te))


if __name__ == '__main__':
    tt_messages = [
        MsgTestingToolReady,
        MsgSessionConfiguration,
        MsgTestingToolConfigured,
        MsgTestSuiteStart,
        MsgStepStimuliExecute,
        MsgStepStimuliExecuted,
        MsgStepVerifyExecute,
        MsgStepVerifyExecuted,
        MsgTestCaseVerdict,
        MsgTestSuiteReport,
        MsgTestingToolTerminate,
    ]

    so_messages = [
    ]

    ui_messages = [
        MsgUiDisplayMarkdownText,
        MsgUiRequestTextInput,
        MsgUiRequestConfirmationButton,
        MsgUiRequestSessionConfiguration,
        MsgUiSessionConfigurationReply,
        MsgUiRequestUploadFile,
        MsgUiRequestQuestionCheckbox,
        MsgUiRequestQuestionRadio

    ]

    results_repo_messages = [
    ]

    viz_tools = [
        MsgVizInitRequest,
        MsgVizInitReply,
        MsgVizDashboardRequest,
        MsgVizDashboardReply,
        MsgVizWrite,
    ]
    resurces_repo_messages = [
    ]

    with open('_messages.md', "w+") as f:
        # Message Type
        f.write('# %s' % (header))
        generate_doc_section_into_file(f, 'Orchestrator events', so_messages)
        generate_doc_section_into_file(f, 'User interface events', ui_messages)
        generate_doc_section_into_file(f, 'Testing Tool events', tt_messages)
        generate_doc_section_into_file(f, 'Results Repository events', results_repo_messages)
        generate_doc_section_into_file(f, 'Resources Repository events', resurces_repo_messages)
        generate_doc_section_into_file(f, 'Visualization tools events', viz_tools)

    print_doc_tables(services, events)
