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

    # IU → metric
    if fu == "IU" and nkey in _IU_CONVERSIONS:
        conv = _IU_CONVERSIONS[nkey]
        for metric_unit, factor in conv.items():
            if metric_unit == tu:
                return amount * factor
            if metric_unit in _METRIC_FACTORS and tu in _METRIC_FACTORS[metric_unit]:
                return amount * factor * _METRIC_FACTORS[metric_unit][tu]

    # metric → IU
    if tu == "IU" and nkey in _IU_CONVERSIONS:
        conv = _IU_CONVERSIONS[nkey]
        for metric_unit, factor in conv.items():
            if metric_unit == fu:
                return amount / factor
            if fu in _METRIC_FACTORS and metric_unit in _METRIC_FACTORS[fu]:
                return (amount * _METRIC_FACTORS[fu][metric_unit]) / factor

    # General metric ↔ metric
    if fu in _METRIC_FACTORS and tu in _METRIC_FACTORS[fu]:
        return amount * _METRIC_FACTORS[fu][tu]

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
        
        # Load from the root data directory
        self._data_dir = Path(__file__).resolve().parent.parent / "data"
        
        self._fixed_data = self._load_json("fixed_rda_constant.json")
        self._varying_data = self._load_json("varying_rda_constant.json")
        self._current_rda = self._get_rda_for_demographic()

    def _load_json(self, filename: str) -> Dict[str, Any]:
        """Load JSON file from data directory"""
        data_path = self._data_dir / filename
        try:
            if data_path.exists():
                with open(data_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            else:
                logger.warning(f"RDA JSON file not found: {data_path}")
                return {}
        except Exception as e:
            logger.error(f"Error loading {filename}: {e}")
            return {}

    def _get_rda_for_demographic(self) -> Dict[str, Any]:
        """
        Get RDA values for the current demographic setting.
        """
        base_rda = {}
        fixed_rda = self._fixed_data.get("RDA", {})
        for nutrient, value in fixed_rda.items():
            if isinstance(value, dict) and "rda_constant" in value:
                base_rda[nutrient] = value

        varying_root = self._varying_data.get("RDA", {})
        gender_data = varying_root.get(self.gender, varying_root.get("men", {}))

        target_data = {}
        if self.activity_level in gender_data:
            target_data = gender_data[self.activity_level]
        elif "sedentary" in gender_data:
            target_data = gender_data["sedentary"]
        else:
            for key, val in gender_data.items():
                if isinstance(val, dict):
                    target_data = val
                    break

        if target_data:
            first_val = next(iter(target_data.values()), None)
            if first_val and isinstance(first_val, dict) and "rda_constant" not in first_val:
                if (self.gender == "women" and self.activity_level == "pregnant" and self.specific_period == "1st_trimester"):
                    sedentary_data = gender_data.get("sedentary") if isinstance(gender_data, dict) else None
                    if isinstance(sedentary_data, dict) and sedentary_data:
                        target_data = sedentary_data
                
                if self.specific_period and self.specific_period in target_data:
                    target_data = target_data[self.specific_period]
                else:
                    default_subkeys = {"pregnant": "2nd_trimester", "lactation": "zero_six_months"}
                    subkey = default_subkeys.get(self.activity_level)
                    if subkey and subkey in target_data:
                        target_data = target_data[subkey]
                    else:
                        if target_data:
                            target_data = next(iter(target_data.values()), {})

        for nutrient, value in target_data.items():
            if isinstance(value, dict) and "rda_constant" in value:
                base_rda[nutrient] = value

        return base_rda

    def get_rda_value(self, nutrient: str) -> Optional[RDAValue]:
        nutrient_key = nutrient.lower().replace(" ", "_")
        value = self._current_rda.get(nutrient_key)
        if value and isinstance(value, dict) and "rda_constant" in value:
            return RDAValue(rda_constant=value["rda_constant"], unit=value.get("unit", ""))
        return None

    def calculate_rda_percentage(self, nutrient: str, amount: float, amount_unit: Optional[str] = None) -> Optional[float]:
        rda = self.get_rda_value(nutrient)
        if not rda or rda.rda_constant <= 0:
            return None

        effective_amount = amount
        if amount_unit and rda.unit:
            if _normalize_unit(amount_unit) != _normalize_unit(rda.unit):
                converted = _convert_amount(nutrient, amount, amount_unit, rda.unit)
                if converted is not None:
                    effective_amount = converted

        return round((effective_amount / rda.rda_constant) * 100, 1)

    def calculate_all_from_entries(self, entries: List[NutritionTableEntry]) -> Dict[str, Dict[str, Any]]:
        results = {}
        for entry in entries:
            key = entry.nutrient.lower().replace(" ", "_")
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
            
            try:
                # V4 specific parsing: per_100g is a string
                amount_str = entry.per_100g.replace(",", "").strip()
                # Remove any non-numeric chars except decimal
                amount_cleaned = "".join(c for c in amount_str if c.isdigit() or c == '.')
                amount = float(amount_cleaned) if amount_cleaned else 0.0
            except:
                amount = 0.0
                
            rda_percentage = self.calculate_rda_percentage(key, amount, entry.unit)
            rda = self.get_rda_value(key)
            
            results[key] = {
                "rda_percentage": rda_percentage,
                "rda": rda.rda_constant if rda else None,
                "rda_unit": rda.unit if rda else None,
                "amount": amount,
                "unit": entry.unit,
                "original_name": entry.nutrient
            }
        return results
