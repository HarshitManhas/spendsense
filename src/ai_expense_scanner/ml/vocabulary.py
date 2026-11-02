from dataclasses import dataclass


@dataclass
class Vocabulary:
    characters: list[str]
    PAD = 0
    BOS = 1
    EOS = 2
    UNK = 3

    @classmethod
    def build(cls, texts):
        return cls(sorted(set(''.join(texts)) | set('{}[]":,null0123456789.-')))

    def __len__(self):
        return len(self.characters) + 4

    def encode(self, text):
        lookup = {char: i + 4 for i, char in enumerate(self.characters)}
        return [lookup.get(char, self.UNK) for char in text]

    def decode(self, ids):
        result = []
        for value in ids:
            if value == self.EOS:
                break
            if value >= 4:
                result.append(self.characters[value - 4])
            elif value == self.UNK:
                result.append("�")
        return ''.join(result)
