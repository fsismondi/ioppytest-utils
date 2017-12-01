import os
import pika
import logging
import threading

# for using it as library and as a __main__
try:
    from messages import *
except:
    from .messages import *

VERSION = '0.0.8'
AMQP_EXCHANGE = 'amq.topic'


class AmqpSynchCallTimeoutError(Exception):
    pass


class AmqpListener(threading.Thread):
    COMPONENT_ID = 'amqp_listener_%s' % uuid.uuid1()
    DEFAULT_TOPIC_SUSBCRIPTIONS = ['#']
    DEFAULT_EXCHAGE = 'amq.topic'

    def __init__(self, amqp_url, amqp_exchange, callback, topics=None):

        threading.Thread.__init__(self)

        if callback is None:
            self.message_dispatcher = print
        else:
            self.message_dispatcher = callback

        self.connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
        self.channel = self.connection.channel()

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
            self.topics = topics
        else:
            self.topics = self.DEFAULT_EXCHAGE

        for t in self.topics:
            self.channel.queue_bind(exchange=self.exchange,
                                    queue=self.services_queue_name,
                                    routing_key=t)

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
            self.message_dispatcher(m)

        except NonCompliantMessageFormatError as e:
            logging.error('%s got a non compliant message error %s' % (self.__class__.__name__, e))

        except Exception as e:
            logging.error(e)
            logging.error('message received:\n\tr_key: %s\n\t%s'%(method.routing_key,body))

        finally:
            ch.basic_ack(delivery_tag=method.delivery_tag)

    def run(self):
        logging.info("Starting thread listening on the event bus on topics %s" % self.topics)
        for i in range(1, 4):
            try:
                self.channel.start_consuming()
            except pika.exceptions.ConnectionClosed as err:
                logging.error('Unexpected connection closed, retrying %s/%s' % (i, 4))
                logging.error(err)

        logging.info('Bye byes!')


def publish_message(connection, message):
    """
    Publishes message into the correct topic (uses Message object metadata)
    Creates temporary channel on it's own
    Connection must be a pika.BlockingConnection
    """
    channel = None

    try:
        channel = connection.channel()

        properties = pika.BasicProperties(**message.get_properties())

        channel.basic_publish(
            exchange=AMQP_EXCHANGE,
            routing_key=message.routing_key,
            properties=properties,
            body=message.to_json(),
        )

    finally:
        if channel and channel.is_open:
            channel.close()


def amqp_request(connection, request_message, component_id):
    """
    Publishes message into the correct topic (uses Message object metadata)
    Returns reply message.
    Uses reply_to and corr id amqp's properties for matching the reply
    Creates temporary channel, and queues on it's own
    Connection must be a pika.BlockingConnection
    """

    # check first that sender didnt forget about reply to and corr id
    assert request_message.reply_to
    assert request_message.correlation_id

    channel = None

    try:
        response = None
        reply_queue_name = 'amqp_rpc_%s@%s' % (str(uuid.uuid4())[:8], component_id)

        channel = connection.channel()
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
        retries_left = 10

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
            # clean up
            channel.queue_delete(reply_queue_name)
            raise AmqpSynchCallTimeoutError(
                "Response timeout! rkey: %s , request type: %s" % (
                    request_message.routing_key,
                    request_message._type
                )
            )

        return response

    finally:
        if channel and channel.is_open:
            # clean up
            channel.queue_delete(reply_queue_name)
            channel.close()


if __name__ == '__main__':

    try:
        AMQP_EXCHANGE = str(os.environ['AMQP_EXCHANGE'])
    except KeyError as e:
        AMQP_EXCHANGE = "amq.topic"

    try:
        AMQP_URL = str(os.environ['AMQP_URL'])
        print('Env vars for AMQP connection succesfully imported')

    except KeyError as e:
        AMQP_URL = "amqp://guest:guest@localhost/"


    def callback_function(message_received):
        print("Callback function received: \n\t" + repr(message_received))


    # amqp listener example:
    amqp_listener_thread = AmqpListener(
        amqp_url=AMQP_URL,
        amqp_exchange=AMQP_EXCHANGE,
        callback=callback_function,
        topics='#'
    )

    try:
        amqp_listener_thread.start()
    except Exception as e:
        print(e)

    # publish message example
    retries_left = 3
    while retries_left > 0:
        try:
            connection = pika.BlockingConnection(pika.URLParameters(AMQP_URL))
            m = MsgTest()
            publish_message(connection, m)
            break
        except pika.exceptions.ConnectionClosed:
            retries_left -= 1
            print('retrying..')
            time.sleep(0.2)

    # example of a request sent into the bus
    m = MsgTestSuiteGetTestCases()
    try:
        r = amqp_request(connection, m, 'someImaginaryComponent')
        print("This is the response I got:\n\t" + repr(r))

    except AmqpSynchCallTimeoutError as e:
        print("Nobody answered to our request :'(")
