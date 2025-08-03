# 📱 Mobile Setup Guide: Mistral + Gemini Integration

Perfect setup for mobile users who want powerful AI capabilities without local infrastructure!

## 🎯 Why This Setup is Perfect for Mobile

- **No Local Installation**: Everything runs in the cloud
- **Ultra Affordable**: ~$0.14/month for typical usage
- **Best Quality**: Mistral Codestral for coding + Gemini Flash for general tasks
- **Easy Setup**: Just two API keys needed

## 🚀 Quick Start (5 Minutes)

### Step 1: Get Your API Keys

**Mistral API Key** (for coding tasks):
1. Go to [console.mistral.ai](https://console.mistral.ai/)
2. Sign up/login
3. Create API key
4. Copy the key

**Gemini API Key** (for general tasks):
1. Go to [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Sign in with Google account
3. Create API key
4. Copy the key

### Step 2: Deploy to Cloud

**Option A: GitHub Codespaces (Recommended)**
1. Fork this repository
2. Click "Code" → "Codespaces" → "Create codespace"
3. Wait for environment to load
4. Set your environment variables (see Step 3)

**Option B: Railway**
1. Go to [railway.app](https://railway.app)
2. Connect your GitHub account
3. Deploy this repository
4. Set environment variables in Railway dashboard

**Option C: Render**
1. Go to [render.com](https://render.com)
2. Connect GitHub and deploy
3. Set environment variables in Render dashboard

### Step 3: Configure Environment Variables

Set these in your deployment platform:

```bash
# Required API Keys
MISTRAL_API_KEY=your_mistral_key_here
GEMINI_API_KEY=your_gemini_key_here

# Optimal Model Configuration
LLM_BEST_CODING_MODEL=codestral        # Mistral's coding specialist
LLM_UNIVERSAL_MODEL=gemini-flash       # Fast and cheap
LLM_ULTRA_FAST_MODEL=gemini-flash-lite # Ultra cheap
LLM_VISION_MODEL=gemini-flash          # Good vision support
```

### Step 4: Test Your Setup

```bash
# In your cloud environment terminal
python -c "
from agent.llm.utils import get_best_coding_llm_client
client = get_best_coding_llm_client()
print('✅ Mistral Codestral ready for coding!')
"

python -c "
from agent.llm.utils import get_universal_llm_client  
client = get_universal_llm_client()
print('✅ Gemini Flash ready for general tasks!')
"
```

## 💰 Cost Breakdown

### Your Hybrid Setup Costs

**Mistral Codestral** (coding tasks):
- Input: $0.3 per 1M tokens
- Output: $0.9 per 1M tokens
- **Typical usage**: ~$0.12/month

**Gemini Flash** (general tasks):
- Input: $0.075 per 1M tokens  
- Output: $0.15 per 1M tokens
- **Typical usage**: ~$0.02/month

**Total Monthly Cost**: ~$0.14/month for typical usage! 🎉

### Usage Examples

**Light Usage** (personal projects):
- 50K coding tokens/month: $0.06
- 50K general tokens/month: $0.01
- **Total**: $0.07/month

**Medium Usage** (active development):
- 200K coding tokens/month: $0.24
- 200K general tokens/month: $0.04
- **Total**: $0.28/month

**Heavy Usage** (professional use):
- 1M coding tokens/month: $1.20
- 1M general tokens/month: $0.22
- **Total**: $1.42/month

## 🛠️ Available Models

### Mistral Models (Your API Key)

| Model | Use Case | Cost (per 1M tokens) |
|-------|----------|---------------------|
| `codestral` | **Coding tasks** | $0.3 / $0.9 |
| `mistral-large` | Complex reasoning | $2.0 / $6.0 |
| `mistral-small` | Cost-effective | $0.1 / $0.3 |
| `ministral-8b` | Ultra efficient | $0.1 / $0.1 |

### Gemini Models (Free Credits Available)

| Model | Use Case | Cost (per 1M tokens) |
|-------|----------|---------------------|
| `gemini-flash` | **General tasks** | $0.075 / $0.15 |
| `gemini-flash-lite` | **Ultra fast** | $0.0375 / $0.075 |
| `gemini-pro` | Premium quality | $1.25 / $5.0 |

## 🎯 Recommended Configurations

### Budget Setup (~$0.05/month)
```bash
LLM_BEST_CODING_MODEL=mistral-small     # $0.1/$0.3 per 1M tokens
LLM_UNIVERSAL_MODEL=gemini-flash        # $0.075/$0.15 per 1M tokens
LLM_ULTRA_FAST_MODEL=gemini-flash-lite  # $0.0375/$0.075 per 1M tokens
```

### Balanced Setup (~$0.14/month) ⭐ **Recommended**
```bash
LLM_BEST_CODING_MODEL=codestral         # $0.3/$0.9 per 1M tokens
LLM_UNIVERSAL_MODEL=gemini-flash        # $0.075/$0.15 per 1M tokens
LLM_ULTRA_FAST_MODEL=gemini-flash-lite  # $0.0375/$0.075 per 1M tokens
```

### Quality Setup (~$0.50/month)
```bash
LLM_BEST_CODING_MODEL=codestral         # $0.3/$0.9 per 1M tokens
LLM_UNIVERSAL_MODEL=gemini-pro          # $1.25/$5.0 per 1M tokens
LLM_ULTRA_FAST_MODEL=gemini-flash       # $0.075/$0.15 per 1M tokens
```

## 🔧 Advanced Configuration

### Custom Model Selection

You can override models for specific tasks:

```python
from agent.llm.utils import get_llm_client

# Use Mistral Large for complex reasoning
reasoning_client = get_llm_client(model_name="mistral-large")

# Use Gemini Flash-Lite for simple tasks
fast_client = get_llm_client(model_name="gemini-flash-lite")

# Use Codestral specifically for coding
coding_client = get_llm_client(model_name="codestral")
```

### Environment Variables Reference

```bash
# API Keys
MISTRAL_API_KEY=your_key
GEMINI_API_KEY=your_key

# Model Selection
LLM_BEST_CODING_MODEL=codestral
LLM_UNIVERSAL_MODEL=gemini-flash
LLM_ULTRA_FAST_MODEL=gemini-flash-lite
LLM_VISION_MODEL=gemini-flash

# Advanced Configuration
MISTRAL_BASE_URL=https://api.mistral.ai/v1
MISTRAL_TIMEOUT=60
MISTRAL_MAX_RETRIES=3
GEMINI_TIMEOUT=60
GEMINI_MAX_RETRIES=3

# Caching (reduces costs)
CACHE_ENABLED=true
CACHE_TTL=3600
```

## 🚀 Cloud Deployment Platforms

### GitHub Codespaces (Free Tier)
- **Cost**: Free 60 hours/month
- **Perfect for**: Development and testing
- **Setup**: One-click from GitHub

### Railway
- **Cost**: $5/month for hobby plan
- **Perfect for**: Production deployment
- **Features**: Auto-deploy from GitHub

### Render
- **Cost**: Free tier available
- **Perfect for**: Small projects
- **Features**: Easy environment management

### DigitalOcean App Platform
- **Cost**: $5/month basic plan
- **Perfect for**: Scalable deployment
- **Features**: Managed infrastructure

## 🎉 You're Ready!

With this setup, you have:

✅ **Excellent coding capabilities** with Mistral Codestral  
✅ **Fast, cheap general AI** with Gemini Flash  
✅ **Ultra-low costs** (~$0.14/month)  
✅ **No local infrastructure needed**  
✅ **Mobile-friendly cloud deployment**  

Your agent is now ready to handle any task with optimal cost and performance! 🚀

## 🆘 Troubleshooting

**API Key Issues:**
- Ensure keys are set correctly in environment variables
- Check that keys have sufficient credits/quota
- Verify API key permissions

**Model Not Found:**
- Check spelling of model names
- Ensure the model is available in your region
- Try alternative models if one is unavailable

**High Costs:**
- Enable caching to reduce duplicate requests
- Use cheaper models for simple tasks
- Monitor usage in provider dashboards

**Need Help?**
- Check the logs for detailed error messages
- Test individual components separately
- Refer to provider documentation for API limits
