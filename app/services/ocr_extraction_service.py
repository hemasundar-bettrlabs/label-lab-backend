import os
import io
import json
from google.genai import types
from dotenv import load_dotenv

from app.models.schemas import ClaimsExtractionResult
from app.services.image_processor import decode_image_from_base64
from app.services.llm_service import llm_service

load_dotenv()

# Use individual model config if exists, fallback to Analysis Model
OCR_EXTRACTION_MODEL = os.getenv("OCR_EXTRACTION_MODEL")

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'prompts')

OCR_PROMPT_PATH = os.path.join(PROMPTS_DIR, 'OCRPrompt.md')

with open(OCR_PROMPT_PATH, 'r', encoding='utf-8') as f:
    OCR_PROMPT = f.read()

def load_extraction_schema() -> dict:
    schema_path = os.path.join(os.path.dirname(__file__), '..', 'schemas', 'claims_input.json')
    try:
        with open(schema_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Schema not found at {schema_path}")
        return {}

def clean_json_response(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

async def extract_raw_ocr_text(base64_image: str) -> str:
    """Phase 1: Simple OCR — dump all visible text from the image."""
    try:
        from app.utils.logger import pipeline_logger
        
        img = decode_image_from_base64(base64_image)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG')
        img_bytes = img_byte_arr.getvalue()

        response = await llm_service.generate_content_async(
            model_name=OCR_EXTRACTION_MODEL or os.getenv("OCR_EXTRACTION_MODEL"),
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                "Extract ALL text visible on this food label exactly as printed. Preserve line breaks, table structure, and order. Do not interpret."
            ],
            response_mime_type="text/plain"
        )
        
        full_text = response.text

        pipeline_logger.json_dump("RAW OCR TEXT", full_text)
        
        return full_text

    except Exception as e:
        from app.utils.logger import pipeline_logger
        pipeline_logger.error("OCR Phase 1", f"Failed: {e}")
        return ""

async def extract_label_data(base64_image: str) -> ClaimsExtractionResult:
    """Phase 2: Structured extraction using Image + OCR text as dual input."""
    try:
        from app.utils.logger import pipeline_logger
        pipeline_logger.info("OCR Phase 2", "Starting structured JSON extraction...")
        
        # Step 1: Get raw text
        raw_text = await extract_raw_ocr_text(base64_image)
        
        schema = load_extraction_schema()
        img = decode_image_from_base64(base64_image)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG')
        img_bytes = img_byte_arr.getvalue()
        
        prompt = f"""
## RAW OCR TEXT (Ground Truth)
The following text was extracted verbatim from the label image via OCR. 
Use this as the authoritative source. Map it into the JSON schema.
Do NOT add any nutrition values, ingredients, or claims that do not appear in this text.

---
{raw_text}
---

Now, using both the image and the OCR text above, extract structured data per the schema.
"""
        
        response = await llm_service.generate_content_async(
            model_name=OCR_EXTRACTION_MODEL or os.getenv("OCR_EXTRACTION_MODEL"),

            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                prompt
            ],
            system_instruction=OCR_PROMPT,
            response_mime_type="application/json",
            response_schema=schema
        )
        
        result_json = json.loads(clean_json_response(response.text))
        pipeline_logger.info("OCR", "Phase 2 structured JSON extracted successfully.")
        return ClaimsExtractionResult(**result_json)
        
    except Exception as e:
        from app.utils.logger import pipeline_logger
        pipeline_logger.error("OCR Phase 2", f"Failed: {e}")
        raise ValueError(f"Failed to extract label data: {str(e)}")
