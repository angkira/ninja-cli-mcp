# 🚀 Quick Start - Model Experiments

Get started with model comparison and cost analysis in 5 minutes!

## 1️⃣ Install Dependencies

```bash
# From project root
cd ninja-cli-mcp

# Install notebook dependencies
uv sync --extra notebooks
```

This installs:
- `jupyter` - Notebook environment
- `matplotlib` - Charts
- `seaborn` - Beautiful visualizations
- `pandas` - Data analysis

## 2️⃣ Set API Key

```bash
# Load your config (if you used the installer)
source ~/.ninja-cli-mcp.env

# Or set manually
export OPENROUTER_API_KEY='your-key-here'
```

**Note:** Cost Analysis notebook works without API key (uses pricing API only)

## 3️⃣ Launch Notebooks

### Option A: Quick Launch Script

```bash
./scripts/run_notebooks.sh
```

This will:
- Check dependencies
- Load your config
- Launch Jupyter in the notebooks directory

### Option B: Manual Launch

```bash
cd notebooks
uv run jupyter notebook
```

## 4️⃣ Choose a Notebook

### 🥷 Model Comparison - Start Here!

**File:** `01_model_comparison.ipynb`

**What it does:**
- Runs simple coding tasks with different models
- Compares cost, speed, and success rate
- Shows you the best value model

**Cost:** ~$0.01-0.05 (makes real API calls)

**Run time:** ~2-3 minutes

---

### 💰 Cost Analysis - No API Calls!

**File:** `02_cost_analysis.ipynb`

**What it does:**
- Fetches real-time pricing from OpenRouter
- Projects monthly costs for your workload
- Analyzes cache savings (~90% discount)

**Cost:** FREE (only fetches pricing, no model calls)

**Run time:** <30 seconds

---

## 5️⃣ Run the Notebook

Once Jupyter opens in your browser:

1. Click on a notebook (e.g., `02_cost_analysis.ipynb`)
2. Click **Cell → Run All** (or press Shift+Enter repeatedly)
3. Watch the magic happen! 🎉

## 📊 What You'll Get

### Charts Generated

- `cost_comparison.png` - Which model costs least
- `performance_comparison.png` - Speed & success rates
- `cost_vs_performance.png` - Best value model
- `pricing_comparison.png` - Token pricing breakdown
- `monthly_costs.png` - Monthly projections
- `cache_savings.png` - Cache discount analysis

### Data Files

- `model_comparison_results.json` - Raw experiment data

## 🎯 Quick Tips

### Want to Compare Specific Models?

Edit the `MODELS` dict in the notebook:

```python
MODELS = {
    "my-model": "provider/model-id",
    # Add your models here
}
```

### Want to Test Your Own Tasks?

Edit `TEST_TASKS` in `01_model_comparison.ipynb`:

```python
TEST_TASKS.append({
    "name": "My Task",
    "description": "What to do",
    "code": "# Your test code",
    "expected_tokens": 100,
})
```

### Want Different Workload Scenarios?

Edit `SCENARIOS` in `02_cost_analysis.ipynb`:

```python
SCENARIOS["My Workload"] = {
    "description": "100 medium tasks/day",
    "input_tokens": 5000,
    "output_tokens": 2000,
}
```

## 🔧 Troubleshooting

### "Module not found" errors

```bash
# Reinstall notebook dependencies
uv sync --extra notebooks
```

### "No API key" warnings

```bash
# Set your key
export OPENROUTER_API_KEY='sk-or-v1-...'

# Or load from config
source ~/.ninja-cli-mcp.env
```

### Rate limit errors

The notebooks include 1-second delays between calls. If you still hit limits:

1. Reduce the number of models tested
2. Increase the delay in the code
3. Run experiments in smaller batches

### Charts not displaying

If running headless (no GUI):

```python
# Add at top of notebook
import matplotlib
matplotlib.use('Agg')  # Use non-GUI backend
```

## 💡 Recommendations

### For Budget Analysis
Start with **Cost Analysis** (02) - it's free and instant!

### For Real Comparisons
Run **Model Comparison** (01) with your actual tasks.

### For Production Planning
1. Run Cost Analysis to see pricing
2. Customize Model Comparison with your tasks
3. Use results to choose the right model

## 📚 Learn More

- [Full Notebook Documentation](README.md)
- [OpenRouter Models](https://openrouter.ai/models)
- [ninja-cli-mcp Docs](../README.md)

---

## 🎉 Example Output

```
🏆 Winners:
  💰 Cheapest:      Gemini 2.0 Flash ($0.000012/task)
  ✅ Most Reliable: Claude Sonnet 4 (100% success)
  ⚡ Fastest:        Claude Haiku 4 (312.1 tok/s)
  💎 Best Value:    Qwen 2.5 Coder 32B (score: 1123)

💡 Recommendations:
  → Use Qwen 2.5 Coder 32B for best overall value
  → Use Gemini 2.0 Flash if budget is critical
  → Use Claude Haiku 4 when speed is important

📈 Total Experiments: 12
💸 Total Cost: $0.003456
⏱️  Total Time: 8.42s
```

---

**Happy experimenting! 🥷📊**

Need help? Check [notebooks/README.md](README.md) for detailed documentation.
