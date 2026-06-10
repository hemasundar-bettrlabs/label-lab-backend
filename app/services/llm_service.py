import os
import logging
import warnings
from google import genai
from google.genai import types
from dotenv import load_dotenv
from typing import Optional, Any, Union, Dict, List

# Gemini 2.5 models always attach a `thought_signature` field to response parts
# even when thinking_budget=0. The SDK warns when it encounters these non-text
# parts while reading .text / .parsed. The text content is still returned
# correctly, so suppress the noisy but harmless warning.
warnings.filterwarnings(
    "ignore",
    message="there are non-text parts in the response",
    category=UserWarning,
)

load_dotenv()

logger = logging.getLogger(__name__)

class VertexLLMService:
    _instance = None
    _client = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VertexLLMService, cls).__new__(cls)
            cls._initialize_client()
        return cls._instance

    @classmethod
    def _initialize_client(cls):
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        
        if not gemini_api_key:
            logger.warning("GEMINI_API_KEY is not set. Gemini API initialization may fail.")
        
        cls._client = genai.Client(api_key=gemini_api_key)
        logger.info("VertexLLMService initialized with Gemini API key")

    def generate_content(
        self,
        model_name: str,
        contents: Union[str, List[Union[str, Any]]],
        system_instruction: Optional[str] = None,
        temperature: float = 0.0,
        response_mime_type: str = "text/plain",
        response_schema: Optional[Dict[str, Any]] = None
    ):
        """
        Centrally managed LLM generation through Vertex AI.
        """
        try:
            config = types.GenerateContentConfig(
                temperature=temperature,
                system_instruction=system_instruction,
                response_mime_type=response_mime_type,
                response_schema=response_schema,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=0
                )
            )
            
            # Ensure contents is a list for the SDK
            if isinstance(contents, str):
                request_contents = [contents]
            else:
                request_contents = contents

            response = self._client.models.generate_content(
                model=model_name,
                contents=request_contents,
                config=config
            )
            return response

        except Exception as e:
            logger.error(f"Error in VertexLLMService.generate_content: {e}")
            raise e

    async def generate_content_async(self, *args, **kwargs):
        """Asynchronous wrapper to prevent blocking the FastAPI ASGI event loop."""
        import asyncio
        return await asyncio.to_thread(self.generate_content, *args, **kwargs)

# Create a global instance for reuse
llm_service = VertexLLMService()
