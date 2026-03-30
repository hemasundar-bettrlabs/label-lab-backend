import os
from google import genai
from google.genai import types
from dotenv import load_dotenv
from typing import Optional, Any, Union, Dict, List

load_dotenv()

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
        gcp_project_id = os.getenv("GCP_PROJECT_ID")
        gcp_location = os.getenv("GCP_LOCATION", "us-central1")
        
        if not gcp_project_id:
            print("WARNING: GCP_PROJECT_ID is not set. Vertex AI initialization may fail.")
        
        cls._client = genai.Client(vertexai=True, project=gcp_project_id, location=gcp_location)
        print(f"INFO: VertexLLMService initialized for project {gcp_project_id} in {gcp_location}")

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
            print(f"ERROR in VertexLLMService.generate_content: {e}")
            raise e

    async def generate_content_async(self, *args, **kwargs):
        """Asynchronous wrapper to prevent blocking the FastAPI ASGI event loop."""
        import asyncio
        return await asyncio.to_thread(self.generate_content, *args, **kwargs)

# Create a global instance for reuse
llm_service = VertexLLMService()
