# NEW для сохранения черкашей без привязки к  виджетам
class VectorManager:
    def __init__(self):
        self.vectors = {}

    def Add(self, item: dict, key: int) -> bool:
        # item - словарь типа <str, list>
        # key - ключ, по которому при вызове брался item (переделать)
        # Если нет словаря с указанным ключом - просто добавляем и не паримся
        if not (key in item):  # key not in self.vectors:
            self.vectors[key] = item
            return True
        # Если указанный ключ есть - паримся (добавляем элементы в соответствующие list)
        for type_vector in item.keys():  # strokes, rect и т.д.
            self.vectors[key][type_vector] = list(set(self.vectors[key][type_vector] + item[type_vector]))

    def getByIndex(self, index: int):
        try:
            return self.vectors[index]
        except:
            return None

    def rotate(self, index: int):
        vector = self.getByIndex(index)
        if not vector is None:
            print(f"rotate {vector}")

    def clearByIndex(self, index: int):
        self.vectors[index] = {}

    def Remove(self, key: int):
        self.vectors.pop(key)

    def isHasValue(self) -> bool:
        return self.vectors != {}

    def Clear(self):
        self.vectors = {}
