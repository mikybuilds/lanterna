"""Before a message goes to an online model: does it carry a card number, an IBAN, a password, a PIN or a key?

Only what the user typed is looked at, here on this computer; nothing is sent anywhere for it. Each find says where
it is, a short hint to show (never the whole secret) and what can go in its place, so the user can hide it and still
ask. Card numbers pass the Luhn check and IBANs their own check digits, so ordinary long numbers don't count.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

DOT = "••••"


@dataclass
class Found:
    kind: str          # card | iban | key | pin | password
    start: int
    end: int
    hint: str          # what the warning shows ("•••• 4242"), never the whole secret
    mask: str          # what goes to the model instead, when the user hides it


# keys and tokens of well-known services (the same as github.SECRET_TEXT, plus a few more), a private key whole
_PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)")
_KEY = re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{40,}|\bgsk_[A-Za-z0-9]{40,}|"
                  r"\bAIza[0-9A-Za-z_-]{35}\b|\bsk-[A-Za-z0-9_-]{30,}|\bGOCSPX-[A-Za-z0-9_-]{20,}|"
                  r"\bxox[abpr]-[A-Za-z0-9-]{20,}|\bAKIA[0-9A-Z]{16}\b|\bhf_[A-Za-z0-9]{30,}|\bcsk-[A-Za-z0-9]{30,}|"
                  r"\b[sr]k_live_[A-Za-z0-9]{20,}|\b\d{8,10}:AA[A-Za-z0-9_-]{33}\b|"
                  r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")
# "api_key = …", "token: …": the value only
_KEY_VALUE = re.compile(r"(?i)\b(?:api[_ -]?key|secret(?:[_ -]?key)?|client[_ -]?secret|access[_ -]?(?:key|token)|"
                        r"auth[_ -]?token|token|ключ(?:[ ]api)?|токен)\b[\"']?[ \t]*[:=][ \t]*[\"']?([A-Za-z0-9_\-.+/]{16,})")

# a card: 13-19 digits that start like a card network's (2-6), alone or in groups of four (Amex: 4-6-5)
_CARD = re.compile(r"(?<![\w+.,/-])[2-6](?:[ -]?\d){12,18}(?!\w|[-.,/]\d)")
# an IBAN: two letters, two check digits, then the account, alone or in groups of four
_IBAN = re.compile(r"(?<!\w)[A-Za-z]{2}\d{2}(?: ?[A-Za-z0-9]{4}){2,7}(?: ?[A-Za-z0-9]{1,4})?(?!\w)")

_PW = r"пароль|паролі|пароля|паролю|паролем|password|passwort|passwd|pwd|contraseña|mot de passe|hasło|haslo|parola"
# "пароль від пошти: Kotik2024", "password = hunter22", "пароль від wifi — Kotik2024"
_PASSWORD = re.compile(rf"(?i)\b(?:{_PW})\b(?:[ \t]+[^\s:=—–]{{1,20}}){{0,3}}?(?:[ \t]*[:=][ \t]*|[ \t]+[—–-][ \t]+)"
                       r"[\"'«“]?([^\s\"'»”]{3,})")
# "мій пароль Kotik2024", "the password is hunter22": with no ":" only a value with a digit and a letter counts
_PASSWORD_SAID = re.compile(rf"(?i)\b(?:{_PW})[ \t]+(?:(?:—|–|-|це|is|ist|è|es|est|to)[ \t]+){{0,2}}"
                            r"((?=[^\s]*\d)(?=[^\s]*[^\W\d_])[^\s\"'»”]{6,})")
_PIN = re.compile(r"(?i)\b(?:pin(?:[ -]?(?:code|код))?|пін(?:[ -]?код)?|пин(?:[ -]?код)?|cvv2?|cvc2?)\b"
                  r"(?:[ \t]+(?:від[ \t]+|of[ \t]+the[ \t]+|my[ \t]+)?(?:картки|карти|карты|card))?"
                  r"[ \t]*(?:[:=—–-]|is|це|ist|è)?[ \t]*(\d{3,6})\b")
_END = ".,;:!?)]}»”\"'"


def _luhn(digits: str) -> bool:
    total = 0
    for i, c in enumerate(reversed(digits)):
        n = int(c)
        if i % 2:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


_GROUPS = ([4, 4, 4, 4], [4, 4, 4, 4, 3], [4, 4, 4, 3], [4, 4, 4, 2], [4, 6, 5], [4, 6, 4])


def _card_groups(raw: str) -> bool:
    """Written as cards are: all together, in fours (a 19-digit card ends with three) or 4-6-5 / 4-6-4."""
    sizes = [len(p) for p in re.split(r"[ -]", raw)]
    return len(sizes) == 1 or sizes in _GROUPS


def _iban_ok(raw: str) -> bool:
    s = re.sub(r"\s", "", raw).upper()
    if not 15 <= len(s) <= 34 or not s[:2].isalpha():
        return False
    return int("".join(str(int(c, 36)) for c in s[4:] + s[:4])) % 97 == 1


def _password_ok(value: str) -> bool:
    """A value that looks like a password, not a word ("Пароль: забув"): a digit, a sign or a capital inside it."""
    value = value.rstrip(_END)
    if len(value) < 4 or re.match(r"(?i)https?://|[$%<{*]", value) or re.fullmatch(r"(.)\1+", value):
        return False                                      # a link, "${DB_PASS}", "<your password>", "****"
    if re.match(r"[A-Za-z_]\w*(?:\.\w+)*[(\[]", value) or re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+", value):
        return False                                      # code: password = os.environ["DB_PASS"], cfg.password
    return bool(re.search(r"\d|[^\w\s]|_", value) or re.search(r"\w[A-ZА-ЯЇІЄҐ]", value))


def _cards(text: str) -> list[Found]:
    out = []
    for m in _CARD.finditer(text):
        raw = m.group(0)
        while True:                                       # "4111 1111 1111 1111 3 рази": the tail is not the card
            digits = re.sub(r"\D", "", raw)
            if len(digits) < 13:
                break
            if _card_groups(raw) and _luhn(digits):
                tail = digits[-4:]
                out.append(Found("card", m.start(), m.start() + len(raw), f"{DOT} {tail}", f"{DOT} {tail}"))
                break
            cut = re.search(r"[ -]\d+$", raw)
            if not cut:
                break
            raw = raw[:cut.start()]
    return out


def find(text: str) -> list[Found]:
    """Everything private in the text, in order; a find inside another one counts once."""
    text = text or ""
    finds: list[Found] = []

    def add(f: Found) -> None:
        if not any(f.start < x.end and x.start < f.end for x in finds):
            finds.append(f)

    for m in _PEM.finditer(text):
        add(Found("key", m.start(), m.end(), "-----BEGIN…", f"[private key {DOT}]"))
    for m in _KEY.finditer(text):
        v = m.group(0)
        head = v[:4] if not v[:1].isdigit() else ""
        add(Found("key", m.start(), m.end(), head + "…", head + DOT))
    for m in _KEY_VALUE.finditer(text):
        v = m.group(1).rstrip(_END)
        if len(v) >= 16 and re.search(r"\d", v) and re.search(r"[A-Za-z]", v):
            add(Found("key", m.start(1), m.start(1) + len(v), v[:3] + "…", DOT))
    for m in _IBAN.finditer(text):
        if _iban_ok(m.group(0)):
            s = re.sub(r"\s", "", m.group(0)).upper()
            add(Found("iban", m.start(), m.end(), f"{s[:4]} … {s[-4:]}", f"{s[:4]} {DOT} {s[-4:]}"))
    for f in _cards(text):
        add(f)
    for m in _PIN.finditer(text):
        add(Found("pin", m.start(1), m.end(1), "", DOT))
    for rx in (_PASSWORD, _PASSWORD_SAID):
        for m in rx.finditer(text):
            v = m.group(1).rstrip(_END)
            if _password_ok(v):
                add(Found("password", m.start(1), m.start(1) + len(v), "", DOT))
    return sorted(finds, key=lambda f: f.start)


def mask(text: str, finds: list[Found]) -> str:
    """The text with each find put out of sight (from the end, so the places stay right)."""
    for f in sorted(finds, key=lambda f: f.start, reverse=True):
        text = text[:f.start] + f.mask + text[f.end:]
    return text
