from langchain_core.language_models import BaseChatModel
import json

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field

from toc_rag.agent import (
    AnswerResult,
    ChatTurn,
    Draft,
    LibraryNavigator,
    Navigator,
    Step,
    run_agent,
    stream_agent,
)
from toc_rag.agent.citations import extract_markers
from toc_rag.indexing.blocks import Heading, Image, Paragraph
from toc_rag.indexing.tree import build_tree
from toc_rag.models import DocumentIndex, ImageRecord


class ScriptedModel(BaseChatModel):
    """Returns preset replies in order, so the graph can be tested without an API."""

    replies: list  # AIMessages, or exceptions to raise as provider failures
    seen: list = Field(default_factory=list)  # the messages passed to each call

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.seen.append(list(messages))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):  # a scripted provider failure
            raise reply
        return ChatResult(generations=[ChatGeneration(message=reply)])

    def bind_tools(self, tools, **kwargs):
        return self


class StreamingModel(ScriptedModel):
    """Like ScriptedModel, but sends text replies in 4-character pieces and tool calls as streamed chunks."""

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(list(messages))
        reply = self.replies.pop(0)
        # Text first, 4 characters at a time, then any tool calls: the order a real model sends them in.
        chunks = [AIMessageChunk(reply.content[i : i + 4]) for i in range(0, len(reply.content), 4)]
        if reply.tool_calls:
            calls = [
                {"name": c["name"], "args": json.dumps(c["args"]), "id": c["id"], "index": i}
                for i, c in enumerate(reply.tool_calls)
            ]
            chunks.append(AIMessageChunk("", tool_call_chunks=calls))
        for chunk in chunks:
            yield ChatGenerationChunk(message=chunk)


def call(name: str, **args) -> AIMessage:
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": f"call-{name}"}])


def make_ships() -> DocumentIndex:
    blocks = [
        Heading(1, "Ship"),
        Heading(2, "Crew"),
        Paragraph("The captain is Ada."),
        Image(b"x", "png"),
        Heading(2, "Engines"),
        Paragraph("Two fusion engines."),
    ]
    root, _ = build_tree(blocks, "Ships", "markdown")
    image = ImageRecord(id="img-1", file="images/img-1.png", mime="image/png", node_id="1.1", description="crew photo")
    return DocumentIndex(
        doc_id="ships", title="Ships", source_path="ships.md", kind="markdown", summary="About ships.", root=root,
        images=[image],
    )


def make_cars() -> DocumentIndex:
    blocks = [Heading(1, "Cars"), Heading(2, "Engines"), Paragraph("A V8 engine.")]
    root, _ = build_tree(blocks, "Cars", "markdown")
    return DocumentIndex(
        doc_id="cars", title="Cars", source_path="cars.md", kind="markdown", summary="About cars.", root=root
    )


def test_navigator_marks_visited_and_lists_images():
    nav = Navigator(make_ships())
    assert "[1] Ship" in nav.list_children("root")
    nav.read_node("1.2")
    listing = nav.go_up("1.2")
    assert "[1.2] Engines (leaf, visited)" in listing
    assert "[1.1] Crew (leaf)" in listing
    assert "img-1: crew photo" in nav.read_node("1.1")
    assert nav.go_up("root") == "Already at the top of the document."
    assert nav.read_node("9.9") == "Unknown node id '9.9'."


def test_library_navigator_requires_an_open_document():
    nav = LibraryNavigator([make_ships(), make_cars()])
    assert "No document is open" in nav.list_children("root")
    assert "[ships] Ships (markdown): About ships." in nav.list_documents()
    assert "Unknown document id" in nav.open_document("nope")

    opened = nav.open_document("cars")
    assert 'Opened "Cars"' in opened and "[1] Cars" in opened
    # Qualified ids from a section header work as tool input too.
    assert "A V8 engine." in nav.read_node("cars:1.1")
    assert "switch documents" in nav.go_up("root")


def test_single_document_library_starts_open():
    nav = LibraryNavigator([make_ships()])
    assert nav.current == "ships"
    assert "[1] Ship" in nav.list_children("root")


def test_agent_navigates_backtracks_and_answers():
    model = ScriptedModel(
        replies=[
            call("list_children", node_id="root"),
            call("list_children", node_id="1"),
            call("read_node", node_id="1.2"),  # wrong branch
            call("go_up", node_id="1.2"),
            call("read_node", node_id="1.1"),
            AIMessage(
                "The captain is Ada [ships:1.1] [bogus:9.9] [ships:1, ships:9.9]. "
                "[img:ships:img-1] [img:ships:img-9]"
            ),
        ]
    )

    result = run_agent(LibraryNavigator([make_ships()]), model, "Who is the captain?", max_steps=10)

    assert result.found
    assert result.text == "The captain is Ada."
    assert [(c.doc_id, c.node_id) for c in result.citations] == [("ships", "1.1")]
    assert result.citations[0].doc_title == "Ships"
    assert result.citations[0].location == "Ship > Crew"
    assert [(i.doc_id, i.image_id, i.file) for i in result.images] == [("ships", "img-1", "images/img-1.png")]


def test_agent_routes_between_documents_and_streams_steps():
    model = ScriptedModel(
        replies=[
            call("open_document", doc_id="cars"),  # wrong document
            call("list_children", node_id="1"),
            call("list_documents"),
            call("open_document", doc_id="ships"),
            call("read_node", node_id="1.1"),
            AIMessage("Ada. [ships:1.1]"),
        ]
    )

    events = list(stream_agent(LibraryNavigator([make_ships(), make_cars()]), model, "Who is the captain?", 10))

    *steps, result = events
    steps = [event for event in steps if not isinstance(event, Draft)]  # a model that cannot stream sends one Draft
    assert all(isinstance(step, Step) for step in steps)
    assert isinstance(result, AnswerResult)
    assert [step.label for step in steps] == [
        'Opened "Cars"',
        'Looked inside "Cars"',
        "Listed documents",
        'Opened "Ships"',
        'Read "Crew"',
    ]
    assert steps[-1].doc_id == "ships" and steps[-1].node_id == "1.1"
    assert [(c.doc_id, c.node_id) for c in result.citations] == [("ships", "1.1")]


def test_agent_prompt_lists_documents_and_includes_history():
    model = ScriptedModel(replies=[AIMessage("Nothing.")])
    history = [ChatTurn(role="user", content="Hi"), ChatTurn(role="assistant", content="Hello")]

    run_agent(LibraryNavigator([make_ships(), make_cars()]), model, "And cars?", max_steps=5, history=history)

    system, *conversation = model.seen[0]
    assert "[ships] Ships" in system.content and "[cars] Cars" in system.content
    assert "No document is open yet" in system.content
    assert [type(m) for m in conversation] == [HumanMessage, AIMessage, HumanMessage]
    assert [m.content for m in conversation] == ["Hi", "Hello", "And cars?"]


def test_agent_gives_up_after_step_budget():
    model = ScriptedModel(replies=[call("list_children", node_id="root") for _ in range(3)])
    result = run_agent(LibraryNavigator([make_ships()]), model, "Anything?", max_steps=3)
    assert not result.found
    assert "budget" in result.text and result.error


def test_agent_not_found():
    model = ScriptedModel(replies=[AIMessage("The library has no info about cargo.")])
    result = run_agent(LibraryNavigator([make_ships()]), model, "Cargo?", max_steps=5)
    assert not result.found
    assert result.text == "The library has no info about cargo."
    assert result.citations == []


def test_agent_cannot_cite_what_it_did_not_read():
    model = ScriptedModel(
        replies=[
            call("list_children", node_id="1"),
            call("read_node", node_id="1.2"),
            AIMessage("Engines [ships:1.2]. Crew [ships:1.1]. [img:ships:img-1]"),  # 1.1 and its image were never read
        ]
    )
    result = run_agent(LibraryNavigator([make_ships()]), model, "?", max_steps=10)
    assert [c.node_id for c in result.citations] == ["1.2"]
    assert result.images == []


def test_agent_unknown_tool_and_bad_arguments_go_back_to_the_model():
    model = ScriptedModel(
        replies=[
            call("fly"),
            AIMessage("", tool_calls=[{"name": "read_node", "args": {}, "id": "call-bad"}]),
            AIMessage("Done."),
        ]
    )
    result = run_agent(LibraryNavigator([make_ships()]), model, "?", max_steps=5)
    tool_results = [m.content for m in model.seen[-1] if isinstance(m, ToolMessage)]
    assert tool_results == ["Unknown tool 'fly'.", "Invalid arguments for read_node."]
    assert result.text == "Done." and not result.found
    assert not result.error  # a real reply without citations is not an error: it stays in the history


def read_call(reason: str = "", text: str = "") -> AIMessage:
    args = {"node_id": "1.1", **({"reason": reason} if reason else {})}
    return AIMessage(text, tool_calls=[{"name": "read_node", "args": args, "id": "c1"}])


def test_the_step_carries_its_reason_and_drafts_are_only_the_answer():
    model = StreamingModel(
        replies=[
            read_call(reason="The crew section names the captain."),
            AIMessage("The captain is Ada [ships:1.1]. She has sailed for years [ships:1.1]."),
        ]
    )

    events = list(stream_agent(LibraryNavigator([make_ships()]), model, "Who is the captain?", 5))

    *middle, result = events
    step = next(e for e in middle if isinstance(e, Step))
    assert step.note == "The crew section names the captain."  # the reason from the tool call travels with its step
    drafts = [e.text for e in middle if isinstance(e, Draft)]
    assert len(drafts) > 3  # the answer arrived in pieces
    assert all(later.startswith(earlier) for earlier, later in zip(drafts, drafts[1:]))
    assert not any("[" in d for d in drafts)  # no marker, not even half of one
    assert drafts[-1] == "The captain is Ada. She has sailed for years." == result.text
    # The Step comes before any draft: every draft is answer text.
    kinds = [type(e).__name__ for e in middle]
    assert kinds.index("Step") < kinds.index("Draft")
    assert [c.node_id for c in result.citations] == ["1.1"]


def test_a_sentence_written_before_a_tool_call_is_a_note_never_a_draft():
    # Some models still say a sentence before calling a tool. It is held back, then goes with the step.
    model = StreamingModel(replies=[read_call(text="Let me check the crew section."), AIMessage("Ada [ships:1.1].")])

    events = list(stream_agent(LibraryNavigator([make_ships()]), model, "Who is the captain?", 5))

    *middle, result = events
    step = next(e for e in middle if isinstance(e, Step))
    assert step.note == "Let me check the crew section."
    drafts = [e.text for e in middle if isinstance(e, Draft)]
    assert drafts == ["Ada."]  # a one-sentence answer is held to the end of the reply, then sent once
    assert result.text == "Ada." and result.found


def test_a_reason_wins_over_text_before_the_call():
    model = StreamingModel(replies=[read_call(reason="Crew names.", text="Checking."), AIMessage("Ada [ships:1.1].")])
    step = next(e for e in stream_agent(LibraryNavigator([make_ships()]), model, "Who?", 5) if isinstance(e, Step))
    assert step.note == "Crew names."


def test_tools_accept_a_reason():
    from toc_rag.agent.graph import make_tools

    tools = {t.name: t for t in make_tools(LibraryNavigator([make_ships()]), search=True)}
    assert all("reason" in t.args for t in tools.values())
    assert "The captain is Ada." in tools["read_node"].invoke({"node_id": "ships:1.1", "reason": "To find the captain."})


def test_agent_asks_again_after_an_empty_reply():
    model = ScriptedModel(
        replies=[
            call("read_node", node_id="1.1"),
            AIMessage(""),  # nothing at all: no text, no tool call
            AIMessage("The captain is Ada [ships:1.1]."),
        ]
    )
    result = run_agent(LibraryNavigator([make_ships()]), model, "Who?", max_steps=5)
    assert result.found and result.text == "The captain is Ada." and not result.error
    assert len(model.seen) == 3  # the empty reply was retried


def test_agent_reports_a_reply_that_stays_empty():
    model = ScriptedModel(replies=[AIMessage(""), AIMessage(""), AIMessage("")])
    result = run_agent(LibraryNavigator([make_ships()]), model, "Who?", max_steps=5)
    assert not result.found and "empty reply" in result.text and result.error


class OverloadedError(Exception):
    """Like OpenAI's error sent inside a stream: no HTTP status, only its text."""


def test_agent_tries_again_when_the_provider_is_overloaded(monkeypatch):
    monkeypatch.setattr("toc_rag.agent.graph.TEMPORARY_ERROR_WAITS", (0, 0))
    model = ScriptedModel(
        replies=[
            OverloadedError("Our servers are currently overloaded. Please try again later."),
            call("read_node", node_id="1.1"),
            OverloadedError("Our servers are currently overloaded. Please try again later."),
            AIMessage("The captain is Ada [ships:1.1]."),
        ]
    )
    result = run_agent(LibraryNavigator([make_ships()]), model, "Who?", max_steps=5)
    assert result.found and result.text == "The captain is Ada."
    assert len(model.seen) == 4


def test_agent_gives_up_on_an_overload_that_lasts_and_on_other_errors(monkeypatch):
    import pytest

    from toc_rag.errors import friendly_error

    monkeypatch.setattr("toc_rag.agent.graph.TEMPORARY_ERROR_WAITS", (0, 0))
    busy = OverloadedError("Our servers are currently overloaded. Please try again later.")
    model = ScriptedModel(replies=[busy, busy, busy, AIMessage("never reached")])
    with pytest.raises(OverloadedError) as raised:
        run_agent(LibraryNavigator([make_ships()]), model, "Who?", max_steps=5)
    assert len(model.seen) == 3  # the first try and two more
    assert "overloaded" in friendly_error(raised.value, "OpenAI") and "OpenAI" in friendly_error(raised.value, "OpenAI")

    model = ScriptedModel(replies=[ValueError("a bug of ours"), AIMessage("never reached")])
    with pytest.raises(ValueError):
        run_agent(LibraryNavigator([make_ships()]), model, "Who?", max_steps=5)
    assert len(model.seen) == 1  # not a provider failure: not retried


def test_agent_does_not_retry_a_refusal():
    refusal = AIMessage(
        "", response_metadata={"stop_reason": "refusal", "stop_details": {"category": "reasoning_extraction"}}
    )
    model = ScriptedModel(replies=[refusal, AIMessage("never reached")])
    result = run_agent(LibraryNavigator([make_ships()]), model, "Who?", max_steps=5)
    assert not result.found and "declined" in result.text and result.error
    assert len(model.seen) == 1


def test_extract_markers():
    text = "Fact [a:1.2], more [b:3, a:1.2] at [10:30] and a [link](x). [img:a:img-1]\n\n[a:2]"
    clean, sections, images = extract_markers(text)
    assert sections == ["a:1.2", "b:3", "a:2"]
    assert images == ["a:img-1"]
    # Bug: a time in brackets has the shape of a ref, and vanished from the answer ("at and a").
    assert clean == "Fact, more at [10:30] and a [link](x)."


def test_times_and_ratios_in_brackets_stay_in_the_answer():
    text = "Shift A starts [06:00], the mix is [3:1], see [2:30pm] [ships:1.1]."
    clean, sections, _ = extract_markers(text, {"ships"})
    assert clean == "Shift A starts [06:00], the mix is [3:1], see [2:30pm]."
    assert sections == ["ships:1.1"]
    # A document whose id is only digits still cites: the library says it is a document.
    clean, sections, _ = extract_markers("Revenue rose [2024:1.2].", {"2024"})
    assert (clean, sections) == ("Revenue rose.", ["2024:1.2"])
    # A made-up document id is still taken out of the text: it cites nothing.
    assert extract_markers("Ada [bogus:9.9].", {"ships"})[0] == "Ada."


def test_agent_answer_keeps_a_bracketed_time():
    model = ScriptedModel(replies=[call("read_node", node_id="1.1"), AIMessage("Ada's watch starts at [08:00]. [ships:1.1]")])
    result = run_agent(LibraryNavigator([make_ships()]), model, "When does Ada start?", max_steps=5)
    assert result.text == "Ada's watch starts at [08:00]."
    assert [c.node_id for c in result.citations] == ["1.1"]


def test_a_section_of_another_document_can_be_read_by_its_qualified_id():
    # Bug: read_node shows qualified ids ([ships:1.1]); after opening another document, going back to one
    # of them by that id failed as "Unknown node id", costing the agent a step (or the answer).
    nav = LibraryNavigator([make_ships(), make_cars()])
    nav.open_document("ships")
    assert "Ada" in nav.read_node("ships:1.1")
    nav.open_document("cars")
    assert "Ada" in nav.read_node("ships:1.1")  # back in the first document, without open_document
    assert nav.current == "ships"
    assert [s.label for s in nav.trace][-2:] == ['Opened "Ships"', 'Read "Crew"']  # the switch shows in the path
    assert nav.has_read("ships", "1.1")
    # An id naming no section stays with the open document and says so; it does not switch.
    assert "Unknown node id" in nav.list_children("cars:9.9")
    assert nav.current == "ships"


def test_listing_depth_two_shows_grandchildren_titles_only():
    nav = Navigator(make_ships(), listing_depth=2)
    listing = nav.list_children("root")
    assert "- [1] Ship (2 subsections): no summary" in listing
    assert "  - [1.1] Crew (leaf)" in listing
    assert "  - [1.2] Engines (leaf)" in listing
    assert nav.visited == {"root"}  # only the listed node counts as visited
    # The agent can go straight to a grandchild it saw, without listing its parent first.
    assert "The captain is Ada." in nav.read_node("1.1")


def test_listing_depth_one_is_unchanged():
    listing = Navigator(make_ships()).list_children("root")
    assert listing == "Subsections of [root] Ships:\n- [1] Ship (2 subsections): no summary"


def test_deep_listings_are_capped_and_previews_are_marked():
    blocks = [Heading(1, "Big")] + [Heading(2, f"S{i}") for i in range(80)]
    root, _ = build_tree(blocks, "Doc", "markdown")
    root.children[0].summary, root.children[0].summary_source = "First sentence.", "preview"
    index = DocumentIndex(doc_id="d", title="Doc", source_path="d.md", kind="markdown", root=root)

    listing = Navigator(index, listing_depth=3).list_children("root")

    assert "- [1] Big (80 subsections): (preview) First sentence." in listing
    assert listing.count("\n  - [") == 60
    assert "(+20 deeper subsections not shown; use list_children to see them)" in listing


def test_library_navigator_passes_the_listing_depth_on():
    nav = LibraryNavigator([make_ships(), make_cars()], listing_depth=2)
    assert "  - [1.1] Engines (leaf)" in nav.open_document("cars")


# ---- keyword search ----


def test_search_finds_exact_words_with_excerpts_and_marks_nothing_read():
    nav = Navigator(make_ships())
    hits = nav.search("Fusion engines")
    assert [hit.node.id for hit in hits] == ["1.2"]
    assert "**fusion engines**" in hits[0].snippet.lower()
    assert nav.read == set() and nav.visited == set()
    assert nav.search("engine") == []  # exact words: "engine" is not "engines"
    assert nav.search("the of") == []  # only common words: nothing to look for


def test_search_ranks_phrase_then_all_words_then_some():
    blocks = [
        Heading(1, "Leave"),
        Heading(2, "Sick"),
        Paragraph("Leave for illness. Parents may also ask."),
        Heading(2, "Parental"),
        Paragraph("Parental leave is 16 weeks."),
        Heading(2, "Other"),
        Paragraph("Parental rights are listed elsewhere."),
    ]
    root, _ = build_tree(blocks, "HR", "markdown")
    index = DocumentIndex(doc_id="hr", title="HR", source_path="hr.md", kind="markdown", root=root)
    ids = [hit.node.id for hit in Navigator(index).search("parental leave")]
    assert ids[0] == "1.2"  # the phrase
    assert ids.index("1.1") < ids.index("1.3") or "1.1" not in ids


def test_search_finds_image_descriptions():
    hits = Navigator(make_ships()).search("crew photo")
    assert hits[0].node.id == "1.1"


def test_library_search_spans_documents_and_is_in_the_path():
    nav = LibraryNavigator([make_ships(), make_cars()])
    result = nav.search("engine")
    assert "[cars:1.1] Engines (Cars" in result and "V8 **engine**" in result
    assert "ships:" not in result  # "engines" is a different word
    assert nav.trace[-1].tool == "search" and nav.trace[-1].label == 'Searched for "engine" (1 section found)'
    assert nav.search("submarine").startswith("No section contains")


def test_search_tool_is_offered_only_when_switched_on():
    from toc_rag.agent.graph import make_tools

    nav = LibraryNavigator([make_ships()])
    assert "search" not in [t.name for t in make_tools(nav)]
    assert "search" in [t.name for t in make_tools(nav, search=True)]


def test_agent_searches_then_reads_and_cites():
    model = ScriptedModel(
        replies=[
            call("search", query="fusion"),
            call("read_node", node_id="ships:1.2"),
            AIMessage("Two fusion engines [ships:1.2]."),
        ]
    )
    events = list(stream_agent(LibraryNavigator([make_ships(), make_cars()]), model, "Engines?", 10, search=True))
    steps = [e for e in events if isinstance(e, Step)]
    assert [s.tool for s in steps] == ["search", "open_document", "read_node"]
    result = events[-1]
    assert result.found and result.citations[0].node_id == "1.2"
    assert "search finds sections" in model.seen[0][0].content


def test_search_hint_is_left_out_when_off():
    model = ScriptedModel(replies=[AIMessage("Not found.")])
    run_agent(LibraryNavigator([make_ships()]), model, "?", max_steps=3)
    assert "search" not in model.seen[0][0].content


def test_search_prefers_more_words_over_a_title_and_ignores_the_document_title():
    nav = Navigator(make_ships())
    assert nav.search("ships") == []  # only the document's own title says "Ships"
    # "Ship" matches one word, in a title; "Crew" holds two of the words ("crew" in its title, "captain" in its text).
    assert [hit.node.id for hit in nav.search("ship crew captain")][0] == "1.1"
