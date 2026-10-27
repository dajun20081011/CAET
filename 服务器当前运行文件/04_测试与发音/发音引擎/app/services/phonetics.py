import re

ARPABET_TO_IPA = {
    "AA": "ɑː",
    "AE": "æ",
    "AH": "ʌ",
    "AO": "ɔː",
    "AW": "aʊ",
    "AX": "ə",
    "AY": "aɪ",
    "B": "b",
    "CH": "tʃ",
    "D": "d",
    "DH": "ð",
    "EH": "ɛ",
    "ER": "ɝ",
    "EY": "eɪ",
    "F": "f",
    "G": "ɡ",
    "HH": "h",
    "IH": "ɪ",
    "IY": "iː",
    "JH": "dʒ",
    "K": "k",
    "L": "l",
    "M": "m",
    "N": "n",
    "NG": "ŋ",
    "OW": "oʊ",
    "OY": "ɔɪ",
    "P": "p",
    "R": "ɹ",
    "S": "s",
    "SH": "ʃ",
    "T": "t",
    "TH": "θ",
    "UH": "ʊ",
    "UW": "uː",
    "V": "v",
    "W": "w",
    "Y": "j",
    "Z": "z",
    "ZH": "ʒ",
}


def strip_stress(phone: str) -> str:
    return re.sub(r"\d", "", phone).upper()


def to_ipa(phone: str) -> str:
    clean = strip_stress(phone)
    return ARPABET_TO_IPA.get(clean, clean.lower())


def feedback_zh(expected_ipa: str, observed: str | None, diagnosis: str) -> str:
    if diagnosis == "correct":
        return f"/{expected_ipa}/ 发音清晰。"
    if diagnosis == "weak":
        return f"/{expected_ipa}/ 已识别，但发音力度、时长或口形还可加强。"
    if diagnosis == "deletion":
        return f"未检测到 /{expected_ipa}/，请放慢速度并完整发出该音。"
    return f"目标是 /{expected_ipa}/，本次更接近 /{observed or '?'}/。"
