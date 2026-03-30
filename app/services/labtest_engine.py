import os
import json
from typing import List, Dict, Any
from dotenv import load_dotenv

from app.models.schemas import LabTestSuggestion, ClaimsExtractionResult
from app.services.llm_service import llm_service
from app.utils.logger import pipeline_logger

from app.services.ocr_extraction_service import clean_json_response

load_dotenv()

LAB_TEST_MODEL = os.getenv("LABTEST_SUGGESTION_MODEL")

def load_lab_tests_catalogue() -> str:
    catalogue_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'lab_tests.json')
    try:
        with open(catalogue_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        pipeline_logger.error("Lab Tests", f"Lab tests catalogue not found at {catalogue_path}")
        return "[]"

def load_prompts() -> tuple[str, str]:
    prompt_path = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'LabTestPrompt.md')
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
            system_prompt = content.split('# LAB TEST SUGGESTION SYSTEM PROMPT')[1].split('# LAB TEST VALIDATION PROMPT')[0].strip()
            validation_prompt = content.split('# LAB TEST VALIDATION PROMPT')[1].strip()
            
            return system_prompt, validation_prompt
    except Exception as e:
        pipeline_logger.error("Lab Tests", f"Failed loading lab test prompts: {e}")
        return "", ""

async def run_lab_test_pipeline(
    checks: List[Dict], 
    claims_result: Any, 
    nutrition_checks: List[Dict], 
    extraction: ClaimsExtractionResult
) -> List[LabTestSuggestion]:
    """Generates lab test suggestions based on the aggregated audit results."""
    try:
        system_prompt, validation_template = load_prompts()
        catalogue_json = load_lab_tests_catalogue()

        # 1. Format Compliance Checks (Only Fail or Action)
        relevant_checks = [c for c in checks if c.get('status') in ['Fail', 'Action']]
        compliance_str = "None"
        if relevant_checks:
            compliance_str = "\n".join([f"- {c.get('id')}: {c.get('name')} ({c.get('status')})" for c in relevant_checks])

        # 2. Format Claims Verdicts
        claims_str = "None"
        if claims_result and hasattr(claims_result, 'verdicts'):
            verdicts = claims_result.verdicts
            claims_str = "\n".join([f"- {v.claim_text} ({v.status})" for v in verdicts])

        # 3. Format Nutrition Findings
        nutrition_str = "None"
        if nutrition_checks:
            relevant_nutri = [c for c in nutrition_checks if isinstance(c, dict) and c.get('status') in ['Fail', 'Action']]
            if relevant_nutri:
                nutrition_str = "\n".join([f"- {c.get('id')}: {c.get('name')} ({c.get('status')})" for c in relevant_nutri])

        # 4. Format Ingredients List
        ingredients_str = "None"
        if extraction and hasattr(extraction, 'ingredients') and extraction.ingredients:
            ingredients_str = ", ".join(extraction.ingredients)

        # Build prompt
        prompt = validation_template.replace("{compliance_checks}", compliance_str)
        prompt = prompt.replace("{claims_verdicts}", claims_str)
        prompt = prompt.replace("{nutrition_findings}", nutrition_str)
        prompt = prompt.replace("{ingredients_list}", ingredients_str)
        prompt = prompt.replace("{lab_tests_catalogue}", catalogue_json)

        # Call LLM
        response = await llm_service.generate_content_async(
            model_name=LAB_TEST_MODEL,
            contents=[prompt],
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "testName": {"type": "string"},
                        "category": {"type": "string"},
                        "price": {"type": "number"},
                        "price_low": {"type": "number"},
                        "price_high": {"type": "number"},
                        "priority": {"type": "string", "enum": ["Critical", "Recommended", "Optional"]},
                        "description": {"type": "string"},
                        "relatedChecks": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    },
                    "required": ["testName", "category", "priority", "description", "relatedChecks"]
                }
            }
        )


        
        result_json = json.loads(clean_json_response(response.text))
        
        # Convert to Pydantic models
        suggestions = [LabTestSuggestion(**item) for item in result_json]
        pipeline_logger.info("Lab Tests", f"Generated {len(suggestions)} suggestions")
        return suggestions

    except Exception as e:
        pipeline_logger.error("Lab Tests", f"Lab Test Pipeline Error: {e}")
        return []
