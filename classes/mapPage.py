class MapPage:

    _const_step = 3

    def __init__(self, map_step: int, map_tail: int):
        self._step: int = map_step
        self._map_size_tail = map_tail
        # self._map_max: int = (self._step * 2) + 1

    @property
    def map_size_tail(self):
        return self._map_size_tail

    def calculate(self, index: int, total: int):
        cur_min = index - min(self._step, index)
        cur_max = index + min(self._step, total - index - 1)
        return cur_min, cur_max

    def update(self, new_step: int):
        self._step = new_step + self._const_step
        self._map_size_tail = new_step
