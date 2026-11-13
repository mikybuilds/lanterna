"""«Is this a scam?»: signs of fraud in a message, an e-mail or a link, found without opening the link.

Opening a scam link can already tell the senders that the number or address is alive, so nothing here goes to the
internet: the links are only read as text. The model gets the signs and explains them in plain words; read_page
refuses a link with strong signs, so it is not opened by accident either.
"""
from __future__ import annotations

import ipaddress
import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urlsplit

# a brand's name in an address that is not the brand's own: the usual fake bank, shop or delivery page.
# A key is found anywhere in the address; "=key" only as a whole word of it (so "poster.com" is not Poste).
BRANDS = [
    ("PrivatBank", ("privatbank", "privat24", "=privat"), ("privatbank.ua", "privat24.ua")),
    ("monobank", ("monobank",), ("monobank.ua",)),
    ("Oschadbank", ("oschad",), ("oschadbank.ua",)),
    ("Raiffeisen", ("raiffeisen",), ("raiffeisen.ua", "raiffeisen.com", "raiffeisen.at", "raiffeisen.ch", "raiffeisen.it")),
    ("PUMB", ("=pumb",), ("pumb.ua",)),
    ("Nova Poshta", ("novaposhta", "novapost"), ("novaposhta.ua", "nova.global", "novapost.com", "novaposhta.pl",
                                                 "novaposhta.it")),
    ("Ukrposhta", ("ukrposhta", "ukrpost"), ("ukrposhta.ua",)),
    ("Meest", ("=meest",), ("meest.com", "meest.us", "meest.cn")),
    ("Diia", ("=diia",), ("diia.gov.ua",)),
    ("OLX", ("=olx",), ("olx.ua", "olx.pl", "olx.pt", "olx.ro", "olx.bg", "olx.kz", "olx.uz", "olx.com")),
    ("Rozetka", ("rozetka",), ("rozetka.com.ua", "rozetka.ua")),
    ("Prom.ua", ("=prom",), ("prom.ua",)),
    ("Kyivstar", ("kyivstar",), ("kyivstar.ua", "kyivstar.net")),
    ("lifecell", ("lifecell",), ("lifecell.ua",)),
    ("PayPal", ("paypal",), ("paypal.com", "paypal.me")),
    ("Apple", ("=apple", "icloud"), ("apple.com", "icloud.com")),
    ("Microsoft", ("microsoft", "=outlook", "=office365"), ("microsoft.com", "live.com", "office.com", "microsoftonline.com",
                                                             "outlook.com")),
    ("Netflix", ("netflix",), ("netflix.com",)),
    ("Amazon", ("=amazon",), ("amazon.com", "amazon.de", "amazon.it", "amazon.pl", "amazon.fr", "amazon.es", "amazon.co.uk")),
    ("Facebook", ("facebook",), ("facebook.com", "fb.com", "meta.com")),
    ("Instagram", ("instagram",), ("instagram.com",)),
    ("WhatsApp", ("whatsapp",), ("whatsapp.com", "wa.me")),
    ("Telegram", ("=telegram",), ("telegram.org", "t.me")),
    ("Viber", ("=viber",), ("viber.com",)),
    ("Steam", ("=steam", "steamcommunity", "steampowered"), ("steampowered.com", "steamcommunity.com")),
    ("Binance", ("binance",), ("binance.com",)),
    ("DHL", ("=dhl",), ("dhl.com", "dhl.de", "dhl.it", "dhl.pl", "dhl.fr", "dhl.es")),
    ("InPost", ("inpost",), ("inpost.pl", "inpost.it", "inpost.es", "inpost.eu")),
    ("Poste Italiane", ("=poste", "posteitaliane"), ("poste.it", "posteitaliane.it")),
    ("PKO BP", ("pkobp",), ("pkobp.pl", "pko.pl")),
    ("mBank", ("=mbank",), ("mbank.pl",)),
    ("Intesa Sanpaolo", ("=intesa", "intesasanpaolo"), ("intesasanpaolo.com",)),
    ("UniCredit", ("unicredit",), ("unicredit.it", "unicredit.eu", "unicreditgroup.eu")),
    ("Sparkasse", ("sparkasse",), ("sparkasse.de", "sparkasse.at")),
]
SHORTENERS = {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "cutt.ly", "is.gd", "ow.ly", "rebrand.ly", "shorturl.at",
              "clck.ru", "t.ly", "rb.gy", "tiny.cc", "s.id", "u.to", "qps.ru", "bitly.com", "tr.ee", "v.gd", "lnkd.in"}
# endings that cost almost nothing and are often used for fake pages (a sign, not a proof)
CHEAP = {"top", "xyz", "click", "icu", "buzz", "monster", "rest", "cfd", "sbs", "lol", "cyou", "shop", "live",
         "online", "site", "website", "space", "fun", "tk", "ml", "ga", "cf", "gq", "zip", "mov", "win", "bid", "loan",
         "work", "support", "help", "best", "vip", "life", "today", "store", "info"}
# a bare "name.ending" without https:// counts as a link only with these endings (not "notes.md" or "app.py")
_ENDINGS = CHEAP | {"ua", "com", "net", "org", "pl", "it", "de", "fr", "es", "eu", "uk", "ru", "by", "kz", "io", "co",
                    "me", "cc", "biz", "app", "pro", "link", "page", "su", "укр", "рф"}
# a host made of several of these words is a typical fake ("secure-login-verify.com")
BAIT_WORDS = ("secure", "login", "verify", "verif", "account", "update", "confirm", "support", "bonus", "payment",
              "pay", "delivery", "dostavka", "posylka", "parcel", "refund", "compens", "viplata", "vyplata", "help",
              "dopomoga", "wallet", "auth", "signin", "unlock", "reward", "gift", "prize", "free")

_URL = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\"'«»]+")
_BARE = re.compile(r"(?<![\w@/.-])((?:[^\W_][\w-]{0,62}\.)+([^\W\d_]{2,24}))(/[^\s<>\"'«»]*)?(?![\w-])")
_TAIL = ".,;:!?)]}»”'\""

# what the words of a scam message ask for (several languages; a sign each, the model weighs them)
TEXT_SIGNS = [
    ("asks for card data, a PIN, CVV or a code from an SMS",
     r"cvv|cvc|пін-?код|pin-?код|\bpin\b|код (з|із|из) (смс|sms|повідомлення)|sms-?код|смс-?код|код підтвердження|"
     r"дані (вашої |твоєї )?картки|номер (вашої |твоєї )?картки|термін дії картки|card (number|details)|"
     r"verification code|one-?time code|codice (sms|di verifica)|kod sms|kod z sms|kod weryfikacyjny|"
     r"daten (ihrer|deiner) karte|código (sms|de verificación)|code (sms|de vérification)"),
    ("hurries you or threatens a block",
     r"терміново|негайно|протягом (24|двох|однієї|1|2) (год|годин)|за (24|48) години|заблоков|блокуван|"
     r"останн\w* попередж|urgent|immediately|within 24 hours|suspended|locked|blocked|"
     r"urgente|subito|entro 24 ore|bloccat|sofort|gesperrt|inmediatamente|bloquead|immédiatement|bloqué|"
     r"natychmiast|zablokowan|срочно|немедленно"),
    ("promises money, a prize or a payout",
     r"виграл|виграш|\bприз|розіграш|компенсац|виплат|грошов\w* допомог|допомог\w* від (держави|оон|червоного)|"
     r"\bоон\b|безкоштовн\w* (iphone|айфон|подарун)|you (have )?won|prize|reward|lottery|refund|compensation|"
     r"hai vinto|premio|rimborso|gewonnen|gewinn|erstattung|has ganado|reembolso|vous avez gagné|"
     r"remboursement|wygrał|nagrod|zwrot|выиграл|компенсаци|выплат"),
    ("asks to pay for a delivery, a fee or customs",
     r"оплат\w* (доставк|мит|збор)|доплат|сплат\w* (мит|збір|доставк)|посилк\w* (затрим|не може бути доставлен)|"
     r"pay (the |a )?(delivery|shipping|customs|fee)|parcel (is )?(held|on hold)|pacco (in )?giacenza|"
     r"zahlen sie (die )?(zoll|versand)|paquete retenido|colis (en )?attente|dopłat|paczka (czeka|zatrzymana)"),
    ("asks to move the talk to a messenger or to call back",
     r"напиш\w* (нам )?(у|в) (telegram|телеграм|viber|вайбер|whatsapp|ватсап)|перейд\w* (у|в) (telegram|телеграм|viber)|"
     r"передзвон\w*|write (to us )?on (telegram|whatsapp)|scrivi su (telegram|whatsapp)|"
     r"schreib\w* (uns )?(auf|bei) (telegram|whatsapp)|escríbenos (por|en) (telegram|whatsapp)|"
     r"napisz (na|do nas na) (telegram|whatsapp)"),
    ("someone close writes from a new number and needs money",
     r"(це|я) (я|мама|тато|син|донька|дочка)?,? ?(з|із) (нового|іншого|чужого) номер|"
     r"(мам|тат|бабус|дідус)\w*,? (скинь|позич|переказ|потрібн\w* грош)|"
     r"(it's|its) me,? (mom|mum|dad).{0,20}new number|new number.{0,40}(money|send|transfer)|"
     r"sono io.{0,20}nuovo numero|neue nummer.{0,40}(geld|überweis)|nuevo número.{0,40}(dinero|transfer)|"
     r"nowy numer.{0,40}(pieniądz|przelew)"),
    ("asks you to sign in or confirm your account through a link",
     r"(увійд|авторизу|підтверд|верифіку|оновіть дані|онови дані)\w*.{0,60}(посилан|за лінком|тут|here)|"
     r"(sign in|log ?in|verify|confirm) (to |your )?(account|identity|details)|accedi|verifica (il tuo|i tuoi) (account|dati)|"
     r"bestätigen sie|verifique su|vérifiez votre|zweryfikuj|potwierdź (swoje )?(dane|konto)"),
]
_TEXT_SIGNS = [(why, re.compile(rx, re.I)) for why, rx in TEXT_SIGNS]


@dataclass
class Link:
    url: str
    host: str
    signs: list[str] = field(default_factory=list)
    strong: bool = False            # a fake for sure enough not to open it at all


def _host(url: str) -> tuple[str, str]:
    """The real host of a link (what the browser would open) and the part before @, if any: in a link to
    privatbank.ua@example.com/login that part is only for show, the browser opens example.com."""
    raw = url if re.match(r"(?i)https?://", url) else "http://" + url
    try:
        parts = urlsplit(raw)
        host = (parts.hostname or "").rstrip(".").lower()
    except ValueError:
        return "", ""
    netloc = parts.netloc
    return host, (netloc.rsplit("@", 1)[0] if "@" in netloc else "")


def _letters(host: str) -> list[str]:
    """Each part of the address in its own letters (an "xn--" part turned back into what it shows)."""
    out = []
    for label in host.split("."):
        if label.startswith("xn--"):
            try:
                label = label[4:].encode("ascii").decode("punycode")
            except (UnicodeError, ValueError):
                pass
        out.append(label)
    return out


def _script(ch: str) -> str:
    return "LATIN" if ch.isascii() else unicodedata.name(ch, "?").split(" ")[0]


def _registered(host: str) -> str:
    """The name a person buys (privatbank.ua, nova.global, rozetka.com.ua): the last two parts, three for com.ua etc."""
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in ("com", "co", "org", "net", "gov", "in", "kiev", "edu", "biz") and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _is_own(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def check_link(url: str) -> Link:
    url = url.rstrip(_TAIL)
    host, user = _host(url)
    link = Link(url, host)
    if not host:
        return link
    try:
        ipaddress.ip_address(host.strip("[]"))
        link.signs.append("the address is a bare number (an IP), not a site's name")
        link.strong = True
    except ValueError:
        pass
    if user:
        link.signs.append(f"the part before @ ({user[:40]}) is only for show: the link really opens {host}")
        link.strong = True
    labels = _letters(host)
    scripts = [{_script(c) for c in label if c.isalpha()} for label in labels]
    if any(len(s) > 1 for s in scripts):                     # "privаtbank" with a Cyrillic «а»
        link.signs.append("the address mixes look-alike letters from two alphabets (for example a Cyrillic «а» "
                          "instead of a Latin «a»)")
        link.strong = True
    elif any(s - {"LATIN"} for s in scripts[:-1]) and scripts[-1] <= {"LATIN"}:
        link.signs.append("the address is written in other letters than it seems (non-Latin letters before a Latin ending)")
    words = set(re.split(r"[.\-\d]+", host))
    plain = host.replace("-", "")
    for name, keys, own in BRANDS:
        if any((k[1:] in words) if k.startswith("=") else (k in plain) for k in keys) and not _is_own(host, own):
            link.signs.append(f"it looks like {name} but the site is {_registered(host)}; {name}'s own site is {own[0]}")
            link.strong = True
            break
    if _registered(host) in SHORTENERS or host in SHORTENERS:
        link.signs.append("a short link: it hides where it really goes")
    tld = labels[-1]
    if tld in CHEAP:
        link.signs.append(f"a cheap .{tld} address, often used for fake pages")
    bait = [w for w in BAIT_WORDS if w in plain]
    if len(bait) >= 2 or (bait and host.count("-") >= 2):
        link.signs.append("the address is made of bait words (" + ", ".join(bait[:3]) + ")")
    if len(labels) >= 5:
        link.signs.append("the address has many parts: the real site is only its end, " + _registered(host))
    if re.match(r"(?i)http://", url):
        link.signs.append("no https: what you type there goes unprotected")
    return link


def links(text: str) -> list[Link]:
    """Every link in the text, with or without https:// (a bare "name.ending" only with a web ending)."""
    text = text or ""
    found, spans = [], []
    for m in _URL.finditer(text):
        found.append(m.group(0))
        spans.append(m.span())
    for m in _BARE.finditer(text):
        web = m.group(2).lower() in _ENDINGS or _registered(m.group(1).lower()) in SHORTENERS     # bit.ly/…
        if web and not any(a <= m.start() < b for a, b in spans):
            found.append(m.group(0))
    seen, out = set(), []
    for u in found:
        u = u.rstrip(_TAIL)
        if u.lower() not in seen:
            seen.add(u.lower())
            out.append(check_link(u))
    return out[:10]


def text_signs(text: str) -> list[str]:
    return [why for why, rx in _TEXT_SIGNS if rx.search(text or "")]


def report(text: str) -> str:
    """What the model gets: every link with its signs and the signs in the words. No link is opened."""
    text = (text or "")[:6000]
    found = links(text)
    lines = ["Checked on this computer; no link was opened (opening one can tell the senders the number is alive)."]
    for link in found:
        if link.signs:
            lines.append(f"Link {link.url[:120]} (opens {link.host}): " + "; ".join(link.signs) + ".")
        else:
            lines.append(f"Link {link.url[:120]} (opens {link.host}): no sign in the address itself (that alone "
                         "doesn't make it safe: a known site is safer to open by typing its name).")
    words = text_signs(text)
    if words:
        lines.append("In the words: " + "; ".join(words) + ".")
    if not found and not words:
        lines.append("No link and none of the usual scam signs in the words.")
    marked = [link for link in found if link.signs]
    level = ("likely a scam" if any(link.strong for link in found) or len(words) >= 2 or (marked and words)
             else "some signs, be careful" if words or marked else "no clear signs")
    lines.append(f"Overall: {level}. Explain it simply in the user's language, say what not to do (open the link, give "
                 "card data or codes, pay, send money) and how to check for sure: call the bank, the service or the "
                 "person at a number you already know (on the card, on the official site, in your contacts).")
    return "\n".join(lines)


def refuse(url: str) -> str:
    """read_page: "" = the page may be opened; otherwise why the link is not opened."""
    link = check_link(url)
    if not link.strong:
        return ""
    return ("Not opened: this link looks like a scam (" + "; ".join(link.signs) + "). Opening it can tell the senders "
            "the address is alive. Use scam_check with the whole message instead and explain the signs to the user.")
