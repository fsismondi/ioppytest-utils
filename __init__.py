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
    #from examples_pcap_base64 import PCAP_COAP_TC4_OVER_TUN_INTERFACE_base64,PCAP_ONEM2M_TD_M2M_NH_06
    #base_64_pcap_value = "1MOyoQIABAAAAAAAAAAAAMgAAABlAAAAuDomWkVbCQCLAAAAiwAAAGABrlcAYxFAu7sAAAAAAAAAAAAAAAAAAbu7AAAAAAAAAAAAAAAAAAKOoRYzAGM/fEQC7BP7dUmTsX4Gc2VydmVyBnNlcnZlchEyUTLR4kMWMTAwNDg2oQL/eyJtMm06YWUiOnsicnIiOmZhbHNlLCJhcGkiOjEyMzQ1LCJybiI6ImFlVGVzdEMifX24OiZavKEKAMgAAAAyAgAAYAjkQQIKEUC7uwAAAAAAAAAAAAAAAAACu7sAAAAAAAAAAAAAAAAAARYzjqECCqBwZEHsE/t1SZONES9zZXJ2ZXIvQ0FFMTMxMjU0MDI5MDMwNzk4NjM0M0Ey1ugxMDA0ODaCB9H/ewogICAibTJtOmFlIiA6IHsKICAgICAgInJuIiA6ICJhZVRlc3RDIiwKICAgICAgInR5IiA6IDIsCiAgICAgICJyaSIgOiAiL3NlcnZlci9DQUUxMzEyNTQwMjkwMzA3OTg="
    base_64_pcap_value = "1MOyoQIABAAAAAAAAAAAAMgAAABlAAAAk9MmWiSMDgCLAAAAiwAAAGABhdIAYxFAu7sAAAAAAAAAAAAAAAAAAru7AAAAAAAAAAAAAAAAAAGeoBYzAGMRfUQCGw2HLKvhsX4Gc2VydmVyBnNlcnZlchEyUTLR4kMWMTAwMzk5oQL/eyJtMm06YWUiOnsicnIiOmZhbHNlLCJhcGkiOjEyMzQ1LCJybiI6ImFlVGVzdEMifX2U0yZaDxsAAMgAAAAzAgAAYAQl6AILEUC7uwAAAAAAAAAAAAAAAAABu7sAAAAAAAAAAAAAAAAAAhYznqACC63hZEEbDYcsq+GNES9zZXJ2ZXIvQ0FFMzEzNTI5MDgyMzA2NDI1ODY2OEEy1ugxMDAzOTmCB9H/ewogICAibTJtOmFlIiA6IHsKICAgICAgInJuIiA6ICJhZVRlc3RDIiwKICAgICAgInR5IiA6IDIsCiAgICAgICJyaSIgOiAiL3NlcnZlci9DQUUzMTM1MjkwODIzMDY0MjU="
    save_pcap_from_base64('test2.pcap', base_64_pcap_value)
