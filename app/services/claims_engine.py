import os
import json
from typing import Dict, Any
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
from app.services.rda_calculator import RDACalculator

load_dotenv()

from app.services.ocr_extraction_service import clean_json_response
from app.utils.logger import pipeline_logger

# Use individual model config if exists, fallback to Analysis Model
CLAIMS_VALIDATION_MODEL = os.getenv("CLAIMS_VALIDATION_MODEL")


async def validate_claims(extraction_result: ClaimsExtractionResult, audience: Dict[str, Any] = None) -> list[ClaimVerdict]:
    """Validate extracted claims against nutrition and ingredient data."""
    try:
        if not extraction_result.claims:
            return []

        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        # Initialize RDA Calculator with the correct demographic
        if audience is None:
            audience = {
                "gender": "men",
                "activity_level": "sedentary",
                "specific_period": None
            }
        
        rda_calculator = RDACalculator(
            gender=audience.get("gender", "men"),
            activity_level=audience.get("activity_level", "sedentary"),
            specific_period=audience.get("specific_period")
        )
        
        pipeline_logger.info("Claims", f"Using RDA demographic: {audience}")
        
        # Use calculate_all_from_entries as the single source of truth
        if extraction_result.nutrition_table:
            rda_results = rda_calculator.calculate_all_from_entries(extraction_result.nutrition_table)
            pipeline_logger.info("Claims", f"RDA calculations complete: {len(rda_results)} nutrients processed")
        else:
            rda_results = {}
            pipeline_logger.warning("Claims", "No nutrition table entries found")
        
        # Build nutrition_with_rda from rda_results
        nutrition_with_rda = []
        rda_percentages = {}
        
        for entry in extraction_result.nutrition_table:
            entry_dict = entry.model_dump()
            key = entry.nutrient.lower().replace(" ", "_")
            
            if key in rda_results:
                result = rda_results[key]
                entry_dict['rda_percentage_per_100g'] = result['rda_percentage']
                entry_dict['rda_percentage_per_serve'] = result['rda_percentage_per_serve']
                entry_dict['label_rda_percentage'] = result['label_rda_percentage']
                entry_dict['rda_constant'] = result['rda']
                entry_dict['rda_unit'] = result['rda_unit']
                
                if result['rda_percentage'] is not None:
                    rda_percentages[entry.nutrient.lower()] = result['rda_percentage']
                    pipeline_logger.info("Claims", f"{entry.nutrient}: {result['rda_percentage']}% RDA per 100g")
            
            nutrition_with_rda.append(entry_dict)

        # Convert extraction components to formatted strings
        nutrition_str = json.dumps(nutrition_with_rda, indent=2, default=str)
        ingredients_str = ", ".join(extraction_result.ingredients) if extraction_result.ingredients else "None"
        claims_str = json.dumps([c.model_dump() for c in extraction_result.claims], indent=2)
        nutritional_claims_str = open(os.path.join(root, "app", "data", "nutritional_claims.json")).read()

        # Add RDA percentage info to prompt
        rda_info = json.dumps(rda_percentages, indent=2)
        pipeline_logger.info("Claims (RDA)", f"RDA Percentages: {rda_info}")
        pipeline_logger.info("Claims (RDA)", f"RDA Percentages Count: {len(rda_percentages)}")
        prompt = build_claims_validation_prompt(nutrition_str, ingredients_str, claims_str, nutritional_claims_str, rda_info)

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
                        "reference": { "type": "string" },
                        "rda_percentage": { "type": "number" },
                        "nutrient_involved": { "type": "string" }
                    },
                    "required": ["claim_text", "tag", "status", "reasoning", "reference"]
                }
            }
        )

        result_json = json.loads(clean_json_response(response.text)) # type: ignore
        pipeline_logger.info("Claims", f"Claims Validation Result: {result_json}")
        
        # Process verdicts and ensure RDA fields are properly populated
        processed_verdicts = []
        for verdict in result_json:
            # Ensure optional fields have defaults
            if 'rda_percentage' not in verdict:
                verdict['rda_percentage'] = None
            if 'nutrient_involved' not in verdict:
                verdict['nutrient_involved'] = None
            
            # Log RDA data if captured
            if verdict.get('rda_percentage') is not None:
                nutrient = verdict.get('nutrient_involved', 'Unknown')
                rda_pct = verdict.get('rda_percentage')
                pipeline_logger.info("Claims (RDA)", f"{nutrient}: {rda_pct}% RDA captured in verdict")
            
            processed_verdicts.append(verdict)
        
        return [ClaimVerdict(**v) for v in processed_verdicts]

    except Exception as e:
        pipeline_logger.error("Claims", f"Claims Validation Error: {e}")
        raise ValueError(f"Failed to validate claims: {str(e)}")


async def run_claims_pipeline(extraction: ClaimsExtractionResult, audience: Dict[str, Any] = None) -> ClaimsAnalysisResult:
    """End-to-end claims analysis pipeline."""
    try:
        verdicts = await validate_claims(extraction, audience)
        
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
