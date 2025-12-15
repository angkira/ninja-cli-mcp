# 📊 Ninja CLI MCP Experiments & Analysis

Beautiful Jupyter notebooks for comparing AI models, analyzing costs, and benchmarking performance.

## 📓 Notebooks

### 1. 🥷 Model Comparison (`01_model_comparison.ipynb`)

Compare different AI models on simple coding tasks with **LiveBench rankings**:

**Models tested:**
- **Qwen3 Coder 480B** - Latest agentic coding model (MoE 8/160)
- **Qwen3 Coder 30B** - Smaller MoE variant (8/128 experts)
- **Qwen3 Coder Flash** - Fast & cost-efficient version
- **Claude Sonnet 4** - Top 3 on LiveBench coding (81.2%)
- **Claude Haiku 4** - Fast and cost-effective
- **Gemini 2.0 Flash** - Google's latest
- **GPT-4o, DeepSeek Chat** - Additional comparisons

**Metrics measured:**
- 💰 Cost per task
- ⚡ Speed (tokens/sec)
- 📊 Token usage (input/output)
- ✅ Success rate
- 🏆 **LiveBench coding score** (benchmark ranking)
- 💎 Value score (performance / cost)

**Output:**
- 🏆 LiveBench rankings for coding tasks
- 💡 Budget-based recommendations (low/medium/high)
- 📊 Interactive charts comparing all models
- 💎 LiveBench score vs real performance analysis
- 📈 Cost vs Performance scatter plot
- 🎯 Detailed results grouped by model family

**Estimated cost:** ~$0.02-0.10 (depending on models selected)

**Data sources:**
- [LiveBench Leaderboard](https://livebench.ai)
- [LiveBench on HuggingFace](https://huggingface.co/datasets/livebench/model_judgment)

---

### 2. 💰 Deep Cost Analysis (`02_cost_analysis.ipynb`)

Detailed cost breakdown with LiveBench performance rankings:

**Features:**
- 🔄 Real-time pricing from OpenRouter API
- 🏆 **LiveBench coding scores** for each model
- 📈 Cost per 1M tokens (grouped by model family)
- 💎 Value score: Performance / Cost ratio
- 🎯 Cost projections for typical workloads:
  - Small task (500 tokens)
  - Medium task (2K tokens)
  - Large task (10K tokens)
  - Daily usage (100 tasks)
- 📅 Monthly cost projections (100 tasks/day)
- 💡 Prompt caching savings analysis (~90% discount)
- 🔷 **Qwen3 Coder variant comparison**

**Charts generated:**
- Input/Output pricing + LiveBench scores
- Performance vs Cost visualization
- Monthly projections sorted by LiveBench
- Value score (best performance per dollar)
- Qwen3 family comparison

**No model API calls needed** - uses OpenRouter pricing API only (FREE!)

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
# Install Jupyter and plotting libraries
uv pip install jupyter matplotlib seaborn pandas

# Or add to your environment
uv add --dev jupyter matplotlib seaborn pandas
```

### 2. Set API Key

```bash
# Load your config
source ~/.ninja-cli-mcp.env

# Or set directly
export OPENROUTER_API_KEY='your-key-here'
```

### 3. Launch Jupyter

```bash
cd notebooks
jupyter notebook
```

### 4. Run Notebooks

Open either notebook and run all cells (`Cell > Run All`)

---

## 📊 Sample Results

### Cost Comparison

| Model | Avg Cost/Task | Success Rate | Tokens/sec |
|-------|---------------|--------------|------------|
| Gemini 2.0 Flash | $0.000012 | 100% | 245.3 |
| Qwen 2.5 Coder 32B | $0.000089 | 100% | 189.7 |
| Claude Haiku 4 | $0.000234 | 100% | 312.1 |
| Claude Sonnet 4 | $0.001456 | 100% | 156.8 |

*Sample data - actual results may vary*

### Monthly Projections (100 tasks/day)

| Model | Monthly Cost | With Caching | Savings |
|-------|--------------|--------------|---------|
| Gemini 2.0 Flash | $0.36 | $0.18 | $0.18 |
| Qwen 2.5 Coder | $2.67 | $1.34 | $1.33 |
| Claude Haiku 4 | $7.02 | $3.51 | $3.51 |
| Claude Sonnet 4 | $43.68 | $21.84 | $21.84 |

*Sample data - actual results may vary*

---

## 🎯 Use Cases

### For Budget-Conscious Users
Run `02_cost_analysis.ipynb` to:
- Find the cheapest model for your workload
- Estimate monthly costs
- Calculate cache savings

### For Performance Testing
Run `01_model_comparison.ipynb` to:
- Compare speed across models
- Find best value (cost + performance)
- Test on your specific tasks

### For Production Planning
Use both notebooks to:
- Estimate infrastructure costs
- Choose the right model for each task type
- Optimize with prompt caching

---

## 📁 Output Files

Notebooks generate:

### Charts (PNG)
- `cost_comparison.png` - Cost per task comparison
- `performance_comparison.png` - Speed & success rates
- `cost_vs_performance.png` - Scatter plot
- `pricing_comparison.png` - Per-token pricing
- `monthly_costs.png` - Monthly projections
- `cache_savings.png` - Cache discount analysis

### Data (JSON)
- `model_comparison_results.json` - Raw experiment results

---

## 🔧 Customization

### Add Your Own Models

Edit the `MODELS` dict in either notebook:

```python
MODELS = {
    "my-custom-model": "provider/model-id",
    # ...existing models
}
```

### Add Custom Test Tasks

In `01_model_comparison.ipynb`:

```python
TEST_TASKS.append({
    "name": "My Custom Task",
    "description": "What the model should do",
    "code": "# Your test code here",
    "expected_tokens": 200,
})
```

### Adjust Workload Scenarios

In `02_cost_analysis.ipynb`:

```python
SCENARIOS["My Scenario"] = {
    "description": "Your use case",
    "input_tokens": 5000,
    "output_tokens": 2000,
}
```

---

## ⚠️ Important Notes

### Cost Control

1. **Model comparison** (`01_*`) makes real API calls - costs ~$0.01-0.05
2. **Cost analysis** (`02_*`) only fetches pricing - FREE
3. Set `OPENROUTER_API_KEY` before running experiments
4. Review test tasks before running to estimate costs

### Rate Limits

- Notebooks include 1-second delays between API calls
- If you hit rate limits, increase the delay
- Consider running experiments in batches

### Cache Support

Not all models support prompt caching:
- ✅ Claude models (Sonnet, Haiku)
- ✅ GPT-4 models
- ❌ Qwen models (as of Dec 2024)
- ❌ Gemini models (as of Dec 2024)

Check OpenRouter docs for latest cache support.

---

## 📚 Dependencies

Required Python packages:
- `jupyter` - Notebook environment
- `pandas` - Data manipulation
- `matplotlib` - Plotting
- `seaborn` - Beautiful charts
- `ninja_cli_mcp` - Our package (already installed)

---

## 🤝 Contributing

Have ideas for new analyses?

1. Create a new notebook: `03_your_analysis.ipynb`
2. Follow the existing style (emoji headers, clean charts)
3. Document your metrics clearly
4. Add to this README

---

## 📖 Learn More

- [OpenRouter Pricing](https://openrouter.ai/models) - Full model list
- [Prompt Caching Guide](https://openrouter.ai/docs#prompt-caching)
- [ninja-cli-mcp Docs](../README.md) - Main documentation

---

**Happy experimenting! 🥷📊**
