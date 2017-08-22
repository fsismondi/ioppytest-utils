import six
import pika
import threading
import logging
from datetime import timedelta, datetime
import os
from messages import *
from pure_pcapy import Dumper, Pkthdr, DLT_IEEE802_15_4, DLT_RAW


class AmqpDataPacketDumper(threading.Thread):
    """
    Sniffs data.serial and dumps into pcap file (assumes that frames are DLT_IEEE802_15_4)
    Sniffs data.tun and dumps into pcap file (assumes that frames are DLT_IEEE802_15_4)

    about pcap header:
        ts_sec: the date and time when this packet was captured. This value is in seconds since January 1, 1970 00:00:00 GMT; this is also known as a UN*X time_t. You can use the ANSI C time() function from time.h to get this value, but you might use a more optimized way to get this timestamp value. If this timestamp isn't based on GMT (UTC), use thiszone from the global header for adjustments.
        ts_usec: in regular pcap files, the microseconds when this packet was captured, as an offset to ts_sec. In nanosecond-resolution files, this is, instead, the nanoseconds when the packet was captured, as an offset to ts_sec /!\ Beware: this value shouldn't reach 1 second (in regular pcap files 1 000 000; in nanosecond-resolution files, 1 000 000 000); in this case ts_sec must be increased instead!
        incl_len: the number of bytes of packet data actually captured and saved in the file. This value should never become larger than orig_len or the snaplen value of the global header.
        orig_len: the length of the packet as it appeared on the network when it was captured. If incl_len and orig_len differ, the actually saved packet size was limited by snaplen.
    """
    COMPONENT_ID = 'capture_dumper'

    def __init__(self, connection, topics):
        threading.Thread.__init__(self)
        # queues & default exchange declaration
        self.messages_dumped = 0

        self.connection = connection

        self.channel = self.connection.channel()

        self.data_queue_name = 'data@%s' % self.COMPONENT_ID
        self.channel.queue_declare(queue=self.data_queue_name, auto_delete=True)

        for t in topics:
            self.channel.queue_bind(exchange=AMQP_EXCHANGE,
                                    queue=self.data_queue_name,
                                    routing_key=t)

        # Hello world message
        self.channel.basic_publish(
            body=json.dumps({'_type': '%s.info' % self.COMPONENT_ID,
                             'value': '%s is up!' % self.COMPONENT_ID, }
                            ),
            routing_key='control.%s.info' % self.COMPONENT_ID,
            exchange=AMQP_EXCHANGE,
            properties=pika.BasicProperties(
                content_type='application/json',
            )
        )

        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(self.on_request, queue=self.data_queue_name)

        datetime_string = time.strftime("%Y%m%d_%H%M")
        network_type = "DLT_IEEE802_15_4"
        self.pcap_15_4_dumper = Dumper(
            filename="{0}_{1}.pcap".format(datetime_string, network_type),
            snaplen=200,
            network=DLT_IEEE802_15_4
        )

        network_type = "DLT_RAW"
        self.pcap_raw_ip_dumper = Dumper(
            filename="{0}_{1}.pcap".format(datetime_string, network_type),
            snaplen=200,
            network=DLT_RAW
        )

    def stop(self):
        self.channel.queue_delete(self.data_queue_name)
        self.channel.stop_consuming()
        self.connection.close()

    def on_request(self, ch, method, props, body):
        now = datetime.now()
        # obj hook so json.loads respects the order of the fields sent -just for visualization purposeses-
        req_body_dict = json.loads(body.decode('utf-8'), object_pairs_hook=OrderedDict)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        logging.info("Message sniffed: %s, body: %s" % (json.dumps(req_body_dict), str(body)))
        self.messages_dumped += 1

        try:

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

            m = Message.from_json(body)
            m.update_properties(**props_dict)

            if isinstance(m, MsgTestingToolTerminate):
                ch.stop_consuming()
                self.stop()

            if isinstance(m, MsgPacketSniffedRaw):
                try:
                    if 'serial' in m.interface_name:
                        raw_packet = bytes(m.data)
                        packet_slip = bytes(m.data_slip)

                        # lets build pcap header for packet
                        pcap_packet_header = Pkthdr(
                            ts_sec=now.second,
                            ts_usec=now.microsecond,
                            incl_len=len(raw_packet),
                            orig_len=len(raw_packet),
                        )
                        self.pcap_15_4_dumper.dump(pcap_packet_header, raw_packet)

                    elif 'tun' in m.interface_name:
                        raw_packet = bytes(m.data)

                        # lets build pcap header for packet
                        pcap_packet_header = Pkthdr(
                            ts_sec=now.second,
                            ts_usec=now.microsecond,
                            incl_len=len(raw_packet),
                            orig_len=len(raw_packet),
                        )
                        self.pcap_raw_ip_dumper.dump(pcap_packet_header, raw_packet)

                    else:
                        logging.info('raw packet not dumped to pcap: ' + repr(m))

                except TypeError as e:
                    logging.error(str(e))
                    logging.error(repr(m))


            else:
                logging.info('drop amqp message: ' + repr(m))

        except NonCompliantMessageFormatError as e:
            print('* * * * * * API VALIDATION ERROR * * * * * * * ')
            print("AMQP MESSAGE LIBRARY COULD PROCESS JSON MESSAGE")
            print('* * * * * * * * * * * * * * * * * * * * * * * * *  \n')
            raise NonCompliantMessageFormatError("AMQP MESSAGE LIBRARY COULD PROCESS JSON MESSAGE")

    def run(self):
        print("Starting thread listening on the event bus")
        self.channel.start_consuming()
        print('Bye byes!')


if __name__ == '__main__':

    MESSAGE_UI_SELECTOR = 1

    logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)

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
            "Env variables imported for AMQP connection, User: {0} @ Server: {1} ".format(AMQP_USER,
                                                                                          AMQP_SERVER))

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

    # start pcap dumper
    pcap_amqp_topic_subscriptions = ['data.serial.fromAgent.coap_client_agent',
                                     'data.serial.fromAgent.coap_server_agent',
                                     'data.tun.fromAgent.coap_server_agent',
                                     'data.tun.fromAgent.coap_client_agent',
                                     ]
    pcap_dumper = AmqpDataPacketDumper(
        connection=connection,
        topics=pcap_amqp_topic_subscriptions
    )
    pcap_dumper.start()
