from messages import *

PERF_TT_CONFIGURATION = {
    "testing_tools": "http://orchestrator.f-interop.eu:8181/tests/f-interop/performance-coapclient",
    "tests": [],
    "iuts": [],
    "users": [
        "u1",
        "f-interop"
    ],
    "configuration": {
        "segments": [
            {
                "duration": "10",
                "values": {
                    "coapclient.clients": [
                        "1",
                        "constant"
                    ],
                    "impairment.delay_variation": [
                        "0.0",
                        "constant"
                    ],
                    "impairment.corrupt": [
                        "0.0",
                        "constant"
                    ],
                    "impairment.delay_correlation": [
                        "0.0",
                        "constant"
                    ],
                    "coapclient.request_rate": [
                        "1.0",
                        "constant"
                    ],
                    "impairment.delay": [
                        "0.0",
                        "constant"
                    ],
                    "monitoring.energy_coefficient": [
                        "0.0",
                        "constant"
                    ],
                    "impairment.duplicate": [
                        "0.0",
                        "constant"
                    ],
                    "impairment.loss_correlation": [
                        "0.0",
                        "constant"
                    ],
                    "impairment.loss": [
                        "0.0",
                        "constant"
                    ],
                    "impairment.delay_distribution": [
                        "uniform",
                        "constant"
                    ]
                },
                "name": "Segment 1"
            }
        ],
        "initial": {
            "coapclient.clients": "1",
            "impairment.delay_variation": "0.0",
            "impairment.corrupt": "0.0",
            "impairment.delay_correlation": "0.0",
            "coapclient.request_rate": "1.0",
            "impairment.delay": "0.0",
            "monitoring.energy_coefficient": "0.0",
            "impairment.duplicate": "0.0",
            "impairment.loss_correlation": "0.0",
            "impairment.loss": "0.0",
            "impairment.delay_distribution": "uniform"
        },
        "static": {
            "coapclient.dst_address": "195.176.0.157",
            "coapclient.request_sequence": [
                {
                    "body": "",
                    "path": "/temperature_21",
                    "type": "GET"
                }
            ],
            "coapclient.dst_port": "5684",
            "coapclient.request_timeout": "1000",
            "coapclient.adjust_rate": False,
            "coapclient.src_port": "10000"
        }
    }
}

#message_configuration_example = MsgSessionConfiguration(**PERF_TT_CONFIGURATION)
