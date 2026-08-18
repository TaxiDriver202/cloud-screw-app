#!/usr/bin/env -S uv run --script

# /// script
# dependencies = ["requests"]
# ///

import os
from random import randint

import requests

url = "http://0.0.0.0:8000/request"
headers = {"Authorization": os.getenv("RUUVIDASH_API_KEY", "wapi_676767")}


tags = {
    "data": {
        "gw_mac": "14:AB:53:BC:53",
        "tags": {
            "12:AB:34": {
                "id": "12:AB:34",
                "temperature": randint(-10, -5),
                "humidity": randint(25, 80),
                "pressure": randint(80000, 100000),
                "accelX": randint(-1000, 1000),
                "accelY": randint(-1000, 1000),
                "accelZ": randint(-1000, 1000),
            },
            "34:BC:45": {
                "id": "34:BC:45",
                "temperature": randint(10, 25),
                "humidity": randint(30, 70),
                "pressure": randint(70000, 100000),
                "accelX": randint(-1000, 1000),
                "accelY": randint(-1000, 1000),
                "accelZ": randint(-1000, 1000),
            },
            "42:DB:74": {
                "id": "42:DB:74",
                "temperature": randint(0, 10),
                "humidity": randint(25, 80),
                "pressure": randint(60000, 100000),
                "accelX": randint(-1000, 1000),
                "accelY": randint(-1000, 1000),
                "accelZ": randint(-1000, 1000),
            },
        },
    }
}

r = requests.post(url, json=tags, headers=headers)
print(r.json())
