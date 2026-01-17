# Intelligent Model Selection

## Overview

Ninja-coder now features intelligent model selection that automatically chooses the optimal model based on task complexity, cost preferences, and performance requirements.

## How It Works

The `ModelSelector` analyzes each task and routes it to the most appropriate model using a database of model capabilities, costs, and performance metrics.

### Task Types

Tasks are classified into three complexity levels:

1. **Quick** - Single-pass simple tasks (e.g., "create a hello world function")
2. **Sequential** - Multi-step dependent tasks (e.g., "implement user authentication")
3. **Parallel** - Multiple independent tasks running concurrently

### Model Database

The system maintains a database of models with their characteristics:

```python
{
    "glm-4.6v": {
        "provider": "z.ai",
        "best_for": ["parallel"],
        "concurrent_limit": 20,  # Can handle 20 parallel requests
        "cost": "low",
        "livebench_score": None,
    },
    "glm-4.7": {
        "provider": "z.ai",
        "best_for": ["sequential"],
        "concurrent_limit": 5,
        "cost": "medium",
        "livebench_score": 84.9,  # LiveBench coding score
        "supports_coding_plan_api": True,
    },
    "anthropic/claude-haiku-4.5": {
        "provider": "openrouter",
        "best_for": ["quick", "parallel"],
        "concurrent_limit": 10,
        "cost": "low",
        "livebench_score": 82.0,
    },
}
```

## Selection Rules

### Quick Tasks

For simple, single-pass tasks:

- **Default**: Claude Haiku 4.5 (fast, capable, LiveBench 82.0)
- **Cost-optimized**: GLM-4.0 (z.ai, lowest cost)

### Sequential Tasks

For multi-step complex tasks:

- **Default**: GLM-4.7 (LiveBench 84.9, Coding Plan API)
- **Quality-optimized**: Claude Sonnet 4 or Opus 4 (highest quality)
- **Cost-optimized**: GLM-4.0 (balanced)

### Parallel Tasks

For multiple independent tasks:

- **High fanout (>10)**: GLM-4.6V (20 concurrent, lowest cost)
- **Medium fanout (5-10)**: Claude Haiku 4.5 (balanced)
- **Cost-optimized**: GLM-4.0

## Configuration

### Environment Variables

#### Model Preferences

```bash
# Prioritize cost over quality
export NINJA_PREFER_COST=true

# Prioritize quality over cost
export NINJA_PREFER_QUALITY=true

# Use specific model (disables automatic selection)
export NINJA_MODEL=glm-4.7
```

#### Z.ai Configuration

```bash
# Z.ai API key
export OPENAI_API_KEY=your-zai-key

# Z.ai base URL (standard API)
export OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4

# Or use Coding Plan API endpoint (for GLM-4.7)
# export OPENAI_BASE_URL=https://open.bigmodel.cn/api/coding/paas/v4
```

### Automatic API Selection

The system automatically uses the Coding Plan API for GLM-4.7 on sequential tasks when `use_coding_plan_api=True` is returned by the model selector.

## Usage Examples

### Simple Task (Automatic Selection)

```python
# ToolExecutor automatically passes task_type="quick"
await tools.simple_task({
    "task": "Create a hello world function",
    "repo_root": "/tmp/test",
})

# Selected: Claude Haiku 4.5 (fast, capable)
```

### Sequential Plan (Smart Model)

```python
# ToolExecutor automatically passes task_type="sequential"
await tools.execute_plan_sequential({
    "repo_root": "/tmp/test",
    "steps": [
        {"id": "step1", "title": "Create base", "task": "..."},
        {"id": "step2", "title": "Add tests", "task": "..."},
    ],
})

# Selected: GLM-4.7 (LiveBench 84.9, Coding Plan API)
```

### Parallel Plan (High Concurrency)

```python
# ToolExecutor automatically passes task_type="parallel"
await tools.execute_plan_parallel({
    "repo_root": "/tmp/test",
    "fanout": 15,  # High concurrency
    "steps": [/* 15 independent tasks */],
})

# Selected: GLM-4.6V (20 concurrent, cheapest)
```

## Cost Optimization

### Z.ai Subscription Benefits

With a z.ai subscription, parallel tasks become very cost-effective:

- **GLM-4.6V**: $0.01-0.05 per task (20 concurrent)
- **GLM-4.7**: $0.20-0.50 per task (5 concurrent, highest quality)
- **GLM-4.0**: $0.01-0.03 per task (10 concurrent, balanced)

### Cost vs. Quality Trade-offs

| Task Type | Cost Priority | Quality Priority |
|-----------|---------------|------------------|
| Quick | GLM-4.0 | Claude Haiku 4.5 |
| Sequential | GLM-4.0 | GLM-4.7 or Claude Sonnet 4 |
| Parallel (>10) | GLM-4.6V | Claude Haiku 4.5 |

## Performance Metrics

### LiveBench Scores

LiveBench evaluates models on real-world coding tasks:

- **GLM-4.7**: 84.9 (z.ai, excellent for sequential)
- **Claude Haiku 4.5**: 82.0 (fast, balanced)
- **Claude Sonnet 4**: 88.0 (premium quality)
- **Claude Opus 4**: 91.0 (highest quality)

### Concurrency Limits

Based on provider rate limits:

- **GLM-4.6V (z.ai)**: 20 concurrent requests
- **Claude Haiku 4.5**: 10 concurrent requests
- **GLM-4.7 (z.ai)**: 5 concurrent requests

## Disabling Automatic Selection

To use a specific model for all tasks:

```bash
# Use GLM-4.7 for everything
export NINJA_MODEL=glm-4.7

# Model selector will return this as default
# (no automatic selection based on task type)
```

## Extending the Model Database

To add new models to the selection logic:

1. Edit `src/ninja_common/defaults.py`
2. Add entry to `MODEL_DATABASE`:

```python
"your-model-name": {
    "provider": "provider-name",
    "best_for": ["quick", "sequential", "parallel"],
    "concurrent_limit": 10,
    "cost": "low",  # low, medium, high, very_high
    "livebench_score": 85.0,
    "supports_coding_plan_api": False,
}
```

3. Restart the MCP server

## Monitoring Model Selection

Model selection is logged for every task:

```
[INFO] Selected model: glm-4.7
       (reason: Highest quality for sequential tasks (LiveBench 84.9) with Coding Plan API,
        estimated cost: $0.20-0.50 per task)
```

This helps understand which models are being used and why.

## Best Practices

1. **Use z.ai for parallel tasks** - 20 concurrent with GLM-4.6V
2. **Use GLM-4.7 for complex sequential** - Best LiveBench score on z.ai
3. **Enable cost preference for experimentation** - Use cheaper models for testing
4. **Enable quality preference for production** - Use best models for critical code
5. **Monitor logs** - Check which models are selected and adjust if needed

## Troubleshooting

### Model Not Available

If a selected model is not available:
- Check API key and base URL configuration
- Verify model name is correct
- Check provider rate limits
- System will fall back to default model

### Unexpected Model Selection

If the wrong model is selected:
- Check environment variables (`NINJA_PREFER_COST`, `NINJA_PREFER_QUALITY`)
- Check `NINJA_MODEL` (disables automatic selection if set)
- Review task_type being passed
- Check logs for selection reasoning
