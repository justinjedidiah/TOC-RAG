"""Keyword search over the committed sample library, and the shape of the samples it relies on."""

import pytest

from toc_rag.agent import LibraryNavigator, run_agent
from toc_rag.config import PROJECT_ROOT
from toc_rag.models import DocumentIndex
from toc_rag.storage import Store

from .test_agent import ScriptedModel, call
from langchain_core.messages import AIMessage

SAMPLES = Store(PROJECT_ROOT / "samples" / "index")


@pytest.fixture(scope="module")
def indexes() -> dict[str, DocumentIndex]:
    loaded = [SAMPLES.load_index(entry.doc_id) for entry in SAMPLES.list_documents()]
    return {index.title: index for index in loaded}


@pytest.fixture
def library(indexes) -> LibraryNavigator:
    return LibraryNavigator(list(indexes.values()))


def depth(node) -> int:
    return 1 + max((depth(child) for child in node.children), default=0)


def top_hit(library: LibraryNavigator, query: str) -> tuple[str, str]:
    """(document title, section title) of the best hit."""
    hits = sorted((hit for nav in library.docs.values() for hit in nav.search(query)), key=lambda hit: hit.rank)
    assert hits, f"nothing found for {query!r}"
    return library.indexes[hits[0].doc_id].title, hits[0].node.title


def test_samples_keep_their_outline_levels(indexes):
    for index in indexes.values():
        titles = [node.title for node in index.root.walk()]
        assert depth(index.root) >= 4, f"{index.title} lost its third heading level"  # root + 3 levels
        assert not [t for t in titles if " · " in t or " › " in t], f"{index.title}: sections were merged"
        assert index.structure_source == "headings"
        assert all(node.summary_source == "llm" for node in index.root.walk()), "every section has an LLM summary"
    report, handbook = indexes["Fernhill Annual Report 2026"], indexes["Fernhill Employee Handbook"]
    assert len(list(report.root.walk())) >= 40 and len(list(handbook.root.walk())) >= 40
    assert len(report.images) == 1 and report.images[0].description


@pytest.mark.parametrize(
    ("query", "document", "section"),
    [
        # The app's sample questions
        ("parental leave", "Fernhill Employee Handbook", "Parental leave"),
        ("work from another country", "Fernhill Employee Handbook", "Working from abroad"),
        ("Equipment grew fastest", "Fernhill Annual Report 2026", "Revenue by segment"),
        ("revenue by segment and quarter", "Fernhill Annual Report 2026", "Revenue by segment"),  # the chart
        # Terms no section title or outline mentions: what search is for
        ("PFAS", "Fernhill Annual Report 2026", "Materials"),
        ("Ridgeline", "Fernhill Annual Report 2026", "Jackets and insulation"),
        ("Aspen ultralight", "Fernhill Annual Report 2026", "Leading in lightweight equipment"),
        ("speak-up line", "Fernhill Employee Handbook", "Raising a concern"),
        ("jury duty", "Fernhill Employee Handbook", "Other leave"),
        ("minibar", "Fernhill Employee Handbook", "Hotels"),
        ("Rotterdam", "Fernhill Annual Report 2026", "Distribution and logistics"),
    ],
)
def test_search_finds_the_right_sample_section_first(library, query, document, section):
    assert top_hit(library, query) == (document, section)


def test_search_spans_both_samples(library, indexes):
    result = library.search("gear allowance")
    for index in indexes.values():
        assert f"[{index.doc_id}:" in result, f"no hit in {index.title}"
    assert "**gear allowance**" in result.lower()


def test_search_marks_nothing_read_and_finds_nothing_made_up(library):
    library.search("parental leave")
    assert all(not nav.read and not nav.visited for nav in library.docs.values())
    assert library.search("quantum teleportation").startswith("No section contains")


def test_agent_answers_a_sample_question_through_search(indexes):
    handbook = indexes["Fernhill Employee Handbook"]
    section = next(node for node in handbook.root.walk() if node.title == "Parental leave")
    ref = f"{handbook.doc_id}:{section.id}"
    model = ScriptedModel(
        replies=[
            call("search", query="parental leave"),
            call("read_node", node_id=ref),
            AIMessage(f"Every parent gets 16 weeks of parental leave at full pay [{ref}]."),
        ]
    )
    library = LibraryNavigator(list(indexes.values()))
    result = run_agent(library, model, "How many weeks of parental leave do employees get?", 10, search=True)
    assert result.found and [(c.doc_id, c.title) for c in result.citations] == [(handbook.doc_id, "Parental leave")]
    search_result = model.seen[1][-1].content  # what the search showed the model
    assert search_result.splitlines()[1].startswith(f"- [{ref}] Parental leave")
    assert [step.tool for step in library.trace] == ["search", "open_document", "read_node"]
