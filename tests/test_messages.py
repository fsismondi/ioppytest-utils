# -*- coding: utf-8 -*-
# !/usr/bin/env python3
import unittest
import pika
import os

from messages import *
from event_bus_utils import publish_message

import logging

logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)
logging.getLogger('pika').setLevel(logging.WARNING)

AMQP_EXCHANGE = str(os.environ['AMQP_EXCHANGE'])
AMQP_URL = str(os.environ['AMQP_URL'])


class MessagesLibraryTests(unittest.TestCase):
    """
    python3 -m unittest tests/test_messages.py -vvv
    """

    def setUp(self):

        # let's collect all the messages classes
        self.set_of_collected_messages = {v for (k, v) in globals().items() if 'Msg' in k}
        self.non_serializable_messages_types = {MsgReply, MsgErrorReply}
        self.serializable_messages_types = self.set_of_collected_messages - self.non_serializable_messages_types

        # amqp stuff
        self.conn = pika.BlockingConnection(pika.URLParameters(AMQP_URL))
        self.channel = self.conn.channel()

        # message validation queue
        self.queue_for_post_validation = '%s::queue_for_post_validation' % self.__class__.__name__

        # lets' first clean up the queue
        self.channel.queue_delete(queue=self.queue_for_post_validation)
        self.channel.queue_declare(queue=self.queue_for_post_validation, auto_delete=True)

        # subscribe to all messages in the bus
        self.channel.queue_bind(exchange=AMQP_EXCHANGE, queue=self.queue_for_post_validation, routing_key='#')
        self.channel.basic_qos(prefetch_count=1)

    def tearDown(self):
        self.conn.close()

    def test_serialize_and_deserialize_messages_on_bus(self):
        self.serialize_and_publish_all_messages()
        self.consume_and_deserialize_messages()

    def serialize_and_publish_all_messages(self):
        for i in self.serializable_messages_types:
            try:
                m = i()
            except Exception as e:
                self.fail('%s found, while serializing %s' % (e, str(i)))

            logging.info("publishing message type %s" % str(type(m)))
            publish_message(
                self.conn,
                m
            )

    def consume_and_deserialize_messages(self):

        time.sleep(1)
        message_count = 0

        method, props, body = self.channel.basic_get(self.queue_for_post_validation)

        while method:
            message_count += 1
            logging.info('parsing message %s, number: %s' % (method.routing_key,message_count))
            self.channel.basic_ack(method.delivery_tag)

            # api call 1 - load w/o properties
            message = Message.load(
                json_body=body.decode('utf-8'),
                routing_key=method.routing_key,
                properties=None,

            )

            assert message, 'load w/o properties didnt work for %s' % (body.decode('utf-8'), method.routing_key)

            # api call 2 - load w/ properties
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

            message = Message.load(
                json_body=body.decode('utf-8'),
                routing_key=method.routing_key,
                properties=props_dict,

            )
            assert message, 'load WITH properties didnt work for %s' % (body.decode('utf-8'), method.routing_key)

            # api call 3 - load using pika dependent api call
            message = Message.load_from_pika(
                method,
                props,
                body,
            )
            #print(repr(message))
            assert message, 'load pika properties didnt work for %s' % (body.decode('utf-8'), method.routing_key)

            method, props, body = self.channel.basic_get(self.queue_for_post_validation)

        if len(self.serializable_messages_types) != message_count:
            self.fail('expecting %s messages, but got %s' % (len(self.serializable_messages_types), message_count))
