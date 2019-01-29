from utils import log


class Composer:
    def __init__(self, multijet):
        self.multijet = multijet

    def compose(self, reach):
        selector = 100
        for cp in self.multijet.cps:
            found = False
            for ec in cp.ecs:
                if reach in ec['route']:
                    selector = cp.id
                    found = True
                    break
            if found is True:
                break
        log('selector: ' + str(selector))
        self.multijet.dispatcher.set_selector_table(selector)
