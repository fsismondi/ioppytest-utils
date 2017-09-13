import logging
import os
import base64


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


def get_from_environment(variable, default):
    if variable in os.environ:
        v = os.environ.get(variable)
        logging.info("Using environment variable %s=%s" % (variable, default))
    else:
        v = default
        logging.warning("Using default variable %s=%s" % (variable, default))
    return v


if __name__ == '__main__':
    # example of use for save_pcap_from_base64 function
    #base_64_pcap_value = '1MOyoQIABAAAAAAAAAAAAMgAAABlAAAASJQxWTqkAwA5AAAAOQAAAGAOcR8AERFAu7sAAAAAAAAAAAAAAAAAAbu7AAAAAAAAAAAAAAAAAALk2RYzABGuhFAEANS0dGVzdA=='
    from examples_pcap_base64 import PCAP_COAP_TC4_OVER_TUN_INTERFACE_base64
    base_64_pcap_value = PCAP_COAP_TC4_OVER_TUN_INTERFACE_base64
    save_pcap_from_base64('test.pcap', base_64_pcap_value)
