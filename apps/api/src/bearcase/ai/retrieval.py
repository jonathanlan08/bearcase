"""Lexical evidence retrieval behind an interface. pgvector was deliberately not used: the
demo corpus is small and exact numeric/keyword overlap is what verification needs."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")
STOP = {
    "the",
    "of",
    "and",
    "a",
    "to",
    "in",
    "for",
    "is",
    "on",
    "by",
    "with",
    "as",
    "at",
    "an",
    "or",
    "from",
    "that",
    "this",
    "be",
    "are",
    "was",
    "it",
    "its",
}


def tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOP and len(t) > 1]


@dataclass(frozen=True)
class RetrievedChunk:
    index: int
    score: float


class Retriever(Protocol):
    def search(self, query: str, top_k: int = 8) -> list[RetrievedChunk]: ...


class LexicalRetriever:
    """BM25-style scoring over pre-tokenized chunks."""

    def __init__(self, texts: list[str], k1: float = 1.4, b: float = 0.75):
        self.docs = [tokens(t) for t in texts]
        self.n = len(self.docs)
        self.avgdl = (sum(len(d) for d in self.docs) / self.n) if self.n else 0.0
        self.df: Counter[str] = Counter()
        for d in self.docs:
            self.df.update(set(d))
        self.k1, self.b = k1, b
        self.tf = [Counter(d) for d in self.docs]

    def search(self, query: str, top_k: int = 8) -> list[RetrievedChunk]:
        q = tokens(query)
        if not q or not self.n:
            return []
        scores: list[tuple[float, int]] = []
        for i, d in enumerate(self.docs):
            if not d:
                continue
            s = 0.0
            dl = len(d)
            for term in set(q):
                f = self.tf[i].get(term, 0)
                if not f:
                    continue
                idf = math.log(1 + (self.n - self.df[term] + 0.5) / (self.df[term] + 0.5))
                s += idf * (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1)))
            if s > 0:
                scores.append((s, i))
        scores.sort(reverse=True)
        return [RetrievedChunk(i, round(s, 4)) for s, i in scores[:top_k]]
