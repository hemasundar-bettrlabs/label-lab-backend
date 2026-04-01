from google.genai import types
import os
import json
from typing import Optional, Tuple, AsyncGenerator
from app.models.schemas import (
    LabelValidationResult, AnalysisResult,
    AuditOptions
)
# from app.store.regulatory_store import get_ai_prompt_context
from app.services.image_processor import add_grid_overlay, decode_image_from_base64
from app.services.claims_engine import run_claims_pipeline
from app.services.nutrition_engine import run_nutrition_pipeline
from app.services.labtest_engine import run_lab_test_pipeline
from app.services.ocr_extraction_service import extract_label_data
from app.services.llm_service import llm_service
from app.services.metadata_extraction_service import extract_brand_metadata
from app.services.product_category_engine import ProductCategoryPredictor
from dotenv import load_dotenv
import io
import asyncio

load_dotenv()

# Models
VALIDATION_MODEL = os.getenv("VALIDATION_MODEL")
ANALYSIS_MODEL = os.getenv("ANALYSIS_MODEL")

# System Instructions
VALIDATION_SYSTEM_INSTRUCTION = """
You are an expert Food Regulatory Compliance Auditor.
Your task is to identify if the uploading image is a valid food product label or artwork.
You must be strict. Random objects, blurry photos, or non-food items should returned as isLabel: false.
If it is a food label, detect the potential category.
Return strictly JSON.
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


def resolve_category_context(options: AuditOptions) -> Tuple[str, Optional[str], Optional[str], str]:
    # Priority 1: validation auto-detection
    detected_type = options.detectedCategoryType
    detected_product = options.detectedSpecialCategory
    detected_general = options.detectedCategoryCode
    if detected_type in {'special', 'general'}:
        return detected_type, detected_product, detected_general, 'validation_detected'
    if detected_product:
        return 'special', detected_product, None, 'validation_detected_inferred_special'
    if detected_general:
        return 'general', None, detected_general, 'validation_detected_inferred_general'

    # Priority 2: deterministic default path
    return 'general', None, None, 'default_general'

async def validate_is_label(base64_image: str) -> LabelValidationResult:
    try:
        img = decode_image_from_base64(base64_image)
        
        # Convert to bytes
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG')
        img_bytes = img_byte_arr.getvalue()
        
        prompt = """
        Analyze this image.
        1. Is this a food product label or packaging artwork? (Boolean)
        2. Identify the product category (e.g., Health Supplement, Nutraceutical, General Food).
        3. Confidence score (0-100).
        4. Reason for your decision.
        
        Output JSON:
        {
            "isLabel": boolean,
            "labelType": string,
            "detectedCategoryType": "general" | "special",
            "detectedSpecialCategory": "HS" | "Nutra" | "FSDU" | "FSMP" | "Pre-Pro" | null,
            "confidence": number,
            "reason": string
        }
        """
        
        response = await llm_service.generate_content_async(
            model_name=VALIDATION_MODEL,
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                prompt
            ],
            system_instruction=VALIDATION_SYSTEM_INSTRUCTION,
            response_mime_type="application/json"
        )
        
        result = json.loads(clean_json_response(response.text))
        return LabelValidationResult(**result)
        
    except Exception as e:
        from app.utils.logger import pipeline_logger
        pipeline_logger.error("Validation", f"Validation Error: {str(e)}")
        return LabelValidationResult(
            isLabel=False, 
            confidence=0, 
            reason=f"Error validating image: {str(e)}"
        )

async def run_analysis_job(job_id: str):
    from app.stores.job_store import job_store
    job = await job_store.get_job(job_id)
    if not job:
        return
        
    await job_store.update_status(job_id, "running")
    base64_image = job.image_base64
    options = job.options

    try:
        from app.utils.logger import pipeline_logger
        categories = [c.get('value', c) if isinstance(c, dict) else c for c in options.get('categories', [])]
        core_categories = [c for c in categories if c not in {'Claims', 'Nutrition'}]

        # Determine steps dynamically
        steps = ["Validating image context"]
        if 'Claims' in categories or 'Nutrition' in categories:
            steps.append("Extracting OCR data")
        steps.append("Extracting brand metadata")
        if core_categories:
            steps.append("Running regulatory checks")
        if 'Claims' in categories or 'Nutrition' in categories:
            steps.append("Validating product category")
        if 'Claims' in categories:
            steps.append("Substantiating claims")
        if 'Nutrition' in categories:
            steps.append("Verifying nutrition limits")
        steps.append("Generating lab test suggestions")
        steps.append("Finalizing report")

        total_steps = len(steps)
        current_step = 0

        async def advance_step(stage_id):
            nonlocal current_step
            stage_name = steps[current_step]
            current_step += 1
            pipeline_logger.stage(current_step, total_steps, f"{stage_name}...")
            await job_store.add_event(job_id, "stage", {"stage": f"{stage_name}...", "step": current_step, "total": total_steps})

        await advance_step("validate")
        
        # We need to construct an AuditOptions object for resolve_category_context since it expects an object with attributes
        from app.models.schemas import AuditOptions as AuditOptionsSchema
        options_obj = AuditOptionsSchema(**options)
        
        resolved_category_type, resolved_product_category, resolved_general_category_code, category_source = resolve_category_context(options_obj)
        pipeline_logger.info("Context", f"source={category_source}, type={resolved_category_type}, code={resolved_general_category_code}")

        # Prompt Generation
        processed_image_b64 = add_grid_overlay(base64_image)
        PROMPTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'prompts')

        GENERAL_PROMPT_PATH = os.path.join(PROMPTS_DIR, 'GeneralPrompt.md')
        with open(GENERAL_PROMPT_PATH, 'r', encoding='utf-8') as f:
            GENERAL_PROMPT = f.read()
        base_prompt = GENERAL_PROMPT
        
        final_prompt = f"""
        {base_prompt}
        
        # INSTRUCTIONS
        Analyze the provided food label image against the regulatory requirements above.
        The image has a red grid overlay for spatial reference. 
        
        For each check, determine:
        1. Compliance Status (Complies, Fail, Action)
        2. Location of the element using a BOUNDING BOX (ymin, xmin, ymax, xmax) on a 0-1000 scale.
        3. Specific feedback/observation
        """

        img = decode_image_from_base64(processed_image_b64)
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG')
        img_bytes = img_byte_arr.getvalue()

        def run_main_analysis():
            return llm_service.generate_content(
                model_name=ANALYSIS_MODEL,
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                    final_prompt
                ],
                response_mime_type="application/json",
                response_schema={
                    "type": "object",
                    "properties": {
                        "overallScore": {"type": "number"},
                        "status": {"type": "string", "enum": ["Compliant", "Non-Compliant", "Needs Review"]},
                        "summary": {"type": "string"},
                        "checks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "category": {"type": "string"},
                                    "name": {"type": "string"},
                                    "description": {"type": "string"},
                                    "status": {"type": "string", "enum": ["Complies", "Fail", "Action"]},
                                    "feedback": {"type": "string"},
                                    "boundingBox": {
                                        "type": "object",
                                        "properties": {"ymin": {"type": "number"}, "xmin": {"type": "number"}, "ymax": {"type": "number"}, "xmax": {"type": "number"}},
                                        "required": ["ymin", "xmin", "ymax", "xmax"]
                                    }
                                },
                                "required": ["id", "category", "name", "status", "feedback", "boundingBox"]
                            }
                        }
                    },
                    "required": ["overallScore", "status", "summary", "checks"]
                }
            )

        # Execution pipeline...
        extraction = None
        if 'Claims' in categories or 'Nutrition' in categories:
            await advance_step("ocr")
            pipeline_logger.info("OCR", "Initiating OCR Extraction Service")
            try:
                extraction = await extract_label_data(base64_image)
            except Exception as e:
                pipeline_logger.error("OCR", f"Failed: {e}")

        # Keep execution ordered for real-time progress updates instead of gather.
        
        # Step: Metadata
        await advance_step("metadata")
        pipeline_logger.info("Metadata", "Extracting Brand Metadata")
        extracted_metadata = await extract_brand_metadata(base64_image)
        pipeline_logger.json_dump("EXTRACTED METADATA", extracted_metadata.model_dump())

        result_json = {"overallScore": 100, "status": "Compliant", "summary": "No specific core checks.", "checks": []}
        
        # Category Prediction (after metadata and OCR extraction, before claims/nutrition)
        # Only predict if category is missing from BOTH OCR JSON and metadata
        category_validation_check = None  # Initialize here, populate if prediction succeeds
        ocr_category = extraction.product_category if extraction else None
        metadata_category = extracted_metadata.fssaiCategory if extracted_metadata else None
        
        if ('Claims' in categories or 'Nutrition' in categories) and extraction and not ocr_category and not metadata_category:
            await advance_step("category")
            pipeline_logger.info("Category", "Predicting Product Category")
            try:
                predictor = ProductCategoryPredictor()
                # Convert extracted ingredients list to comma-separated string
                ingredients_str = ", ".join(extraction.ingredients) if extraction.ingredients else ""
                prediction = await predictor.predict_category(
                    product_name=extracted_metadata.productName or "Unknown",
                    brand_name=extracted_metadata.brandName,
                    ingredients=ingredients_str,
                    ocr_category=ocr_category,
                    metadata_category=metadata_category,
                    extraction=extraction,  # Pass extraction for OCR JSON injection
                )
                if prediction:
                    # OCR JSON already updated by predict_category() method
                    # Also update metadata for consistency
                    extracted_metadata.fssaiCategory = extraction.product_category
                    pipeline_logger.info("Category", f"Predicted: {prediction.suggested_category} (confidence: {prediction.confidence_score:.2f})")
                    # Create check dict from prediction with status "Action" (needs review)
                    category_validation_check = {
                        "id": "CAT-001",
                        "category": "Category",
                        "name": "Product Category Prediction",
                        "description": prediction.suggested_category,
                        "status": "Action",
                        "feedback": prediction.reasoning,
                        "boundingBox": {"ymin": 0, "xmin": 0, "ymax": 100, "xmax": 100},
                        "location": {"x": 50, "y": 50}
                    }
            except Exception as e:
                pipeline_logger.error("Category", f"Prediction failed: {e}")
        
        
        if core_categories:
            await advance_step("regulatory")
            pipeline_logger.info("Core", "Running Regulatory Analysis")
            response = await asyncio.to_thread(run_main_analysis)
            result_json = json.loads(clean_json_response(response.text))

        claims_result = None
        if 'Claims' in categories and extraction:
            await advance_step("claims")
            pipeline_logger.info("Claims", "Running Claims Subsystem")
            claims_result = await run_claims_pipeline(extraction)

        nutrition_checks = []
        if 'Nutrition' in categories and extraction:
            await advance_step("nutrition")
            pipeline_logger.info("Nutrition", "Running Nutrition Subsystem")
            nutrition_checks = await run_nutrition_pipeline(extraction)

        await advance_step("labTests")
        pipeline_logger.info("Lab Tests", "Running Lab Test Pipeline")
        lab_tests = await run_lab_test_pipeline(
            checks=result_json.get("checks", []),
            claims_result=claims_result,
            nutrition_checks=nutrition_checks,
            extraction=extraction,
        )

        await advance_step("finalize")
        
        # Deduplicate IDs
        if "checks" in result_json:
            seen_ids = set()
            for check in result_json["checks"]:
                base_id = check.get("id", "UNKNOWN")
                if base_id in seen_ids:
                    counter = 2
                    while f"{base_id}-{counter}" in seen_ids: counter += 1
                    check["id"] = f"{base_id}-{counter}"
                seen_ids.add(check["id"])

                if "boundingBox" in check:
                    bbox = check["boundingBox"]
                    cx = (bbox.get("xmin", 0) + bbox.get("xmax", 0)) / 2
                    cy = (bbox.get("ymin", 0) + bbox.get("ymax", 0)) / 2
                    check["location"] = {"x": round(cx / 10, 2), "y": round(cy / 10, 2)}
                else:
                    check["location"] = {"x": 50, "y": 50}

        if nutrition_checks:
            result_json.setdefault("checks", []).extend(nutrition_checks)

        # Add category validation result if available
        if category_validation_check:
            result_json.setdefault("checks", []).insert(0, category_validation_check)

        if claims_result and ("checks" in result_json):
            for i, verdict in enumerate(claims_result.verdicts):
                claim_name = verdict.claim_text if len(verdict.claim_text) <= 60 else verdict.claim_text[:57] + "..."
                result_json["checks"].append({
                    "id": f"CLM-{(i+1):03d}", "category": verdict.tag, "name": claim_name,
                    "description": verdict.claim_text, "status": verdict.status, "feedback": verdict.reasoning,
                    "clauseRef": verdict.reference, "boundingBox": {"ymin": 0, "xmin": 0, "ymax": 100, "xmax": 100},
                    "location": {"x": 50, "y": 50}
                })

        if lab_tests:
            result_json["suggestedLabTests"] = [test.model_dump() for test in lab_tests]

        result_json["extractedMetadata"] = extracted_metadata.model_dump()
        from app.models.schemas import AnalysisResult
        final_res = AnalysisResult(**result_json)
        pipeline_logger.success(f"Final Score: {final_res.overallScore}%")
        
        await job_store.add_event(job_id, "result", final_res.model_dump())
        await job_store.set_result(job_id, final_res.model_dump())

    except Exception as e:
        from app.utils.logger import pipeline_logger
        pipeline_logger.error("System", f"Analysis failed: {e}")
        await job_store.add_event(job_id, "error", {"message": str(e)})
        await job_store.set_error(job_id, str(e))
    finally:
        await job_store.add_event(job_id, "done", {"status": "finished"})
