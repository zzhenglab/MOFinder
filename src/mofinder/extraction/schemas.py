"""Structured-output schemas for primary MOF synthesis extraction."""

from __future__ import annotations
from typing import List, Optional, Union, Literal
from pydantic import BaseModel, Field, ConfigDict

# Numeric or textual values, retaining the source wording when needed.
NumOrText = Union[float, int, str, None]

class StrictBase(BaseModel):
    # Force additionalProperties: false in the JSON Schema
    model_config = ConfigDict(extra="forbid")

class Reagent(StrictBase):
    """Generic reagent line with original units preserved in amount."""
    name_full: Optional[str] = Field(..., description="Full chemical name as written in the paper, e.g., 'zinc nitrate hexahydrate'.")
    abbreviation: Optional[str] = Field(..., description="Defined in the paper or widely standard, e.g., DMF, EtOH, BDC, BTC. Otherwise leave empty.")
    amount_text: Optional[str] = Field(..., description="Verbatim, original amount or concentration text exactly as reported e.g., '2.0 mmol', '0.25 M, 8 mL'")
    amount_value: Optional[float] = Field(..., description="Numeric if a single mass or mol amount is extractable. If stock solution, convert to mol/mmol or g/mg unit.")
    amount_unit: Optional[str] = Field(..., description="mmol, mg, mol, g etc.")
        
class Solvent(StrictBase):
    name_full: Optional[str] = Field(..., description="Solvent name, e.g., 'N,N-dimethylformamide', 'water'.")
    abbreviation: Optional[str] = Field(..., description="e.g., DMF, H2O, EtOH, MeOH, DEF, DMAc. Leave empty if not standard.")
    amount_text: Optional[str] = Field(..., description="Original text for volume or ratio, e.g., '10 mL', 'DMF/H2O 9:1 v/v'.")
    amount_value_ml: Optional[float] = Field(..., description="Volume in mL if derivable for single solvent and can be convert to ml")
    role: Literal["main","secondary","tertiary","other"] = Field(...)
        
        
class Conditions(StrictBase):
    temperature_c_text: Optional[str] = Field(..., description="Verbtaim phrase or oirginal text or value with unit if explicit. If textual only (e.g., 'reflux', 'RT'), put that string.")
    temperature_c: Optional[float] = Field(..., description="Celsius if numeric")
    time_text: Optional[str] = Field(..., description="Verbtaim phrase or oirginal text for time. Hours/minutes/days if explicit. If textual only (e.g., 'overnight'), put that string.")
    time_h: Optional[float] = Field(..., description="Hours if numeric or converted")
    vessel_type: Optional[str] = Field(..., description="e.g., 'Teflon-lined autoclave', 'glass vial', 'microwave vial', 'mortar and pestle'.")
    stirring: Optional[str] = Field(..., description="e.g., 'stirred', 'static'")

class PostProcessing(StrictBase):
    washing_solvent: Optional[str] = Field(..., description="Short; comma-separated if multiple； e.g., 'DMF， MeOH'.")
    washing_cycles: Optional[str] = Field(..., description="e.g., '3×', 'three times', 'until clear'")
    activation_text: Optional[str] = Field(..., description="Verbatim text, include temperature and time if given, e.g., '120 °C under vacuum for 12 h'.")
    activation_temp_c: Optional[float] = Field(..., description="If numeric converted in degree C")
    activation_time_h: Optional[float] = Field(..., description="If numeric converted in hour")
        
        
class StructureProps(StrictBase):
    topology_code: Optional[str] = Field(..., description="RCSR 3-letter code if reported, e.g., 'pcu', 'dia'. Else leave empty.")
    metal_cluster_connectivity: Optional[str] = Field(..., description="Short phrase, e.g., 'Zr6O4(OH)4 12-connected SBU', 'oxo-bridged rod'.")
    unit_cell_short: Optional[str] = Field(..., description="Keep as one short string, e.g., 'a=25.123(3), b=..., c=..., α=..., β=..., γ=..., Pnma'.")
    pore_diameter_A: Optional[float] = Field(..., description="Pore diameter in Å or aperture if reported. Keep units if textual.")
    BET_surface_area_m2g: Optional[float]  = Field(..., description="BET area if reported. Keep numeric in unit of m2/g.")
    air_stable: Optional[Literal["yes","no","not_reported"]] = Field(..., description="controlled vocab")
    water_stable: Optional[Literal["yes","no","not_reported"]] = Field(..., description="controlled vocab")
    tga_decomposition_temp_c: Optional[float] = Field(..., description="decomposition onset in deg C and numeric if given")
    applications: List[str] = Field(..., description="Short tags (three words max): water_harvesting, CO2_capture, C-H oxidation catalysis, luminescence, sensing, I2 delivery, hydrogen storage, acetylene separation")

class SynthesisRecord(StrictBase):
    # One primary MOF synthesis per item. Exclude postsynthetic modification and composites.
    mof_name: Optional[str] = Field(..., description="Common name, e.g., 'UiO-66', 'MOF-5', 'IRMOF-1'. Leave empty if not given.")
    crystal_code: Optional[str] = Field(..., description="Six-letter/number CCDC code if present ")
    metals: List[Reagent] = Field(..., description="List of metal sources. Include salts, oxides, clusters. Preserve hydration and counterions.")
    linkers: List[Reagent] = Field(..., description="List of organic linkers. Use full name and abbreviation if provided.")
    modulators: List[Reagent] = Field(..., description="Monocarboxylic acids, bases, amines, etc. If a liquid could be both solvent and modulator, treat as modulator here.")
    solvents: List[Solvent] = Field(..., description="Reaction solvents only. Label one as 'main' when obvious from text or majority fraction.")
    conditions: Conditions = Field(..., description="Reaction conditions.")
    post_processing: PostProcessing = Field(..., description="Washing and activation.")
    crystal_morphology: Optional[str] = Field(..., description="color and shape, e.g., 'blue' 'red' 'octahedra', 'rods', 'blocks'.")
    yield_percent: Optional[Union[float, str]] = Field(..., description="Percent if numeric. Else exact wording, e.g., 'quantitative'.")
    crystal_size: Optional[str] = Field(..., description="As reported, e.g., '0.20 × 0.10 × 0.05 mm', '5-10 μm'.")
    structure_properties: StructureProps = Field(..., description="Topological and property lines reported by the authors.")
    reference: str = Field(..., description="DOI string for this synthesis record, e.g., '10.1021/jacs.9b12345'.")


class ArticleExtraction(StrictBase):
    syntheses: List[SynthesisRecord] = Field(..., description="One item per primary MOF synthesis found in the article. Exclude postsynthetic modifications and non-MOF procedures.")
    trial_or_failure_reported: Literal["yes","no"] = Field(..., description="Did the article describe trying multiple conditions in MOF synthesis that failed, or attempts that did not yield the target? This only apply to pristine MOF synthesis. Y/N.")
    trial_or_failure_notes: Optional[str] = Field(None, description="Short evidence phrase, e.g., 'screened temperatures 60-140 °C with no crystals', 'BDC gave amorphous solid'.")
