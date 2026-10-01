"""Well-known mutashabihat pairs, written from memory and used only to measure recall.

They are not used to build the dataset. verify.py first checks each pair against
the Quran text, so a mistake in this list shows up as a pair that fails the text
test instead of silently lowering recall.
"""

GOLD: list[tuple[str, str, str]] = [
    ("2:35", "7:19", "Adam and his wife in Paradise"),
    ("2:58", "7:161", "enter this town"),
    ("2:49", "7:141", "Pharaoh's people: يذبحون / يقتلون أبناءكم"),
    ("2:136", "3:84", "we believe in Allah and what was revealed to us"),
    ("6:151", "17:31", "do not kill your children: نرزقكم وإياهم / نرزقهم وإياكم"),
    ("3:126", "8:10", "victory is only from Allah"),
    ("2:62", "5:69", "those who believed, the Jews and the Sabians"),
    ("16:43", "21:7", "We sent before you only men to whom We revealed"),
    ("2:134", "2:141", "identical verse"),
    ("55:13", "55:16", "refrain of Ar-Rahman"),
    ("55:16", "55:77", "refrain of Ar-Rahman"),
    ("77:15", "77:19", "refrain of Al-Mursalat"),
    ("26:8", "26:67", "refrain of Ash-Shu'ara"),
    ("26:9", "26:68", "refrain of Ash-Shu'ara"),
    ("54:17", "54:22", "refrain of Al-Qamar"),
    ("7:65", "11:50", "Hud: اعبدوا الله ما لكم من إله غيره"),
    ("7:73", "11:61", "Salih: اعبدوا الله ما لكم من إله غيره"),
    ("7:85", "11:84", "Shu'ayb: اعبدوا الله ما لكم من إله غيره"),
    ("7:80", "29:28", "Lut: أتأتون الفاحشة"),
    ("2:40", "2:47", "remember My favour upon you"),
    ("2:48", "2:123", "fear a day when no soul will avail another"),
    ("3:133", "57:21", "hasten to forgiveness and a Garden as wide as the heavens and earth"),
    ("12:22", "28:14", "when he reached maturity We gave him judgment and knowledge"),
]
