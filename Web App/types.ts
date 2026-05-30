export interface MofEntry {
  doi: string;
  mof_name: string;
  mof_description: string;
  
  // Chemistry
  metal_1: string;
  metal_1_abbr: string;
  linker_1: string;
  linker_1_abbr: string;
  topology_code: string;
  
  // Synthesis Conditions
  solvent_main: string;
  temperature_c: number;
  time_h: number;
  yield_percent: number;
  
  // Properties
  bet_surface_area_m2g: number;
  pore_diameter_A: number;
  tga_decomposition_temp_c: number;
  
  // Stability
  water_stable: boolean;
  air_stable: boolean;
  
  // Crystallography
  crystal_morphology: string; // e.g., "block", "needle"
  crystal_form: 'Single Crystal' | 'Powder' | 'Reported'; // Derived from context
  
  // Status
  status: string;

  // Extended Details (New)
  synthesis_procedure: string;
  activation_procedure: string;
  
  // AI Predictions (New)
  ai_metrics: {
    synthesizability: number; // % probability
    water_stability_score: number; // % probability
    thermal_stability_score: number; // % probability
  };
}

export interface FilterState {
  searchQuery: string;
  minSurfaceArea: number;
  minPoreDiameter: number;
  maxTemperature: number;
  maxTime: number;
  minTgaTemp: number;
  waterStable: boolean;
  airStable: boolean;
  topology: string;
  metal: string;
}