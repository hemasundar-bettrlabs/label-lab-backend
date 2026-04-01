"""
RDA (Recommended Daily Allowance) Calculator Service
Adapted for Label Validator V4
"""
import logging
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from app.models.schemas import NutritionTableEntry


logger = logging.getLogger(__name__)


@dataclass
class RDAValue:
    """Represents a single RDA value with its unit"""
    rda_constant: float
    unit: str


def _normalize_unit(unit: str) -> str:
    """Normalize unit string for comparison."""
    u = (unit or "").lower().strip().replace("/d", "").replace(" ", "")
    if u in ("mcg", "ug", "µg"):
        return "µg"
    if u in ("iu",):
        return "IU"
    return u

# Nutrient-specific IU ↔ metric conversion factors
# 1 IU of vitamin_d = 0.025 µg, 1 IU vitamin_a = 0.3 µg RAE, 1 IU vitamin_e = 0.67 mg
_IU_CONVERSIONS: Dict[str, Dict[str, float]] = {
    "vitamin_d": {"µg": 0.025},
    "vitamin_a": {"µg": 0.3},
    "vitamin_e": {"mg": 0.67},
}

_METRIC_FACTORS: Dict[str, Dict[str, float]] = {
    "g":  {"mg": 1000, "µg": 1_000_000},
    "mg": {"g": 0.001, "µg": 1000},
    "µg": {"g": 0.000001, "mg": 0.001},
}

def _convert_amount(nutrient: str, amount: float, from_unit: str, to_unit: str) -> Optional[float]:
    """Convert nutrient amount between units (IU, g, mg, µg)."""
    fu = _normalize_unit(from_unit)
    tu = _normalize_unit(to_unit)
    if fu == tu:
        return amount

    nkey = nutrient.lower().replace(" ", "_")
    logger.debug(f"[RDA] Unit conversion: '{nutrient}' | {amount}{from_unit} ({fu}) -> {to_unit} ({tu})")

    # IU → metric
    if fu == "IU" and nkey in _IU_CONVERSIONS:
        conv = _IU_CONVERSIONS[nkey]
        for metric_unit, factor in conv.items():
            if metric_unit == tu:
                result = amount * factor
                logger.debug(f"[RDA] IU->metric: {amount}IU * {factor} = {result}{tu}")
                return result
            if metric_unit in _METRIC_FACTORS and tu in _METRIC_FACTORS[metric_unit]:
                result = amount * factor * _METRIC_FACTORS[metric_unit][tu]
                logger.debug(f"[RDA] IU->metric->metric: {amount}IU * {factor} * {_METRIC_FACTORS[metric_unit][tu]} = {result}{tu}")
                return result

    # metric → IU
    if tu == "IU" and nkey in _IU_CONVERSIONS:
        conv = _IU_CONVERSIONS[nkey]
        for metric_unit, factor in conv.items():
            if metric_unit == fu:
                result = amount / factor
                logger.debug(f"[RDA] metric->IU: {amount}{fu} / {factor} = {result}IU")
                return result
            if fu in _METRIC_FACTORS and metric_unit in _METRIC_FACTORS[fu]:
                result = (amount * _METRIC_FACTORS[fu][metric_unit]) / factor
                logger.debug(f"[RDA] metric->metric->IU: ({amount}{fu} * {_METRIC_FACTORS[fu][metric_unit]}) / {factor} = {result}IU")
                return result

    # General metric ↔ metric
    if fu in _METRIC_FACTORS and tu in _METRIC_FACTORS[fu]:
        result = amount * _METRIC_FACTORS[fu][tu]
        logger.debug(f"[RDA] metric->metric: {amount}{fu} * {_METRIC_FACTORS[fu][tu]} = {result}{tu}")
        return result

    logger.warning(f"[RDA] Conversion failed: '{nutrient}' | No conversion path from {from_unit} to {to_unit}")
    return None


class RDACalculator:
    """
    Calculator for Recommended Daily Allowance percentages.
    Supports different demographics (men/women) and activity levels.
    """

    def __init__(self, gender: str = "men", activity_level: str = "sedentary", specific_period: Optional[str] = None):
        """
        Initialize the RDA Calculator with demographic settings.
        """
        self.gender = gender.lower() if gender else "men"
        self.activity_level = activity_level.lower() if activity_level else "sedentary"
        self.specific_period = specific_period.lower() if specific_period else None
        
        logger.info(f"[RDA] Initializing RDACalculator | Gender: {self.gender} | Activity: {self.activity_level} | Period: {self.specific_period}")
        
        # Load from the root data directory
        self._data_dir = Path(__file__).resolve().parent.parent / "data"
        logger.debug(f"[RDA] Data directory: {self._data_dir}")
        
        self._fixed_data = self._load_json("fixed_rda_constant.json")
        self._varying_data = self._load_json("varying_rda_constant.json")
        
        logger.debug(f"[RDA] Fixed RDA nutrients loaded: {len(self._fixed_data.get('RDA', {}))} nutrients")
        logger.debug(f"[RDA] Varying RDA structure keys: {list(self._varying_data.get('RDA', {}).keys())}")
        
        self._current_rda = self._get_rda_for_demographic()
        logger.info(f"[RDA] RDA context initialized with {len(self._current_rda)} nutrients for demographic: {self.gender}/{self.activity_level}")

    def _load_json(self, filename: str) -> Dict[str, Any]:
        """Load JSON file from data directory"""
        data_path = self._data_dir / filename
        try:
            if data_path.exists():
                with open(data_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                logger.debug(f"[RDA] Successfully loaded {filename} | Path: {data_path} | Size: {len(data)} keys")
                return data
            else:
                logger.warning(f"[RDA] JSON file not found: {data_path}")
                return {}
        except Exception as e:
            logger.error(f"[RDA] Error loading {filename} from {data_path}: {type(e).__name__}: {e}")
            return {}

    def _get_rda_for_demographic(self) -> Dict[str, Any]:
        """
        Get RDA values for the current demographic setting.
        """
        logger.debug(f"[RDA] Getting RDA for demographic: gender={self.gender}, activity_level={self.activity_level}, specific_period={self.specific_period}")
        
        base_rda = {}
        
        # Load fixed RDA values (nutrients that don't vary by demographic)
        fixed_rda = self._fixed_data.get("RDA", {})
        for nutrient, value in fixed_rda.items():
            if isinstance(value, dict) and "rda_constant" in value:
                base_rda[nutrient] = value
        logger.debug(f"[RDA] Loaded {len(base_rda)} fixed RDA nutrients")

        # Load varying RDA values (nutrients that vary by gender/activity level)
        varying_root = self._varying_data.get("RDA", {})
        logger.debug(f"[RDA] Varying RDA available genders: {list(varying_root.keys())}")
        
        gender_data = varying_root.get(self.gender, varying_root.get("men", {}))
        logger.debug(f"[RDA] Selected gender data for '{self.gender}' | Available activity levels: {list(gender_data.keys()) if isinstance(gender_data, dict) else 'N/A'}")

        target_data = {}
        if self.activity_level in gender_data:
            target_data = gender_data[self.activity_level]
            logger.debug(f"[RDA] Found activity level '{self.activity_level}' in gender data")
        elif "sedentary" in gender_data:
            target_data = gender_data["sedentary"]
            logger.debug(f"[RDA] Activity level '{self.activity_level}' not found, falling back to 'sedentary'")
        else:
            for key, val in gender_data.items():
                if isinstance(val, dict):
                    target_data = val
                    logger.debug(f"[RDA] Using first available activity level: '{key}'")
                    break

        if target_data:
            first_val = next(iter(target_data.values()), None)
            if first_val and isinstance(first_val, dict) and "rda_constant" not in first_val:
                logger.debug(f"[RDA] Target data contains nested structure (not direct RDA constants)")
                
                if (self.gender == "women" and self.activity_level == "pregnant" and self.specific_period == "1st_trimester"):
                    sedentary_data = gender_data.get("sedentary") if isinstance(gender_data, dict) else None
                    if isinstance(sedentary_data, dict) and sedentary_data:
                        target_data = sedentary_data
                        logger.debug(f"[RDA] Special case: pregnant women 1st_trimester, using sedentary data as base")
                
                if self.specific_period and self.specific_period in target_data:
                    target_data = target_data[self.specific_period]
                    logger.debug(f"[RDA] Found specific_period '{self.specific_period}' in target data")
                else:
                    default_subkeys = {"pregnant": "2nd_trimester", "lactation": "zero_six_months"}
                    subkey = default_subkeys.get(self.activity_level)
                    if subkey and subkey in target_data:
                        target_data = target_data[subkey]
                        logger.debug(f"[RDA] Using default subkey '{subkey}' for activity level '{self.activity_level}'")
                    else:
                        if target_data:
                            target_data = next(iter(target_data.values()), {})
                            logger.debug(f"[RDA] Using first available subkey from target data")

        # Merge varying RDA into base_rda
        for nutrient, value in target_data.items():
            if isinstance(value, dict) and "rda_constant" in value:
                base_rda[nutrient] = value
                
        logger.info(f"[RDA] Final RDA context compiled: {len(base_rda)} total nutrients")
        logger.debug(f"[RDA] RDA nutrients: {list(base_rda.keys())}")
        
        return base_rda

    def get_rda_value(self, nutrient: str) -> Optional[RDAValue]:
        nutrient_key = nutrient.lower().replace(" ", "_")
        value = self._current_rda.get(nutrient_key)
        if value and isinstance(value, dict) and "rda_constant" in value:
            rda_val = RDAValue(rda_constant=value["rda_constant"], unit=value.get("unit", ""))
            logger.debug(f"[RDA] get_rda_value('{nutrient}') -> Key: '{nutrient_key}' | RDA: {rda_val.rda_constant}{rda_val.unit}")
            return rda_val
        logger.debug(f"[RDA] get_rda_value('{nutrient}') -> Key: '{nutrient_key}' | Not found in RDA context")
        return None

    def calculate_rda_percentage(self, nutrient: str, amount: float, amount_unit: Optional[str] = None) -> Optional[float]:
        logger.debug(f"[RDA] calculate_rda_percentage(nutrient='{nutrient}', amount={amount}, unit='{amount_unit}')")
        
        rda = self.get_rda_value(nutrient)
        if not rda:
            logger.debug(f"[RDA] {nutrient}: RDA value not found, returning None")
            return None
        
        if rda.rda_constant <= 0:
            logger.warning(f"[RDA] {nutrient}: Invalid RDA constant {rda.rda_constant}, returning None")
            return None

        effective_amount = amount
        if amount_unit and rda.unit:
            if _normalize_unit(amount_unit) != _normalize_unit(rda.unit):
                converted = _convert_amount(nutrient, amount, amount_unit, rda.unit)
                if converted is not None:
                    logger.debug(f"[RDA] {nutrient}: Unit conversion | {amount}{amount_unit} -> {converted}{rda.unit}")
                    effective_amount = converted
                else:
                    logger.warning(f"[RDA] {nutrient}: Could not convert {amount_unit} to {rda.unit}, using original amount")

        percentage = round((effective_amount / rda.rda_constant) * 100, 1)
        logger.debug(f"[RDA] {nutrient}: Calculation | Amount: {effective_amount}{rda.unit} / RDA: {rda.rda_constant}{rda.unit} = {percentage}%")
        
        return percentage

    def calculate_all_from_entries(self, entries: List[NutritionTableEntry]) -> Dict[str, Dict[str, Any]]:
        logger.info(f"[RDA] calculate_all_from_entries: Processing {len(entries)} nutrition entries")
        
        results = {}
        for idx, entry in enumerate(entries):
            key = entry.nutrient.lower().replace(" ", "_")
            original_key = key
            
            # Normalize nutrient key names
            if key in ["carbohydrate"]: key = "total_carbohydrate"
            elif key in ["sugar"]: key = "total_sugars"
            elif key in ["fiber"]: key = "dietary_fiber"
            elif key in ["fat"]: key = "total_fat"
            elif key in ["vitamin_b1"]: key = "thiamine"
            elif key in ["vitamin_b2"]: key = "riboflavin"
            elif key in ["vitamin_b3"]: key = "niacin"
            elif key in ["vitamin_b5"]: key = "pantothenic_acid"
            elif key in ["vitamin_b7"]: key = "biotin"
            elif key in ["vitamin_b9"]: key = "folate"
            elif key in ["phosphorus"]: key = "phosphorous"
            
            if key != original_key:
                logger.debug(f"[RDA] Entry {idx}: Nutrient key normalized '{original_key}' -> '{key}'")
            
            try:
                # V4 specific parsing: per_100g is a string
                amount_str = entry.per_100g.replace(",", "").strip()
                # Remove any non-numeric chars except decimal
                amount_cleaned = "".join(c for c in amount_str if c.isdigit() or c == '.')
                amount = float(amount_cleaned) if amount_cleaned else 0.0
                logger.debug(f"[RDA] Entry {idx} ({entry.nutrient}): Parsed amount | Raw: '{entry.per_100g}' -> Cleaned: '{amount_cleaned}' -> Float: {amount}")
            except Exception as e:
                amount = 0.0
                logger.warning(f"[RDA] Entry {idx} ({entry.nutrient}): Failed to parse amount '{entry.per_100g}': {e}")
                
            rda_percentage = self.calculate_rda_percentage(key, amount, entry.unit)
            rda = self.get_rda_value(key)
            
            result_entry = {
                "rda_percentage": rda_percentage,
                "rda": rda.rda_constant if rda else None,
                "rda_unit": rda.unit if rda else None,
                "amount": amount,
                "unit": entry.unit,
                "original_name": entry.nutrient
            }
            results[key] = result_entry
            
            logger.info(f"[RDA] Entry {idx}: {entry.nutrient} (key:{key}) | Amount: {amount}{entry.unit} | RDA%: {rda_percentage}% | RDA: {rda.rda_constant if rda else 'N/A'}{rda.unit if rda else ''}")
        
        logger.info(f"[RDA] calculate_all_from_entries completed: {len(results)} nutrients processed")
        return results
