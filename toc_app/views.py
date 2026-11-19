"""The page, built from small components."""

import reflex as rx

from toc_rag.providers import PROVIDERS

from toc_rag.sessions import describe_duration

from .runtime import settings
from .state import MAX_LEAF_CHOICES, MIN_LEAF_CHOICES, UPLOAD_ID, State
from .viewmodels import ChatMessage, CitationView, DocView, ImageView, OutlineRowView, PageView, PresetView, StepView

# The sample questions, grouped by the sample they are about (its doc id without the content hash). A group is
# only offered while that sample is turned on.
SAMPLE_QUESTIONS = [
    ("Annual report 2026", "fernhill-annual-report-2026", [
        "Which business segment grew fastest in 2026, and by how much?",
        "Show me the revenue by segment chart from the annual report.",
    ]),
    ("Employee handbook", "fernhill-employee-handbook", [
        "How many weeks of parental leave do employees get?",
        "Can I work from another country for a few weeks?",
    ]),
]
EXAMPLES = [(question, sample) for _, sample, questions in SAMPLE_QUESTIONS for question in questions]
KEY_INPUT_ID = "api-key-input"
CHAT_WIDTH = "760px"  # answers and the input keep a readable line length however wide the pane is
ACCEPTED = {
    "application/pdf": [".pdf"],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
}
MUTED = {"size": "1", "color_scheme": "gray"}
BORDER = "1px solid var(--gray-5)"
SURFACE = "var(--color-panel-solid)"
PRIMARY = {"high_contrast": True}
LABEL = {"size": "2", "color_scheme": "gray", "weight": "medium"}
# A sidebar section: no box, just a hairline below it. The sidebar's order already reads as steps.
SECTION = {"width": "100%", "flex_shrink": "0", "padding": "1em 1.25em 1.1em", "border_bottom": BORDER}
SECTION_TITLE = {"size": "2", "weight": "bold"}
PROSE_STYLE = {
    # A wide table scrolls sideways inside its own box instead of widening the text around it (which then
    # ran past the edge of the source panel and was cut off).
    "& table": {"border_collapse": "collapse", "margin": "0.5em 0", "display": "block", "max_width": "100%", "overflow_x": "auto"},
    "& th, & td": {"padding": "4px 12px", "border": "1px solid var(--gray-6)", "text_align": "left", "overflow_wrap": "normal"},
    "& th": {"background": "var(--gray-3)"},
    "& img": {"max_width": "100%", "border_radius": "8px"},
}


@rx.memo
def prose(text: rx.Var[str]) -> rx.Component:
    """Markdown with readable tables and images that fit.

    A memo component, not a plain function: Reflex's markdown element calls a hook while it is
    built, and that is only valid inside a component of its own, never in a list or a condition.
    """
    # No maths: "$34 billion ... $10 billion" is money, not a formula. No raw HTML: document text and model
    # answers are untrusted, so HTML in them shows as text instead of becoming part of the page.
    return rx.box(
        rx.markdown(text, use_math=False, use_katex=False, use_raw=False),
        style=PROSE_STYLE,
        width="100%",
        min_width="0",
        overflow_wrap="anywhere",
    )


# ---- sidebar ----


def model_select(label: str, value: rx.Var, on_change, hint: str, note: str) -> rx.Component:
    """A dropdown of the models this key can use. `note` sits at the top of the open list: what the model must support."""
    return rx.vstack(
        rx.text(label, size="1", weight="medium"),
        rx.select.root(
            rx.select.trigger(placeholder="Choose a model", width="100%", custom_attrs={"aria-label": label}),
            rx.select.content(
                rx.select.group(
                    rx.select.label(note),
                    rx.foreach(State.models, lambda model: rx.select.item(model, value=model)),
                ),
            ),
            value=value,
            on_change=on_change,
            size="1",
        ),
        rx.text(hint, **MUTED),
        spacing="1",
        width="100%",
    )


def key_card() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text("Your API key", **SECTION_TITLE),
            rx.cond(
                State.key_set,
                rx.vstack(
                    rx.hstack(
                        rx.badge(f"{State.provider_label} key set", color_scheme="green"),
                        rx.button("Remove", variant="ghost", size="1", on_click=State.clear_key),
                        align="center",
                    ),
                    model_select(
                        "Model for indexing", State.index_model, State.set_index_model,
                        "Writes summaries and describes images. A small, cheap model is enough.",
                        "Pick a model that supports structured output and images.",
                    ),
                    model_select(
                        "Model for chat", State.agent_model, State.set_agent_model,
                        "Navigates the documents and answers. Must support tool calling.",
                        "Pick a model that supports tool calling.",
                    ),
                    spacing="3",
                    width="100%",
                ),
                rx.vstack(
                    # Outside the form on purpose: the form clears itself after each submit (so the key does
                    # not linger in the box), and a select inside it would snap back to its first value.
                    rx.select.root(
                        rx.select.trigger(width="100%", custom_attrs={"aria-label": "Provider"}),
                        rx.select.content(
                            *[rx.select.item(info.label, value=pid) for pid, info in PROVIDERS.items()]
                        ),
                        value=State.provider,
                        on_change=State.set_provider,
                        size="2",
                    ),
                    rx.form(
                        rx.hstack(
                            rx.input(
                                name="api_key",
                                id=KEY_INPUT_ID,
                                type="password",
                                placeholder=State.key_placeholder,
                                auto_complete="off",
                                width="100%",
                            ),
                            rx.button("Use", type="submit", loading=State.key_checking, **PRIMARY),
                            width="100%",
                        ),
                        on_submit=State.save_key,
                        reset_on_submit=True,
                        width="100%",
                    ),
                    rx.link(
                        f"Get a key from {State.provider_label}",
                        href=State.key_url,
                        is_external=True,
                        size="1",
                    ),
                    spacing="2",
                    width="100%",
                ),
            ),
            rx.cond(State.key_error != "", rx.text(State.key_error, size="2", color_scheme="red")),
            rx.text(
                f"Needed to chat and for AI summaries. Kept in server memory for this session only, never saved "
                f"or logged, and sent only to {State.provider_label}.",
                **MUTED,
            ),
            spacing="2",
            align="start",
            width="100%",
        ),
        **SECTION,
    )


def doc_row(doc: DocView) -> rx.Component:
    return rx.hstack(
        rx.tooltip(
            # The tooltip wraps a span, not the switch: it would stamp its own data-state ("closed") on the
            # switch, which overwrites "checked" / "unchecked", and the switch is styled from that attribute.
            rx.el.span(
                rx.switch(
                    checked=doc.enabled,
                    on_change=lambda _checked: State.toggle_doc(doc.doc_id),
                    size="1",
                    color_scheme="grass",
                    cursor="pointer",
                    aria_label=rx.cond(doc.enabled, "Turn off: leave this document out of answers", "Turn on: use this document in answers"),
                    class_name="doc-switch",
                ),
                display="inline-flex",
            ),
            content=rx.cond(doc.enabled, "Used in answers. Click to turn off.", "Left out of answers. Click to turn on."),
        ),
        rx.vstack(
            # One line: a long name ends in "..." and shows in full on hover.
            rx.text(
                doc.title,
                size="2",
                weight="medium",
                white_space="nowrap",
                overflow="hidden",
                text_overflow="ellipsis",
                max_width="100%",
                title=doc.title,
            ),
            # Plain text, not a badge, so "sample" lines up with the file type.
            rx.hstack(
                rx.cond(doc.sample, rx.text("sample", size="1", weight="medium", color_scheme="amber", high_contrast=True)),
                rx.cond(doc.sample, rx.text("·", **MUTED)),
                rx.text(doc.kind, **MUTED),
                spacing="1",
                align="center",
            ),
            spacing="0",
            align="start",
            flex="1",
            min_width="0",  # lets the title shrink and truncate instead of pushing the buttons out
            opacity=rx.cond(doc.enabled, "1", "0.5"),  # turned off: dimmed, still browsable
            on_click=State.open_browse(doc.doc_id),  # the name opens the outline too
            cursor="pointer",
        ),
        # An icon, so the name keeps the width. No `title` attribute: the e2e run finds citation chips by it.
        rx.tooltip(
            rx.icon_button(
                rx.icon("list-tree", size=15),
                size="1",
                variant="ghost",
                color_scheme="gray",
                aria_label="Browse the outline",
                on_click=State.open_browse(doc.doc_id),
            ),
            content="Browse the outline",
        ),
        rx.cond(
            ~doc.sample,
            rx.icon_button(
                rx.icon("trash-2", size=14),
                size="1",
                variant="ghost",
                color_scheme="red",
                title="Delete this document",
                on_click=State.delete_doc(doc.doc_id),
            ),
        ),
        width="100%",
        align="center",
        spacing="2",
        padding_y="0.4em",
        border_top=BORDER,
    )


def library_card() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text("Library", **SECTION_TITLE),
            rx.cond(
                State.docs.length() > 0,
                rx.vstack(rx.foreach(State.docs, doc_row), spacing="0", width="100%"),
                rx.text("No documents yet.", **MUTED),
            ),
            rx.cond(
                State.docs.length() > 0,
                rx.text("Switched off: left out of answers, still browsable.", **MUTED),
            ),
            spacing="2",
            align="start",
            width="100%",
        ),
        **SECTION,
    )


def upload_form() -> rx.Component:
    """A drop zone that starts reading the file as soon as one is chosen or dropped: no separate Upload button."""
    return rx.vstack(
        rx.upload(
            rx.cond(
                State.building,
                rx.vstack(
                    rx.spinner(size="2"),
                    rx.text(State.building_label, size="2", text_align="center"),
                    align="center",
                    spacing="2",
                ),
                rx.vstack(
                    rx.icon("upload", size=22),
                    rx.text("Drop a .docx or .pdf here, or click to choose", size="2", text_align="center"),
                    rx.text(
                        f"Up to {settings.max_upload_bytes // (1024 * 1024)} MB, and {settings.max_pdf_pages} pages for a PDF. "
                        "Scanned PDFs and ZIP files are not accepted.",
                        **MUTED,
                    ),
                    align="center",
                    spacing="1",
                ),
            ),
            id=UPLOAD_ID,
            accept=ACCEPTED,
            max_files=1,
            max_size=settings.max_upload_bytes,
            multiple=False,
            on_drop=State.handle_upload,
            disabled=State.building,
            padding="1em",
            border="1px dashed var(--gray-7)",
            border_radius="8px",
            background="var(--gray-2)",
            width="100%",
            cursor=rx.cond(State.building, "progress", "pointer"),
            _hover={"border_color": "var(--gray-9)", "background": "var(--gray-3)"},
        ),
        rx.text("You choose how to index it (and see the cost) before anything is spent.", **MUTED),
        spacing="2",
        width="100%",
    )


def preset_option(choice: PresetView) -> rx.Component:
    chosen = State.preset == choice.name
    return rx.box(
        rx.hstack(
            rx.text(choice.label, size="2", weight="bold"),
            rx.text(choice.description, size="1", color_scheme="gray"),
            align="baseline",
            wrap="wrap",
            spacing="2",
        ),
        rx.text(choice.cost, size="1"),
        on_click=State.set_preset(choice.name),
        cursor="pointer",
        width="100%",
        padding="0.5em 0.7em",
        border_radius="8px",
        # The border width never changes (only its colour); the extra ring is a shadow, which takes no space.
        # A 1px -> 2px border would resize the cards and shift the whole panel on every selection.
        # Only the chosen preset gets a frame; the others are plain rows that highlight on hover.
        border=rx.cond(chosen, "1px solid var(--gray-12)", "1px solid transparent"),
        box_shadow=rx.cond(chosen, "0 0 0 1px var(--gray-12)", "none"),
        background=rx.cond(chosen, SURFACE, "transparent"),
        _hover={"background": rx.cond(chosen, SURFACE, "var(--gray-3)")},
        custom_attrs={"role": "radio", "aria-checked": rx.cond(chosen, "true", "false"), "data-preset": choice.name},
    )


def option_row(label: str, control: rx.Component) -> rx.Component:
    return rx.hstack(rx.text(label, size="1", flex="1"), control, align="center", width="100%")


def choice_select(items: list[tuple[str, str]], value: rx.Var, on_change, **props) -> rx.Component:
    """A small select whose items show a label but send a value."""
    return rx.select.root(
        rx.select.trigger(min_width="9em"),
        rx.select.content(*[rx.select.item(label, value=item) for item, label in items]),
        value=value,
        on_change=on_change,
        size="1",
        **props,
    )


def advanced_options() -> rx.Component:
    return rx.vstack(
        option_row(
            "Split sections too big to read in one go",
            rx.switch(checked=State.opt_split, on_change=State.set_opt_split, size="1"),
        ),
        option_row(
            "Largest section before splitting",
            choice_select([(c, f"{c} tokens") for c in MAX_LEAF_CHOICES], State.opt_max_leaf, State.set_opt_max_leaf),
        ),
        option_row(
            "Small sections",
            choice_select(
                [("off", "Keep as they are"), ("merge", "Merge tiny ones"), ("fold", "Merge and fold")],
                State.opt_small,
                State.set_opt_small,
            ),
        ),
        option_row(
            "Tiny means under",
            choice_select([(c, f"{c} tokens") for c in MIN_LEAF_CHOICES], State.opt_min_leaf, State.set_opt_min_leaf),
        ),
        option_row(
            "Section summaries",
            choice_select(
                [("llm", "AI summaries"), ("preview", "Free previews")], State.opt_summaries, State.set_opt_summaries
            ),
        ),
        option_row(
            "Summary length",
            choice_select(
                [("short", "Short"), ("detailed", "Detailed")],
                State.opt_summary_length,
                State.set_opt_summary_length,
                disabled=State.opt_summaries == "preview",
            ),
        ),
        option_row(
            "Describe images with the model",
            rx.switch(checked=State.opt_images, on_change=State.set_opt_images, size="1"),
        ),
        rx.text(
            "Merging joins runs of tiny sibling sections and sections with a single subsection. Folding also turns "
            "any part of the outline small enough to read in one go into one section. Original headings are kept.",
            **MUTED,
        ),
        spacing="2",
        width="100%",
        padding="0.6em",
        border=BORDER,
        border_radius="8px",
    )


def pending_view() -> rx.Component:
    return rx.vstack(
        rx.text(State.pending_name, weight="medium", size="2", word_break="break-word"),
        rx.cond(State.replace_note != "", rx.callout(State.replace_note, icon="refresh-cw", size="1", color_scheme="gray", id="replace-note")),
        rx.vstack(
            rx.foreach(State.preset_choices, preset_option),
            spacing="2",
            width="100%",
            custom_attrs={"role": "radiogroup"},
        ),
        rx.button(
            rx.cond(State.show_advanced, rx.icon("chevron-down", size=14), rx.icon("chevron-right", size=14)),
            rx.cond(State.preset == "custom", "Advanced options (custom)", "Advanced options"),
            variant="ghost",
            size="1",
            color_scheme="gray",
            on_click=State.toggle_advanced,
        ),
        rx.cond(State.show_advanced, advanced_options()),
        rx.text(State.pending_detail, size="2", id="pending-detail"),
        rx.cond(State.index_hint != "", rx.text(State.index_hint, size="1", color_scheme="amber")),
        rx.hstack(
            rx.button(
                "Index it",
                on_click=State.ask_to_index,
                loading=State.rebuilding,
                disabled=State.index_hint != "",
                **PRIMARY,
            ),
            rx.button("Cancel", variant="soft", color_scheme="gray", on_click=State.cancel_pending),
        ),
        confirm_indexing_dialog(),
        spacing="2",
        align="start",
        width="100%",
    )


def _cost_row(label: str, value) -> rx.Component:
    return rx.data_list.item(
        rx.data_list.label(label, min_width="96px"),
        rx.data_list.value(value),
        align="center",
    )


def confirm_indexing_dialog() -> rx.Component:
    """Shown before indexing spends anything on the visitor's key: what will happen, and what it costs."""
    return rx.alert_dialog.root(
        rx.alert_dialog.content(
            rx.alert_dialog.title(f"Index {State.pending_name}?"),
            rx.alert_dialog.description(
                "This uses your API key. Your provider charges the cost to your account.", **MUTED
            ),
            rx.box(
                rx.data_list.root(
                    _cost_row("Preset", State.preset_label),
                    _cost_row("Model", f"{State.provider_label} · {State.index_model}"),
                    _cost_row("Document", State.pending_size),
                    _cost_row("Model calls", f"about {State.pending_calls}"),
                    _cost_row("Tokens", State.pending_tokens),
                    size="2",
                    spacing="2",
                ),
                padding="1em",
                margin_y="1em",
                border=BORDER,
                border_radius="8px",
                id="confirm-cost",
            ),
            rx.hstack(
                rx.alert_dialog.cancel(rx.button("Cancel", variant="soft", color_scheme="gray")),
                rx.alert_dialog.action(rx.button("Start indexing", on_click=State.start_indexing, **PRIMARY)),
                justify="end",
                spacing="3",
            ),
            max_width="420px",
        ),
        open=State.confirm_open,
        on_open_change=State.set_confirm_open,
    )


def indexing_view() -> rx.Component:
    return rx.vstack(
        rx.text(rx.cond(State.needs_key_to_index, "Indexing with your key...", "Indexing..."), size="2", weight="medium"),
        rx.progress(value=State.index_percent, max=100, width="100%"),
        rx.text(f"{State.index_done} of {State.index_total}: {State.index_label}", **MUTED),
        spacing="2",
        align="start",
        width="100%",
    )


def upload_card() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text("Add a document", **SECTION_TITLE),
            rx.cond(State.indexing, indexing_view(), rx.cond(State.has_pending, pending_view(), upload_form())),
            rx.cond(State.upload_error != "", rx.text(State.upload_error, size="2", color_scheme="red")),
            spacing="2",
            align="start",
            width="100%",
        ),
        **SECTION,
    )


def agent_settings_card() -> rx.Component:
    """How the chat agent reads the library. Collapsed by default: the defaults are fine for most visitors."""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text("Agent settings", **SECTION_TITLE),
                rx.spacer(),
                rx.cond(State.show_agent_settings, rx.icon("chevron-down", size=16), rx.icon("chevron-right", size=16)),
                on_click=State.toggle_agent_settings,
                cursor="pointer",
                align="center",
                width="100%",
                id="agent-settings-toggle",
            ),
            rx.cond(
                State.show_agent_settings,
                rx.vstack(
                    rx.hstack(
                        rx.text("Outline levels per look", size="2"),
                        rx.select(
                            ["1", "2", "3"],
                            value=State.listing_depth,
                            on_change=State.set_listing_depth,
                            size="1",
                            id="listing-depth",
                        ),
                        align="center",
                        justify="between",
                        width="100%",
                    ),
                    rx.text(
                        "How many levels of a document's outline the agent sees each time it looks. "
                        "More levels means fewer steps to reach a section, but longer listings.",
                        **MUTED,
                    ),
                    rx.hstack(
                        rx.text("Keyword search", size="2"),
                        rx.switch(
                            checked=State.agent_search,
                            on_change=State.set_agent_search,
                            size="1",
                            id="agent-search",
                        ),
                        align="center",
                        justify="between",
                        width="100%",
                    ),
                    rx.text(
                        "Lets the agent also look for exact words across your documents, then read the sections "
                        "it finds. Helps with names, numbers and terms the outline does not show. Still no vectors.",
                        **MUTED,
                    ),
                    spacing="2",
                    width="100%",
                ),
            ),
            spacing="2",
            align="start",
            width="100%",
        ),
        **SECTION,
    )


# ---- chat ----


def citation_chip(citation: CitationView) -> rx.Component:
    return rx.button(
        rx.icon("file-text", size=14),
        rx.text(citation.title, size="1", weight="medium"),
        rx.cond(citation.location != "", rx.text(citation.location, size="1", color_scheme="gray")),
        variant="outline",
        color_scheme="gray",
        size="1",
        radius="full",
        on_click=State.open_source(citation.ref),
        title=citation.doc_title,
    )


def answer_image(image: ImageView) -> rx.Component:
    return rx.vstack(
        rx.image(src=image.url, alt=image.description, max_width="420px", width="100%", border_radius="8px", border=BORDER),
        rx.text(image.description, **MUTED),
        spacing="1",
        align="start",
    )


def step_line(step: StepView) -> rx.Component:
    """What the model said, then what it did. Smaller than the answer: the path is how it got there, the answer is the point."""
    return rx.vstack(
        rx.cond(step.note != "", rx.text(step.note, size="2")),
        rx.hstack(
            rx.icon("corner-down-right", size=12, color="var(--gray-9)"),
            rx.text(step.label, size="1", color_scheme="gray"),
            spacing="1",
            align="center",
        ),
        spacing="0",
        align="start",
    )


def step_list(steps) -> rx.Component:
    """The agent's path, as one block set off by a rule on its left."""
    return rx.vstack(
        rx.foreach(steps, step_line),
        spacing="2",
        align="start",
        padding_left="0.85em",
        border_left="2px solid var(--gray-5)",
    )


def live_answer() -> rx.Component:
    """The answer being written: its steps so far, then its text, or "Working..." before any text."""
    return rx.vstack(
        rx.cond(State.live_steps.length() > 0, step_list(State.live_steps)),
        rx.cond(
            State.live_text == "",
            rx.hstack(rx.spinner(size="1"), rx.text("Working...", size="2", color_scheme="gray"), align="center"),
            prose(text=State.live_text),
        ),
        spacing="3",
        align="start",
        max_width="95%",
    )


def assistant_message(message: ChatMessage) -> rx.Component:
    return rx.vstack(
        rx.cond(message.steps.length() > 0, step_list(message.steps)),
        # Every reply looks the same, cited or not: "not found" is still an answer.
        rx.cond(message.text != "", prose(text=message.text)),
        rx.foreach(message.images, answer_image),
        rx.cond(
            message.citations.length() > 0,
            rx.hstack(rx.foreach(message.citations, citation_chip), wrap="wrap", spacing="2"),
        ),
        spacing="3",
        align="start",
        max_width="95%",
    )


def message_view(message: ChatMessage) -> rx.Component:
    return rx.cond(
        message.role == "user",
        rx.box(
            rx.text(message.text, size="3"),
            align_self="flex-end",
            background="var(--gray-4)",
            padding="0.55em 0.95em",
            border_radius="12px",
            max_width="80%",
        ),
        assistant_message(message),
    )


def example_question(question: str) -> rx.Component:
    """A sample question as a plain line of text: a button, with no box until hovered."""
    return rx.el.button(
        question,
        on_click=State.ask_example(question),
        type="button",
        class_name="example-question",
    )


def question_group(title: str, sample: str, questions: list[str]) -> rx.Component:
    """One sample's questions under its name, offered only while that sample is turned on."""
    return rx.cond(
        State.enabled_sample_names.contains(sample),
        rx.box(
            rx.text(title, size="1", weight="medium", color_scheme="gray", margin_bottom="0.2em"),
            *[example_question(question) for question in questions],
            width="100%",
        ),
    )


def chat_hint_line() -> rx.Component:
    """What is still needed before chatting, as one quiet line. Without a key it links to the key field."""
    return rx.cond(
        ~State.key_set,
        rx.text(
            rx.el.button(
                "Add an API key",
                type="button",
                class_name="text-link",
                on_click=rx.call_script(
                    f"(e => {{ if (e) {{ e.scrollIntoView({{block: 'center'}}); e.focus(); }} }})"
                    f"(document.getElementById('{KEY_INPUT_ID}'))"
                ),
            ),
            " to ask. You can browse the library without one.",
            size="2",
            color_scheme="gray",
        ),
        rx.cond(State.chat_hint != "", rx.text(State.chat_hint, size="2", color_scheme="gray")),
    )


def empty_chat() -> rx.Component:
    """The empty chat, centred in the pane: a heading, the sample questions by document, and what is missing."""
    return rx.vstack(
        rx.heading("Ask the documents", size="5", weight="bold", letter_spacing="-0.01em"),
        rx.cond(
            State.samples_enabled,  # with every sample off, these questions have nothing to be answered from
            rx.vstack(
                *[question_group(title, sample, questions) for title, sample, questions in SAMPLE_QUESTIONS],
                spacing="4",
                width="100%",
            ),
        ),
        chat_hint_line(),
        spacing="5",
        align="start",
        width="100%",
        max_width="560px",
    )


def composer() -> rx.Component:
    return rx.form(
        rx.hstack(
            rx.input(
                name="question",
                placeholder=rx.cond(
                    ~State.key_set,
                    "Add your API key to chat",
                    rx.cond(State.agent_model == "", "Choose a chat model to start", "Ask a question about the documents"),
                ),
                disabled=~State.can_chat,
                auto_complete="off",
                variant="soft",
                size="3",
                background="transparent",
                flex="1",
            ),
            rx.icon_button(
                rx.icon("arrow-up", size=18),
                type="submit",
                radius="full",
                size="3",
                loading=State.thinking,
                disabled=~State.can_chat,
                title="Send",
                **PRIMARY,
            ),
            align="center",
            width="100%",
            padding="0.4em 0.4em 0.4em 0.9em",
            background=SURFACE,
            border=BORDER,
            border_radius="12px",
        ),
        on_submit=State.ask,
        reset_on_submit=True,
        width="100%",
    )


def chat_panel() -> rx.Component:
    empty = (State.messages.length() == 0) & ~State.thinking
    return rx.vstack(
        # While the chat is empty, its first screen fills the pane, centred; the (empty) scroll area stays
        # mounted so the scroll-to-end script always finds it.
        rx.cond(empty, rx.center(empty_chat(), flex="1", width="100%", padding="2em 1.25em", min_height="0")),
        rx.scroll_area(
            rx.vstack(
                rx.foreach(State.messages, message_view),
                rx.cond(State.thinking, live_answer()),
                rx.box(id="chat-end"),
                spacing="5",
                width="100%",
                max_width=CHAT_WIDTH,
                margin="0 auto",
                padding="1.5em 1.25em 0.5em",
                custom_attrs={"data-zoom-area": ""},  # pictures here enlarge on click (ZOOM_SCRIPT)
            ),
            type="auto",
            scrollbars="vertical",
            flex=rx.cond(empty, "0", "1"),
            width="100%",
            min_height="0",
        ),
        rx.box(
            rx.cond(
                (State.messages.length() > 0) | State.thinking,
                rx.hstack(
                    rx.button(
                        rx.icon("eraser", size=14),
                        "Clear chat",
                        variant="ghost",
                        color_scheme="gray",
                        size="1",
                        on_click=State.clear_chat,
                        title="Start a new conversation. Your documents and settings stay.",
                        id="clear-chat",
                    ),
                    justify="end",
                    width="100%",
                    padding_bottom="0.4em",
                ),
            ),
            composer(),
            padding="0.5em 1.25em 1.25em",
            width="100%",
            max_width=CHAT_WIDTH,
            margin="0 auto",
        ),
        spacing="0",
        height=["80vh", "80vh", "100%"],
        min_height="420px",
        min_width="0",
        width="100%",
        background="var(--gray-1)",
    )


# ---- dialogs ----


def outline_row(row: OutlineRowView) -> rx.Component:
    return rx.box(
        rx.button(
            rx.vstack(
                rx.text(row.title, size="2", weight="medium", color="var(--gray-12)", text_align="left"),
                rx.text(row.summary, size="1", color_scheme="gray", white_space="normal", text_align="left", class_name="clamp-2"),
                spacing="0",
                align="start",
            ),
            variant="ghost",
            height="auto",
            on_click=State.open_source(row.ref),
            justify_content="start",
            width="100%",
        ),
        padding_left=row.indent,
        width="100%",
    )


def source_view() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.text("Source", **LABEL),
            rx.spacer(),
            rx.icon_button(
                rx.icon("x", size=14),
                variant="ghost",
                color_scheme="gray",
                size="1",
                title="Close panel",
                on_click=State.set_source_open(False),
            ),
            align="center",
            width="100%",
        ),
        rx.text(State.source_title, size="4", weight="bold"),
        rx.text(State.source_location, **MUTED),
        rx.cond(
            State.source_summary != "",
            rx.vstack(
                rx.text("Summary", size="1", weight="medium", color_scheme="gray"),
                rx.text(State.source_summary, size="2", color="var(--gray-11)"),
                spacing="1",
                padding_left="0.85em",
                border_left="2px solid var(--gray-5)",
            ),
        ),
        rx.cond(
            State.source_pages.length() > 0,
            rx.segmented_control.root(
                rx.segmented_control.item("Text", value="text"),
                rx.segmented_control.item("Pages", value="pages"),
                value=State.source_tab,
                on_change=State.set_source_tab,
                size="1",
                id="source-tab",
            ),
        ),
        rx.cond(State.source_tab == "pages", source_pages(), prose(text=State.source_text)),
        spacing="3",
        align="start",
        width="100%",
    )


def source_page(page: PageView) -> rx.Component:
    return rx.vstack(
        rx.text(f"p. {page.label}", **MUTED),
        # Rendered when first asked for, so only load the pages scrolled to. Click to enlarge (ZOOM_SCRIPT).
        rx.el.img(
            src=page.url,
            alt=f"Page {page.label}",
            loading="lazy",
            width="100%",
            style={"border": BORDER, "border_radius": "6px", "background": "white", "min_height": "120px"},
        ),
        spacing="1",
        width="100%",
    )


def source_pages() -> rx.Component:
    """The section's pages, as they look in the PDF."""
    return rx.vstack(
        rx.text("Click a page to enlarge it.", **MUTED),
        rx.foreach(State.source_pages, source_page),
        rx.cond(State.source_pages_note != "", rx.text(State.source_pages_note, **MUTED)),
        spacing="4",
        width="100%",
        id="source-pages",
    )


def browse_view() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.text("Outline", **LABEL),
            rx.spacer(),
            rx.icon_button(
                rx.icon("x", size=14),
                variant="ghost",
                color_scheme="gray",
                size="1",
                title="Close panel",
                on_click=State.set_browse_open(False),
            ),
            align="center",
            width="100%",
        ),
        rx.text(State.browse_title, size="4", weight="bold"),
        rx.cond(State.browse_structure != "", rx.text(State.browse_structure, **MUTED, id="browse-structure")),
        rx.text("Click a section to read it.", **MUTED),
        rx.vstack(rx.foreach(State.browse_rows, outline_row), spacing="1", width="100%"),
        spacing="3",
        align="start",
        width="100%",
    )


def source_panel() -> rx.Component:
    """The outline or source being read. Hidden until a citation or an outline is opened, so the chat has the
    width the rest of the time."""
    is_open = State.source_open | State.browse_open
    return rx.box(
        rx.cond(State.source_open, source_view(), rx.cond(State.browse_open, browse_view())),
        id="source-panel",
        custom_attrs={"data-zoom-area": ""},  # pictures here enlarge on click (ZOOM_SCRIPT)
        display=rx.cond(is_open, "block", "none"),
        width=["100%", "100%", "420px"],
        padding="1.25em",
        overflow_y="auto",
        min_height="0",
        min_width="0",
        border_left=[BORDER, BORDER, BORDER],
        border_top=[BORDER, BORDER, "none"],
        background=SURFACE,
    )


# ---- page ----


def session_timer() -> rx.Component:
    """How long until this visitor's uploads are deleted: a live countdown once a session exists."""
    return rx.cond(
        State.session_expires_at > 0,
        rx.hstack(
            rx.icon("timer", size=14, color="var(--gray-10)"),
            rx.text("Uploads deleted in ", size="1", color_scheme="gray"),
            rx.el.span(
                id="session-countdown",
                custom_attrs={"data-expires-at": State.session_expires_at},
                style={"font_variant_numeric": "tabular-nums", "font_size": "var(--font-size-1)", "font_weight": "500"},
            ),
            spacing="1",
            align="center",
            title="Everything you add is deleted when this reaches zero, or when you end the session.",
        ),
        rx.text(
            f"Uploads are kept for {describe_duration(settings.session_ttl_seconds)}",
            size="1",
            color_scheme="gray",
            title="The timer starts when you add your first document.",
        ),
    )


def header() -> rx.Component:
    return rx.hstack(
        rx.link(  # back to the home page
            rx.hstack(
                rx.icon("book-open-text", size=20, stroke_width=1.75),
                rx.vstack(
                    rx.text("TOC RAG", size="3", weight="bold"),
                    rx.text("Vectorless RAG: chat by navigating a table of contents", size="1", color_scheme="gray", display=["none", "none", "block"]),
                    spacing="0",
                    align="start",
                ),
                align="center",
            ),
            href="/",
            underline="none",
            color="inherit",
            title="Home",
        ),
        rx.spacer(),
        session_timer(),
        rx.button(
            rx.icon("trash-2", size=14),
            "End session and delete my data",
            variant="outline",
            color_scheme="gray",
            radius="full",
            size="1",
            on_click=State.end_session,
        ),
        align="center",
        width="100%",
        padding="0.75em 1.25em",
        border_bottom=BORDER,
        background=SURFACE,
        wrap="wrap",
    )


def left_column() -> rx.Component:
    return rx.vstack(
        key_card(),
        library_card(),
        upload_card(),
        agent_settings_card(),
        spacing="0",
        align="stretch",
        overflow_y="auto",
        min_height="0",
        min_width="0",
        background="var(--gray-2)",
        border_right=["none", "none", BORDER],
    )


def index() -> rx.Component:
    """The app fills the window: header on top, then sidebar, chat and (when open) the source panel."""
    return rx.box(
        header(),
        rx.grid(
            left_column(),
            chat_panel(),
            source_panel(),
            columns=rx.breakpoints(initial="1", lg="300px minmax(0, 1fr) auto"),
            flex="1",
            min_height="0",
            width="100%",
        ),
        display="flex",
        flex_direction="column",
        height=rx.breakpoints(initial="auto", lg="100vh"),
        min_height="100vh",
        width="100%",
        background=SURFACE,
    )
