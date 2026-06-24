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


class LLMService:
    """
    Unified LLM service supporting both Gemini API and Vertex AI backends.
    Backend selection is controlled by IS_VERTEX environment variable.
    Uses google-genai SDK for both backends with ADC for Vertex AI.
    """
    _instance = None
    _client = None
    _use_vertex = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LLMService, cls).__new__(cls)
            cls._initialize_client()
        return cls._instance

    @classmethod
    def _initialize_client(cls):
        """Initialize the appropriate LLM client based on IS_VERTEX setting."""
        cls._use_vertex = os.getenv("IS_VERTEX", "false").lower() == "true"
        
        if cls._use_vertex:
            cls._initialize_vertex_ai()
        else:
            cls._initialize_gemini_api()

    @classmethod
    def _initialize_vertex_ai(cls):
        """Initialize Vertex AI client via google-genai SDK using ADC."""
        try:
            gcp_project_id = os.getenv("GCP_PROJECT_ID")
            
            if not gcp_project_id:
                raise ValueError("GCP_PROJECT_ID is not set for Vertex AI initialization")
            
            location = os.getenv("GCP_LOCATION", "us-central1")
            
            # Create client with Vertex AI endpoint using Application Default Credentials
            cls._client = genai.Client(
                api_key="",  # Empty key triggers ADC (Application Default Credentials)
                vertexai=True,
                project=gcp_project_id,
                location=location
            )
            logger.info(f"LLMService initialized with Vertex AI (project: {gcp_project_id}, location: {location})")
        except Exception as e:
            logger.error(f"Failed to initialize Vertex AI: {e}")
            raise e

    @classmethod
    def _initialize_gemini_api(cls):
        """Initialize Gemini API client via google-genai SDK using API key."""
        try:
            gemini_api_key = os.getenv("GEMINI_API_KEY")
            
            if not gemini_api_key:
                raise ValueError("GEMINI_API_KEY is not set for Gemini API initialization")
            
            cls._client = genai.Client(api_key=gemini_api_key)
            logger.info("LLMService initialized with Gemini API key")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini API: {e}")
            raise e

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
        Centrally managed LLM generation through either Gemini API or Vertex AI.
        Both backends use the google-genai SDK.
        
        Args:
            model_name: The model identifier
            contents: Input content (string or list)
            system_instruction: System prompt
            temperature: Temperature setting (0.0-2.0)
            response_mime_type: Expected response format
            response_schema: JSON schema for structured output
            
        Returns:
            Response object from google-genai SDK
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
            logger.error(f"Error in LLMService.generate_content: {e}")
            raise e

    async def generate_content_async(self, *args, **kwargs):
        """Asynchronous wrapper to prevent blocking the FastAPI ASGI event loop."""
        import asyncio
        return await asyncio.to_thread(self.generate_content, *args, **kwargs)


# Create a global instance for reuse
llm_service = LLMService()
