import json
import os
import platform

import redis
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import set_ev_cls, MAIN_DISPATCHER
from ryu.lib.packet import packet, ipv4
from ryu.ofproto import ofproto_v1_3

from api_server import ApiServer
from control_plane import ControlPlane
from dispatcher import Dispatcher
from composer import Composer
from utils import log
from verify_pool import VerifyPool

MULTIJET_IP_PROTO = 143


class Multijet(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(Multijet, self).__init__(*args, **kwargs)
        self.dispatcher = None
        self.dp = None
        self.verify_pool = None
        self.msg_buf = {}

        t = ApiServer(self.on_trigger)
        t.start()

        self.cps = [ControlPlane(10), ControlPlane(100)]

        self.ds = redis.Redis(host='localhost', port=6379, db=0)
        p = self.ds.pubsub()
        p.subscribe(**{'add_rule': self.ds_add_rule_handler, 'cmd': self.ds_cmd_handler})
        p.run_in_thread(sleep_time=0.001)

        self.composer = Composer(self)

    def ds_add_rule_handler(self, msg):
        rule = json.loads(msg['data'])
        self.get_cp_by_id(100).add_rule(rule)

    def ds_cmd_handler(self, msg):
        cmd = msg['data']
        if cmd == 'init':
            self.get_cp_by_id(100).build_space()
        elif cmd == 'verify':
            self.verify_pool.work(self.get_cp_by_id(100))
            # self.verify_pool.work(self.get_cp_by_id(10))
        elif cmd == 'addcp': # we copy ospf rules as new cp currently for test
            self.dp.send_msg(self.dp.ofproto_parser.OFPFlowStatsRequest(datapath=self.dp))
        elif cmd[:7] == 'compose':
            self.dispatcher.set_selector_table(10)
            # self.composer.compose(cmd[8:])
        elif cmd[:8] == 'linkdown':
            if cmd.split()[1] == platform.node():
                port = cmd.split()[2]
                cmd = 'ifconfig i' + port + ' down && ifconfig e' + port + 'down'
                os.system(cmd)
                self.dispatcher.set_selector_table(100)
        elif cmd[:6] == 'linkup':
            if cmd.split()[1] == platform.node():
                port = cmd.split()[2]
                cmd = 'ifconfig i' + port + ' up && ifconfig e' + port + 'up'
                os.system(cmd)
                self.dispatcher.set_selector_table(10)

    def get_cp_by_id(self, id):
        for cp in self.cps:
            if cp.id == id:
                return cp
        return None

    def on_trigger(self, comps):
        if comps['type'][0] == 'init':
            for cp in self.cps:
                self.verify_pool.work(cp)

    @set_ev_cls(ofp_event.EventOFPStateChange, MAIN_DISPATCHER)
    def switch_in_handler(self, ev):
        if self.dp is not None:
            print 'Multijet only supports one local switch'
            return

        print 'switch connected'
        dp = ev.datapath
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        self.dp = dp
        self.dispatcher = Dispatcher(multijet=self)
        self.verify_pool = VerifyPool(multijet=self)


        # init verify msg rules
        ofmatch = parser.OFPMatch(eth_type=2048, ip_proto=MULTIJET_IP_PROTO)
        actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        msg = parser.OFPFlowMod(datapath=dp, priority=44444, match=ofmatch,
                                command=ofp.OFPFC_ADD,
                                flags=ofp.OFPFF_SEND_FLOW_REM,
                                instructions=inst)
        dp.send_msg(msg)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):

        in_port = ev.msg.match['in_port']
        pkt = packet.Packet(data=ev.msg.data)
        pkt_ip = pkt.get_protocol(ipv4.ipv4)
        if not pkt_ip.proto == MULTIJET_IP_PROTO:
            return
        payload = pkt.protocols[-1]
        msg = json.loads(payload)
        if not self.msg_buf.has_key(msg['seq']):
            self.msg_buf[msg['seq']] = []

        self.msg_buf[msg['seq']].append(msg['data'])

        if len(self.msg_buf[msg['seq']]) == msg['count']:
            payload = ''.join(self.msg_buf[msg['seq']])
            log('received from ' + str(in_port) + ': ' + payload)

            parsed = json.loads(payload)
            parsed['in_port'] = in_port

            self.dispatcher.dispatch(parsed)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply_handler(self, ev):
        rules = []
        dp = self.dp
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        for stat in ev.msg.body:
            if stat.table_id != 100:  # continue if not ospf table
                continue

            match = {}
            action = {}
            for k, v in stat.match.items():
                if k == 'eth_type': # ignore this type, because we didn't set it from fpm
                    continue
                match[k] = v

            for inst in stat.instructions:
                for act in inst.actions:
                    if act.type == 0:
                        action['output'] = act.port

            rules.append({'match': match, 'action': action})

            ofmatch = parser.OFPMatch(eth_type=2048, ipv4_dst=(match['ipv4_dst']))
            actions = [parser.OFPActionOutput(action['output'], ofp.OFPCML_NO_BUFFER)]
            inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
            msg = parser.OFPFlowMod(datapath=dp, priority=1, match=ofmatch, table_id=10,
                                    command=ofp.OFPFC_ADD,
                                    flags=ofp.OFPFF_SEND_FLOW_REM,
                                    instructions=inst)
            dp.send_msg(msg)

        self.get_cp_by_id(10).set_rules(rules)
