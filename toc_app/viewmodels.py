"""Plain data shown by the page. Dataclasses, so Reflex can read their fields in the UI."""

import dataclasses


@dataclasses.dataclass
class DocView:
    doc_id: str
    title: str
    kind: str
    summary: str
    sample: bool
    enabled: bool = True  # turned off: still listed and browsable, but left out of answers


@dataclasses.dataclass
class CitationView:
    ref: str  # "doc_id:node_id"
    doc_title: str
    title: str
    location: str


@dataclasses.dataclass
class ImageView:
    url: str
    description: str


@dataclasses.dataclass
class PageView:
    url: str  # a picture of the page, rendered on first request
    label: str  # the page number printed on it ("iv", "19")


@dataclasses.dataclass
class StepView:
    label: str
    note: str = ""  # the model's reason for this step, from its tool call


@dataclasses.dataclass
class ReplyBlock:
    """One piece of a reply before its answer, in the order it happened: text the model wrote, or a run of steps."""

    text: str = ""
    steps: list[StepView] = dataclasses.field(default_factory=list)  # a run of steps when not empty


@dataclasses.dataclass
class ChatMessage:
    role: str  # "user" or "assistant"
    text: str = ""  # the answer: the model's last text (this alone goes into the history sent with later questions)
    blocks: list[ReplyBlock] = dataclasses.field(default_factory=list)  # text and steps before the answer
    citations: list[CitationView] = dataclasses.field(default_factory=list)
    images: list[ImageView] = dataclasses.field(default_factory=list)
    found: bool = True  # has citations; uncited replies are shown in grey
    error: bool = False  # written by the app, not the model: left out of the agent's history


@dataclasses.dataclass
class PresetView:
    name: str  # "free", "budget" or "full"
    label: str
    description: str
    cost: str  # the estimate for the pending document


@dataclasses.dataclass
class OutlineRowView:
    ref: str
    title: str
    summary: str
    indent: str  # CSS length, e.g. "1.5em"
