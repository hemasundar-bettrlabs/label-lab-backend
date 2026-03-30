import os
import json
from typing import Dict, Any
from dotenv import load_dotenv

from app.models.schemas import ClaimsExtractionResult
from app.services.rda_calculator import RDACalculator
from app.services.llm_service import llm_service
from app.utils.logger import pipeline_logger

load_dotenv()

MODEL_NAME = os.getenv("NUTRITION_VALIDATION_MODEL")

AUDIENCE_SYSTEM_PROMPT = """
You are a food and nutrition demographic expert. Your task is to analyze details from a food label and determine the primary target audience in order to assign the correct Recommended Daily Allowance (RDA) demographic.

RDA demographics are structured into three parts: gender, activity_level, and specific_period.

Options for gender:
- "men", "women", "boys", "girls", "infants", or "all" (if it applies universally, map to "men" as the general adult population)

Options for activity_level (for adults):
- "sedentary" (default for general adult population)
- "moderate"
- "heavy" (e.g., strong sports or intensive labor targeting)
- "pregnant"
- "lactation"
(For children/infants, leave activity_level as "sedentary" or simply default to the appropriate sub-category if known, but usually "sedentary" applies).

Options for specific_period (only when applicable):
- For pregnant: "2nd_trimester", "3rd_trimester"
- For lactation: "zero_six_months", "seven_twelve_months"
- For infants: "zero_six_months", "six_twelve_months"

Return your answer strictly in the following JSON format:
{
    "gender": "...",
    "activity_level": "...",
    "specific_period": "...",
    "reasoning": "..."
}
"""

async def predict_target_audience(extraction: ClaimsExtractionResult) -> Dict[str, Any]:
    """Uses LLM to predict the RDA demographic based on product metadata."""
    prompt_parts = []
    if extraction.claims:
        claims_text = "; ".join(c.text for c in extraction.claims)
        prompt_parts.append(f"Product Claims: {claims_text}")
    if extraction.ingredients:
        ingredients_text = ", ".join(extraction.ingredients)
        prompt_parts.append(f"Ingredients: {ingredients_text}")
    
    prompt = "\n".join(prompt_parts) if prompt_parts else "Analyze the general population for a standard food product."

    fallback = {
        "gender": "men",
        "activity_level": "sedentary",
        "specific_period": None,
        "reasoning": "Fallback to base adult population."
    }

    try:
        response = await llm_service.generate_content_async(
            model_name=MODEL_NAME,
            contents=[prompt],
            system_instruction=AUDIENCE_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema={
                "type": "object",
                "properties": {
                    "gender": {"type": "string"},
                    "activity_level": {"type": "string"},
                    "specific_period": {"type": "string"},
                    "reasoning": {"type": "string"}
                },
                "required": ["gender", "activity_level", "specific_period", "reasoning"]
            }
        )
        
        from app.services.ocr_extraction_service import clean_json_response
        result = json.loads(clean_json_response(response.text))
        
        if result.get("gender", "men").lower() in ["all", "general", "both"]:
            result["gender"] = "men"
        if result.get("specific_period") in ["", "none", "null"]:
            result["specific_period"] = None
            
        pipeline_logger.info("Nutrition", f"Predicted Target Audience: {result}")
        return result
    except Exception as e:
        pipeline_logger.error("Nutrition", f"Error predicting audience: {e}")
        return fallback

async def run_nutrition_pipeline(extraction: ClaimsExtractionResult) -> list[dict]:
    """Validates nutrients against RDA and returns compliance check objects."""
    checks = []
    
    try:
        if not extraction.nutrition_table:
            return []
            
        # 1. Predict Audience
        audience = await predict_target_audience(extraction)
        
        # 2. Calculate RDA
        calc = RDACalculator(
            gender=audience.get("gender"),
            activity_level=audience.get("activity_level"),
            specific_period=audience.get("specific_period")
        )
        
        rda_results = calc.calculate_all_from_entries(extraction.nutrition_table)
        
        # 3. Build Check Objects
        violations = []
        warnings = []
        compliant_nutrients = []
        
        for key, res in rda_results.items():
            pct = res.get("rda_percentage")
            if pct is None:
                continue
                
            nutrient_display = res["original_name"]
            amount_display = f"{res['amount']} {res['unit']}"
            rda_display = f"{res['rda']} {res['rda_unit']}"
            
            if pct > 100:
                violations.append({
                    "name": nutrient_display,
                    "feedback": f"{nutrient_display} ({amount_display}) is {pct:.1f}% of RDA ({rda_display}) - Exceeds daily recommended allowance for {audience['gender']} ({audience['activity_level']})."
                })
            elif pct < 5 and res["amount"] > 0 and key in ["energy", "protein", "calcium"]:
                warnings.append({
                    "name": nutrient_display,
                    "feedback": f"{nutrient_display} is unusually low ({pct:.1f}% of RDA), ensure declaration is correct."
                })
            else:
                compliant_nutrients.append(nutrient_display)
        
        # Merge results into standard checks
        # Add violations as individual FAIL checks
        for i, v in enumerate(violations):
            checks.append({
                "id": f"NUT-FAIL-{i+1:03d}",
                "category": "Nutrition",
                "name": f"Nutrition Violation: {v['name']}",
                "description": f"Mandatory RDA Compliance for {v['name']}",
                "status": "Fail",
                "feedback": v["feedback"],
                "location": {"x": 50, "y": 50},
                "boundingBox": {"ymin": 0, "xmin": 0, "ymax": 100, "xmax": 100}
            })
            
        # Add warnings as individual ACTION checks
        for i, w in enumerate(warnings):
            checks.append({
                "id": f"NUT-WARN-{i+1:03d}",
                "category": "Nutrition",
                "name": f"Nutrition Warning: {w['name']}",
                "description": f"RDA Adequacy Review for {w['name']}",
                "status": "Action",
                "feedback": w["feedback"],
                "location": {"x": 50, "y": 50},
                "boundingBox": {"ymin": 0, "xmin": 0, "ymax": 100, "xmax": 100}
            })
            
        # Total Summary result if any
        summary_msg = f"Nutrition validation complete for {audience['gender']}/{audience['activity_level']} demographic."
        if not violations and not warnings:
            checks.append({
                "id": "NUT-PASS-001",
                "category": "Nutrition",
                "name": "Nutrition RDA Compliance",
                "description": "Validation of declared nutritional values against standard RDA constants.",
                "status": "Complies",
                "feedback": f"All declared nutrients comply with the Recommended Daily Allowance (RDA) for {audience['gender']} patients/consumers. Tested {len(compliant_nutrients)} parameters.",
                "location": {"x": 50, "y": 50},
                "boundingBox": {"ymin": 0, "xmin": 0, "ymax": 100, "xmax": 100}
            })

    except Exception as e:
        pipeline_logger.error("Nutrition", f"Nutrition Pipeline Error: {e}")
        checks.append({
            "id": "NUT-ERR-001",
            "category": "Nutrition",
            "name": "Nutrition Analysis Error",
            "description": "System encountered an error during deterministic RDA validation.",
            "status": "Action",
            "feedback": f"Could not complete RDA validation: {str(e)}",
            "location": {"x": 50, "y": 50},
            "boundingBox": {"ymin": 0, "xmin": 0, "ymax": 100, "xmax": 100}
        })
        
    return checks
