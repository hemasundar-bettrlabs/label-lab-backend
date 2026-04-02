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
    """Load the MicrobiologicalHazards.json regulatory document."""
    microbiological_hazards_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'microbiological_hazards.json')
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
    extraction: ClaimsExtractionResult,
    metadata: Dict[str, Any]
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

        # 5. Extract Metadata (from parameter or empty dict)
        if metadata is None:
            metadata = extraction.metadata if extraction and hasattr(extraction, 'metadata') else {}

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


        
        result_json = json.loads(clean_json_response(response.text)) # pyright: ignore[reportArgumentType]
        
        # Convert to Pydantic models
        suggestions = [LabTestSuggestion(**item) for item in result_json]
        pipeline_logger.info("Lab Tests", f"Generated {len(suggestions)} suggestions")

        pipeline_logger.info("Lab Tests", "Starting contaminants analysis...")
        contaminants_tests = await run_contaminants_lab_test_analysis(
            extraction=extraction,
            all_checks=checks
        )
        if contaminants_tests:
            pipeline_logger.info("Lab Tests", f"Generated {len(contaminants_tests)} contaminants-related tests")
            suggestions.extend(contaminants_tests)
        else:
            pipeline_logger.info("Lab Tests", "No contaminants-related tests generated.")
        
        # Append microbiological hazards analysis if it identifies relevant tests
        pipeline_logger.info("Lab Tests", "Starting microbiological hazards analysis...")
        microbiological_tests = await run_microbiological_hazard_lab_test_analysis(
            extraction=extraction,
            metadata=metadata,
            all_checks=checks
        )
        if microbiological_tests:
            pipeline_logger.info("Lab Tests", f"Generated {len(microbiological_tests)} microbiological hazard-related tests")
            suggestions.extend(microbiological_tests)
        else:
            pipeline_logger.info("Lab Tests", "No microbiological hazard-related tests generated.")
        
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
        
        # Format category
        category_str = "General Food Product"
        if extraction and hasattr(extraction, 'product_category') and extraction.product_category:
            category_str = extraction.product_category
        
        # Build contaminants analysis prompt
        contaminants_prompt = f"""## 
        CONTAMINANTS ANALYSIS REQUEST

You are an expert in FSSAI Food Safety and Standards (Contaminants, Toxins and Residues) Regulations, 2011.

Analyze whether the food product below requires contaminants testing, based strictly on the regulatory document provided.

---

### PRODUCT INFORMATION
- **Category**: {category_str}

---

### REGULATORY DOCUMENT
{contaminants_doc}

---

### CLASSIFICATION RULES

1. **Classify by final product, not ingredients.**
   - Match the product to its category in the regulatory document.
   - If no exact match exists, fall back to "Food Not Specified / All Foods / Other Foods."
   - If the product does not fit any defined category or fallback, return an empty array.

2. **Apply only defined limits.**
   - Only recommend tests for contaminants explicitly listed for the matched category.
   - If a parameter (e.g., copper) is not listed for the product category, do not suggest it — unless it appears under the "Food Not Specified / All Foods / Other Foods" fallback.
---

### ANALYSIS TASK

Using the matched category and regulatory limits, determine which of the following require testing:

| Group | Parameters |
|---|---|
| Heavy Metals | Lead, Copper, Arsenic, Tin, Cadmium, Mercury |
| Mycotoxins & Crop Contaminants | Aflatoxins, Ochratoxin A, Patulin, Deoxynivalenol |
| Naturally Occurring Toxic Substances | As applicable per category |
| Pesticide Residues | As applicable per category |
| Microbiological Safety | As applicable per category |

Only include test groups where at least one parameter is explicitly regulated for this product.

---

### OUTPUT RULES

- Return a JSON array only. No explanation or preamble.
- If no tests are applicable, return: `[]`
- All entries must have `"category": "Safety Test"` and `"priority": "Critical"`.
- Group related parameters into a single test entry per contaminant type (e.g., one entry for all heavy metals).

---

### OUTPUT FORMAT
```json
[
  {{
    "testName": "Heavy Metals Analysis (Lead, Arsenic, Cadmium, Mercury)",
    "category": "Safety Test",
    "price": 880,
    "price_low": 880,
    "price_high": 1000,
    "priority": "Critical",
    "description": "Testing for regulated heavy metals under FSSAI Contaminants Regulations for {category_str}.",
    "relatedChecks": []
  }},
  {{
    "testName": "Mycotoxin Analysis (Aflatoxins, Ochratoxin A, Patulin)",
    "category": "Safety Test",
    "price": 880,
    "price_low": 880,
    "price_high": 1000,
    "priority": "Critical",
    "description": "Testing for mycotoxins and crop contaminants under FSSAI regulations for {category_str}.",
    "relatedChecks": []
  }}
]
```
### Pricing reference Must Be Followed Strictly No Hallucinations (INR):
  For All the Test Keep the price range between 880-1000 INR, with 880 INR being the most common price for basic contaminant panels in Indian labs.

"""

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
        
        result_json = json.loads(clean_json_response(response.text)) # pyright: ignore[reportArgumentType]
        contaminants_tests = [LabTestSuggestion(**item) for item in result_json]
        
        return contaminants_tests

    except Exception as e:
        pipeline_logger.error("Lab Tests", f"Contaminants Analysis Error: {e}")
        return []
    

async def run_microbiological_hazard_lab_test_analysis(
    extraction: ClaimsExtractionResult,
    metadata: Dict[str, Any],
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

        # Format ingredients_str
        ingredients_str = "None"
        if extraction and hasattr(extraction, 'ingredients') and extraction.ingredients:
            ingredients_str = ", ".join(extraction.ingredients)
        
        # Build microbiological hazards analysis prompt
        microbiological_hazard_prompt = f"""
MICROBIOLOGICAL HAZARDS ANALYSIS REQUEST
You are an expert in FSSAI Food Safety and Standards (Microbiological Hazards) Regulations, 2011.
Based on the regulatory document provided below, analyze whether the following food product requires microbiological hazard testing.
PRODUCT INFORMATION:

Category: {category_str}
Metadata: {json.dumps(metadata)}
Ingredient List: {ingredients_str}


STEP 1 — CLASSIFY THE PRODUCT INTO AN EXACT SUBCATEGORY
You must map the product to one and only one subcategory from the table below. If no match is found, output an empty array [] and stop.
Do not invent subcategories. Do not blend subcategories.
Group A — Fruits and Vegetables and their Products
Subcategory KeyDefinitionCut or minimally processed and packed, including juices (Nonthermally processed)Washed, sanitized, peeled, cut, or juiced fruits/vegetables — packed without thermal treatmentFermented or pickled or acidified or with preservativesPreserved using fermentation (yeast, bacteria, mold, enzyme), brine, lactic acid, vinegar, salt, or sugarPasteurized JuicesFruit/vegetable juices subjected to pasteurizationCarbonated Fruit BeveragesBeverage made from fruit juice + water or carbonated water, with sugar/glucose, may contain peel oil or fruit essencesFrozenFruits/vegetables or their products frozen and maintained at −18°CDehydrated or driedFruits/vegetables preserved by removing water content through a dehydration processThermally processed (other than pasteurization at less than 100°C)Heat-processed in a sealed container before or after sealing, to prevent spoilage (not retort)Retort processedCanned or flexible-packaged, processed by retorting
Group B — Food Grain Products
Subcategory KeyDefinitionBatters and Doughs (Ready to Cook)Raw, uncooked grain-based products the consumer must cook. Includes: pancake mix, idli/dosa batter, cake premixes, raw pizza dough. A powder or dry mix that is intended to be mixed with liquid and cooked (e.g., dosa batter powder, pancake mix) falls here — not in the RTE category.Fermented products other than batters and doughs (ready to cook) including bread, cakes, doughnuts, other ready to eat grain products, malted milk food, instant noodles* and pasta products*Products that have already undergone a kill-step (baking, steaming, frying) during manufacturing. Includes: sliced bread, cupcakes, roasted snacks, instant noodles (pre-steamed/fried).

STEP 2 — RETRIEVE ALLOWED TESTS FOR THAT SUBCATEGORY
Once you identify the exact subcategory, use only the tests listed for it in the table below. Do not add any test that is not listed for the matched subcategory.
Fruits and Vegetables and their Products:

  Cut or minimally processed and packed, including juices (Nonthermally processed):
    - Aerobic Plate Count
    - Yeast and Mold Count
    - Enterobacteriaceae
    - Staphylococcus aureus
    - Salmonella
    - Listeria monocytogenes
    - E. Coli O157 and Vero or Shiga toxin producing E. coli
    - Vibrio cholerae

  Fermented or pickled or acidified or with preservatives:
    - Yeast and Mold Count
    - Enterobacteriaceae
    - Staphylococcus aureus
    - Salmonella
    - Listeria monocytogenes
    - E. Coli O157 and Vero or Shiga toxin producing E. coli
    - Vibrio cholerae

  Pasteurized Juices:
    - Aerobic Plate Count
    - Yeast and Mold Count
    - Enterobacteriaceae
    - Staphylococcus aureus
    - Salmonella
    - Listeria monocytogenes
    - E. Coli O157 and Vero or Shiga toxin producing E. coli
    - Vibrio cholerae

  Carbonated Fruit Beverages:
    - Aerobic Plate Count
    - Yeast and Mold Count
    - Enterobacteriaceae
    - Staphylococcus aureus
    - Salmonella
    - Listeria monocytogenes
    - E. Coli O157 and Vero or Shiga toxin producing E. coli
    - Vibrio cholerae

  Frozen:
    - Aerobic Plate Count
    - Yeast and Mold Count
    - Enterobacteriaceae
    - Staphylococcus aureus
    - Salmonella
    - Listeria monocytogenes
    - E. Coli O157 and Vero or Shiga toxin producing E. coli
    - Vibrio cholerae

  Dehydrated or dried:
    - Aerobic Plate Count
    - Yeast and Mold Count
    - Enterobacteriaceae
    - Staphylococcus aureus
    - Salmonella
    - Listeria monocytogenes
    - E. Coli O157 and Vero or Shiga toxin producing E. coli
    - Vibrio cholerae

  Thermally processed (other than pasteurization at less than 100°C):
    - Aerobic Plate Count
    - Yeast and Mold Count
    - Enterobacteriaceae
    - Staphylococcus aureus
    - Salmonella
    - Listeria monocytogenes
    - E. Coli O157 and Vero or Shiga toxin producing E. coli
    - Vibrio cholerae

  Retort processed:
    - Aerobic Plate Count
    - Enterobacteriaceae
    - Staphylococcus aureus
    - Salmonella
    - Listeria monocytogenes
    - E. Coli O157 and Vero or Shiga toxin producing E. coli
    - Vibrio cholerae

Food Grain Products:

  Batters and Doughs (Ready to Cook):
    - Enterobacteriaceae count
    - Staphylococcus aureus count

  Fermented products other than batters and doughs (ready to cook) including bread, cakes, doughnuts,
  other ready to eat grain products, malted milk food, instant noodles and pasta products:
    - Enterobacteriaceae count
    - Salmonella
    - Listeria monocytogenes

STEP 3 — CLASSIFICATION RULES (apply before matching)

Dry powder/mix that requires adding liquid + cooking → classify as Batters and Doughs (Ready to Cook), even if sold as a powder. Example: dosa batter mix, pancake powder, cake premix.
Product that has already been baked, steamed, or fried → classify as the RTE Food Grain subcategory.
Fresh whole fruit/vegetable not further processed → falls under "Fresh" which has no microbiological tests defined in scope → return [].
Product does not match any subcategory in Group A or Group B → return [].
Never combine tests from two subcategories, even if the product seems to straddle both.

STEP 4 — OUTPUT
Return only a JSON array. One object per test. No additional text, no explanation outside the array.
If no subcategory matched → return [].
[
  {{
    "testName": "<exact test name from the allowed list>",
    "category": "Safety Test",
    "price": 750,
    "price_low": 750,
    "price_high": 1000,
    "priority": "Critical",
    "description": "<one sentence: why this test matters for this specific product and subcategory>",
    "relatedChecks": []
  }}
]

### Pricing reference Must Be Followed Strictly No Hallucinations:

Aerobic Plate Count: 750-1000
Yeast and Mold Count: 750-1000
Enterobacteriaceae: 750-1000
Staphylococcus aureus: 750-1000
Salmonella: 750-1000
Listeria monocytogenes: 750-1000
E. Coli O157 / Shiga toxin: 750-1000
Vibrio cholerae: 750-1000
"""

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
        
        result_json = json.loads(clean_json_response(response.text)) # pyright: ignore[reportArgumentType]
        microbiological_tests = [LabTestSuggestion(**item) for item in result_json]
        
        return microbiological_tests

    except Exception as e:
        pipeline_logger.error("Lab Tests", f"Microbiological Hazards Analysis Error: {e}")
        return []