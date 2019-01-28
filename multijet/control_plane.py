import json

from utils import log
from space import Space
import platform


class ControlPlane:
    def __init__(self, id_):
        self.id = id_
        self.rules = []
        self.__rules_group_by_output = {}
        self.ecs = []
        self.seq = 0

    def set_rules(self, rules):
        self.rules = rules
        self.ecs = []
        self.build_space()

    def get_rules_group_by_output(self):
        return self.__rules_group_by_output

    def build_space(self):
        self.__rules_group_by_output = {}

        for rule in self.rules:
            if rule['action']['output'] not in self.__rules_group_by_output:
                self.__rules_group_by_output[rule['action']['output']] = Space()
            self.__rules_group_by_output[rule['action']['output']].plus(Space(match=rule['match']))

        self.add_ec([platform.node()], Space(areas=[''.ljust(336, '*')]))
        log('finish build ec')
        log(json.dumps(self.rules))

    def add_ec(self, route, space):
        for ec in self.ecs:
            if ec['route'] == route:
                ec['space'].plus(space)
                return
        self.ecs.append({'route': route, 'space': space})

    def dump_ecs(self):
        log('ecs count: ' + str(len(self.ecs)))
        for ec in self.ecs:
            log(ec['route'])
