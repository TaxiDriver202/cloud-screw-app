#!/usr/bin/env -S uv run --script

# /// script
# dependencies = ["requests"]
# ///

import os
import requests
from random import randint

url = "http://0.0.0.0:8000/request"
headers = {"Authorization": os.getenv("RUUVIDASH_API_KEY", "wapi_676767") }


tags = { "data": { 
           "gwmac": "14:AB:53:BC:53",
            "tags": {
                "12:AB:34": {
                    "mac": "12:AB:34",
                    "temperature": randint(-10, -5),
                    "humidity": randint(25, 80),
                    "pressure": randint(80000, 100000)
                },
                "34:BC:45": {
                    "mac": "34:BC:45",
                    "temperature": randint(10, 25),
                    "humidity": randint(30, 70),
                    "pressure": randint(70000, 100000)
                },
                "42:DB:74": {
                    "mac": "42:DB:74",
                    "temperature": randint(0, 10),
                    "humidity": randint(25, 80),
                    "pressure": randint(60000, 100000)
                }
            }
        }
}

r = requests.post(url, json=tags, headers=headers)
print(r.json())
