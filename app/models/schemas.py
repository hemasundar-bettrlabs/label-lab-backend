from typing import List, Optional, Literal
from enum import Enum

from pydantic import BaseModel

# Enums
class ProcessingState(str, Enum):
    IDLE = 'idle'
    VALIDATING = 'validating'
    PDF_SELECTION = 'pdf_selection'
    ASSIGNING = 'assigning'
    CONFIGURING = 'configuring'
    ANALYZING = 'analyzing'
    EDITING = 'editing'
    COMPLETE = 'complete'
    ERROR = 'error'

class CheckStatus(str, Enum):
    PASS = 'Complies'
    FAIL = 'Fail'
    WARNING = 'Action'

class RuleCategory(str, Enum):
    LEGAL = 'Legal'
    INGREDIENTS = 'Ingredients'
    BRANDING = 'Branding'
    DIMENSIONS = 'Dimensions'
    BARCODES = 'Barcodes'
    SPELLING = 'Spelling'
    REGULATORY = 'Regulatory'
    FONTS = 'Fonts'
    CLAIMS = 'Claims'
    NUTRITION = 'Nutrition'

class RegulationStandard(str, Enum):
    FDA = 'FDA'
    FSSAI = 'FSSAI'
    EU_FIC = 'EU_FIC'
    GENERAL = 'GENERAL'

class RegulatoryRequirement(BaseModel):
    id: str
    name: str
    description: str
    category: RuleCategory
    mandatory: bool
    checkPoints: List[str]
    commonViolations: List[str]
    legalReference: Optional[str] = None

class AllergenInfo(BaseModel):
    name: str
    alternateNames: List[str]
    declarationFormat: str

class SymbolRequirement(BaseModel):
    name: str
    description: str
    specifications: str
    placement: str
    mandatory: bool

class NutrientDeclaration(BaseModel):
    nutrient: str
    unit: str
    mandatory: bool
    order: Optional[int] = None
    notes: Optional[str] = None

class RegulatoryBody(BaseModel):
    code: str
    name: str
    fullName: str
    country: str
    website: str
    keyRegulations: List[str]
    requirements: List[RegulatoryRequirement]
    allergens: List[AllergenInfo]
    symbols: List[SymbolRequirement]
    nutrients: List[NutrientDeclaration]
    dateFormats: List[str]
    additionalGuidelines: str

# Request Models
class LabelValidationRequest(BaseModel):
    base64Image: str

class AuditOptions(BaseModel):
    standard: str = 'FSSAI'
    categories: List[RuleCategory]
    detectedCategoryType: Optional[str] = None
    detectedSpecialCategory: Optional[str] = None
    detectedCategoryCode: Optional[str] = None
    customContext: Optional[str] = None

class Panel(BaseModel):
    id: str
    viewType: str
    imageData: str # base64
    pageNumber: Optional[int] = None

class MultiPanelAnalysisRequest(BaseModel):
    panels: List[Panel]
    options: AuditOptions

class SinglePanelAnalysisRequest(BaseModel):
    base64Image: str
    options: AuditOptions
    panelCount: int = 1
    panelOffsets: Optional[list] = None

# Alias for route compatibility
AnalysisRequest = SinglePanelAnalysisRequest

# Response Models
class Coordinate(BaseModel):
    x: float = 0
    y: float = 0

class ExtractedMetadata(BaseModel):
    brandName: str
    productName: str
    fssaiCategory: str
    licenseNo: str
    sampleType: Optional[str] = None
    pdpArea: Optional[str] = None
    nablReportId: Optional[str] = None
    claimsBasis: Optional[str] = None
    productCompliant: Optional[bool] = None
    categoryCompliant: Optional[bool] = None

class BoundingBox(BaseModel):
    ymin: float
    xmin: float
    ymax: float
    xmax: float

class ComplianceRule(BaseModel):
    id: str
    category: str
    name: str
    description: str
    status: CheckStatus
    feedback: str
    clauseRef: Optional[str] = None
    clause: Optional[str] = None
    location: Optional[Coordinate] = None
    boundingBox: Optional[BoundingBox] = None
    panelIndex: Optional[int] = None

class LabTestSuggestion(BaseModel):
    testName: str
    category: str
    price: Optional[float] = None
    price_low: Optional[float] = None
    price_high: Optional[float] = None
    description: str
    relatedChecks: List[str]
    priority: Literal['Critical', 'Recommended', 'Optional']

class AnalysisResult(BaseModel):
    overallScore: float
    status: Literal['Compliant', 'Non-Compliant', 'Needs Review']
    checks: List[ComplianceRule]
    suggestedLabTests: Optional[List[LabTestSuggestion]] = None
    summary: str
    extractedMetadata: Optional[ExtractedMetadata] = None

class LabelValidationResult(BaseModel):
    isLabel: bool
    confidence: float
    labelType: Optional[str] = None
    reason: str
    detectedCategoryType: Optional[str] = None
    detectedCategoryCode: Optional[str] = None
    detectedSpecialCategory: Optional[str] = None
    categoryConfidence: Optional[float] = None

class NutritionTableEntry(BaseModel):
    nutrient: str
    per_100g: str
    per_serve: Optional[str] = None
    unit: str

class ServingsInfo(BaseModel):
    serving_size: Optional[str] = None
    servings_per_container: Optional[str] = None

class ExtractedClaim(BaseModel):
    text: str
    type: Literal["Nutritional Claim", "Health Claim", "Ingredient Claim"]

class ClaimsExtractionResult(BaseModel):
    nutrition_table: List[NutritionTableEntry]
    ingredients: List[str]
    allergens: List[str]
    servings: ServingsInfo
    claims: List[ExtractedClaim]

class ClaimVerdict(BaseModel):
    claim_text: str
    tag: Literal["Nutritional Claim", "Health Claim", "Ingredient Claim"]
    status: Literal['Complies', 'Fail', 'Action']
    reasoning: str
    reference: str

class ClaimsAnalysisResult(BaseModel):
    extraction: ClaimsExtractionResult
    verdicts: List[ClaimVerdict]
    summary: str
