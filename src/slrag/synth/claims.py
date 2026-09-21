"""ClaimGraph — the answer as a data structure (Rule 3, S-4, roadmap 4.2).

The session holds claims, never an answer string; ``answer`` is a projection of
the active claims rendered last (synth/renderer.py). Each claim is the frozen
``core.schemas.Claim``; everything the contract cannot carry (confidence,
superseded_by, supporting chunks) lives in ``ClaimMeta`` alongside it.

Invariants enforced here, not by convention:
  * a claim can only cite labels previously admitted via ``register_evidence``
    (closed citation allowlist, S-6 defence in depth — fabricated IDs cannot
    enter the graph even if every upstream check were bypassed);
  * mutations only happen inside a ``Revision``; a committed revision bumps the
    version exactly once and records a ``VersionLineage``;
  * retained claims are never rewritten — superseding flips status only;
  * state is in-process and ephemeral (HC-4): ``destroy()`` drops everything.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Sequence

from slrag.core.citations import label_for_chunk, normalize_label
from slrag.core.schemas import Claim, RetrievedChunk
from slrag.synth.types import CitationNotAllowedError, ClaimGraphError, VersionLineage


@dataclass(frozen=True)
class ClaimMeta:
    confidence: float = 1.0
    intent_id: str | None = None
    supporting_chunk_ids: tuple[str, ...] = ()
    superseded_by: tuple[str, ...] = ()
    superseded_in_version: int | None = None


class ClaimGraph:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._version = 0
        self._claims: dict[str, Claim] = {}
        self._meta: dict[str, ClaimMeta] = {}
        self._lineage: list[VersionLineage] = []
        self._evidence: dict[str, RetrievedChunk] = {}      # chunk_id -> chunk
        self._label_chunks: dict[str, list[str]] = {}       # label -> [chunk_id]
        self._next_id = 1
        self._open: Revision | None = None

    # -- evidence / allowlist ------------------------------------------------
    def register_evidence(self, chunks: Iterable[RetrievedChunk]) -> list[str]:
        """Admit chunks to the session context; returns their (ordered, unique) labels."""
        labels: list[str] = []
        for chunk in chunks:
            label = label_for_chunk(chunk)
            if chunk.chunk_id not in self._evidence:
                self._evidence[chunk.chunk_id] = chunk.model_copy(deep=True)
                self._label_chunks.setdefault(label, []).append(chunk.chunk_id)
            if label not in labels:
                labels.append(label)
        return labels

    def known_labels(self) -> frozenset[str]:
        return frozenset(self._label_chunks)

    def chunks_for_label(self, label: str) -> list[RetrievedChunk]:
        canonical = normalize_label(label) or label
        return [self._evidence[cid].model_copy(deep=True) for cid in self._label_chunks.get(canonical, [])]

    def evidence(self) -> list[RetrievedChunk]:
        return [chunk.model_copy(deep=True) for chunk in self._evidence.values()]

    # -- reads -----------------------------------------------------------------
    @property
    def version(self) -> int:
        return self._version

    @property
    def lineage(self) -> list[VersionLineage]:
        return list(self._lineage)

    def latest_lineage(self) -> VersionLineage | None:
        return self._lineage[-1] if self._lineage else None

    def __contains__(self, claim_id: object) -> bool:
        return claim_id in self._claims

    def __len__(self) -> int:
        return len(self._claims)

    def get(self, claim_id: str) -> Claim:
        try:
            return self._claims[claim_id].model_copy(deep=True)
        except KeyError:
            raise ClaimGraphError(f"unknown claim {claim_id!r}") from None

    def meta(self, claim_id: str) -> ClaimMeta:
        try:
            return self._meta[claim_id]
        except KeyError:
            raise ClaimGraphError(f"unknown claim {claim_id!r}") from None

    def all_claims(self) -> list[Claim]:
        return [claim.model_copy(deep=True) for claim in self._claims.values()]

    def active(self, facet: str | None = None) -> list[Claim]:
        return [
            claim.model_copy(deep=True)
            for claim in self._claims.values()
            if claim.status == "active" and (facet is None or claim.facet == facet)
        ]

    def snapshot(self, version: int) -> list[Claim]:
        """Claims as they were active at ``version`` (drives the UI V1<->V2 slider)."""
        out = []
        for claim_id, claim in self._claims.items():
            if claim.introduced_in_version > version:
                continue
            gone_at = self._meta[claim_id].superseded_in_version
            if gone_at is not None and gone_at <= version:
                continue
            out.append(claim.model_copy(update={"status": "active"}, deep=True))
        return out

    def citations(self, version: int | None = None) -> list[str]:
        """Ordered union of citations over the active claims (at ``version`` if given)."""
        claims = self.active() if version is None else self.snapshot(version)
        return list(dict.fromkeys(label for claim in claims for label in claim.citations))

    def facets(self) -> list[str]:
        return list(dict.fromkeys(claim.facet for claim in self._claims.values() if claim.status == "active"))

    def to_output(self, *, include_superseded: bool = False) -> list[dict]:
        """The additive ``claims`` output field (A_FINAL_ARCHITECTURE §6)."""
        rows = []
        for claim in self._claims.values():
            if claim.status != "active" and not include_superseded:
                continue
            rows.append(
                {
                    "claim_id": claim.claim_id,
                    "facet": claim.facet,
                    "text": claim.text,
                    "citations": list(claim.citations),
                    "status": claim.status,
                    "introduced_in_version": claim.introduced_in_version,
                }
            )
        return rows

    # -- writes ----------------------------------------------------------------
    def revise(self) -> Revision:
        if self._open is not None:
            raise ClaimGraphError("a revision is already open on this ClaimGraph")
        self._open = Revision(self)
        return self._open

    def destroy(self) -> None:
        """Session end (HC-4): drop every claim, lineage record and evidence reference."""
        self._claims.clear()
        self._meta.clear()
        self._lineage.clear()
        self._evidence.clear()
        self._label_chunks.clear()
        self._version = 0
        self._open = None

    def _mint_id(self) -> str:
        claim_id = f"c{self._next_id}"
        self._next_id += 1
        return claim_id


class Revision:
    """A staged set of mutations; ``commit()`` applies them atomically as version+1.

    Usable as a context manager: commits on normal exit, aborts on exception.
    """

    def __init__(self, graph: ClaimGraph) -> None:
        self._graph = graph
        self._added: dict[str, Claim] = {}
        self._added_meta: dict[str, ClaimMeta] = {}
        self._superseded: dict[str, tuple[str, ...]] = {}
        self._closed = False
        self.lineage: VersionLineage | None = None

    @property
    def target_version(self) -> int:
        return self._graph.version + 1

    @property
    def added_ids(self) -> list[str]:
        return list(self._added)

    def add(
        self,
        *,
        facet: str,
        text: str,
        citations: Sequence[str],
        preconditions: dict | None = None,
        confidence: float = 1.0,
        intent_id: str | None = None,
        supporting_chunk_ids: Sequence[str] = (),
    ) -> str:
        self._check_open()
        if not facet:
            raise ClaimGraphError("claim facet must be non-empty")
        if not text or not text.strip():
            raise ClaimGraphError("claim text must be non-empty")
        normalized = []
        for label in citations:
            canonical = normalize_label(label)
            if canonical is None or canonical not in self._graph._label_chunks:
                raise CitationNotAllowedError(
                    f"citation {label!r} was never admitted to session context"
                )
            if canonical not in normalized:
                normalized.append(canonical)
        if not normalized:
            raise CitationNotAllowedError("a claim must carry at least one allowlisted citation")

        claim_id = self._graph._mint_id()
        self._added[claim_id] = Claim(
            claim_id=claim_id,
            facet=facet,
            text=text.strip(),
            citations=normalized,
            preconditions=dict(preconditions or {}),
            status="active",
            introduced_in_version=self.target_version,
        )
        self._added_meta[claim_id] = ClaimMeta(
            confidence=confidence,
            intent_id=intent_id,
            supporting_chunk_ids=tuple(supporting_chunk_ids),
        )
        return claim_id

    def supersede(self, claim_id: str, superseded_by: Sequence[str] = ()) -> None:
        self._check_open()
        claim = self._graph._claims.get(claim_id)
        if claim is None:
            raise ClaimGraphError(f"cannot supersede unknown claim {claim_id!r}")
        if claim.status != "active":
            raise ClaimGraphError(f"claim {claim_id!r} is already superseded")
        self._superseded[claim_id] = tuple(superseded_by)

    def commit(self) -> VersionLineage | None:
        """Apply staged changes. Returns None (and keeps the version) if nothing changed."""
        self._check_open()
        graph = self._graph
        try:
            if not self._added and not self._superseded:
                return None
            for claim_id, by in self._superseded.items():
                unknown = [cid for cid in by if cid not in self._added and cid not in graph._claims]
                if unknown:
                    raise ClaimGraphError(f"superseded_by references unknown claims {unknown}")

            new_version = graph._version + 1
            retained = tuple(
                cid for cid, claim in graph._claims.items()
                if claim.status == "active" and cid not in self._superseded
            )
            for claim_id, by in self._superseded.items():
                graph._claims[claim_id] = graph._claims[claim_id].model_copy(update={"status": "superseded"})
                graph._meta[claim_id] = replace(
                    graph._meta[claim_id], superseded_by=by, superseded_in_version=new_version
                )
            graph._claims.update(self._added)
            graph._meta.update(self._added_meta)
            graph._version = new_version

            self.lineage = VersionLineage(
                from_version=new_version - 1,
                to_version=new_version,
                retained=retained,
                superseded=tuple(self._superseded),
                added=tuple(self._added),
            )
            graph._lineage.append(self.lineage)
            return self.lineage
        finally:
            self._close()

    def abort(self) -> None:
        if not self._closed:
            self._close()

    def _check_open(self) -> None:
        if self._closed:
            raise ClaimGraphError("revision is closed")

    def _close(self) -> None:
        self._closed = True
        self._graph._open = None

    def __enter__(self) -> Revision:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.abort()
        elif not self._closed:
            self.commit()
