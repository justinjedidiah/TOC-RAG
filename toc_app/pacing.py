"""Give out streamed text at a steady reading pace, whatever rhythm the model sends it in.

A model's reply arrives in bursts: nothing for a moment, then a whole sentence. Shown as it comes, the chat
jumps. The pacer holds the text received so far (`target`) and, on every tick, hands out a little more of it
(`shown`): a few characters, rounded up to the end of a word, and more when a lot is waiting, so it is never
far behind. Plain Python, no Reflex: State drives it from the chat loop.
"""

import math

TICK_SECONDS = 0.05  # how often the chat loop asks for more text (20 small updates a second)
MIN_CHARS = 4  # the slowest pace: 4 characters a tick, about 80 a second (13-14 words)
CATCH_UP = 6  # otherwise a sixth of what is waiting, so a long backlog empties in about half a second
WORD_SLACK = 12  # finish the word being shown if it ends within this many characters


class TextPacer:
    def __init__(self) -> None:
        self.target = ""
        self.shown = 0

    def set_target(self, text: str) -> None:
        """The reply so far. It normally only grows; if an earlier part changed, keep only what still matches."""
        if not text.startswith(self.target[: self.shown]):
            same = 0
            for a, b in zip(text, self.target[: self.shown]):
                if a != b:
                    break
                same += 1
            self.shown = same
        self.target = text

    def reset(self) -> None:
        """Start over with new text (the next note or the answer)."""
        self.target, self.shown = "", 0

    def behind(self) -> int:
        return len(self.target) - self.shown

    def tick(self) -> str | None:
        """Show a little more and return the text to display, or None if everything is already shown."""
        waiting = self.behind()
        if waiting <= 0:
            return None
        end = min(len(self.target), self.shown + max(MIN_CHARS, math.ceil(waiting / CATCH_UP)))
        space = self.target.find(" ", end)
        if space != -1 and space - end < WORD_SLACK:
            end = space + 1
        elif space == -1 and len(self.target) - end < WORD_SLACK:
            end = len(self.target)
        self.shown = end
        return self.target[:end]

    def text(self) -> str:
        return self.target[: self.shown]
