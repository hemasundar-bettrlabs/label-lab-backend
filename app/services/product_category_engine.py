"""
Product Category Prediction Engine

Predicts product category based on ingredients when category is not provided.
Acts as metadata enrichment layer in the analysis pipeline.

Workflow:
1. Check if category exists in OCR JSON (primary source)
2. Check if category exists in metadata extraction (secondary source)
3. If both missing, use LLM to predict category from ingredients
4. Inject predicted category back into OCR data for downstream use
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List

from app.models.schemas import ClaimsExtractionResult
from app.services.llm_service import llm_service
from app.utils.logger import pipeline_logger

load_dotenv = __import__('dotenv').load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)
_pipeline_logger = pipeline_logger  # Alias for use in methods

# Environment configuration
CATEGORY_PREDICTION_MODEL = os.getenv("CATEGORY_PREDICTION_MODEL", "gemini-2.5-flash")
CATEGORY_PREDICTION_TEMPERATURE = float(os.getenv("CATEGORY_PREDICTION_TEMPERATURE", "0.5"))
CATEGORY_PREDICTION_PROMPT= os.path.join(os.path.dirname(__file__), '..', 'prompts', 'CategoryPrompt.md')

class CategoryPredictionResult:
    """Result of category prediction."""
    
    def __init__(
        self,
        suggested_category: str,
        confidence_score: float,
        alternative_categories: Optional[List[Dict[str, Any]]] = None,
        reasoning: str = "",
        basis: str = "ingredients"
    ):
        self.suggested_category = suggested_category
        self.confidence_score = confidence_score
        self.alternative_categories = alternative_categories or []
        self.reasoning = reasoning
        self.basis = basis
    
    def model_dump(self) -> Dict[str, Any]:
        """Return dict representation."""
        return {
            "suggested_category": self.suggested_category,
            "confidence_score": self.confidence_score,
            "alternative_categories": self.alternative_categories,
            "reasoning": self.reasoning,
            "basis": self.basis,
        }


class ProductCategoryPredictor:
    """
    Predicts product category based on ingredients when category is missing.

    Workflow:
    1. Check OCR JSON for product_category (primary source)
    2. Check metadata for fssaiCategory (secondary source)
    3. If both missing, use LLM to predict from ingredients
    4. Inject predicted category back into OCR JSON object
    """

    def __init__(self):
        """Initialize predictor (minimal setup, no KB loading)."""
        _pipeline_logger.info("Category", "Initializing Product Category Predictor (LLM-based)")

    def _create_category_prediction_prompt(
        self,
        product_name: str,
        brand_name: str,
        ingredients: str,
    ) -> str:
        """
        Create LLM prompt for category prediction.
        
        Args:
            product_name: Product name from label
            brand_name: Brand name from label
            ingredients: Comma-separated ingredient list
            
        Returns:
            Prompt string for LLM
        """
        # Format allowed categories nicely
        categories_str = "\n".join(f"  - {cat}" for cat in ALLOWED_CATEGORIES)

        # concatenate prompt with product info and instructions
        with open(CATEGORY_PREDICTION_PROMPT, "r") as f:
            base_prompt = f.read()
        
        prompt = f"""{base_prompt}
Here are the current details of the product based on the label information:

**Product Information:**
- Brand: {brand_name}
- Product Name: {product_name}
- Ingredients: {ingredients if ingredients else "No ingredients provided"}

**Task:**
1. Analyze the ingredients and product name to determine the best category
2. Suggest the top-3 category alternatives with confidence scores
3. Provide reasoning for your primary suggestion

**Return a JSON object with the following structure:**
{{
    "suggested_category": "string (must be from the allowed list above)",
    "confidence": number (0.0 to 1.0),
    "alternatives": [
        {{"category": "string", "confidence": number}},
        {{"category": "string", "confidence": number}}
    ],
    "reasoning": "string explaining why this category was chosen"
}}

**Rules:**
- suggested_category must be exactly one of the allowed categories
- confidence must be between 0.0 and 1.0
- alternatives should not include the suggested_category
- Keep reasoning concise (1-2 sentences)
"""
        return prompt

    async def predict_category(
        self,
        product_name: str,
        brand_name: Optional[str] = None,
        ingredients: Optional[str] = None,
        ocr_category: Optional[str] = None,
        metadata_category: Optional[str] = None,
        extraction: Optional[ClaimsExtractionResult] = None,
    ) -> Optional[CategoryPredictionResult]:
        """
        Predict product category if not detected in OCR JSON or metadata.
        
        Priority:
        1. If ocr_category exists, return None (no prediction needed)
        2. If metadata_category exists, return None (no prediction needed)
        3. Both missing → predict using LLM and inject into extraction object
        
        Args:
            product_name: Product name from label
            brand_name: Brand name (optional)
            ingredients: Comma-separated ingredient list (optional)
            ocr_category: Category from OCR JSON (primary source)
            metadata_category: Category from metadata extraction (secondary source)
            extraction: OCRData/ClaimsExtractionResult object to inject result into
            
        Returns:
            CategoryPredictionResult if prediction was made and injection succeeded
            None if category already available from OCR JSON or metadata
        """
        # Guard 1: If category already in OCR JSON, return None (no prediction needed)
        if ocr_category:
            _pipeline_logger.info("Category", f"✓ Category found in OCR JSON: {ocr_category}")
            return None
        
        # Guard 2: If category in metadata, return None (no prediction needed)
        if metadata_category:
            _pipeline_logger.info("Category", f"✓ Category found in metadata: {metadata_category}")
            return None
        
        # Both sources missing → proceed with LLM prediction
        _pipeline_logger.info("Category", "No category in OCR JSON or metadata. Predicting from ingredients...")
        
        # Handle empty ingredients
        if not ingredients:
            _pipeline_logger.info("Category", "No ingredients provided - cannot predict category")
            return None
        
        # Create LLM prompt
        brand = brand_name or "Unknown"
        prompt = self._create_category_prediction_prompt(product_name, brand, ingredients)
        
        try:
            # Call LLM with structured response
            response = await llm_service.generate_content_async(
                model_name=CATEGORY_PREDICTION_MODEL,
                contents=[prompt],
                response_mime_type="application/json"
            )
            
            if not response or not response.text:
                _pipeline_logger.error("Category", "LLM returned empty response")
                return None
            
            # Parse JSON response
            try:
                llm_result = json.loads(response.text)
            except json.JSONDecodeError as e:
                _pipeline_logger.error("Category", f"Failed to parse LLM response: {e}")
                return None
            
            # Validate response structure
            suggested = llm_result.get("suggested_category")
            confidence = llm_result.get("confidence", 0.0)
            alternatives = llm_result.get("alternatives", [])
            reasoning = llm_result.get("reasoning", "")
            
            if not suggested or suggested not in ALLOWED_CATEGORIES:
                _pipeline_logger.error("Category", f"Invalid suggested category: {suggested}")
                return None
            
            # Validate confidence score
            if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
                _pipeline_logger.info("Category", f"Invalid confidence score: {confidence}, using 0.5")
                confidence = 0.5
            
            # Create result object
            prediction = CategoryPredictionResult(
                suggested_category=suggested,
                confidence_score=float(confidence),
                alternative_categories=alternatives,
                reasoning=reasoning,
                basis="ingredients"
            )
            
            # INJECT BACK INTO EXTRACTION OBJECT (critical step)
            if extraction:
                extraction.product_category = suggested
                _pipeline_logger.info("Category", f"✓ Predicted & Injected: {suggested} (confidence: {confidence:.2f})")
            else:
                _pipeline_logger.info("Category", f"Predicted {suggested} but no extraction object to inject into")
            
            # Log the prediction
            logger.info(
                f"Category prediction: product='{product_name}', "
                f"predicted='{suggested}', confidence={confidence:.2f}"
            )
            
            return prediction
        
        except Exception as e:
            _pipeline_logger.error("Category", f"Prediction failed: {e}")
            logger.exception(f"Error predicting category: {e}")
            return None
