# Vector Search

Vector search, also called dense retrieval, represents both the query and the
documents as embeddings — dense numerical vectors produced by a neural
encoder. Relevance is measured as the cosine similarity (or dot product)
between the query vector and each document vector.

Because embeddings capture meaning rather than exact wording, vector search
excels at semantic matching: a query like "how do I make my code run faster"
can retrieve a document about "performance optimization techniques" even
though the two share almost no vocabulary. This makes dense retrieval strong
for paraphrased questions, synonyms, and conceptual queries.

The weakness is precision on exact tokens. Vector search can struggle with
rare identifiers, product codes, acronyms, or exact phrase matches, because
the encoder may not have learned a sharp enough representation for tokens it
rarely saw during training. It also depends heavily on embedding quality —
a poorly chosen or outdated embedding model will silently degrade recall.
