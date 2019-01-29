from utils import log


class Composer:
    def __init__(self, multijet):
        self.multijet = multijet

    def compose(self, reach):
        selector = None
        for cp in self.multijet.cps:
            for ec in cp.ecs:
                if reach in ec['route']:
                    selector = cp.id
        log('selector: ' + str(selector))
        if selector is not None:
            self.multijet.dispatcher.set_selector_table(selector)
