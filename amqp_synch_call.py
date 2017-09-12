import six
import os
import pika
import time
import logging
import threading
from binascii import unhexlify
from datetime import datetime

from messages import *

VERSION = '0.0.3'

try:
    AMQP_EXCHANGE = str(os.environ['AMQP_EXCHANGE'])
except KeyError as e:
    print('couldnt import AMQP_EXCHANGE from environment')
    AMQP_EXCHANGE = "default"

try:
    AMQP_URL = str(os.environ['AMQP_URL'])
except KeyError as e:
    print('couldnt import AMQP_URL from environment')
    AMQP_URL = "amqp://guest:guest@localhost/"


def publish_message(channel, message):
    """ Published which uses message object metadata

    :param channel:
    :param message:
    :return:
    """

    properties = pika.BasicProperties(**message.get_properties())

    channel.basic_publish(
        exchange=AMQP_EXCHANGE,
        routing_key=message.routing_key,
        properties=properties,
        body=message.to_json(),
    )


def amqp_request(channel, request_message, component_id):
    """
    NOTE: channel must be a pika channel
    """

    global AMQP_EXCHANGE

    # check first that sender didnt forget about reply to and corr id
    assert request_message.reply_to
    assert request_message.correlation_id

    if AMQP_EXCHANGE is None:
        AMQP_EXCHANGE = 'amq.topic'

    response = None

    reply_queue_name = 'amqp_rpc_%s@%s' % (str(uuid.uuid4())[:8], component_id)

    result = channel.queue_declare(queue=reply_queue_name, auto_delete=True)

    callback_queue = result.method.queue

    # bind and listen to reply_to topic
    channel.queue_bind(
        exchange=AMQP_EXCHANGE,
        queue=callback_queue,
        routing_key=request_message.reply_to
    )

    channel.basic_publish(
        exchange=AMQP_EXCHANGE,
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

    # clean up
    channel.queue_delete(reply_queue_name)

    return response




if __name__ == '__main__':
    logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.WARNING)

    # m = MsgSniffingGetCapture()
    # r = amqp_request(m, 'someImaginaryComponent')
    # print(repr(r))

    try:
        AMQP_EXCHANGE = str(os.environ['AMQP_EXCHANGE'])
        print('Imported AMQP_EXCHANGE env var: %s' % AMQP_EXCHANGE)

    except KeyError as e:
        AMQP_EXCHANGE = "amq.topic"
        print('Cannot retrieve environment variables for AMQP EXCHANGE. Loading default: %s' % AMQP_EXCHANGE)

    try:
        AMQP_URL = str(os.environ['AMQP_URL'])
        print('Imported AMQP_URL env var: %s' % AMQP_URL)

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


