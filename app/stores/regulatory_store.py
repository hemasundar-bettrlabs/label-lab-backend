from app.models.schemas import (
    RegulatoryBody, RegulatoryRequirement, AllergenInfo, SymbolRequirement, 
    NutrientDeclaration, RuleCategory, RegulationStandard
)

# ============================================================================
# FSSAI
# ============================================================================

FSSAI_ALLERGENS = [
    AllergenInfo(name="Cereals containing gluten", alternateNames=["wheat", "rye", "barley", "oats", "spelt", "kamut"], declarationFormat="Contains: [Allergen] or bold in ingredients"),
    AllergenInfo(name="Crustacean", alternateNames=["shrimp", "prawn", "crab", "lobster", "crayfish"], declarationFormat="Contains: [Allergen] or bold in ingredients"),
    AllergenInfo(name="Eggs", alternateNames=["egg", "albumin", "lysozyme", "mayonnaise", "meringue"], declarationFormat="Contains: [Allergen] or bold in ingredients"),
    AllergenInfo(name="Fish", alternateNames=["fish", "fish sauce", "fish oil", "anchovy", "sardine"], declarationFormat="Contains: [Allergen] or bold in ingredients"),
    AllergenInfo(name="Peanuts", alternateNames=["peanut", "groundnut", "arachis oil", "monkey nuts"], declarationFormat="Contains: [Allergen] or bold in ingredients"),
    AllergenInfo(name="Soybeans", alternateNames=["soy", "soya", "soy lecithin", "tofu", "edamame"], declarationFormat="Contains: [Allergen] or bold in ingredients"),
    AllergenInfo(name="Milk", alternateNames=["milk", "cream", "butter", "cheese", "whey", "casein", "lactose", "ghee", "paneer"], declarationFormat="Contains: [Allergen] or bold in ingredients"),
    AllergenInfo(name="Tree nuts", alternateNames=["almonds", "cashews", "walnuts", "pistachios", "hazelnuts", "macadamia", "pecans", "brazil nuts"], declarationFormat="Contains: [Allergen] or bold in ingredients"),
    AllergenInfo(name="Sulphites", alternateNames=["sulphite", "sulfite", "sulphur dioxide", "SO2", "E220-E228"], declarationFormat="Must declare if >=10 mg/kg concentration"),
]

FSSAI_SYMBOLS = [
    SymbolRequirement(
        name="Vegetarian Symbol",
        description="Green filled circle inside a green square outline",
        specifications="Circle diameter should be minimum 3mm for packages up to 100cm2, minimum 5mm for larger packages. Square outline must be clearly visible.",
        placement="Must be displayed prominently on the Principal Display Panel, near the product name",
        mandatory=True
    ),
    SymbolRequirement(
        name="Non-Vegetarian Symbol",
        description="Brown filled triangle inside a brown square outline",
        specifications="Triangle should have equal sides, minimum 3mm for packages up to 100cm2, minimum 5mm for larger packages. Square outline must be clearly visible.",
        placement="Must be displayed prominently on the Principal Display Panel, near the product name",
        mandatory=True
    ),
    SymbolRequirement(
        name="FSSAI Logo",
        description="Official FSSAI logo with License Number",
        specifications="Logo must be clearly visible with 'Lic. No.' followed by 14-digit license number. Format: FSSAI Logo + 'Lic. No. XXXXXXXXXXXXXX'",
        placement="Must be on the label, preferably on Principal Display Panel",
        mandatory=True
    ),
    SymbolRequirement(
        name="Not for Human Consumption Symbol",
        description="Black cross within a square outlined in black",
        specifications="For non-food retail items like Pooja water, Ghee for diya, Pooja oil",
        placement="Prominently displayed on package",
        mandatory=True
    )
]

FSSAI_NUTRIENTS = [
    NutrientDeclaration(nutrient="Energy", unit="kcal", mandatory=True, order=1, notes="Must be expressed in kcal per 100g/100ml and per serve"),
    NutrientDeclaration(nutrient="Protein", unit="g", mandatory=True, order=2),
    NutrientDeclaration(nutrient="Carbohydrate", unit="g", mandatory=True, order=3),
    NutrientDeclaration(nutrient="Total Sugars", unit="g", mandatory=True, order=4, notes="Subset of carbohydrates"),
    NutrientDeclaration(nutrient="Added Sugars", unit="g", mandatory=True, order=5, notes="Must be declared separately from total sugars"),
    NutrientDeclaration(nutrient="Total Fat", unit="g", mandatory=True, order=6),
    NutrientDeclaration(nutrient="Saturated Fat", unit="g", mandatory=True, order=7, notes="Subset of total fat"),
    NutrientDeclaration(nutrient="Trans Fat", unit="g", mandatory=True, order=8, notes="Subset of total fat"),
    NutrientDeclaration(nutrient="Cholesterol", unit="mg", mandatory=False, order=9),
    NutrientDeclaration(nutrient="Sodium", unit="mg", mandatory=True, order=10),
    NutrientDeclaration(nutrient="Dietary Fibre", unit="g", mandatory=False, order=11),
]

FSSAI_REQUIREMENTS = [
    RegulatoryRequirement(
        id="FSSAI-001",
        name="Name of Food",
        description="The name of food shall be clear, prominent, and indicate the true nature of the food",
        category=RuleCategory.LEGAL,
        mandatory=True,
        checkPoints=[
            "Name must be clear and concise",
            "Printed in easily understandable font",
            "Must correspond to the classification/nature of food",
            "Should not be misleading",
            "Brand name should not substitute the common/generic name"
        ],
        commonViolations=[
            "Using only brand name without generic food name",
            "Misleading names that don't reflect actual product",
            "Font too small or illegible"
        ],
        legalReference="FSS (Packaging and Labelling) Regulations, 2011"
    ),
    RegulatoryRequirement(
        id="FSSAI-002",
        name="List of Ingredients",
        description="Complete list of ingredients in descending order of composition by weight",
        category=RuleCategory.INGREDIENTS,
        mandatory=True,
        checkPoints=[
            "Heading 'Ingredients' or 'List of Ingredients' must be present",
            "Listed in descending order by weight at time of manufacture",
            "All ingredients must be disclosed including additives",
            "Class names (e.g., 'Emulsifier') must be followed by specific names or INS numbers",
            "Compound ingredients must list their sub-ingredients",
            "Water must be declared if added as ingredient"
        ],
        commonViolations=[
            "Missing ingredient heading",
            "Ingredients not in descending order",
            "Additives without INS numbers",
            "Missing sub-ingredients of compound ingredients"
        ],
        legalReference="FSS (Packaging and Labelling) Regulations, 2011 - Regulation 2.2.2"
    ),
    RegulatoryRequirement(
        id="FSSAI-003",
        name="Nutritional Information",
        description="Nutritional information per 100g/100ml and per serve",
        category=RuleCategory.REGULATORY,
        mandatory=True,
        checkPoints=[
            "Title 'Nutritional Information' or 'Nutrition Facts' must be present",
            "Values per 100g or 100ml must be declared",
            "Values per serve should also be declared with serve size",
            "Energy must be in kcal (kilojoules optional)",
            "All mandatory nutrients must be listed in correct order",
            "Percent Daily Value (%DV) based on 2000 kcal diet recommended"
        ],
        commonViolations=[
            "Missing mandatory nutrients",
            "Incorrect units (kJ instead of kcal)",
            "No per-serve information",
            "Missing serve size declaration"
        ],
        legalReference="FSS (Packaging and Labelling) Regulations, 2011 - Schedule II"
    ),
    RegulatoryRequirement(
        id="FSSAI-004",
        name="Veg/Non-Veg Declaration",
        description="Mandatory symbol indicating vegetarian or non-vegetarian food",
        category=RuleCategory.REGULATORY,
        mandatory=True,
        checkPoints=[
            "Symbol must be prominently displayed",
            "Green circle in green square for vegetarian",
            "Brown triangle in brown square for non-vegetarian",
            "Must be near the product name on Principal Display Panel",
            "Size must be clearly visible (min 3mm for small packs, 5mm for larger)",
            "Colors must be accurate (green or brown, not faded)"
        ],
        commonViolations=[
            "Symbol missing",
            "Wrong color used",
            "Symbol too small",
            "Symbol placed in obscure location",
            "Faded or unclear symbol"
        ],
        legalReference="FSS (Packaging and Labelling) Regulations, 2011 - Regulation 2.2.2(4)"
    ),
    RegulatoryRequirement(
        id="FSSAI-005",
        name="FSSAI Logo and License Number",
        description="FSSAI logo with 14-digit license number",
        category=RuleCategory.REGULATORY,
        mandatory=True,
        checkPoints=[
            "Official FSSAI logo must be displayed",
            "License number must be 14 digits",
            "Format: 'Lic. No.' or 'License No.' followed by number",
            "Must be clearly legible",
            "Logo should not be distorted or modified"
        ],
        commonViolations=[
            "Missing FSSAI logo",
            "Incorrect or incomplete license number",
            "Logo distorted or too small",
            "Expired license number"
        ],
        legalReference="FSS (Licensing and Registration) Regulations, 2011"
    ),
     RegulatoryRequirement(
        id="FSSAI-006",
        name="Name and Address of Manufacturer/Packer",
        description="Complete name and address of manufacturer, packer, or brand owner",
        category=RuleCategory.LEGAL,
        mandatory=True,
        checkPoints=[
            "Full name of manufacturer/packer/brand owner",
            "Complete postal address with PIN code",
            "For imported foods: Importer's name and address required",
            "Must be legible and in the same field of vision"
        ],
        commonViolations=[
            "Incomplete address",
            "Missing PIN code",
            "Only brand name without company details",
            "Missing importer details for imported products"
        ],
        legalReference="FSS (Packaging and Labelling) Regulations, 2011 - Regulation 2.2.2(1)(v)"
    ),
    RegulatoryRequirement(
        id="FSSAI-007",
        name="Net Quantity Declaration",
        description="Net quantity in metric units as per Legal Metrology Act",
        category=RuleCategory.LEGAL,
        mandatory=True,
        checkPoints=[
            "Net quantity must be declared",
            "Must use metric units (g, kg, ml, L)",
            "Font size must comply with Legal Metrology Act",
            "Must be in the same field of vision as product name",
            "For solid in liquid: Drained weight should also be mentioned"
        ],
        commonViolations=[
            "Font size too small",
            "Non-metric units used",
            "Net quantity not prominent",
            "Missing drained weight for applicable products"
        ],
        legalReference="Legal Metrology (Packaged Commodities) Rules, 2011"
    ),
    RegulatoryRequirement(
        id="FSSAI-008",
        name="Batch/Lot/Code Number",
        description="Batch identification for traceability",
        category=RuleCategory.REGULATORY,
        mandatory=True,
        checkPoints=[
            "Batch No., Lot No., or Code No. must be present",
            "Must be clearly marked with prefix 'Batch No.' or 'Lot No.' or 'Code No.'",
            "Should enable traceability",
            "Can be embossed, stamped, or printed"
        ],
        commonViolations=[
            "Missing batch number",
            "Illegible batch code",
            "No prefix identifying it as batch/lot number"
        ],
        legalReference="FSS (Packaging and Labelling) Regulations, 2011 - Regulation 2.2.2(1)(viii)"
    ),
    RegulatoryRequirement(
        id="FSSAI-009",
        name="Date Marking",
        description="Manufacturing date and expiry/best before date",
        category=RuleCategory.REGULATORY,
        mandatory=True,
        checkPoints=[
            "Date of Manufacture or Packaging - MANDATORY",
            "Best Before or Use By/Expiry Date - MANDATORY",
            "Format should be clear (DD/MM/YYYY or MM/YYYY)",
            "Month should be in words or numbers (not ambiguous)",
            "Dates must be in same field of vision",
            "Must not be altered or tampered"
        ],
        commonViolations=[
            "Missing manufacture date",
            "Missing expiry date",
            "Ambiguous date format",
            "Dates not clearly visible",
            "Tampered or overprinted dates"
        ],
        legalReference="FSS (Packaging and Labelling) Regulations, 2011 - Regulation 2.2.2(1)(vii)"
    ),
    RegulatoryRequirement(
        id="FSSAI-010",
        name="Food Additives Declaration",
        description="Declaration of all food additives with class name and specific name/INS number",
        category=RuleCategory.INGREDIENTS,
        mandatory=True,
        checkPoints=[
            "All additives must be declared in ingredient list",
            "Class name required (e.g., 'Preservative', 'Emulsifier', 'Colour')",
            "Specific name or INS number in parentheses",
            "Format: Class Name (Specific Name or INS No.)",
            "Colors must use specific names or numbers"
        ],
        commonViolations=[
            "Missing class names",
            "Missing INS numbers",
            "Undeclared additives",
            "Incorrect INS numbers"
        ],
        legalReference="FSS (Food Product Standards and Food Additives) Regulations, 2011"
    ),
    RegulatoryRequirement(
        id="FSSAI-011",
        name="Allergen Declaration",
        description="Declaration of common food allergens",
        category=RuleCategory.INGREDIENTS,
        mandatory=True,
        checkPoints=[
            "All allergens must be declared",
            "'Contains:' statement or emphasized in ingredients",
            "Allergens should be highlighted (bold, different color, or underline)",
            "Must include: cereals with gluten, crustacean, eggs, fish, peanuts, soybeans, milk, tree nuts",
            "Sulphites must be declared if >=10 mg/kg",
            "'May contain' for cross-contamination risks"
        ],
        commonViolations=[
            "Allergens not highlighted",
            "Missing allergen declaration",
            "Incomplete allergen list",
            "Missing 'may contain' warnings"
        ],
        legalReference="FSS (Packaging and Labelling) Regulations, 2011 - Regulation 2.2.2(6)"
    ),
    RegulatoryRequirement(
        id="FSSAI-012",
        name="Country of Origin (Imported Foods)",
        description="Declaration of country of origin for imported foods",
        category=RuleCategory.LEGAL,
        mandatory=True,
        checkPoints=[
            "Country of Origin must be declared for imported foods",
            "Importer's name and address in India required",
            "FSSAI import license number required",
            "Must comply with FSS (Import) Regulations, 2017"
        ],
        commonViolations=[
            "Missing country of origin",
            "Missing importer details",
            "Invalid import license"
        ],
        legalReference="FSS (Import) Regulations, 2017"
    ),
    RegulatoryRequirement(
        id="FSSAI-013",
        name="Instructions for Use",
        description="Usage instructions including storage and reconstitution",
        category=RuleCategory.LEGAL,
        mandatory=False,
        checkPoints=[
            "Storage instructions if special storage required",
            "Reconstitution instructions if applicable",
            "'Refrigerate after opening' if needed",
            "Cooking/heating instructions if required",
            "Should be clear and in consumer-understandable language"
        ],
        commonViolations=[
            "Missing storage instructions for perishables",
            "Incomplete reconstitution instructions",
            "Instructions in foreign language only"
        ],
        legalReference="FSS (Packaging and Labelling) Regulations, 2011 - Regulation 2.2.2(1)(x)"
    ),
    RegulatoryRequirement(
        id="FSSAI-014",
        name="Consumer Care Details",
        description="Customer care contact information",
        category=RuleCategory.LEGAL,
        mandatory=True,
        checkPoints=[
            "Customer care phone number or email",
            "Should be toll-free or local number",
            "Must be functional and responsive"
        ],
        commonViolations=[
            "Missing customer care details",
            "Non-functional contact numbers",
            "No email provided"
        ],
        legalReference="FSS (Packaging and Labelling) Regulations, 2011"
    ),
    RegulatoryRequirement(
        id="FSSAI-015",
        name="MRP (Maximum Retail Price)",
        description="Maximum Retail Price inclusive of all taxes",
        category=RuleCategory.LEGAL,
        mandatory=True,
        checkPoints=[
            "MRP must be declared",
            "Must include 'MRP' or 'Maximum Retail Price'",
            "Must state 'Inclusive of all taxes'",
            "Must be in Indian Rupees",
            "Font size as per Legal Metrology requirements"
        ],
        commonViolations=[
            "Missing MRP",
            "Not stating 'inclusive of all taxes'",
            "Font too small"
        ],
        legalReference="Legal Metrology (Packaged Commodities) Rules, 2011"
    )
]

FSSAI_REGULATIONS = RegulatoryBody(
    code="FSSAI",
    name="FSSAI",
    fullName="Food Safety and Standards Authority of India",
    country="India",
    website="https://www.fssai.gov.in",
    keyRegulations=[
        "Food Safety and Standards Act, 2006",
        "FSS (Packaging and Labelling) Regulations, 2011",
        "FSS (Food Product Standards and Food Additives) Regulations, 2011",
        "FSS (Licensing and Registration) Regulations, 2011",
        "FSS (Import) Regulations, 2017",
        "Legal Metrology (Packaged Commodities) Rules, 2011"
    ],
    requirements=FSSAI_REQUIREMENTS,
    allergens=FSSAI_ALLERGENS,
    symbols=FSSAI_SYMBOLS,
    nutrients=FSSAI_NUTRIENTS,
    dateFormats=["DD/MM/YYYY", "DD-MM-YYYY", "DD MMM YYYY", "MMM YYYY"],
    additionalGuidelines="""
    FSSAI CRITICAL VALIDATION POINTS:
    
    1. VEGETARIAN/NON-VEGETARIAN SYMBOL (MOST CRITICAL):
       - Vegetarian: Green filled circle inside green square outline
       - Non-Vegetarian: Brown filled triangle inside brown square outline
       - Must be prominently placed near product name
       - Minimum size: 3mm for packs <=100cm2, 5mm for larger packs
    
    2. FSSAI LICENSE:
       - Must display official FSSAI logo
       - 14-digit license number format
       - Prefix: "Lic. No." or "License No."
    
    3. NUTRITIONAL INFORMATION:
       - Per 100g/100ml MANDATORY
       - Per serve RECOMMENDED
       - Energy MUST be in kcal
       - Mandatory nutrients: Energy, Protein, Carbohydrate, Total Sugars, Added Sugars, Total Fat, Saturated Fat, Trans Fat, Sodium
    
    4. DATE FORMATS:
       - Manufacturing Date: "Mfg. Date" or "Date of Manufacture" or "Pkg. Date"
       - Expiry: "Best Before" or "Use By" or "Expiry Date"
       - Format: Clearly unambiguous (day before month)
    
    5. ALLERGEN DECLARATION:
       - Must highlight: Cereals with gluten, Crustacean, Eggs, Fish, Peanuts, Soybeans, Milk, Tree nuts
       - Sulphites if >=10 mg/kg
       - Use "Contains:" statement or bold in ingredients
    
    6. ADDITIVES:
       - Format: Class Name (Specific Name or INS XXX)
       - Example: "Preservative (INS 211)" or "Emulsifier (Soy Lecithin)"
    """
)

# ============================================================================
# EXPORT
# ============================================================================

REGULATORY_STORE = {
    "FSSAI": FSSAI_REGULATIONS,
    "FDA": FSSAI_REGULATIONS, # Placeholder - In full prod we'd map FDA too
    "EU_FIC": FSSAI_REGULATIONS, # Placeholder
    "GENERAL": FSSAI_REGULATIONS # Placeholder
}

def get_regulatory_requirements(standard: str) -> RegulatoryBody:
    return REGULATORY_STORE.get(standard, FSSAI_REGULATIONS)

def get_ai_prompt_context(standard: str, categories: list[str]) -> str:
    regulations = REGULATORY_STORE.get(standard, FSSAI_REGULATIONS)
    nl = chr(10)  # Define newline outside f-string to avoid backslash issues
    
    # Filter requirements by active categories
    relevant_requirements = [req for req in regulations.requirements if req.category in categories]
    
    # Build requirement sections
    requirement_blocks = []
    for req in relevant_requirements:
        checkpoints = nl.join([f'  ✓ {cp}' for cp in req.checkPoints])
        violations = nl.join([f'  ⚠ {cv}' for cv in req.commonViolations])
        legal_ref = f'**Legal Reference:** {req.legalReference}' if req.legalReference else ''
        mandatory_tag = '[MANDATORY]' if req.mandatory else '[OPTIONAL]'
        
        block = f'''
### {req.id}: {req.name} {mandatory_tag}
**Description:** {req.description}
**Category:** {req.category}
**Check Points:**
{checkpoints}
**Common Violations:**
{violations}
{legal_ref}
'''
        requirement_blocks.append(block)
    
    regulations_list = nl.join([f'- {r}' for r in regulations.keyRegulations])
    
    prompt = f"""
# {regulations.fullName} ({regulations.country})
## Reference: {regulations.website}

## KEY REGULATIONS:
{regulations_list}

## MANDATORY REQUIREMENTS TO CHECK:
{nl.join(requirement_blocks)}
"""

    if 'Ingredients' in categories and regulations.allergens:
        allergen_lines = []
        for a in regulations.allergens:
            names = ", ".join(a.alternateNames)
            allergen_lines.append(f'- **{a.name}**: {names}')
            allergen_lines.append(f'  Declaration: {a.declarationFormat}')
        allergens_str = nl.join(allergen_lines)
        prompt += f"""
## ALLERGENS TO CHECK (CRITICAL):
{allergens_str}
"""

    if 'Regulatory' in categories and regulations.symbols:
        symbol_lines = []
        for s in regulations.symbols:
            tag = "[MANDATORY]" if s.mandatory else "[IF APPLICABLE]"
            symbol_lines.append(f'- **{s.name}** {tag}')
            symbol_lines.append(f'  {s.description}')
            symbol_lines.append(f'  Specifications: {s.specifications}')
            symbol_lines.append(f'  Placement: {s.placement}')
        symbols_str = nl.join(symbol_lines)
        prompt += f"""
## MANDATORY SYMBOLS TO VERIFY:
{symbols_str}
"""

    if 'Regulatory' in categories and regulations.nutrients:
        mandatory_nutrients = [n for n in regulations.nutrients if n.mandatory]
        nutrient_lines = []
        for n in mandatory_nutrients:
            note = f" - {n.notes}" if n.notes else ""
            nutrient_lines.append(f'{n.order}. {n.nutrient} ({n.unit}){note}')
        nutrients_str = nl.join(nutrient_lines)
        prompt += f"""
## NUTRITION DECLARATION ORDER (VERIFY SEQUENCE):
{nutrients_str}
"""

    prompt += f"""
## ADDITIONAL VALIDATION GUIDELINES:
{regulations.additionalGuidelines}
"""
    return prompt
