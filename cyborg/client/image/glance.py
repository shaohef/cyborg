#!/usr/bin/python

import requests
import json
import os
import random
import uuid as uuidlib
import sys


HOST = "127.0.0.1"
HOSTURL = "http://%s" % HOST
BASEURL = "http://%s/image" % HOST


def pretty_print(r):
    if not r.ok:
        print r.content
        return
    data = r.json()
    res = json.dumps(data, sort_keys=True, indent=4, separators=(',', ': '))
    print res
    return data

# OP for glance
def get_all_fpga_image(token, url=BASEURL, **payload):
    """payload = {'tag': 'FPGA'}"""
    HEADERS = {"Content-Type": "application/json",
               "X-Auth-Token": token}
    params = {'tag': 'FPGA'}
    params.update(payload)
    url = url + "/v2/images"
    r = requests.get(url, headers=HEADERS, params=params)
    if r.ok:
       return r.json()
    # res = pretty_print(r)
    else:
        print r.content


def download_fpga_image(token, uuid, url=BASEURL,
                        filepath="/tmp/cyborg/image", **payload):
    """payload = {'tag': 'FPGA'}"""
    HEADERS = {"Content-Type": "application/json",
               "X-Auth-Token": token}
    params = {}
    params.update(payload)
    url = os.path.join(url, "v2/images", uuid, "file")

    r = requests.get(url, headers=HEADERS, params=params, stream=True)
    if not r.ok:
        print r.content

    if not os.path.lexists(filepath):
        os.makedirs(filepath)
    filename = os.path.join(filepath, uuid)
    with open(filename, 'wb') as fd:
        for chunk in r.iter_content(chunk_size=1024):
            fd.write(chunk)
