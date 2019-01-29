import json

from ryu.lib.packet import packet, ethernet, ipv4

from utils import log

MULTIJET_IP_PROTO = 143


class Dispatcher:

    def __init__(self, multijet):
        self.multijet = multijet
        self.dp = multijet.dp
        self.seq = 0

    def dispatch(self, msg):
        cp = self.multijet.get_cp_by_id(msg['cpid'])
        self.multijet.verify_pool.work(cp, msg)

    def unicast(self, msg, port, seq):
        size = len(msg)
        buf_size = 1200
        offset = 0
        count = size / buf_size + 1
        while size > 0:
            frag = msg[offset:offset + buf_size]
            offset = offset + buf_size
            size = size - buf_size
            pkt_data = json.dumps({
                'seq': seq,
                'count': count,
                'data': frag
            })
            p = packet.Packet()
            eth_header = ethernet.ethernet()
            ip_header = ipv4.ipv4(proto=MULTIJET_IP_PROTO)
            ip_header.serialize(pkt_data, eth_header)
            p.add_protocol(eth_header)
            p.add_protocol(ip_header)
            p.add_protocol(pkt_data)

            ofp = self.dp.ofproto
            parser = self.dp.ofproto_parser
            p.serialize()
            data = p.data
            actions = [parser.OFPActionOutput(port)]
            out = parser.OFPPacketOut(datapath=self.dp, buffer_id=ofp.OFP_NO_BUFFER, in_port=ofp.OFPP_CONTROLLER,
                                      actions=actions, data=data)
            self.dp.send_msg(out)
        log('unicast finished')

    def flood(self, msg, seq, except_port=None):
        size = len(msg)
        buf_size = 1200
        offset = 0
        count = size / buf_size + 1
        while size > 0:
            frag = msg[offset:offset + buf_size]
            offset = offset + buf_size
            size = size - buf_size
            pkt_data = json.dumps({
                'seq': seq,
                'count': count,
                'data': frag
            })
            p = packet.Packet()
            eth_header = ethernet.ethernet()
            ip_header = ipv4.ipv4(proto=MULTIJET_IP_PROTO)
            ip_header.serialize(pkt_data, eth_header)
            p.add_protocol(eth_header)
            p.add_protocol(ip_header)
            p.add_protocol(pkt_data)

            ofp = self.dp.ofproto
            parser = self.dp.ofproto_parser
            p.serialize()
            data = p.data
            actions = [parser.OFPActionOutput(ofp.OFPP_FLOOD)]
            if except_port is None:
                except_port = ofp.OFPP_CONTROLLER
            out = parser.OFPPacketOut(datapath=self.dp, buffer_id=ofp.OFP_NO_BUFFER, in_port=except_port,
                                      actions=actions, data=data)
            self.dp.send_msg(out)
        log('flood finished')

    def set_selector_table(self, next_table_id):

        dp = self.multijet.dp
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        ofmatch = parser.OFPMatch()
        inst = [parser.OFPInstructionGotoTable(next_table_id)]
        msg = parser.OFPFlowMod(datapath=dp, priority=1, match=ofmatch, table_id=0,
                                command=ofp.OFPFC_ADD,
                                flags=ofp.OFPFF_SEND_FLOW_REM,
                                instructions=inst)
        dp.send_msg(msg)
