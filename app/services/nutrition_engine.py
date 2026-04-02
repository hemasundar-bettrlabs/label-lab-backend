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

async def run_nutrition_pipeline(extraction: ClaimsExtractionResult) -> tuple[list[dict], Dict[str, Any]]:
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
        below_adequacy = []
        compliant_nutrients = []
        
        for key, res in rda_results.items():
            pct = res.get("rda_percentage")
            if pct is None:
                continue
                
            nutrient_display = res["original_name"]
            amount_display = f"{res['amount']} {res['unit']}"
            rda_display = f"{res['rda']} {res['rda_unit']}"
            
            # Define adequacy thresholds for different nutrient types
            critical_nutrients = ["energy", "protein", "calcium", "dietary_fiber"]
            vitamin_minerals = ["vitamin_a", "vitamin_c", "vitamin_d", "vitamin_e", "vitamin_k", "calcium", "zinc", "iron", "magnesium", "potassium", "phosphorus", "chromium", "selenium", "biotin", "vitamin_b1", "vitamin_b2", "vitamin_b3", "vitamin_b5", "vitamin_b6", "vitamin_b9", "vitamin_b12"]
            
            if pct > 100:
                violations.append({
                    "name": nutrient_display,
                    "feedback": f"{nutrient_display} ({amount_display}) is {pct:.1f}% of RDA ({rda_display}) - Exceeds daily recommended allowance for {audience['gender']} ({audience['activity_level']})."
                })
            # Check critical nutrients for minimum adequacy (should be >= 10% RDA per 100g)
            elif key in critical_nutrients and pct < 10 and res["amount"] > 0:
                below_adequacy.append({
                    "name": nutrient_display,
                    "pct": pct,
                    "feedback": f"Critical nutrient {nutrient_display} ({amount_display}) is BELOW ADEQUACY: {pct:.1f}% of RDA (requires ≥10% for {audience['gender']} {audience['activity_level']})."
                })
            # For vitamins/minerals, flag if BELOW 15% RDA (inadequate for source claims)
            elif key in vitamin_minerals and pct < 15 and res["amount"] > 0:
                below_adequacy.append({
                    "name": nutrient_display,
                    "pct": pct,
                    "feedback": f"Vitamin/Mineral {nutrient_display} ({amount_display}) is BELOW ADEQUACY: {pct:.1f}% of RDA (requires ≥15% to claim as 'source' for {audience['gender']} {audience['activity_level']})."
                })
            else:
                compliant_nutrients.append(nutrient_display)
        
        # Overall RDA Compliance Summary with consolidated nutrition details
        total_nutrients = len(rda_results)
        
        if violations or below_adequacy:
            # FAIL: If there are any violations or nutrients below adequacy
            num_inadequate = len(violations) + len(below_adequacy)
            # Combine violations and below-adequacy items for detailed display
            nutrition_details = violations + below_adequacy
            checks.append({
                "id": "NUT-COMPLIANCE-001",
                "category": "Nutrition",
                "name": "Nutrition RDA Compliance",
                "description": "Validation of declared nutritional values against standard RDA constants.",
                "status": "Fail",
                "feedback": f"RDA Compliance Failed: {num_inadequate} out of {total_nutrients} nutrients fail RDA adequacy standards. {len(below_adequacy)} nutrient(s) are below minimum adequacy thresholds for {audience['gender']} ({audience['activity_level']}).",
                "location": {"x": 50, "y": 50},
                "boundingBox": {"ymin": 0, "xmin": 0, "ymax": 100, "xmax": 100},
                "nutritionDetails": nutrition_details
            })
        else:
            # COMPLIES: Only if ALL nutrients meet RDA adequacy standards
            checks.append({
                "id": "NUT-COMPLIANCE-001",
                "category": "Nutrition",
                "name": "Nutrition RDA Compliance",
                "description": "Validation of declared nutritional values against standard RDA constants.",
                "status": "Complies",
                "feedback": f"All declared nutrients comply with RDA adequacy standards for {audience['gender']} ({audience['activity_level']}) patients/consumers. All {total_nutrients} parameters tested are within acceptable RDA ranges.",
                "location": {"x": 50, "y": 50},
                "boundingBox": {"ymin": 0, "xmin": 0, "ymax": 100, "xmax": 100},
                "nutritionDetails": []
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
        
    pipeline_logger.info("Nutrition", f"Nutrition validation complete with audience: {audience}")
    return checks, audience
