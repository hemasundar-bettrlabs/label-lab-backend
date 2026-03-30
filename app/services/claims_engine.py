import os
import json
from dotenv import load_dotenv

from app.models.schemas import (
    ClaimsExtractionResult,
    ClaimVerdict,
    ClaimsAnalysisResult
)

from app.stores.claims_store import (
    CLAIMS_VALIDATION_SYSTEM_PROMPT,
    build_claims_validation_prompt
)

from app.services.llm_service import llm_service

load_dotenv()

from app.services.ocr_extraction_service import clean_json_response
from app.utils.logger import pipeline_logger

# Use individual model config if exists, fallback to Analysis Model
CLAIMS_VALIDATION_MODEL = os.getenv("CLAIMS_VALIDATION_MODEL")


async def validate_claims(extraction_result: ClaimsExtractionResult) -> list[ClaimVerdict]:
    """Validate extracted claims against nutrition and ingredient data."""
    try:
        if not extraction_result.claims:
            return []

        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        # Convert extraction components to formatted strings
        nutrition_str = json.dumps([n.model_dump() for n in extraction_result.nutrition_table], indent=2)
        ingredients_str = ", ".join(extraction_result.ingredients)
        claims_str = json.dumps([c.model_dump() for c in extraction_result.claims], indent=2)
        nutritional_claims_str = open(os.path.join(root, "app", "data", "nutritional_claims.json")).read()

        prompt = build_claims_validation_prompt(nutrition_str, ingredients_str, claims_str, nutritional_claims_str)

        response = await llm_service.generate_content_async(
            model_name=CLAIMS_VALIDATION_MODEL,
            contents=[prompt],
            system_instruction=CLAIMS_VALIDATION_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim_text": { "type": "string" },
                        "tag": { 
                            "type": "string",
                            "enum": ["Nutritional Claim", "Health Claim", "Ingredient Claim"]
                        },
                        "status": {
                            "type": "string",
                            "enum": ["Complies", "Fail", "Action"]
                        },
                        "reasoning": { "type": "string" },
                        "reference": { "type": "string" }
                    },
                    "required": ["claim_text", "tag", "status", "reasoning", "reference"]
                }
            }
        )

        result_json = json.loads(clean_json_response(response.text))
        pipeline_logger.info("Claims", f"Claims Validation Result: {result_json}")
        return [ClaimVerdict(**v) for v in result_json]

    except Exception as e:
        pipeline_logger.error("Claims", f"Claims Validation Error: {e}")
        raise ValueError(f"Failed to validate claims: {str(e)}")


async def run_claims_pipeline(extraction: ClaimsExtractionResult) -> ClaimsAnalysisResult:
    """End-to-end claims analysis pipeline."""
    try:
        verdicts = await validate_claims(extraction)
        
        failed_count = sum(1 for v in verdicts if v.status == 'Fail')
        action_count = sum(1 for v in verdicts if v.status == 'Action')
        pass_count = sum(1 for v in verdicts if v.status == 'Complies')
        
        summary = f"Analyzed {len(verdicts)} claim(s). {pass_count} passed, {failed_count} failed, {action_count} need review."

        pipeline_logger.info("Claims", f"Claims Analysis Result: {summary}")
        
        return ClaimsAnalysisResult(
            extraction=extraction,
            verdicts=verdicts,
            summary=summary
        )
    except Exception as e:
        pipeline_logger.error("Claims", f"Claims Pipeline Error: {e}")
        return ClaimsAnalysisResult(
            extraction=extraction,
            verdicts=[],
            summary=f"Analysis failed: {str(e)}"
        )
