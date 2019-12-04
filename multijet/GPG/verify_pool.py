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
        if self.verified_false: 
            return # No need to verify anymore since the CP must be wrong

        with open('gpg.json') as json_file:
            data = json.load(json_file)

        # load Global Product Graph (GPG) from json file 
        import networkx as nx
        G = nx.DiGraph()
        for u, v in data['edges']:
            G.add_edge(u, v)

        # FIXME match port id with "A", "B", ... in gpg.json
        #       Solution 1: change port id into node ids: "A", "B"
        #       Solution 2: change json file to match port id
        
        # collects related states 
        states = []
        for n in data['nodes']: 
            if n[0] == platform.node(): # n[0] is the node_id, n[1] is the state_id
                states.append(n)

        frules = cp.get_rules_group_by_output()
        if msg is None:
            # scan the actions in FIB
            for eg_node in frules:
                flag = False
                for state in states:
                    ing_states = dict() # (key: ing_node, value: ing_state_id)
                    
                    # check if this state DOES NOT allow this action,
                    # which means this state may have problem
                    if not G.has_successor(state, eg_node):
                        for ing in G.predecessors(state): # retrieve ingress for this problemaitc state
                            if not ing[0] in ing_states.keys(): # ing[0] is the id of node
                                ing_states[ing[0]] = [ing[1]]
                            elif not ing[1] in ing_states[ing[0]]: 
                                ing_states[ing[0]].append(ing[1]) # ing[1] is the id of states
                    else: flag = True

                if flag:  # On the other hand side, if all states do not allow this action; 
                          # there is no need to send message because we already know the CP must be wrong.
                    for ing in ing_states.keys(): # send message to every ing node
                        m = { 
                            'cpid': cp.id,
                            'src': platform.node(),
                            'data': {
                                'type': 'ec',
                                'states': ing_states[ing], # notify the related states for ing node
                                'space': cp.get_my_space().multiply(frules[eg_port])
                            }
                        }
                        # self.dispatcher.unicast(json.dumps(m), FIXME port to ing (node), self.gen_seq(cp))
                else:
                    pass
                    # self.verified_false = True # acutally, we can stop verification here 
        else:
            in_port = msg['in_port']
            state_ids = msg['data']['states']
            frules = cp.get_rules_group_by_output()
            if in_port not in frules:
                return
            if route[-1] == platform.node():
                return
            space = Space(areas=msg['data']['space'])
            space.multiply(frules[in_port])
            if len(space.areas) == 0:
                log('empty')
                return

            # WARNING the GPG approach may not send any message at all, 
            #          which means the flow rule insertion should not depend on its messages
            # route.insert(0, platform.node()) 
            # cp.add_ec(route, space)
            
            ing_states = dict()
            for s_id in state_ids:
                for ing in G.predecessors(platform.node() + s_id): # FIXME complete_id is ( node_id + state_id )
                    if not ing[0] in ing_states.keys():
                        ing_states[ing[0]] = [ing[1]]
                    elif not ing[1] in ing_states[ing[0]]: 
                        ing_states[ing[0]].append(ing[1])

            for ing in ing_states.keys(): # recursively notify ingress nodes 
                                          # until the space become empty or there is no ingress
                m = {
                    'cpid': cp.id,
                    'src': platform.node(),
                    'data': {
                        'type': 'ec',
                        'route': ing_states[ing],
                        'space': space.areas
                    }
                }
                # self.dispatcher.unicast(json.dumps(m), FIXME port to ing (node), self.gen_seq(cp))

            cp.dump_ecs()

    def work(self, cp, msg=None):
        self.verified_false = False
        self.pool.apply_async(self.verify, (cp, msg))
