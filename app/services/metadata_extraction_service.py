import os
import io
import json
from google.genai import types
from app.models.schemas import ExtractedMetadata
from app.services.image_processor import decode_image_from_base64
from app.services.llm_service import llm_service
from app.utils.logger import pipeline_logger
from dotenv import load_dotenv
import asyncio
import traceback

load_dotenv()

METADATA_MODEL = os.getenv("METADATA_EXTRACTION_MODEL")

METADATA_SYSTEM_INSTRUCTION = """
You are an expert food label reader. Extract only the key identity fields
from this food product label. Be precise and literal — extract exactly what
is printed. If a field is not present on the label, return an empty string "".
Return strictly JSON following this exact structure with realistic examples:
{
    "brandName": "Example Brand",
    "productName": "Example Product Name",
    "fssaiCategory": "Instant Noodles",
    "licenseNo": "10014011000123",
    "sampleType": "Physical Pack",
    "pdpArea": "",
    "nablReportId": "",
    "claimsBasis": ""
}
"""

def clean_json_response(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

async def extract_brand_metadata(base64_image: str) -> ExtractedMetadata:
    """
    Always-run step: extract brand identity metadata from the label.
    Uses the fast validation model. Guaranteed to return a valid ExtractedMetadata.
    """
    try:
        img = decode_image_from_base64(base64_image)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG')
        img_bytes = img_byte_arr.getvalue()

        def run_llm():
            return llm_service.generate_content(
                model_name=METADATA_MODEL,
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                    "Look at this food product label image carefully. Extract these fields by reading the actual text printed on the label: brandName, productName, fssaiCategory, licenseNo. Return JSON only."
                ],
                system_instruction=METADATA_SYSTEM_INSTRUCTION,
                response_mime_type="application/json"
            )

        response = await asyncio.to_thread(run_llm)

        result_text = clean_json_response(response.text)
        pipeline_logger.info("Metadata", f"Metadata LLM raw output: {result_text}")
        result = json.loads(result_text)
        
        # Merge with defaults to prevent Pydantic missing-field crashes
        defaults = {
            "brandName": "",
            "productName": "",
            "fssaiCategory": "",
            "licenseNo": "",
            "sampleType": "Physical Pack",
            "pdpArea": "",
            "nablReportId": "",
            "claimsBasis": "Verified against FSSAI standards."
        }
        
        for k, v in result.items():
            if v is not None:
                defaults[k] = v

        return ExtractedMetadata(**defaults)

    except Exception as e:
        pipeline_logger.error("Metadata", f"Metadata extraction failed: {str(e)}")
        traceback.print_exc()
        # Guaranteed non-crashing fallback
        return ExtractedMetadata(
            brandName="", productName="",
            fssaiCategory="", licenseNo=""
        )
