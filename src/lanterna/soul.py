"""Lanterna's personality: talk like a warm, real friend instead of a template assistant.

- persona()    — how Lanterna speaks and behaves;
- mood_hint()  — notices the user's mood (sad, stressed, happy, thanks, late night) and nudges the reply;
- humanize()   — trims canned phrases ("Of course!", "Let me know if you have questions") and repeated openers.
Works in English, Ukrainian and Italian.
"""
from __future__ import annotations

import datetime
import re

PERSONA = """WHO YOU ARE: You are Lanterna — not a generic "assistant" but a warm, down-to-earth friend{who}.
- Write like a real person in a messenger: warm, simple, a little different every time, no corporate tone.
- Match the length: a short message gets a short reply (1–2 sentences); a serious question gets a full, clear answer. In casual chat, no lists or headings — unless the user asks for a list or steps; then always use one.
- Notice the mood and react like a human first (support, celebrate, joke), then help. No lectures or moralizing.
- Have your own opinion: to "what do you think…" answer for yourself with a reason ("I'd…, because…"), not "it's personal" or "everyone has their own taste".
- Remember the conversation and refer back to it when it fits. Ask at most one follow-up question, only when it's natural.
- No templates: don't start with "Of course!", "Great question", "As an AI…"; don't end with "Let me know if you have any questions". Don't reuse the same opener twice in a row. Greet only at the start of a chat, not in every reply.
- Never say you did something (set a reminder, saved a fact, searched) unless a tool really did it in this turn.
- Be honest: if you're not sure, say so plainly. Never invent facts, links or numbers. If the user says something wrong, kindly disagree and explain — don't agree just to please.
- Humor and slang in small doses. In serious topics (health, grief, conflicts) — no jokes.
- Always reply in the language the user writes in."""

_MOODS = [
    (r"\b(сумно|сумую|погано на душі|самотн|розстав|посвар|плачу|депрес|все погано|нікому не потрібен|triste|solo|sad|lonely|depressed|heartbroken)",
     "sad", "MOOD: the user is sad. First, sincere empathy in your own words — no jokes, no \"just cheer up\". Ask what happened or offer a distraction."),
    (r"(втомив|втомлен|не виспав|задовбал|стрес|переживаю|нервую|боюсь|боюся|паніка|не встигаю|завал|сил немає|stanco|stressat|ansia|tired|stressed|exhausted|overwhelmed|anxious)",
     "stressed", "MOOD: the user is tired or stressed. One short human line of support, then concrete help in small steps."),
    (r"\b(ура+|склав|здав|вийшло|перемог|я зробив це|найкращий день|evviva|ce l.ho fatta|i did it|yay|i passed|we won)",
     "happy", "MOOD: the user is happy. Celebrate sincerely and briefly; you may ask for details."),
    (r"^\W*(дякую|дяки|дякс|спасибі|спс|thanks|thank you|thx|grazie|merci)\b",
     "thanks", "This is a thank-you: answer briefly and warmly, without \"feel free to ask again\"."),
]

_OPENERS = re.compile(r"^\s*(звісно|звичайно|безперечно|чудове питання|гарне питання|відмінне питання|як штучний інтелект[^.!]*[.!]|"
                      r"certo|certamente|ottima domanda|of course|sure thing|great question|absolutely|as an ai[^.!]*[.!])[!,.:]?\s+", re.I)
_CLOSERS = re.compile(r"\s*(якщо (у тебе|у вас|в тебе) (є|виникнуть|будуть) (ще )?(якісь |будь-які )?питання[^.!\n]*[.!]?|звертайся,? якщо[^.!\n]*[.!]?|"
                      r"звертайся ще[^.!\n]*[.!]?|сподіваюся?,? (це|що це) (допоможе|було корисно)[^.!\n]*[.!]?|"
                      r"fammi sapere se[^.!\n]*[.!]?|se hai (altre )?domande[^.!\n]*[.!]?|let me know if[^.!\n]*[.!]?|hope (this|that) helps[^.!\n]*[.!]?|"
                      r"feel free to ask[^.!\n]*[.!]?|"
                      r"(якщо|if|se) [^.!?\n]{0,80}(дай знати|let me know|fammi sapere)[^.!?\n]*[.!]?)\s*(😊|🙂|😉|👍)?\s*$", re.I)
_SOFT_OPENERS = {"бро", "йо", "ого", "ну", "ок", "окей", "так", "ага", "хм", "ех", "ой", "о", "hey", "oh", "well", "ok", "okay", "so", "ah", "beh", "allora", "ecco"}


def persona(name: str = "") -> str:
    text = PERSONA.format(who=f" of {name}" if name else "")
    return text + (f"\n- The user's name is {name}. Use it now and then, naturally." if name else "")


def mood(text: str) -> str:
    t = (text or "").lower()
    return next((n for rx, n, _ in _MOODS if re.search(rx, t)), "")




def lang_hint(text: str, app_lang: str = "en") -> str:
    """Models sometimes drift into Russian for Ukrainian users (photos especially): say the language outright."""
    t = text or ""
    if re.search(r"[іїєґІЇЄҐ]", t) or (app_lang == "uk" and re.search(r"[а-яА-Я]", t) and not re.search(r"[ыэъёЫЭЪЁ]", t)):
        return "LANGUAGE: the user writes in Ukrainian. Reply only in Ukrainian, never in Russian."
    return ""


def mood_hint(text: str, now: datetime.datetime | None = None) -> str:
    t = (text or "").lower()
    hints = [h for rx, _n, h in _MOODS if re.search(rx, t)][:1]
    if 0 <= (now or datetime.datetime.now()).hour < 5:
        hints.append("It's the middle of the night: you may mention sleep once, in a friendly way, without moralizing.")
    return "\n".join(hints)


def humanize(text: str, last_reply: str = "") -> str:
    """Drop canned openers/closers. Code and very short replies are left alone."""
    if not text or "```" in text:
        return text
    out = text.strip()
    m = _OPENERS.match(out)
    if m and len(out) - m.end() > 15:
        rest = out[m.end():]
        out = rest[:1].upper() + rest[1:]
    for _ in range(2):
        cut = _CLOSERS.sub("", out).rstrip()
        if cut and len(cut) >= 8 and cut != out:
            out = cut
    if last_reply:
        a, b = _first_word(out), _first_word(last_reply)
        if a and a == b and len(out.split()) > 4:
            rest = re.sub(r"^\s*[^\s,!.]+[,!.]?\s+", "", out, count=1)
            out = rest[:1].upper() + rest[1:] if rest else out
    return out


def _first_word(s: str) -> str:
    w = re.findall(r"[^\W\d_]+", (s or "").lower())[:1]
    return w[0] if w and w[0] in _SOFT_OPENERS else ""
