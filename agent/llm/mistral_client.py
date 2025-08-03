"""
Mistral AI client implementation for the agent system.

Supports Mistral's latest models including Codestral for coding tasks,
Mistral Large for complex reasoning, and Mistral Small for cost-effective operations.
"""

import os
import json
import asyncio
from typing import List, Optional, Dict, Any
import httpx
from dataclasses import dataclass

from .common import AsyncLLM, Message, Completion, Tool, TextRaw, ToolUse, ContentBlock
from log import get_structured_logger

logger = get_structured_logger(__name__)


@dataclass
class MistralConfig:
    """Configuration for Mistral API client."""
    api_key: str
    base_url: str = "https://api.mistral.ai/v1"
    timeout: int = 60
    max_retries: int = 3


class MistralClient(AsyncLLM):
    """Async Mistral AI client implementing the AsyncLLM protocol."""
    
    def __init__(self, config: MistralConfig):
        self.config = config
        self.client = httpx.AsyncClient(
            base_url=config.base_url,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=config.timeout,
        )
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    def _convert_messages_to_mistral(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert internal messages to Mistral API format."""
        mistral_messages = []
        
        for msg in messages:
            content_parts = []
            
            for block in msg.content:
                if isinstance(block, TextRaw):
                    content_parts.append(block.text)
                elif isinstance(block, ToolUse):
                    # Mistral uses function calling format
                    content_parts.append(f"[TOOL_USE: {block.name}({json.dumps(block.input)})]")
                # Add other content block types as needed
            
            mistral_messages.append({
                "role": msg.role,
                "content": " ".join(content_parts) if content_parts else ""
            })
        
        return mistral_messages
    
    def _convert_tools_to_mistral(self, tools: Optional[List[Tool]]) -> Optional[List[Dict[str, Any]]]:
        """Convert tools to Mistral function calling format."""
        if not tools:
            return None
        
        mistral_tools = []
        for tool in tools:
            mistral_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool["input_schema"]
                }
            })
        
        return mistral_tools
    
    def _parse_mistral_response(self, response_data: Dict[str, Any]) -> Completion:
        """Parse Mistral API response into internal Completion format."""
        choice = response_data["choices"][0]
        message = choice["message"]
        usage = response_data.get("usage", {})
        
        # Parse content
        content_blocks: List[ContentBlock] = []
        content_text = message.get("content", "")
        
        if content_text:
            content_blocks.append(TextRaw(text=content_text))
        
        # Handle function calls if present
        if "function_call" in message:
            func_call = message["function_call"]
            content_blocks.append(ToolUse(
                name=func_call["name"],
                input=json.loads(func_call["arguments"]),
                id=f"mistral_{func_call['name']}"
            ))
        
        # Determine stop reason
        finish_reason = choice.get("finish_reason", "unknown")
        stop_reason_map = {
            "stop": "end_turn",
            "length": "max_tokens",
            "function_call": "tool_use",
            "content_filter": "stop_sequence"
        }
        stop_reason = stop_reason_map.get(finish_reason, "unknown")
        
        return Completion(
            role="assistant",
            content=content_blocks,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            stop_reason=stop_reason
        )
    
    async def completion(
        self,
        messages: List[Message],
        max_tokens: int,
        model: Optional[str] = None,
        temperature: float = 1.0,
        tools: Optional[List[Tool]] = None,
        tool_choice: Optional[str] = None,
        system_prompt: Optional[str] = None,
        *args,
        **kwargs,
    ) -> Completion:
        """Generate completion using Mistral API."""
        
        # Default to Codestral for coding tasks
        if model is None:
            model = "codestral-latest"
        
        # Convert messages
        mistral_messages = self._convert_messages_to_mistral(messages)
        
        # Add system prompt if provided
        if system_prompt:
            mistral_messages.insert(0, {
                "role": "system",
                "content": system_prompt
            })
        
        # Prepare request payload
        payload = {
            "model": model,
            "messages": mistral_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        
        # Add tools if provided
        if tools:
            payload["tools"] = self._convert_tools_to_mistral(tools)
            if tool_choice:
                payload["tool_choice"] = tool_choice
        
        # Make API request with retries
        last_exception = None
        for attempt in range(self.config.max_retries):
            try:
                logger.debug("Making Mistral API request", 
                           model=model, attempt=attempt + 1, 
                           message_count=len(mistral_messages))
                
                response = await self.client.post("/chat/completions", json=payload)
                response.raise_for_status()
                
                response_data = response.json()
                completion = self._parse_mistral_response(response_data)
                
                logger.info("Mistral completion successful",
                          model=model,
                          input_tokens=completion.input_tokens,
                          output_tokens=completion.output_tokens,
                          stop_reason=completion.stop_reason)
                
                return completion
                
            except httpx.HTTPStatusError as e:
                last_exception = e
                if e.response.status_code == 429:  # Rate limit
                    wait_time = 2 ** attempt
                    logger.warning(f"Rate limited, waiting {wait_time}s", 
                                 attempt=attempt + 1)
                    await asyncio.sleep(wait_time)
                    continue
                elif e.response.status_code >= 500:  # Server error
                    wait_time = 2 ** attempt
                    logger.warning(f"Server error, retrying in {wait_time}s", 
                                 status_code=e.response.status_code,
                                 attempt=attempt + 1)
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    # Client error, don't retry
                    logger.error("Mistral API client error", 
                               status_code=e.response.status_code,
                               response=e.response.text)
                    raise
                    
            except Exception as e:
                last_exception = e
                if attempt < self.config.max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Request failed, retrying in {wait_time}s", 
                                 error=str(e), attempt=attempt + 1)
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    break
        
        # All retries failed
        logger.error("All Mistral API retries failed", error=str(last_exception))
        raise last_exception


def get_mistral_client(
    api_key: Optional[str] = None,
    model: Optional[str] = None
) -> MistralClient:
    """Get configured Mistral client."""
    
    if api_key is None:
        api_key = os.getenv("MISTRAL_API_KEY")
        if not api_key:
            raise ValueError("MISTRAL_API_KEY environment variable is required")
    
    config = MistralConfig(
        api_key=api_key,
        base_url=os.getenv("MISTRAL_BASE_URL", "https://api.mistral.ai/v1"),
        timeout=int(os.getenv("MISTRAL_TIMEOUT", "60")),
        max_retries=int(os.getenv("MISTRAL_MAX_RETRIES", "3"))
    )
    
    return MistralClient(config)


# Available Mistral models
MISTRAL_MODELS = {
    "mistral-large": "mistral-large-2411",      # Premium reasoning
    "codestral": "codestral-latest",            # Code generation
    "mistral-small": "mistral-small-2409",      # Cost-effective
    "ministral-8b": "ministral-8b-2410",       # Ultra efficient
    "ministral-3b": "ministral-3b-2410",       # Edge deployment
    "pixtral": "pixtral-large-2411",           # Vision tasks
}


def get_mistral_model_name(model_key: str) -> str:
    """Get actual Mistral model name from key."""
    return MISTRAL_MODELS.get(model_key, model_key)
