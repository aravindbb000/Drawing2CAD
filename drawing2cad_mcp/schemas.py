"""
Pydantic schemas for the Drawing2CAD intermediate representation, review flags,
and validation reports.
"""

from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field


class PartMetadata(BaseModel):
    name: str = Field(..., description="Part name from title block or file")
    drawing_number: Optional[str] = None
    revision: Optional[str] = "A"
    units: str = "mm"
    scale: Optional[str] = "1:1"
    material: Optional[str] = None
    projection: Literal["first_angle", "third_angle", "unknown"] = "first_angle"


class DimensionItem(BaseModel):
    value: float
    unit: str = "mm"
    tolerance_plus: float = 0.0
    tolerance_minus: float = 0.0
    source_view: Optional[str] = None
    confidence: float = 1.0
    assumed: bool = False
    assumption_reason: Optional[str] = None


class FeatureItem(BaseModel):
    id: str = Field(..., description="Unique feature identifier, e.g., F001")
    type: Literal[
        "extrude", "revolve", "hole", "pocket", "slot", "fillet", "chamfer", "shell", "pattern"
    ]
    description: str
    parameters: Dict[str, Any]
    source_view: Optional[str] = None
    confidence: float = 1.0
    assumed: bool = False
    assumption_reason: Optional[str] = None


class ReviewFlag(BaseModel):
    id: str = Field(..., description="Flag identifier, e.g., R001")
    severity: Literal["critical", "warning", "info"] = "warning"
    feature_id: Optional[str] = None
    parameter: Optional[str] = None
    message: str
    assumed_value: Optional[Any] = None
    must_verify: bool = True
    verified: bool = False


class BuildStrategy(BaseModel):
    base_operation: Literal["extrude", "revolve", "sweep", "loft"]
    operation_sequence: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class PartIntermediateRepresentation(BaseModel):
    part: PartMetadata
    overall_dimensions: Dict[str, DimensionItem] = Field(default_factory=dict)
    features: List[FeatureItem] = Field(default_factory=list)
    review_flags: List[ReviewFlag] = Field(default_factory=list)
    build_strategy: BuildStrategy


class DimensionCheckResult(BaseModel):
    feature: str
    expected: float
    actual: float
    delta: float
    tolerance: float = 0.05
    passed: bool


class ValidationReport(BaseModel):
    is_closed_solid: bool
    is_geometrically_valid: bool
    bounding_box: Dict[str, float]
    volume: float
    step_reimport_valid: bool
    step_reimport_volume: Optional[float] = None
    dimension_checks: List[DimensionCheckResult] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    overall_pass: bool
