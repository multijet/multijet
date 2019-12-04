import json
import networkx as nx
import matplotlib.pyplot as plt

filename = 'data.json'
sources = ['S']

G = nx.DiGraph()
node2Id = dict()

ids = dict()
table = dict()
def node2Id(state, data, SM):
    s = str(state)
    if s in table:
        return table[s]

    node = state["node"]
    ids[node] = ids[node] + 1
    table[s] = node + str(ids[node])

    flag = True
    for name in SM:
        if not state[name] in data[name]["acceptance"]:
            flag = False

    if flag == True:
        table[s] = node + str("X") # table[s]

    return table[s]

def add_edge(u, v):
    G.add_edge(str(u), str(v))

def transition(sm, state, token):
    if token in sm["links"][state].keys():
        return True, sm["links"][state][token]
    return False, "null" 
    

def extend(state, data, SM):
    for v in data["Topology"]["links"][state["node"]]:
        vstate = dict()
        vstate["node"] = v

        flag = True
        for name in SM:
            t, vstate[name] = transition(data[name], state[name], v)
            flag = flag and t
         
        if flag:
            # print(state, vstate)
            add_edge(node2Id(state, data, SM), node2Id(vstate, data, SM))
            extend(vstate, data, SM)
    
with open(filename) as json_file:
    data = json.load(json_file)

N = data["Topology"]["links"].keys()
# print(N)

SM = []
for name in data.keys():
    if name != "Topology":
        SM.append(name)
# print(SM)

for node in N:
    ids[node] = 0

for node in N:
    state = dict()
    state["node"] = node

    flag = True
    for name in SM:
        t, state[name] = transition(data[name], data[name]["init"], node)
        flag = flag and t

    if flag and node in sources:
        extend(state, data, SM)

G2 = nx.DiGraph()
vis = set()

help(G2)

def verify(node):
    if node in vis:
        return
    else: vis.add(node)

    for vnode in G.predecessors(node):
        G2.add_edge(vnode, node)
        verify(vnode)

for node in G.nodes():
    if node[1] == "X":
        verify(node)

import collections
def compare(s, t):
    return collections.Counter(s) == collections.Counter(t)

while True:
    flag = True
    
    nodes = list(G2.nodes)
    l = len(nodes)
    for i in range(0, l):
        for j in range(i + 1, l):
            if flag:
                u, v = nodes[i], nodes[j]
                if u[0] == v[0] and compare(G2.successors(u), G2.successors(v)):
                    print(u, v)
                    for t in G2.predecessors(u):
                        if not G2.has_predecessor(v, t):
                            G2.add_edge(t, v)
                    G2.remove_node(u)
                    flag = False
                    break
    if flag:
        break

from networkx.readwrite import json_graph
with open('gpg.json', 'w', encoding='utf-8') as f:
    json.dump(dict(nodes=[[n] for n in G2.nodes()],
                   edges=[(u, v) for u, v in G2.edges()]),
              f, ensure_ascii=False, indent=4)

color_map = []
for node in G2:
    if node[1] == '1' and node[0] in sources:
        color_map.append('g')
    elif node[1] == 'X':
        color_map.append('r')
    else: color_map.append('y')    

pos = nx.layout.spring_layout(G2)
nx.draw_networkx_nodes(G2, pos, node_color = color_map, cmap=plt.get_cmap('jet'), node_size = 500)
nx.draw_networkx_labels(G2, pos)
nx.draw_networkx_edges(G2, pos, edgelist=G2.edges(), arrows=True)
plt.show()
