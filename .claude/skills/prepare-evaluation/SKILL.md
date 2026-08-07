---
name: prepare-evaluation
description: Workflow for creating evaluation datasets, metrics, and test scenarios
---

# Prepare Evaluation Skill

_Originally authored as a workflow for `test-specialist`, invoked as `/prepare-evaluation`._

> **Corrected 2026-08-06** (documentation-utility pass): step 3 previously referenced four
> manifest files that don't exist (`local-vector-rag.yaml`, `local-bm25-rag.yaml`,
> `local-hybrid-reranked-rag.yaml`, `local-hybrid-gpt4-rag.yaml`) — `manifests/presets/`
> actually contains three Runnable manifests (Étape 7, ADR-0007): `local-hybrid-rag.yaml`,
> `secure-enterprise-rag.yaml` (V2 native), and `langgraph-rag.yaml` (V2 delegated, renamed
> from `agentic-rag.yaml`). `graph-memory-rag.yaml`/`multimodal-rag.yaml` live under
> `manifests/blueprints/` — never runnable, see `manifests/README.md`.
> Step 4's `_load_pipeline()` also imported from the wrong module
> (`modular_rag.orchestration.load_pipeline` doesn't exist); the real function is
> `load_pipeline()` in `src/modular_rag/app/bootstrap.py`. Both fixed below. The rest of this
> file (`EvaluationMetrics`, `EvaluationRunner`, golden-set JSON shape) is illustrative
> scaffolding to build, not a claimed existing API — the real `eval/` package
> (`eval/datasets/`, `eval/scorers/`, `eval/runners/`, `eval/quality_gate.py`, `eval/reports/`)
> has its own, narrower shipped surface (`ExactMatchEvaluator` today); check there first before
> assuming any of this section's classes already exist.

Systematic workflow for creating comprehensive evaluation suites with datasets, metrics, and benchmarks.

## State of the Art First (mandatory)

Before defining metrics or golden sets, read [docs/research/DIGEST-evaluation.md](../../../docs/research/DIGEST-evaluation.md) and cite the arXiv id backing each choice. Key baselines from the corpus: exact formulas for NDCG@k, MRR, Recall@k, MAP (retrieval) and Relevance/Faithfulness/Correctness (generation); aggregate nDCG is biased — measure per semantic stratum; reranker regressions tracked via Δ nDCG@k at small k.

If a design choice contradicts the digest, justify it explicitly in the MR.

## When to Use

- Establishing performance baselines
- Creating golden test sets
- Measuring component quality
- Regression detection
- Release validation

## Workflow Steps

### 1. Create Golden Dataset (20 min)

**Define test queries with ground truth:**

```python
GOLDEN_SET = {
    "rag_fundamentals": [
        {
            "query": "What is RAG?",
            "relevant_documents": ["rag-overview.md"],
            "expected_answer": "RAG is Retrieval-Augmented Generation, combining retrieval and generation",
            "difficulty": "easy",
            "category": "definition"
        },
        {
            "query": "How does vector search improve retrieval?",
            "relevant_documents": ["retrieval-methods.md", "vector-search.md"],
            "expected_answer": "Vector search uses embeddings to find semantically similar documents",
            "difficulty": "medium",
            "category": "technical"
        },
        # ... more test cases
    ],
    "complex_reasoning": [
        {
            "query": "Compare BM25 and vector search. When use each?",
            "relevant_documents": ["retrieval-comparison.md"],
            "expected_answer": "BM25 for keywords, vector for semantic similarity",
            "difficulty": "hard",
            "category": "comparison"
        },
        # ... more
    ]
}

# Save to file
import json
with open("golden_dataset.json", "w") as f:
    json.dump(GOLDEN_SET, f, indent=2)
```

**Guidelines for golden set:**
- Mix easy, medium, hard questions
- Cover all document categories
- Include edge cases
- Minimum 20 test cases per category
- Human-verified answers

### 2. Define Evaluation Metrics (20 min)

**Implement metric suite:**

```python
import numpy as np
from sklearn.metrics import ndcg_score, mean_reciprocal_rank

class EvaluationMetrics:
    """Comprehensive evaluation metrics."""
    
    @staticmethod
    def ndcg_at_k(retrieved_ids: list[str], relevant_ids: list[str], k: int = 10) -> float:
        """NDCG: Normalized Discounted Cumulative Gain."""
        # relevance = 1 if in relevant set, 0 otherwise
        y_true = [1 if doc_id in relevant_ids else 0 for doc_id in retrieved_ids[:k]]
        y_score = list(range(len(y_true), 0, -1))
        
        if sum(y_true) == 0:
            return 0.0
        
        return ndcg_score([y_true], [y_score])
    
    @staticmethod
    def recall_at_k(retrieved_ids: list[str], relevant_ids: list[str], k: int = 10) -> float:
        """Recall: % of relevant docs retrieved."""
        if not relevant_ids:
            return 0.0
        
        matches = sum(1 for doc_id in retrieved_ids[:k] if doc_id in relevant_ids)
        return matches / len(relevant_ids)
    
    @staticmethod
    def precision_at_k(retrieved_ids: list[str], relevant_ids: list[str], k: int = 10) -> float:
        """Precision: % of retrieved docs that are relevant."""
        if k == 0:
            return 0.0
        
        matches = sum(1 for doc_id in retrieved_ids[:k] if doc_id in relevant_ids)
        return matches / k
    
    @staticmethod
    def mean_reciprocal_rank(retrieved_ids: list[str], relevant_ids: list[str]) -> float:
        """MRR: Average position of first relevant doc (1/rank)."""
        for rank, doc_id in enumerate(retrieved_ids, 1):
            if doc_id in relevant_ids:
                return 1.0 / rank
        return 0.0
    
    @staticmethod
    def f1_score(retrieved_ids: list[str], relevant_ids: list[str], k: int = 10) -> float:
        """F1: Harmonic mean of precision and recall."""
        precision = EvaluationMetrics.precision_at_k(retrieved_ids, relevant_ids, k)
        recall = EvaluationMetrics.recall_at_k(retrieved_ids, relevant_ids, k)
        
        if precision + recall == 0:
            return 0.0
        
        return 2 * (precision * recall) / (precision + recall)
    
    @staticmethod
    def answer_quality(generated_answer: str, expected_answer: str) -> float:
        """LLM-judged similarity of generated vs expected answer."""
        # Rough approximation using token overlap
        gen_tokens = set(generated_answer.lower().split())
        exp_tokens = set(expected_answer.lower().split())
        
        if not exp_tokens:
            return 0.0
        
        overlap = len(gen_tokens & exp_tokens)
        return overlap / len(exp_tokens)
```

**Metrics to track:**
- Retrieval: NDCG@10, Recall@10, MRR, F1
- Generation: Answer quality, token count, latency
- Overall: End-to-end latency, success rate

### 3. Create Test Scenarios (15 min)

**Define evaluation scenarios:**

```python
EVALUATION_SCENARIOS = {
    "baseline": {
        "name": "Baseline Configuration",
        "config": "manifests/presets/local-hybrid-rag.yaml",
        "description": "Standard hybrid retrieval + OpenAIGenerator (default model gpt-4o-mini)"
    },
}
# Additional scenarios (vector-only, BM25-only, reranked, alt-model) require their own manifest
# files under manifests/presets/ — none of those variants ship today (only local-hybrid-rag.yaml
# is Runnable end-to-end, see manifests/README.md). Copy local-hybrid-rag.yaml and change the
# relevant component's `type`/`config` to build one, and confirm it still wires with
# `load_pipeline(...)` before adding it here.

# Save scenarios
import json
with open("evaluation_scenarios.json", "w") as f:
    json.dump(EVALUATION_SCENARIOS, f, indent=2)
```

### 4. Implement Evaluation Runner (25 min)

**Execute evaluation:**

```python
import time
import json
from datetime import datetime

class EvaluationRunner:
    """Execute evaluation suite."""
    
    def __init__(self, golden_set: dict, scenarios: dict, metrics: EvaluationMetrics):
        self.golden_set = golden_set
        self.scenarios = scenarios
        self.metrics = metrics
    
    def run_evaluation(self) -> dict:
        """Run full evaluation suite."""
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "scenarios": {}
        }
        
        for scenario_name, scenario_config in self.scenarios.items():
            print(f"\nEvaluating scenario: {scenario_name}")
            
            # Load configuration
            pipeline = self._load_pipeline(scenario_config["config"])
            
            scenario_results = {
                "scenario": scenario_name,
                "description": scenario_config["description"],
                "categories": {}
            }
            
            # Evaluate each category
            for category, test_cases in self.golden_set.items():
                category_metrics = []
                
                for test_case in test_cases:
                    query = test_case["query"]
                    relevant_docs = test_case["relevant_documents"]
                    
                    # Retrieval
                    start = time.time()
                    retrieved = pipeline.retrieve(query, k=10)
                    retrieval_latency = time.time() - start
                    
                    retrieved_ids = [r.doc_id for r in retrieved]
                    
                    # Compute retrieval metrics
                    ndcg = self.metrics.ndcg_at_k(retrieved_ids, relevant_docs)
                    recall = self.metrics.recall_at_k(retrieved_ids, relevant_docs)
                    mrr = self.metrics.mean_reciprocal_rank(retrieved_ids, relevant_docs)
                    
                    # Generation
                    start = time.time()
                    answer = pipeline.generate(query, retrieved)
                    generation_latency = time.time() - start
                    
                    # Compute generation metrics
                    answer_quality = self.metrics.answer_quality(
                        answer,
                        test_case["expected_answer"]
                    )
                    
                    # Overall
                    total_latency = retrieval_latency + generation_latency
                    
                    category_metrics.append({
                        "query": query,
                        "retrieval_ndcg": ndcg,
                        "retrieval_recall": recall,
                        "retrieval_mrr": mrr,
                        "retrieval_latency_ms": retrieval_latency * 1000,
                        "generation_latency_ms": generation_latency * 1000,
                        "total_latency_ms": total_latency * 1000,
                        "answer_quality": answer_quality
                    })
                
                # Aggregate category results
                scenario_results["categories"][category] = self._aggregate_metrics(category_metrics)
            
            results["scenarios"][scenario_name] = scenario_results
        
        return results
    
    def _aggregate_metrics(self, metrics: list[dict]) -> dict:
        """Aggregate metrics for category."""
        
        agg = {}
        for key in metrics[0].keys():
            if key == "query":
                continue
            
            values = [m[key] for m in metrics]
            agg[key] = {
                "mean": np.mean(values),
                "min": np.min(values),
                "max": np.max(values),
                "stdev": np.std(values) if len(values) > 1 else 0
            }
        
        return agg
    
    def _load_pipeline(self, config_path: str):
        """Load RAG pipeline from config."""
        from modular_rag.app.bootstrap import load_pipeline
        return load_pipeline(config_path)
```

### 5. Generate Evaluation Report (15 min)

**Create comprehensive report:**

```python
def generate_evaluation_report(results: dict) -> str:
    """Generate evaluation report."""
    
    report = []
    report.append("# Evaluation Report")
    report.append(f"**Date:** {results['timestamp']}")
    report.append("")
    
    # Summary table
    report.append("## Summary")
    report.append("")
    report.append("| Scenario | NDCG@10 | Recall@10 | Total Latency (ms) |")
    report.append("|----------|---------|-----------|-------------------|")
    
    for scenario_name, scenario_data in results["scenarios"].items():
        # Average across all categories
        all_ndcg = []
        all_recall = []
        all_latency = []
        
        for category_data in scenario_data["categories"].values():
            all_ndcg.append(category_data["retrieval_ndcg"]["mean"])
            all_recall.append(category_data["retrieval_recall"]["mean"])
            all_latency.append(category_data["total_latency_ms"]["mean"])
        
        avg_ndcg = np.mean(all_ndcg)
        avg_recall = np.mean(all_recall)
        avg_latency = np.mean(all_latency)
        
        report.append(f"| {scenario_name} | {avg_ndcg:.3f} | {avg_recall:.3f} | {avg_latency:.0f} |")
    
    report.append("")
    
    # Detailed results per scenario
    for scenario_name, scenario_data in results["scenarios"].items():
        report.append(f"## {scenario_name}")
        report.append("")
        
        for category_name, category_data in scenario_data["categories"].items():
            report.append(f"### {category_name}")
            report.append("")
            
            for metric_name, metric_stats in category_data.items():
                if metric_name == "query":
                    continue
                
                report.append(f"**{metric_name}**:")
                report.append(f"- Mean: {metric_stats['mean']:.3f}")
                report.append(f"- Min: {metric_stats['min']:.3f}")
                report.append(f"- Max: {metric_stats['max']:.3f}")
                report.append(f"- Stdev: {metric_stats['stdev']:.3f}")
                report.append("")
    
    return "\n".join(report)

# Generate report
runner = EvaluationRunner(GOLDEN_SET, EVALUATION_SCENARIOS, EvaluationMetrics())
results = runner.run_evaluation()
report = generate_evaluation_report(results)

# Save report
with open("evaluation_report.md", "w") as f:
    f.write(report)

# Save results
with open("evaluation_results.json", "w") as f:
    json.dump(results, f, indent=2)

print(report)
```

### 6. Set Performance Baselines (10 min)

**Establish success criteria:**

```python
PERFORMANCE_BASELINES = {
    "retrieval_quality": {
        "ndcg@10": {
            "baseline": 0.75,
            "target": 0.85,
            "warning": 0.70,
            "critical": 0.60
        },
        "recall@10": {
            "baseline": 0.70,
            "target": 0.85,
            "warning": 0.65,
            "critical": 0.55
        }
    },
    "generation_quality": {
        "answer_quality": {
            "baseline": 0.70,
            "target": 0.85,
            "warning": 0.65,
            "critical": 0.55
        }
    },
    "performance": {
        "total_latency_ms": {
            "baseline": 500,
            "target": 300,
            "warning": 700,
            "critical": 1000
        }
    }
}

# Save baselines
with open("performance_baselines.json", "w") as f:
    json.dump(PERFORMANCE_BASELINES, f, indent=2)
```

### 7. Setup Regression Detection (10 min)

**Automated regression detection:**

```python
def detect_regressions(current_results: dict, baseline: dict) -> dict:
    """Detect performance regressions."""
    
    regressions = []
    improvements = []
    
    for scenario_name in current_results["scenarios"]:
        current_scenario = current_results["scenarios"][scenario_name]
        baseline_scenario = baseline["scenarios"][scenario_name]
        
        for category_name in current_scenario["categories"]:
            current_cat = current_scenario["categories"][category_name]
            baseline_cat = baseline_scenario["categories"][category_name]
            
            # Check each metric
            for metric_name in current_cat:
                current_val = current_cat[metric_name]["mean"]
                baseline_val = baseline_cat[metric_name]["mean"]
                
                pct_change = ((current_val - baseline_val) / baseline_val) * 100
                
                # Check against thresholds
                if metric_name == "total_latency_ms" and pct_change > 10:
                    regressions.append({
                        "type": "latency_regression",
                        "metric": metric_name,
                        "pct_change": pct_change
                    })
                elif metric_name in ["retrieval_ndcg", "answer_quality"] and pct_change < -5:
                    regressions.append({
                        "type": "quality_regression",
                        "metric": metric_name,
                        "pct_change": pct_change
                    })
    
    return {
        "regressions": regressions,
        "regression_count": len(regressions)
    }
```

## Evaluation Template Structure

```
evaluation/
├── golden_dataset.json           # Test queries + ground truth
├── evaluation_scenarios.json     # Configuration variants
├── performance_baselines.json    # Success criteria
├── evaluation_results.json       # Latest results
└── evaluation_report.md          # Human-readable report
```

## Success Criteria

✅ Golden dataset with 50+ test cases
✅ 5+ evaluation metrics defined
✅ 3+ scenarios evaluated
✅ Performance baselines established
✅ Regression detection working
✅ Report generated and saved
✅ Baselines committed to repo

## Time Estimate

**Total:** 1.5 hours for initial setup, 15 min for subsequent runs
