"""Tree navigation, with a record of what the agent has visited."""

import re
from collections import defaultdict
from typing import Literal, NamedTuple

from pydantic import BaseModel

from ..models import DocumentIndex, ImageRecord, Node

AT_TOP = "Already at the top of the document."
MAX_DEEPER_LINES = 60  # cap on title-only lines below the first level of a listing
NO_DOCUMENT = "No document is open. Use open_document first (list_documents shows the ids)."
MAX_SEARCH_HITS = 8
SNIPPET_CHARS = 220
_WORD = re.compile(r"\w+")
# Words too common to find anything on their own. They still count inside a phrase match.
_STOPWORDS = frozenset(
    "a an and are as at be by for from has have how in is it its of on or that the this to was were what when "
    "where which who why will with".split()
)


class Step(BaseModel):
    """One navigation action, in a form the UI can show as part of the path taken."""

    tool: Literal["list_documents", "open_document", "list_children", "read_node", "go_up", "search"]
    doc_id: str | None = None
    node_id: str | None = None
    label: str
    note: str = ""  # what the model said just before this action, when it said anything


class Navigator:
    """Navigation inside one document. `prefix` qualifies the ids shown for citation.

    `listing_depth` is how many tree levels one listing shows. Levels below the first show titles
    only, so the agent can jump straight to a deep section without a call per level.
    """

    def __init__(self, index: DocumentIndex, prefix: str = "", listing_depth: int = 1):
        self.index = index
        self.prefix = prefix
        self.listing_depth = max(1, listing_depth)
        self.nodes = index.node_map()
        self.parents = index.parent_map()
        self.images_by_node: dict[str, list[ImageRecord]] = defaultdict(list)
        for record in index.images:
            if record.node_id:
                self.images_by_node[record.node_id].append(record)
        self.visited: set[str] = set()  # nodes the agent has looked at in any way
        self.read: set[str] = set()  # nodes whose text it has actually read

    def list_children(self, node_id: str) -> str:
        node = self.nodes.get(node_id)
        if node is None:
            return f"Unknown node id {node_id!r}."
        self.visited.add(node_id)
        if not node.children:
            return f"[{node.id}] {node.title} has no subsections. Use read_node to read it."

        lines = [f"Subsections of [{node.id}] {node.title}:"]
        deeper_shown = 0
        hidden = 0
        for child in node.children:
            visited = ", visited" if child.id in self.visited else ""
            lines.append(f"- [{child.id}] {child.title} ({_shape(child)}{visited}): {_summary(child)}")
            for depth, descendant in _descendants(child, self.listing_depth - 1):
                if deeper_shown >= MAX_DEEPER_LINES:
                    hidden += 1
                    continue
                deeper_shown += 1
                lines.append(f"{'  ' * depth}- [{descendant.id}] {descendant.title} ({_shape(descendant)})")
        if hidden:
            lines.append(f"(+{hidden} deeper subsections not shown; use list_children to see them)")
        return "\n".join(lines)

    def read_node(self, node_id: str) -> str:
        node = self.nodes.get(node_id)
        if node is None:
            return f"Unknown node id {node_id!r}."
        self.visited.add(node_id)
        self.read.add(node_id)
        text = node.text or "(No text of its own. Its content is in its subsections.)"
        out = f"[{self.prefix}{node.id}] {node.title} ({node.location.label()})\n\n{text}"
        images = self.images_by_node.get(node_id)
        if images:
            listed = "\n".join(f"- {self.prefix}{r.id}: {r.description or 'no description'}" for r in images)
            out += f"\n\nImages in this section:\n{listed}"
        return out

    def go_up(self, node_id: str) -> str:
        parent_id = self.parents.get(node_id)
        if parent_id is None:
            return AT_TOP
        return self.list_children(parent_id)

    def search(self, query: str) -> list["SearchHit"]:
        """Sections whose title, text or image descriptions contain the query's words (exact words, any case).

        Ranked: the whole query as a phrase first, then sections holding all the words, then the most words.
        Nothing is marked read: a hit is a pointer, and the agent still has to read the section to cite it.
        """
        words = [w for w in dict.fromkeys(_WORD.findall(query.lower())) if w not in _STOPWORDS]
        if not words:
            return []
        phrase = re.compile(r"\b" + r"\W+".join(map(re.escape, _WORD.findall(query.lower()))) + r"\b", re.IGNORECASE)
        patterns = [re.compile(rf"\b{re.escape(w)}\b", re.IGNORECASE) for w in words]
        hits = []
        for order, node in enumerate(self.index.root.walk()):
            descriptions = " ".join(r.description for r in self.images_by_node.get(node.id, []))
            haystack = f"{node.title}\n{node.text}\n{descriptions}"
            found = [p for p in patterns if p.search(haystack)]
            if not found:
                continue
            in_phrase = phrase.search(haystack)
            first = in_phrase or min((p.search(haystack) for p in found), key=lambda m: m.start())
            rank = (not in_phrase, -len(found), order)
            hits.append(SearchHit(self.index.doc_id, node, _snippet(haystack, first.start(), first.end()), rank))
        return sorted(hits, key=lambda hit: hit.rank)


class SearchHit(NamedTuple):
    doc_id: str
    node: Node
    snippet: str  # the text around the first match
    rank: tuple  # sort key: lower is better


def _snippet(text: str, start: int, end: int) -> str:
    """About SNIPPET_CHARS of `text` around a match, on one line, with the match in **bold**."""
    pad = max(0, (SNIPPET_CHARS - (end - start)) // 2)
    left, right = max(0, start - pad), min(len(text), end + pad)
    out = f"{text[left:start]}**{text[start:end]}**{text[end:right]}"
    out = re.sub(r"\s+", " ", out).strip()
    return f"{'...' if left else ''}{out}{'...' if right < len(text) else ''}"


def _shape(node: Node) -> str:
    return "leaf" if not node.children else f"{len(node.children)} subsections"


def _summary(node: Node) -> str:
    if not node.summary:
        return "no summary"
    return f"(preview) {node.summary}" if node.summary_source == "preview" else node.summary


def _descendants(node: Node, levels: int, depth: int = 1) -> list[tuple[int, Node]]:
    """The node's descendants down to `levels` below it, in document order, with their indent depth."""
    if levels <= 0:
        return []
    out = []
    for child in node.children:
        out.append((depth, child))
        out.extend(_descendants(child, levels - 1, depth + 1))
    return out


class LibraryNavigator:
    """Navigation over several documents. Section tools act on the document that is open."""

    def __init__(self, indexes: list[DocumentIndex], listing_depth: int = 1):
        if not indexes:
            raise ValueError("A library needs at least one document.")
        self.indexes = {index.doc_id: index for index in indexes}
        self.docs = {
            index.doc_id: Navigator(index, prefix=f"{index.doc_id}:", listing_depth=listing_depth) for index in indexes
        }
        self.current: str | None = indexes[0].doc_id if len(indexes) == 1 else None
        self.trace: list[Step] = []

    def documents_listing(self) -> str:
        lines = []
        for index in self.indexes.values():
            marker = ", open" if index.doc_id == self.current else ""
            lines.append(f"- [{index.doc_id}] {index.title} ({index.kind}{marker}): {index.summary or 'no summary'}")
        return "\n".join(lines)

    def list_documents(self) -> str:
        self.trace.append(Step(tool="list_documents", label="Listed documents"))
        return self.documents_listing()

    def open_document(self, doc_id: str) -> str:
        index = self.indexes.get(doc_id)
        if index is None:
            return f"Unknown document id {doc_id!r}. Use list_documents to see the ids."
        self.current = doc_id
        self.trace.append(Step(tool="open_document", doc_id=doc_id, label=f'Opened "{index.title}"'))
        return f'Opened "{index.title}".\n\n' + self.docs[doc_id].list_children("root")

    def list_children(self, node_id: str) -> str:
        nav, node_id = self._target(node_id)
        if nav is None:
            return NO_DOCUMENT
        result = nav.list_children(node_id)
        self._record("list_children", nav, node_id, "Looked inside")
        return result

    def read_node(self, node_id: str) -> str:
        nav, node_id = self._target(node_id)
        if nav is None:
            return NO_DOCUMENT
        result = nav.read_node(node_id)
        self._record("read_node", nav, node_id, "Read")
        return result

    def go_up(self, node_id: str) -> str:
        nav, node_id = self._target(node_id)
        if nav is None:
            return NO_DOCUMENT
        result = nav.go_up(node_id)
        if result == AT_TOP:
            return f"{AT_TOP} Use list_documents and open_document to switch documents."
        self._record("go_up", nav, node_id, "Went back up from")
        return result

    def search(self, query: str) -> str:
        """Find sections across the whole library that contain the query's exact words."""
        query = " ".join(query.split())[:200]
        hits = sorted((hit for nav in self.docs.values() for hit in nav.search(query)), key=lambda hit: hit.rank)
        count = f"{len(hits)} section{'s' if len(hits) != 1 else ''}"
        self.trace.append(Step(tool="search", label=f'Searched for "{query}" ({count} found)'))
        if not hits:
            return (
                f'No section contains the words "{query}". Try other words (a synonym, a single key term), '
                "or browse the outline."
            )
        lines = [f'Sections containing "{query}" (best first, {count}):']
        for hit in hits[:MAX_SEARCH_HITS]:
            title = self.indexes[hit.doc_id].title
            lines.append(f"- [{hit.doc_id}:{hit.node.id}] {hit.node.title} ({title}, {hit.node.location.label()}): {hit.snippet}")
        if len(hits) > MAX_SEARCH_HITS:
            lines.append(f"(+{len(hits) - MAX_SEARCH_HITS} more; add words to narrow the search)")
        lines.append("These are excerpts. Use read_node with an id above to read the section before citing it.")
        return "\n".join(lines)

    def find_node(self, ref: str) -> tuple[DocumentIndex, Node] | None:
        """Resolve a qualified `doc_id:node_id` (or a bare node id in the open document)."""
        doc_id, local = self._split(ref)
        nav = self.docs.get(doc_id) if doc_id else None
        node = nav.nodes.get(local) if nav else None
        return (nav.index, node) if nav and node else None

    def find_image(self, ref: str) -> tuple[DocumentIndex, ImageRecord] | None:
        doc_id, local = self._split(ref)
        index = self.indexes.get(doc_id) if doc_id else None
        record = next((r for r in index.images if r.id == local), None) if index else None
        return (index, record) if index and record else None

    def has_read(self, doc_id: str, node_id: str) -> bool:
        nav = self.docs.get(doc_id)
        return nav is not None and node_id in nav.read

    def _open(self) -> Navigator | None:
        return self.docs.get(self.current) if self.current else None

    def _split(self, ref: str) -> tuple[str | None, str]:
        doc_id, sep, local = ref.partition(":")
        return (doc_id, local) if sep else (self.current, ref)

    def _target(self, node_id: str) -> tuple[Navigator | None, str]:
        """The document and local id a section tool acts on.

        A qualified id ("doc_id:1.2", as read_node shows them) names its own document: if that is not the
        open one, it is opened first (and shown in the path). Without this, going back to a section read in
        another document failed as an unknown id. An id that names no section stays with the open document.
        """
        doc_id, sep, local = node_id.partition(":")
        target = self.docs.get(doc_id) if sep else None
        if target is not None and local in target.nodes:
            if doc_id != self.current:
                self.current = doc_id
                self.trace.append(Step(tool="open_document", doc_id=doc_id, label=f'Opened "{target.index.title}"'))
            return target, local
        return self._open(), node_id

    def _record(self, tool: str, nav: Navigator, node_id: str, verb: str) -> None:
        node = nav.nodes.get(node_id)
        if node is not None:
            self.trace.append(
                Step(tool=tool, doc_id=nav.index.doc_id, node_id=node_id, label=f'{verb} "{node.title}"')
            )
