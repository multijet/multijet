#!/usr/bin/python
import json
import socket
import struct
import os
import netifaces
import fpm_pb2 as fpm
import time
import logging
import redis

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.INFO)
handler = logging.FileHandler("/tmp/fpmlog")
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

ifaces = netifaces.interfaces()
ifaces.remove('eth0')
ifaces.remove('lo')

r = redis.Redis(host='localhost', port=6379, db=0)


# fpm nexthop interface id to ovs port id, eg: 9 -> 2 means #9 is i0, ofport is e0 id = 1
def ifIdtoPortId(ifId):
    if ifId > 100:  # it's docker bridge
        return None

    for iface in ifaces:
        with open('/sys/class/net/' + iface + '/ifindex') as f:
            ifindex = f.read()
            if int(ifindex) == ifId:
                idx = iface[1:]
                return 2 * int(idx) + 1

    return None


def add_flow(dst, output):
    if dst == '10.0.0.0/24':
        actions = 'mod_dl_dst:00:00:00:00:00:01' + ',output:' + output
    elif dst == '10.0.1.0/24':
        actions = 'mod_dl_dst:00:00:00:00:00:02' + ',output:' + output
    else:
        actions = 'output:' + output

    cmd = 'ovs-ofctl add-flow s table=100,ip,nw_dst=' + dst + ',actions=' + actions
    logger.info(cmd)
    os.system(cmd)
    cmd = 'ovs-ofctl add-flow s table=100,arp,arp_tpa=' + dst + ',actions=' + actions
    logger.info(cmd)
    os.system(cmd)
    r.publish('add_rule', json.dumps({
        'match': {'ipv4_dst': [dst[:-3], '255.255.255.0']},
        'action': {
            'output': int(output)
        }
    }))


def bytes2Ip(bts):
    for i in range(len(bts), 4):
        bts += '\0'

    return '.'.join("{:d}".format(ord(x)) for x in bts)


# table 1 is pvv, pvv table should be controlled by controller
# cmd = 'ovs-ofctl add-flow s table=0,priority=0,actions=resubmit\(,1\)'
# os.system(cmd)

addr = ('127.0.0.1', 2620)
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(addr)
s.listen(10)
flow_count = 1
while True:
    conn, addr = s.accept()
    logger.info("new conn")

    while True:
        try:
            data = conn.recv(4)
            d = bytearray(data)
            x, y, size = struct.unpack(">ccH", d)
            body = conn.recv(size - 4)
            m = fpm.Message()
            m.ParseFromString(body)
            logger.info(m)
            if m.add_route:
                dst = bytes2Ip(m.add_route.key.prefix.bytes) + '/' + str(m.add_route.key.prefix.length)
                output = ifIdtoPortId(m.add_route.nexthops[0].if_id.index)
                if output is not None:
                    add_flow(dst, str(output))
                    logger.info(str(flow_count))
                    flow_count = flow_count + 1
        except (SystemExit, KeyboardInterrupt):
            raise
        except Exception:
            logger.error("Faild", exc_info=True)
