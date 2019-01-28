import json
import platform
import sys
from multiprocessing.pool import ThreadPool
from space import Space
from utils import log

import redis


class VerifyPool:
    def __init__(self, multijet):
        self.multijet = multijet
        self.dispatcher = multijet.dispatcher
        self.pool = ThreadPool()

    def gen_seq(self, cp):
        seq = str(self.multijet.dp.id) + str(cp.id) + str(cp.seq)
        cp.seq = cp.seq + 1
        return seq

    def verify(self, cp, msg=None):
        if msg is None:
            m = {
                'cpid': cp.id,
                'src': platform.node(),
                'data': {
                    'type': 'ec',
                    'route': [platform.node()],
                    'space': [''.ljust(336, '*')]  # self.get_init_ec_space().areas
                }
            }
            log(json.dumps(m))
            self.dispatcher.flood(json.dumps(m), self.gen_seq(cp))
        else:
            in_port = msg['in_port']
            route = msg['data']['route']
            frules = cp.get_rules_group_by_output()
            if in_port not in frules:
                return
            space = Space(areas=msg['data']['space'])
            space.multiply(frules[in_port])
            if len(space.areas) == 0:
                log('empty')
                return
            route.insert(0, platform.node())
            cp.add_ec(route, space)
            m = {
                'cpid': cp.id,
                'src': platform.node(),
                'data': {
                    'type': 'ec',
                    'route': route,
                    'space': space.areas
                }
            }

            log(json.dumps(m))
            self.dispatcher.flood(json.dumps(m), self.gen_seq(cp), in_port)

            cp.dump_ecs()

    def work(self, cp, msg=None):
        self.pool.apply_async(self.verify, (cp, msg))
