# BM25 Lexical Search

BM25 (Best Matching 25) is a probabilistic ranking function built on term
frequency and inverse document frequency. Unlike vector search, it works
directly on tokens: a document scores high for a query when it contains the
query's exact terms often, weighted down if those terms are common across
the whole corpus.

This makes BM25 extremely reliable for keyword-heavy queries — exact
identifiers, product SKUs, error codes, acronyms, proper nouns, and any
query where the precise wording matters. It requires no training and no
embedding model, so it is fast, cheap, and fully explainable: you can always
point to which terms drove a match.

The weakness is the mirror image of vector search's strength: BM25 has no
notion of meaning. A query about "how do I make my code run faster" will not
match a document about "performance optimization techniques" unless the
words actually overlap. Synonyms, paraphrases, and cross-lingual queries are
invisible to a pure lexical index.
