import os
import json
import asyncio
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

def load_contaminants_document() -> str:
    """Load the Contaminants.md regulatory document."""
    contaminants_path = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'Contaminants.md')
    try:
        with open(contaminants_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        pipeline_logger.error("Lab Tests", f"Contaminants document not found at {contaminants_path}")
        return ""
    
def load_microbiological_hazards_document() -> str:
    """Load the MicrobiologicalHazards.md regulatory document."""
    microbiological_hazards_path = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'MicrobiologicalHazards.md')
    try:
        with open(microbiological_hazards_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        pipeline_logger.error("Lab Tests", f"Microbiological Hazards document not found at {microbiological_hazards_path}")
        return ""

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
        
        # Append microbiological hazards analysis if it identifies relevant tests
        microbiological_tests = await run_microbiological_hazard_lab_test_analysis(
            extraction=extraction,
            all_checks=checks
        )
        if microbiological_tests:
            pipeline_logger.info("Lab Tests", f"Generated {len(microbiological_tests)} microbiological hazard-related tests")
            suggestions.extend(microbiological_tests)
        
        return suggestions

    except Exception as e:
        pipeline_logger.error("Lab Tests", f"Lab Test Pipeline Error: {e}")
        return []


async def run_contaminants_lab_test_analysis(
    extraction: ClaimsExtractionResult,
    all_checks: List[Dict]
) -> List[LabTestSuggestion]:
    """
    Generates contaminants-specific lab test suggestions using FSSAI regulations.
    
    Analyzes the product's ingredients and composition against contaminant limits
    defined in the Food Safety and Standards (Contaminants, Toxins and Residues)
    Regulations, 2011.
    """
    try:
        contaminants_doc = load_contaminants_document()
        if not contaminants_doc:
            return []
        
        # Format product info
        ingredients_str = "None"
        if extraction and hasattr(extraction, 'ingredients') and extraction.ingredients:
            ingredients_str = ", ".join(extraction.ingredients)
        
        # Format category
        category_str = "General Food Product"
        if extraction and hasattr(extraction, 'product_category') and extraction.product_category:
            category_str = extraction.product_category
        
        # Build contaminants analysis prompt
        contaminants_prompt = f"""## CONTAMINANTS ANALYSIS REQUEST

You are an expert in FSSAI Food Safety and Standards (Contaminants, Toxins and Residues) Regulations, 2011.

Based on the regulatory document provided below, analyze whether the following food product requires contaminants testing.

### PRODUCT INFORMATION:
- **Category**: {category_str}

### REGULATORY DOCUMENT (FSSAI Contaminants Standards):
{contaminants_doc}

### IMPROTANT NOTE:
1) Only recommend text based on fine product category given as grounded data. Do not make assumptions beyond the provided category and ingredients. If the category is vague, default to general food product guidelines. Always refer to the regulatory document for limits and testing requirements.
The system should detect based on product not ingredient.
Example: If a product is labeled as chocolate and contains cocoa powder, 
the system should not classify it based on the ingredient (cocoa powder). 
Instead, it should consider the final product category as chocolate. 
If the chocolate category is not available in the system, the product should be classified under “Food Not Specified, all foods, other foods”.
If it does not fall under any defined category, it should be treated as ignored, without applying category-specific validations or suggesting specific tests.

2) For contaminants such as heavy metals, toxins, and residues, each should be handled based on their respective defined lists. 
If a specific parameter (e.g., lead) is applicable and available for the product category, 
it should be identified and flagged. However, 
if a parameter (e.g., copper) is not defined for that category but if food not specified,
all foods, other foods present can take that, else, the system should not suggest or enforce testing for it. 

### ANALYSIS TASK:
1. Identify which contaminant categories are relevant for this product category based on the regulatory limits table.
2. Based on the product's composition, determine if testing for the following contaminant categories is needed:
   - Heavy metals (Lead, Copper, Arsenic, Tin, Cadmium, Mercury)
   - Crop contaminants and mycotoxins (Aflatoxins, Ochratoxin A, Patulin, Deoxynivalenol)
   - Naturally occurring toxic substances
   - Pesticide residues
   - Microbiological safety

3. Return a JSON array of lab test suggestions ONLY for contaminant types that are relevant to this product.

4. Ensure a clear distinction between Heavy Metal Tests, Toxin Tests, and Residue Tests, and organize all relevant analyses under these three explicitly defined categories.

5. Keep everything as critical by default.

6. Keep the category as Contaminants for all tests generated in this section, to allow for clear grouping and filtering of contaminant-related tests in the final output.

### OUTPUT FORMAT:
Return a JSON array with this structure (empty array if no contaminants testing is needed):
```json
[
  {{
    "testName": "Heavy Metals Analysis (Lead, Arsenic, Cadmium, Mercury)",
    "category": "Contaminants",
    "price": 2500,
    "price_low": 2000,
    "price_high": 3500,
    "priority": "Critical",
    "description": "Comprehensive testing for toxic heavy metals as per FSSAI limits. Relevant for this {category_str} product.",
    "relatedChecks": []
  }},
  {{
    "testName": "Mycotoxin Analysis (Aflatoxins, Ochratoxin A, Patulin)",
    "category": "Contaminants",
    "price": 3000,
    "price_low": 2500,
    "price_high": 4000,
    "priority": "Critical",
    "description": "Testing for crop contaminants and mycotoxins as per FSSAI regulations. Essential for products containing susceptible ingredients.",
    "relatedChecks": []
  }}
]
```

Only include tests that are truly relevant to this product category and ingredient composition."""

        # Call LLM for contaminants analysis
        response = await llm_service.generate_content_async(
            model_name=LAB_TEST_MODEL,
            contents=[contaminants_prompt],
            system_instruction="You are an expert in FSSAI food safety regulations and laboratory testing requirements. Provide recommendations only based on regulatory requirements and product composition.",
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
        contaminants_tests = [LabTestSuggestion(**item) for item in result_json]
        
        return contaminants_tests

    except Exception as e:
        pipeline_logger.error("Lab Tests", f"Contaminants Analysis Error: {e}")
        return []
    

async def run_microbiological_hazard_lab_test_analysis(
    extraction: ClaimsExtractionResult,
    all_checks: List[Dict]
) -> List[LabTestSuggestion]:
    """
    Generates microbiological hazard-specific lab test suggestions using FSSAI regulations.
    
    Analyzes the product's ingredients and composition against microbiological hazard limits
    defined in the Food Safety and Standards (Microbiological Hazards) Regulations, 2011.
    """
    try:
        microbiological_hazards_doc = load_microbiological_hazards_document()
        if not microbiological_hazards_doc:
            return []
        
        # Format category
        category_str = "General Food Product"
        if extraction and hasattr(extraction, 'product_category') and extraction.product_category:
            category_str = extraction.product_category
        
        # Build microbiological hazards analysis prompt
        microbiological_hazard_prompt = f"""## MICROBIOLOGICAL HAZARDS ANALYSIS REQUEST

You are an expert in FSSAI Food Safety and Standards (Microbiological Hazards) Regulations, 2011.

Based on the regulatory document provided below, analyze whether the following food product requires microbiological hazard testing.

### PRODUCT INFORMATION:
- **Category**: {category_str}

### REGULATORY DOCUMENT (FSSAI Microbiological Hazards Standards):
{microbiological_hazards_doc}

### IMPORTANT NOTE:
1) Only recommend tests based on fine product category given as grounded data. Do not make assumptions beyond the provided category. If the category is vague, default to general food product guidelines. Always refer to the regulatory document for limits and testing requirements.
The system should detect based on product not ingredient.
Example: If a product is labeled as chocolate, the system should not classify it based on the ingredients. Instead, it should consider the final product category as chocolate. 
If the chocolate category is not available in the system, the product should be classified under "Food Not Specified, all foods, other foods".
If it does not fall under any defined category, it should be treated as ignored, without applying category-specific validations or suggesting specific tests.

2) For microbiological hazards such as pathogens, each should be handled based on their respective defined lists. 
If a specific parameter (e.g., E. coli) is applicable and available for the product category, it should be identified and flagged. However, 
if a parameter is not defined for that category but general food or "not specified" category is available, then it can be recommended, else, the system should not suggest or enforce testing for it.

### ANALYSIS TASK:
1. Identify which microbiological hazard categories are relevant for this product category based on the regulatory limits table.
2. Based on the product's composition, determine if testing for the following microbiological hazard categories is needed:
   - Bacterial pathogens (E. coli, Salmonella, Listeria, Staphylococcus aureus)
   - Viral pathogens (Hepatitis A, Norovirus)
   - Fungal contaminants
   - Mycotoxin producers
   - Spore-forming bacteria

3. Return a JSON array of lab test suggestions ONLY for microbiological hazard types that are relevant to this product.

4. Ensure a clear distinction between Pathogenic Bacteria Tests, Viral Tests, and Fungal Contamination Tests.

5. Keep everything as critical by default.

6. Keep the category as Microbiological Hazards for all tests generated in this section, to allow for clear grouping and filtering of microbiological hazard-related tests in the final output.

### OUTPUT FORMAT:
Return a JSON array with this structure (empty array if no microbiological hazard testing is needed):
```json
[
  {{
    "testName": "Pathogenic Bacteria Testing (E. coli, Salmonella, Listeria)",
    "category": "Microbiological Hazards",
    "price": 3500,
    "price_low": 3000,
    "price_high": 4500,
    "priority": "Critical",
    "description": "Comprehensive testing for pathogenic bacteria as per FSSAI microbiological hazards limits. Essential for this {category_str} product.",
    "relatedChecks": []
  }},
  {{
    "testName": "Viral Pathogens Testing (Hepatitis A, Norovirus)",
    "category": "Microbiological Hazards",
    "price": 4000,
    "price_low": 3500,
    "price_high": 5000,
    "priority": "Critical",
    "description": "Testing for viral pathogens as per FSSAI regulations. Critical for ready-to-eat and high-risk products.",
    "relatedChecks": []
  }}
]
```

Only include tests that are truly relevant to this product category and ingredient composition."""

        # Call LLM for microbiological hazards analysis
        response = await llm_service.generate_content_async(
            model_name=LAB_TEST_MODEL,
            contents=[microbiological_hazard_prompt],
            system_instruction="You are an expert in FSSAI food safety regulations and laboratory testing requirements. Provide recommendations only based on regulatory requirements and product composition.",
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
        microbiological_tests = [LabTestSuggestion(**item) for item in result_json]
        
        return microbiological_tests

    except Exception as e:
        pipeline_logger.error("Lab Tests", f"Microbiological Hazards Analysis Error: {e}")
        return []