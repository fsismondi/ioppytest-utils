# -*- coding: utf-8 -*-

"""
This module provides the API message formats used in F-Interop.

The idea is to be able to have an
- organized and centralized way of dealing with the big amount of messages formats used in the platform;
- to be able to import (or just copy/paste) these messages formats from any component in the F-Interop platform,
- re-use this also for the integration testing;
- to have version control the messages e.g. messages_testcase_start API v1 and API v2;
- to have a direct way of exporting this as doc.

Usage:
------
>>> from messages import *
>>> m = MsgTestCaseSkip()
>>> print(m)
 -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  - - -
Message representation:
 - - -
routing_key / topic : control.testcoordination
 - - -
_type : testcoordination.testcase.skip
testcase_id : TD_COAP_CORE_02_v01
 -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  - - -
>>> m.routing_key
'control.testcoordination'
>>> m.testcase_id
'TD_COAP_CORE_02_v01'
# also we can modify some of the fields (rewrite the default ones)
>>> m = MsgTestCaseSkip(testcase_id = 'TD_COAP_CORE_03_v01')
>>> m
 -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  - - -
Message representation:
 - - -
routing_key / topic : control.testcoordination
 - - -
_type : testcoordination.testcase.skip
testcase_id : TD_COAP_CORE_03_v01
 -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  - - -
>>> m.testcase_id
'TD_COAP_CORE_03_v01'
# and even export the message in json format (for example for sending the message though the amqp event bus)
>>> m.to_json()
'{"_type": "testcoordination.testcase.skip", "testcase_id": "TD_COAP_CORE_03_v01"}'
"""

from collections import OrderedDict
import json
import uuid
import logging

API_VERSION = '0.1.0'

# TODO use metaclasses instead?
# TODO Define also a reply method which provides amessage with routig key for the reply, correlation id, reply_to,etc


class NonCompliantMessageFormatError(Exception):

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)

class Message:

    def __init__(self,**kwargs):
        global API_VERSION

        # hard copy the message template
        self._msg_data = {k:v for k,v in self._msg_data_template.items()}

        # init properties
        self._properties = dict(
                content_type='application/json',
                message_id=str(uuid.uuid4()),
        )

        #if message is a service request then add some extra props
        if self.routing_key.endswith('.service'):
            self._properties['reply_to'] = '%s.%s'%(self.routing_key,'reply')
            self._properties['correlation_id'] = self._properties['message_id']

        # rewrite default metadata and data fields of the message instance
        self._msg_data.update(kwargs)

        # add API's version
        self._msg_data['_api_version'] = API_VERSION

        # add values as objects attributes
        for key in self._msg_data:
            setattr(self, key, self._msg_data[key])


    def to_dict(self) -> OrderedDict:
        resp = OrderedDict()
        for field in self._msg_data:
            resp[field] = getattr(self, field)
        # for readability
        resp.move_to_end('_type',False)

        return resp

    def to_json(self):
        return json.dumps(self.to_dict())

    def get_properties(self) -> dict:
        return self._properties

    def __str__(self):
        str = ' - '*20 + '\n'
        str += 'Message routing key: %s' %self.routing_key
        str += '\n'
        str += 'Message properties: %s'%json.dumps(self.get_properties())
        str += '\n'
        str += 'Message body: %s' %self.to_json()
        str += '\n' + ' - ' * 20
        return str

    @classmethod
    def from_json(cls, body):

        try:
            logging.debug('Converting json into a Message object..')
            message_dict = json.loads(body.decode('utf-8'))
            logging.debug('json: %s' %json.dumps(message_dict))
            message_type = message_dict['_type']
            if message_type in _message_types_dict:
                return _message_types_dict[message_type](**message_dict)
        except :
            raise NonCompliantMessageFormatError('Cannot load json message: %s'%str(body))


###### TEST COORDINATION MESSAGES ######

class MsgTestSuiteStart(Message):
    """
    Testing Tool MUST-implement API endpoint
    GUI -> Testing Tool
    """

    routing_key = "control.testcoordination"

    _msg_data_template = {
        '_type': "testcoordination.testsuite.start",
    }


class MsgTestCaseStart(Message):
    """
    Testing Tool MUST-implement API endpoint
    GUI -> Testing Tool
    Message used for indicating the testing tool to start the test case (the one previously selected)
    """
    routing_key = "control.testcoordination"

    _msg_data_template = {
        '_type': "testcoordination.testcase.start",
    }


class MsgTestCaseStop(Message):
    """
    Testing Tool MUST-implement API endpoint
    GUI -> Testing Tool
    Message used for indicating the testing tool to stop the test case (the one running)
    """

    routing_key = 'control.testcoordination'

    _msg_data_template = {
        '_type': 'testcoordination.testcase.stop',
    }


class MsgTestCaseRestart(Message):
    """
    Testing Tool MUST-implement API endpoint
    GUI -> Testing Tool
    """

    routing_key = 'control.testcoordination'

    _msg_data_template = {
        '_type': 'testcoordination.testcase.restart',
    }

#TODO step.execute event

class MsgStimuliExecuted(Message):
    """
    Testing Tool MUST-implement API endpoint
    GUI (or automated-IUT)-> Testing Tool
    """

    routing_key = 'control.testcoordination'

    _msg_data_template = {
        '_type': 'testcoordination.step.stimuli.executed',
    }


class MsgCheckResponse(Message):
    """
    Testing Tools'internal call.
    In the context of IUT to IUT test execution, this message is used for indicating that the previously executed
    messages (stimuli message and its reply) CHECK or comply to what is described in the Test Description.
    Testing tools' coordinator -> Testing Tool's analyzer (TAT)
    Not used in CoAP testing Tool (analysis of traces is done post mortem)
    """

    routing_key = 'control.testcoordination'


    _msg_data_template = {
        '_type': 'testcoordination.step.check.response',
        'partial_verdict':'pass',
        'description':'TAT says: step complies (checks) with specification'
    }


class MsgVerifyResponse(Message):
    """
    Testing Tool MUST-implement API endpoint
    Message provided by user declaring if the IUT VERIFY the step previously executed as described in the Test
    Description.
    GUI (or automated-IUT)-> Testing Tool
    """

    routing_key = 'control.testcoordination'

    _msg_data_template = {
        '_type': 'testcoordination.step.verify.response',
        'verify_response': True,
        'response_type': 'bool'
    }

class MsgTestCaseFinish(Message):
    """
    Testing Tool MUST-implement API endpoint
    GUI (or automated-IUT)-> Testing Tool
    Not used in CoAP Testing Tool (test coordinator deduces it automatically by using the testcase's step sequence)
    """

    routing_key = 'control.testcoordination'

    _msg_data_template = {
        '_type': 'testcoordination.testcase.finish',
    }

class MsgTestCaseSkip(Message):
    """
    Testing Tool MUST-implement API endpoint
    GUI (or automated-IUT)-> Testing Tool
    """

    routing_key = 'control.testcoordination'

    _msg_data_template = {
        '_type': 'testcoordination.testcase.skip',
        'testcase_id': 'TD_COAP_CORE_02_v01',
    }


class MsgTestCaseSelect(Message):
    """
    Testing Tool MUST-implement API endpoint
    GUI (or automated-IUT)-> Testing Tool
    """

    routing_key = 'control.testcoordination'

    _msg_data_template = {
        '_type': 'testcoordination.testcase.select',
        'testcase_id': 'TD_COAP_CORE_03_v01',
    }

class MsgTestSuiteAbort(Message):
    """
    Testing Tool MUST-implement API endpoint
    GUI (or automated-IUT)-> Testing Tool
    """

    routing_key = 'control.testcoordination'

    _msg_data_template = {
        '_type': 'testcoordination.testsuite.abort',
    }

class MsgTestSuiteGetStatus(Message):
    """
    Testing Tool SHOULD-implement API entrypoint
    Describes current state of the test suite.
    Format for the response not standardised.

    GUI -> Testing Tool

    GUI MUST implement
    """

    routing_key = 'control.testcoordination.service'

    _msg_data_template = {
        '_type': 'testcoordination.testsuite.getstatus',
    }

class MsgTestSuiteGetTestCases(Message):
    """
    Testing Tool's MUST-implement API entrypoint
    GUI -> Testing Tool
    GUI MUST implement
    """

    routing_key = 'control.testcoordination.service'

    _msg_data_template = {
        '_type': 'testcoordination.testsuite.gettestcases',
    }

###### SNIFFING SERVICES REQUEST MESSAGES ######

class MsgSniffingStart(Message):
    """
    Testing Tools'internal call.
    Coordinator -> Sniffer
    Testing Tool SHOULD implement (design recommendation)
    """

    routing_key = 'control.sniffing.service'

    _msg_data_template = {
        '_type': 'sniffing.start',
        'capture_id': 'TD_COAP_CORE_01',
        'filter_if': 'tun0',
        'filter_proto': 'udp port 5683'
    }

class MsgSniffingStop(Message):
    """
    Testing Tools'internal call.
    Coordinator -> Sniffer
    Testing Tool SHOULD implement (design recommendation)
    """

    routing_key = 'control.sniffing.service'

    _msg_data_template = {
        '_type': 'sniffing.stop',
    }

class MsgSniffingGetCapture(Message):
    """
    Testing Tools'internal call.
    Coordinator -> Sniffer
    Testing Tool SHOULD implement (design recommendation)
    """

    routing_key = 'control.sniffing.service'

    _msg_data_template = {
        '_type': 'sniffing.getcapture',
        "get_last": False,
        "capture_id": "TD_COAP_CORE_01",

    }

class MsgSniffingGetCaptureLast(Message):
    """
    Testing Tools'internal call.
    Coordinator -> Sniffer
    Testing Tool SHOULD implement (design recommendation)
    """

    routing_key ='control.sniffing.service'

    _msg_data_template = {
        '_type': 'sniffing.getlastcapture',
    }

###### ANALYSIS SERVICES REQUESTS MESSAGES ######

class MsgAnalysisTestCaseAnalyze(Message):
    """
    Testing Tools'internal call.
    Coordinator -> Analyzer
    Testing Tool SHOULD implement (design recommendation)
    """

    PCAP_empty_base64 = '1MOyoQIABAAAAAAAAAAAAMgAAAAAAAAA'

    routing_key = 'control.analysis.service'

    _msg_data_template = {
        '_type': 'analysis.testcase.analyze',
        "testcase_id": "TD_COAP_CORE_01",
        "testcase_ref": "http://f-interop.paris.inria.fr/tests/TD_COAP_CORE_01_v01",
        "file_enc": "pcap_base64",
        "filename": "TD_COAP_CORE_01.pcap",
        "value": PCAP_empty_base64,
    }

###### DISSECTION SERVICES REQUESTS MESSAGES ######
class MsgDissectionDissectCapture(Message):
    """
    Testing Tools'internal call.
    Coordinator -> Dissector
    and
    Analyzer -> Dissector
    Testing Tool SHOULD implement (design recommendation)
    """

    PCAP_COAP_GET_OVER_TUN_INTERFACE_base64 = "1MOyoQIABAAAAAAAAAAAAMgAAABlAAAAqgl9WK8aBgA7AAAAOwAAAGADPxUAExFAu7s" \
                                              "AAAAAAAAAAAAAAAAAAbu7AAAAAAAAAAAAAAAAAALXvBYzABNZUEABcGO0dGVzdMECqg" \
                                              "l9WMcaBgCQAAAAkAAAAGAAAAAAaDr//oAAAAAAAAAAAAAAAAAAA7u7AAAAAAAAAAAAA" \
                                              "AAAAAGJAAcTAAAAALu7AAAAAAAAAAAAAAAAAAK7uwAAAAAAAAAAAAAAAAACBAgAAAAA" \
                                              "AABgAz8VABMRQLu7AAAAAAAAAAAAAAAAAAG7uwAAAAAAAAAAAAAAAAAC17wWMwATWVB" \
                                              "AAXBjtHRlc6oJfVjSGgYAOwAAADsAAABgAz8VABMRP7u7AAAAAAAAAAAAAAAAAAG7uw" \
                                              "AAAAAAAAAAAAAAAAAC17wWMwATWVBAAXBjtHRlc3TBAg=="

    routing_key = 'control.dissection.service'

    _msg_data_template = {
        '_type': 'dissection.dissectcapture',
        "file_enc": "pcap_base64",
        "filename": "TD_COAP_CORE_01.pcap",
        "value": PCAP_COAP_GET_OVER_TUN_INTERFACE_base64,
        "protocol_selection": 'coap',
    }


_message_types_dict = {
    "testcoordination.testsuite.start": MsgTestSuiteStart,
    "testcoordination.testcase.start": MsgTestCaseStart,
    "testcoordination.testcase.stop": MsgTestCaseStop,
    "testcoordination.testcase.restart": MsgTestCaseRestart,
    "testcoordination.step.stimuli.executed": MsgStimuliExecuted,
    "testcoordination.step.check.response": MsgCheckResponse,
    "testcoordination.step.verify.response": MsgVerifyResponse,
    "testcoordination.testcase.finish": MsgTestCaseFinish,
    "testcoordination.testcase.skip": MsgTestCaseSkip,
    "testcoordination.testcase.select": MsgTestCaseSelect,
    "testcoordination.testsuite.abort": MsgTestSuiteAbort,
    "testcoordination.testsuite.getstatus": MsgTestSuiteGetStatus,
    "testcoordination.testsuite.gettestcases": MsgTestSuiteGetTestCases,
    "sniffing.start": MsgSniffingStart,
    "sniffing.stop": MsgSniffingStop,
    "sniffing.getcapture": MsgSniffingGetCapture,
    "analysis.testcase.analyze": MsgAnalysisTestCaseAnalyze,
    "dissection.dissectcapture": MsgDissectionDissectCapture,
}


if __name__ == '__main__':
    # m1=MsgTestCaseStart()
    # print(json.dumps(m1.to_dict()))
    # print(m1.routing_key)
    # print(m1.to_json())
    # print(m1)

    m1 = MsgTestCaseStart( hola = 'verano')
    m2 = MsgTestCaseStart()
    #m2 = MsgTestCaseStart(routing_key = 'lolo', hola='verano')

    print(m1)
    print(m1.to_json())
    print(m1._msg_data)

    print(m2)
    print(m2.to_json())
    print(m2._msg_data)
    #
    # m2=MsgTestSuiteStart()
    # print(json.dumps(m2.to_dict()))
    # print(m2.routing_key)
    # print(m2.to_json())
    # print(m2)
    #
    # m3=MsgTestCaseStop()
    # print(json.dumps(m3.to_dict()))
    # print(m3.routing_key)
    # print(m3.to_json())
    # print(m3)

    j = json.dumps({
        '_type': 'dissection.dissectcapture',
        "file_enc": "pcap_base64",
        "filename": "TD_COAP_CORE_01.pcap",
        "protocol_selection": 'coap',
    })
    r = Message.from_json(j)
    print(type(r))
    print(r)

