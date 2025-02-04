# Local Model Inference

The Naptha Node supports local inference using either VLLM or Ollama, along with LiteLLM as a fully OpenAI-compatible API server. 

1. Standard API Interface
2. Standard Tool Calling for a Variety of Models
3. Structured Outputs for a Variety of Models
4. Optimized Throughput for Multi-Agent Simulations

## Standard API Interface

The Naptha Node runs a [LiteLLM](https://docs.litellm.ai/docs/) proxy server to (i) provide an OpenAI-compatible proxy that can be connected to a wide variety of LLM backends, including non-OpenAI-compatible models (this means you can do neat things like call Anthropic models in an OpenAI-compatible way), and (ii) to aggregate our vLLM instances into a single endpoint. 

## Standard Tool Calling for a Variety of Models

Not many open source models support tool calling out of the box. vLLM has "native" support for _some_ SLM  models' tool-calling capabilities, but not all. The Naptha Node provides:

- OpenAI-compatible tool calling for supported models; where the model's innate tool calling capability is mapped onto OpenAI's standard for non-streaming and/or streaming requests. 
- Additional ad-hoc tool parser plugins.

Note that _only_ **non-streaming** tool extraction is currently supported. 

Please refer to the [vLLM docs](https://docs.vllm.ai/en/latest/usage/tool_calling.html) for a list of models with officially-supported SLM tool parsers that include both non-streaming and streaming tool extraction).

## Structured Outputs for a Variety of Models

The Naptha Node supports structured outputs using OpenAI-compatible "JSON mode" structured generation using guided decoding, and non-OpenAI-spec extended guided generation capabilities (e.g. regex-based, "choice"-based etc.). 

## Optimized Throughput for Multi-Agent Simulations

The configurations in the Naptha Node have been optimized for throughput for specific multi-agent simulations up to 50k agents. Since use cases vary, you may need to modify the configurations based on the performance characteristics that _you_ care about (TTFT, TPOT, ITL, E2EL, total throughput, etc.)

## Notes on Tool Calling with Specific Models

- Mistral 7B only reliably generates tool-calls at `0` and near-`0` temperature configurations
- Not all small tool-calling models are created equal. Tool calling reliability can be quite good in some 7B models, and quite poor in other 7B models. Generally, the more recent that your model is, the better. 
- < 7B models, such as 3B models, will frequently struggle to generate even simple tool calls, and often even at near-`0` temperatures. You should not expect to be able to use 3B models for agentic purposes without using guided decoding/structured generation.
- Not all models support "parallel" tool calls, e.g. the Llama 3.x models
- Not all models support multi-turn conversations involving calls; some are designed as "action" models that receive a prompt and output a tool call (e.g. Hammer 7B) but do not support passing tool results back into the model.
- Most SLMs perform best at a "soft cap" of 4-5 tools, and definitely < 10. 
- SLMs frequently struggle with "recursive" or "nested" tool calls (distinct from **parallel** tool calls) due to not having seen examples in their training data. While larger models can handle these well, small models usually do not.
- Unlike cloud API models, SLMs can hallucinate tool calls.

Every SLM has its own limitations with tool calling. _It is important to pick a model that works well for you and your use-case._ Make sure to understand any system prompts or chat templates that are required, and to understand what the model's tool call-oriented training focused on, e.g. multi-turn agentic interactions vs. one-off calls. 

There is no such thing as a "one size fits all" tool calling SLM. That being said, some labs that we are partial to, because their tool-calling SLMs support a broad variety of a capabilities for most use-cases (multi-turn, agentic, and/or parallel tool calls) and are generally very reliable include:

- Alibaba Qwen (e.g. Qwen 2.5 7B Instruct)
- Nous Research (e.g. Hermes 3 Llama 3.1 8B)

## Notes on Chat templating

Most SLMs are _extremely_ sensitive to chat templates and tokenization issues when you are doing tool-calling, so make sure that if you are providing an unofficial one, it has one-to-one token parity with the official template. 

Many SLMs _also_ bake in a system prompt for tool-calling purposes when tools are enabled. This is necessary in many cases, but depending on your use-case (e.g. one-off tool calling vs. multi-turn agentic interactions) these may need to be modified, and in some cases this may have to be done in the chat template. 

If you are having issues with tool calling with your model, the chat template (and baked-in system prompt) is always a good place to start looking. Read your model's Hugging Face model card _carefully_ for discussion about tool use.

When tools are passed into your model's chat template, they are usually passed into the system prompt and rendered in a JSON format, pythonic format, or some other type of format (the model has to know about what tools are available somehow). For SLMs with limited context length e.g. 4k and 8k-context models, tools can consume a significant portion of this context if you give the model too many. 

## Further Resources

The following links are some good resources to learn more about tool calling in vLLM:

- [vLLM's Tool-calling documentation](https://docs.vllm.ai/en/latest/usage/tool_calling.html#quickstart) is the authoritative guide to officially supported tool-calling LLMs in vLLM, and provides documentation on how to write a tool parser plugin for your own model if it's not currently supported.
- [Berkeley Function-Calling Leaderboard](https://gorilla.cs.berkeley.edu/leaderboard.html) ranks top-performing tool-calling LLMs.
- [Kyle Mistele's talk on tool parsing in vLLM](https://www.youtube.com/watch?v=7_XPHw_wi-c&t=2s) dives into some of the complexities on OpenAI-compatible tool use in vLLM, particularly surrounding streaming. If you want to use tool streaming, or add a tool streaming parser, this may be a helpful resources.





