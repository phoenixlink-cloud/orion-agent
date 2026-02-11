# Integration Catalog

Complete catalog of all 79+ integrations available in Orion Agent.

## Overview

Orion integrates with external services across 10 categories:

| Category | Count | Module |
|----------|-------|--------|
| [LLM Providers](#llm-providers) | 11 | `core/llm/providers.py` |
| [Voice TTS](#voice-text-to-speech) | 8 | `integrations/voice/` |
| [Voice STT](#voice-speech-to-text) | 6 | `integrations/voice/` |
| [Image Generation](#image-generation) | 8 | `integrations/image_gen/` |
| [Video Generation](#video-generation) | 7 | `integrations/video_gen/` |
| [Messaging](#messaging) | 15 | `integrations/messaging/` |
| [Social Platforms](#social-platforms) | 5 | `integrations/social/` |
| [Automation](#automation) | 5 | `integrations/automation/` |
| [Storage](#storage) | 4 | `integrations/storage/` |
| [Dev Tools](#dev-tools) | 10+ | Various |

## LLM Providers

Core functionality -- these power Orion's AI capabilities.

| Provider | Models | API Key Env Var | Local |
|----------|--------|-----------------|-------|
| **OpenAI** | GPT-4o, GPT-4-turbo, GPT-3.5-turbo | `OPENAI_API_KEY` | No |
| **Anthropic** | Claude 3.5 Sonnet, Claude 3 Opus, Haiku | `ANTHROPIC_API_KEY` | No |
| **Google** | Gemini Pro, Gemini Ultra | `GOOGLE_API_KEY` | No |
| **Ollama** | Llama 3, Mistral, CodeLlama, Phi-3 | None (local) | Yes |
| **Groq** | Llama 3 70B, Mixtral 8x7B | `GROQ_API_KEY` | No |
| **Mistral** | Mistral Large, Medium, Small | `MISTRAL_API_KEY` | No |
| **Cohere** | Command R+, Command R | `COHERE_API_KEY` | No |
| **Together** | Various open models | `TOGETHER_API_KEY` | No |
| **Perplexity** | pplx-7b, pplx-70b | `PERPLEXITY_API_KEY` | No |
| **Fireworks** | Various open models | `FIREWORKS_API_KEY` | No |
| **DeepSeek** | DeepSeek Coder, DeepSeek Chat | `DEEPSEEK_API_KEY` | No |

### Configuration
```
> /settings provider openai
> /settings model gpt-4o
```

## Voice (Text-to-Speech)

| Provider | Quality | API Key Required | Notes |
|----------|---------|-----------------|-------|
| **ElevenLabs** | Premium | Yes | Best quality, 29+ voices |
| **OpenAI TTS** | High | Yes (OpenAI key) | tts-1, tts-1-hd models |
| **Edge-TTS** | Good | No | Microsoft Edge voices, free |
| **Piper** | Good | No | Local, offline capable |
| **Deepgram** | High | Yes | Low latency streaming |
| **Azure Speech** | High | Yes | Enterprise grade |
| **Google Cloud TTS** | High | Yes | WaveNet voices |
| **AWS Polly** | Good | Yes | Neural voices available |

### Configuration
```yaml
voice:
  tts_provider: elevenlabs
  tts_voice: "Rachel"
```

## Voice (Speech-to-Text)

| Provider | Quality | API Key Required | Notes |
|----------|---------|-----------------|-------|
| **Whisper** | Excellent | No (local) or Yes (API) | OpenAI's model, local or API |
| **Vosk** | Good | No | Fully offline |
| **Deepgram** | Excellent | Yes | Real-time streaming |
| **AssemblyAI** | Excellent | Yes | Best accuracy |
| **Azure Speech** | High | Yes | Enterprise grade |
| **Google Cloud STT** | High | Yes | Streaming support |

### Configuration
```yaml
voice:
  stt_provider: whisper
  stt_model: base
```

## Image Generation

| Provider | Models | API Key Required | Notes |
|----------|--------|-----------------|-------|
| **DALL-E** | DALL-E 3, DALL-E 2 | Yes (OpenAI) | Best for general images |
| **Stability AI** | SDXL, SD 1.5 | Yes | Open-source models |
| **Midjourney** | Midjourney v5+ | Yes | Via API proxy |
| **Replicate** | Various | Yes | Run any model |
| **Leonardo.ai** | Various | Yes | Game/concept art focus |
| **Fal.ai** | Various | Yes | Fast inference |
| **HuggingFace** | Various | Yes | Open-source models |
| **DeepAI** | Various | Yes | Simple API |

## Video Generation

| Provider | Type | API Key Required | Notes |
|----------|------|-----------------|-------|
| **HeyGen** | Avatar video | Yes | AI avatars, presentations |
| **Runway** | Gen-2, Gen-3 | Yes | Text/image to video |
| **Pika** | Text to video | Yes | Creative video generation |
| **Synthesia** | Avatar video | Yes | Enterprise presentations |
| **D-ID** | Talking head | Yes | Face animation |
| **Veed.io** | Video editing | Yes | AI-powered editing |
| **API.video** | Video hosting | Yes | Streaming + analytics |

## Messaging

| Connector | Protocol | API Key Required | Notes |
|-----------|----------|-----------------|-------|
| **Slack** | Socket Mode | Yes (Bot token) | Channels, DMs, threads |
| **Discord** | Gateway | Yes (Bot token) | Servers, channels, DMs |
| **Telegram** | Long polling | Yes (Bot token) | Groups, channels, DMs |
| **Microsoft Teams** | Bot Framework | Yes | Enterprise messaging |
| **WhatsApp (Twilio)** | REST API | Yes | Via Twilio |
| **WhatsApp (Meta)** | Cloud API | Yes | Direct Meta API |
| **Matrix** | Client-Server | Yes | Decentralized |
| **Facebook Messenger** | Send API | Yes | Pages integration |
| **Instagram** | Messaging API | Yes | Business accounts |
| **LINE** | Messaging API | Yes | Popular in Asia |
| **Viber** | REST API | Yes | Chatbots |
| **Signal** | signal-cli | No | Privacy-focused |
| **Twilio SMS** | REST API | Yes | SMS messaging |
| **Vonage** | REST API | Yes | SMS + voice |
| **MessageBird** | REST API | Yes | Omnichannel |

## Social Platforms

| Platform | Features | API Key Required |
|----------|----------|-----------------|
| **YouTube** | Upload, manage, analytics | Yes (OAuth) |
| **X / Twitter** | Post, reply, search | Yes (OAuth) |
| **Reddit** | Post, comment, search | Yes (OAuth) |
| **TikTok** | Upload, analytics | Yes (OAuth) |
| **LinkedIn** | Post, share, analytics | Yes (OAuth) |

## Automation

| Platform | Type | API Key Required |
|----------|------|-----------------|
| **n8n** | Self-hosted workflow | Yes (instance URL) |
| **Zapier** | Cloud workflow | Yes |
| **Make (Integromat)** | Cloud workflow | Yes |
| **Pipedream** | Developer workflow | Yes |
| **Workato** | Enterprise automation | Yes |

## Storage

| Platform | Features | API Key Required |
|----------|----------|-----------------|
| **Dropbox** | File sync, sharing | Yes (OAuth) |
| **OneDrive** | File sync, sharing | Yes (OAuth) |
| **SharePoint** | Document management | Yes (OAuth) |
| **Bitbucket** | Git hosting | Yes |

## Dev Tools

Built-in integrations for development workflows:

| Tool | Features |
|------|----------|
| **Git** | Commit, diff, branch, savepoints |
| **GitHub** | Issues, PRs, Actions, releases |
| **GitLab** | Issues, MRs, CI/CD |
| **Docker** | Container management, sandbox |
| **tree-sitter** | Code parsing, AST analysis |
| **pytest** | Test discovery, execution |
| **Ruff** | Linting, formatting |
| **Jira** | Issue tracking |
| **Linear** | Issue tracking |
| **Notion** | Documentation, wikis |

## Installing Integration Dependencies

```bash
# All integrations
pip install orion-agent[all]

# Specific groups
pip install orion-agent[voice]
pip install orion-agent[image]
pip install orion-agent[messaging]
```

## Adding New Integrations

Orion's integration system is extensible. Each category follows an abstract base class pattern:

1. Create a new provider class implementing the category ABC
2. Register it in the category's router
3. Add configuration to settings
4. Add tests

See [Contributing](../CONTRIBUTING.md) for details.

---

**Next:** [Configuration](CONFIGURATION.md) | [Deployment](DEPLOYMENT.md)
