---
name: parallel-feature-analysis
description: Workflow for parallel analysis of retrieval, generation, security features
---

# Parallel Feature Analysis Skill

_Originally authored as a workflow for `observability-expert`, invoked as `/parallel-feature-analysis`._


Systematic workflow for analyzing multiple framework features in parallel.

## When to Use

- Comparing component implementations
- Performance benchmarking across versions
- Impact analysis for proposed changes
- Regression detection
- Complex feature interactions

## Parallel Execution Model

**Serial (traditional):**
```
Feature A (2h) → Feature B (2h) → Feature C (2h) = 6h total
```

**Parallel (optimized):**
```
Feature A (2h) ┐
Feature B (2h) ├ = 2h total
Feature C (2h) ┘
```

## Workflow Steps

### 1. Define Analysis Scope (10 min)

**Identify independent features:**

```python
FEATURES_TO_ANALYZE = {
    "retrieval": {
        # names match the real registered types in orchestration/_default_factories.py
        # ("vector", "hybrid") — there is no standalone registered "bm25" retriever
        # type, only via HybridRetriever internally
        "components": ["vector", "hybrid"],
        "metrics": ["ndcg@10", "latency", "memory"],
        "queries": ["q1", "q2", "q3"]
    },
    "generation": {
        "components": ["openai", "anthropic"],  # registered generator type names
        "metrics": ["token_count", "latency", "quality_score"],
        "prompts": ["prompt1", "prompt2"]
    },
    "security": {
        "components": ["pii_detector", "injection_filter"],
        "metrics": ["false_positive_rate", "latency", "coverage"],
        "test_inputs": ["input1", "input2"]
    }
}

# Key: These analysis groups are independent
# Can run in parallel without data dependencies
```

### 2. Create Analysis Functions (15 min)

**Template for each feature:**

```python
import asyncio
from datetime import datetime

async def analyze_retrieval_feature(config: dict) -> dict:
    """Analyze retrieval components."""
    
    start = datetime.now()
    results = {
        "feature": "retrieval",
        "timestamp": start.isoformat(),
        "components": {}
    }
    
    # Analyze each retriever
    for component_name in config["components"]:
        retriever = create_retriever(component_name)
        component_results = {
            "name": component_name,
            "metrics": {}
        }
        
        # Run each metric
        for query in config["queries"]:
            retrieved = retriever.retrieve(query, k=10)
            
            # Compute metrics
            ndcg = compute_ndcg(retrieved, golden_set[query])
            latency = measure_latency(retriever.retrieve, query, k=10)
            memory = measure_memory(retriever)
            
            if query not in component_results["metrics"]:
                component_results["metrics"][query] = {}
            
            component_results["metrics"][query] = {
                "ndcg@10": ndcg,
                "latency_ms": latency * 1000,
                "memory_mb": memory
            }
        
        results["components"][component_name] = component_results
    
    results["duration_seconds"] = (datetime.now() - start).total_seconds()
    return results

async def analyze_generation_feature(config: dict) -> dict:
    """Analyze generation components."""
    # Similar structure to retrieval analysis
    pass

async def analyze_security_feature(config: dict) -> dict:
    """Analyze security components."""
    # Similar structure to retrieval analysis
    pass
```

### 3. Execute Parallel Analysis (15 min)

**Orchestrate parallel tasks:**

```python
async def run_parallel_analysis():
    """Execute all analyses in parallel."""
    
    # Define all analysis tasks
    tasks = [
        analyze_retrieval_feature(FEATURES_TO_ANALYZE["retrieval"]),
        analyze_generation_feature(FEATURES_TO_ANALYZE["generation"]),
        analyze_security_feature(FEATURES_TO_ANALYZE["security"]),
    ]
    
    # Run in parallel
    print("Starting parallel analysis...")
    start_time = datetime.now()
    
    results = await asyncio.gather(*tasks)
    
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"Analysis completed in {elapsed:.1f}s")
    
    return {
        "execution_time": elapsed,
        "analyses": {r["feature"]: r for r in results},
        "timestamp": datetime.now().isoformat()
    }

# Execute
if __name__ == "__main__":
    import asyncio
    results = asyncio.run(run_parallel_analysis())
```

### 4. Collect & Aggregate Results (10 min)

**Consolidate findings:**

```python
def aggregate_results(results: dict) -> dict:
    """Aggregate parallel analysis results."""
    
    aggregated = {
        "summary": {
            "total_components": 0,
            "total_metrics": 0,
            "features": {}
        },
        "details": results
    }
    
    # Summarize each feature
    for feature_name, feature_results in results["analyses"].items():
        components = feature_results.get("components", {})
        
        aggregated["summary"]["features"][feature_name] = {
            "components_analyzed": len(components),
            "avg_metric_value": compute_avg_metrics(components),
            "best_component": find_best_component(components),
            "worst_component": find_worst_component(components)
        }
        
        aggregated["summary"]["total_components"] += len(components)
    
    return aggregated

def compute_avg_metrics(components: dict) -> dict:
    """Average metrics across components."""
    all_metrics = {}
    
    for component in components.values():
        for query, metrics in component["metrics"].items():
            for metric_name, value in metrics.items():
                if metric_name not in all_metrics:
                    all_metrics[metric_name] = []
                all_metrics[metric_name].append(value)
    
    return {
        name: {
            "mean": statistics.mean(values),
            "min": min(values),
            "max": max(values),
            "stdev": statistics.stdev(values) if len(values) > 1 else 0
        }
        for name, values in all_metrics.items()
    }
```

### 5. Generate Report (15 min)

**Create comprehensive report:**

```python
def generate_analysis_report(aggregated_results: dict) -> str:
    """Generate human-readable report."""
    
    report = []
    report.append("# Parallel Feature Analysis Report")
    report.append(f"**Generated:** {aggregated_results['details']['timestamp']}")
    report.append(f"**Total Execution Time:** {aggregated_results['details']['execution_time']:.1f}s")
    report.append("")
    
    # Summary table
    report.append("## Summary")
    report.append("")
    report.append("| Feature | Components | Best | Worst |")
    report.append("|---------|-----------|------|-------|")
    
    for feature, data in aggregated_results["summary"]["features"].items():
        report.append(f"| {feature} | {data['components_analyzed']} | " +
                     f"{data['best_component']} | {data['worst_component']} |")
    
    report.append("")
    
    # Detailed metrics per feature
    for feature_name, feature_data in aggregated_results["details"]["analyses"].items():
        report.append(f"## {feature_name.title()} Analysis")
        report.append("")
        
        for component_name, component_data in feature_data.get("components", {}).items():
            report.append(f"### {component_name}")
            report.append("")
            
            # Metrics table for this component
            report.append("| Query | NDCG@10 | Latency (ms) | Memory (MB) |")
            report.append("|-------|---------|--------------|------------|")
            
            for query, metrics in component_data["metrics"].items():
                report.append(f"| {query} | {metrics.get('ndcg@10', 'N/A'):.3f} | " +
                             f"{metrics.get('latency_ms', 'N/A'):.1f} | " +
                             f"{metrics.get('memory_mb', 'N/A'):.1f} |")
            
            report.append("")
    
    return "\n".join(report)

# Generate and save report
report = generate_analysis_report(aggregated_results)
print(report)

# Save to file
with open("analysis_report.md", "w") as f:
    f.write(report)
```

### 6. Compare Against Baselines (10 min)

**Detect regressions:**

```python
def compare_with_baseline(current_results: dict, baseline_results: dict) -> dict:
    """Compare current analysis against baseline."""
    
    regressions = []
    improvements = []
    
    for feature_name in current_results["analyses"]:
        current_feature = current_results["analyses"][feature_name]
        baseline_feature = baseline_results["analyses"][feature_name]
        
        for component_name in current_feature["components"]:
            current_metrics = current_feature["components"][component_name]["metrics"]
            baseline_metrics = baseline_feature["components"][component_name]["metrics"]
            
            # Compare each metric
            for query in current_metrics:
                for metric_name in current_metrics[query]:
                    current_value = current_metrics[query][metric_name]
                    baseline_value = baseline_metrics[query][metric_name]
                    
                    # Calculate percent change
                    pct_change = ((current_value - baseline_value) / baseline_value) * 100
                    
                    # Flag regressions/improvements
                    if metric_name == "latency_ms" and pct_change > 10:
                        regressions.append({
                            "type": "latency_regression",
                            "component": component_name,
                            "pct_change": pct_change
                        })
                    elif metric_name == "ndcg@10" and pct_change < -5:
                        regressions.append({
                            "type": "quality_regression",
                            "component": component_name,
                            "pct_change": pct_change
                        })
                    elif metric_name == "ndcg@10" and pct_change > 5:
                        improvements.append({
                            "type": "quality_improvement",
                            "component": component_name,
                            "pct_change": pct_change
                        })
    
    return {
        "regressions": regressions,
        "improvements": improvements,
        "regression_count": len(regressions),
        "improvement_count": len(improvements)
    }

# Check for regressions
comparison = compare_with_baseline(current_results, baseline_results)

if comparison["regressions"]:
    print("⚠️  REGRESSIONS DETECTED:")
    for regression in comparison["regressions"]:
        print(f"  - {regression['component']}: {regression['pct_change']:.1f}% {regression['type']}")

if comparison["improvements"]:
    print("✅ IMPROVEMENTS:")
    for improvement in comparison["improvements"]:
        print(f"  - {improvement['component']}: {improvement['pct_change']:.1f}% {improvement['type']}")
```

### 7. Store Baseline (5 min)

**Save for future comparisons:**

```python
import json

def save_analysis_baseline(results: dict, filename: str = "baseline.json"):
    """Save analysis results as baseline."""
    
    with open(filename, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"Baseline saved to {filename}")

# Save current analysis as baseline
save_analysis_baseline(aggregated_results, "analysis_baseline.json")
```

## Execution Timeline

```
Serial: 6 hours
0h      2h      4h      6h
|-------|-------|-------|
[Feature A] [Feature B] [Feature C]

Parallel: 2 hours
0h                2h
|-----------------|
[Feature A]
[Feature B]
[Feature C]

Speedup: 3x faster
```

## Common Parallel Patterns

### Pattern 1: Independent Features
```python
results = await asyncio.gather(
    analyze_retrieval(),
    analyze_generation(),
    analyze_security()
)
# Safe: no dependencies
```

### Pattern 2: Dependent Features
```python
# First analyze retrieval (needed by generation)
retrieval_results = await analyze_retrieval()

# Then analyze generation (depends on retrieval)
generation_results = await analyze_generation(retrieval_results)

# Security independent
security_results = await analyze_security()

# Combine
results = retrieve_results + generation_results + security_results
```

## Success Criteria

✅ Parallel execution completes < 1/3 serial time
✅ All components analyzed
✅ Metrics computed accurately
✅ Report generated
✅ Regressions detected
✅ Baseline saved
✅ Results reproducible

## Time Estimate

**Total:** 30 min for first run, 10 min for subsequent runs (parallel execution)
