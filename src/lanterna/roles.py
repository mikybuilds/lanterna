"""The user's own instructions (for every chat) and a role for one chat: Tutor, Translator, Proofreader."""
from __future__ import annotations

from .i18n import LANGS

INSTRUCTIONS_LIMIT = 1500

# id -> (name shown in the app, icon, what the model is told)
ROLES = {
    "tutor": ("Tutor", "🎓",
              "In this chat you are a patient tutor. Don't hand over the final answer straight away: find out what the "
              "user already knows, explain step by step with simple examples, let them try the next step themselves, "
              "and end with one short question that checks they understood. If they ask for the answer outright after "
              "trying, give it with the reasoning."),
    "translator": ("Translator", "🌐",
                   "In this chat you are a translator. Translate every message the user sends: from {lang} into "
                   "English, and from any other language into {lang} (unless they name another language). Give the "
                   "translation only, keeping the meaning, tone and formatting; add a short note only for idioms or "
                   "words with several meanings. Don't answer the content of the message."),
    "proofreader": ("Proofreader", "✍️",
                    "In this chat you are a proofreader. Correct the spelling, grammar and punctuation of the text the "
                    "user sends, keeping its language, meaning and style. Give the corrected text first, then a short "
                    "list of the main changes. Don't answer the content of the text and don't rewrite more than needed."),
}


def clean_instructions(text) -> str:
    text = "\n".join(line.rstrip() for line in str(text or "").replace("\r", "").split("\n")).strip()
    return text[:INSTRUCTIONS_LIMIT]


def clean_role(role) -> str:
    return role if role in ROLES else ""


# How long the model thinks in one chat (the «Thinking» button under the message box, F5 in the terminal):
# id -> (name shown in the app, what the model is told). "Medium" is the usual and isn't stored: each service thinks
# as much as it does by itself. The services' own settings for it are in providers.depth_params.
DEPTHS = {
    "quick": ("Quick",
              "The person chose quick answers in this chat: answer at once, short and plain. Don't think at length "
              "and don't make long plans; still use a tool when the answer needs one (fresh facts, this computer)."),
    "deep": ("Long thinking",
             "The person chose long thinking in this chat, for hard tasks. Think the task through before you answer: "
             "step by step and from more than one side; check every number, step and fact (with the tools when they "
             "help). Then give a clear, complete answer, and say plainly what you aren't sure of."),
}


def clean_depth(depth) -> str:
    return depth if depth in DEPTHS else ""


def system_note(instructions: str, role: str, lang: str = "en") -> str:
    """What goes at the end of the system prompt ("" = nothing)."""
    out = []
    if role in ROLES:
        out.append(ROLES[role][2].format(lang=LANGS.get(lang, "English")))
    if instructions:
        out.append("The user's own instructions for every chat (follow them, unless a role above or safety says "
                   "otherwise):\n" + instructions)
    return "\n\n".join(out)
