import networkx as nx
from networkx.drawing.nx_agraph import graphviz_layout

import matplotlib.pyplot as plt

routers = {}


class Router:
    def __init__(self, id):
        self.id = id
        self.neighbors = []


with open('eval/rocketfuel/1755.r0.cch', 'r') as f:
    for line in f:
        arr = line.split()
        routers[arr[0]] = Router(arr[0])

    f.seek(0)

    for line in f:
        arr = line.split('->')
        arr = arr[1].split('=')
        nei_str = arr[0].replace(' ', '')
        nei_ids = nei_str[1:-1].split('><')
        print nei_ids
        t = line.split()
        router = routers[t[0]]
        for nei in nei_ids:
            router.neighbors.append(routers[nei])

    G = nx.Graph()
    for id, r in routers.items():
        G.add_node(id, time=id)
        for n in r.neighbors:
            G.add_edge(id, n.id)

    # pos = nx.spring_layout(G, scale=20)

    # nx.spring_layout(G, k=0.05, iterations=20)
    options = {
        'node_size': 10,
        'font_size': 12,
        'with_labels': True,
        'pos': graphviz_layout(G)
    }
    nx.draw(G, **options)
    print len(routers)
    plt.savefig('topo.png')