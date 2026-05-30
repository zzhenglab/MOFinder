import React from 'react';
import { FilterState } from '../types';
import { TOPOLOGIES, METALS } from '../constants';
import { SmilesEditor } from './SmilesEditor';
import { Flame, Droplets, Wind, Thermometer, Clock, RotateCcw, ChevronDown } from 'lucide-react';

interface FilterSidebarProps {
  filters: FilterState;
  setFilters: React.Dispatch<React.SetStateAction<FilterState>>;
  resultsCount: number;
}

export const FilterSidebar: React.FC<FilterSidebarProps> = ({ filters, setFilters, resultsCount }) => {
  
  const handleChange = (key: keyof FilterState, value: any) => {
    setFilters(prev => ({ ...prev, [key]: value }));
  };

  const resetFilters = () => {
    setFilters({
      searchQuery: filters.searchQuery, // Keep search query
      minSurfaceArea: 0,
      minPoreDiameter: 0,
      maxTemperature: 300,
      maxTime: 100,
      minTgaTemp: 0,
      waterStable: false,
      airStable: false,
      topology: '',
      metal: '',
    });
  };

  return (
    <div className="w-full lg:w-80 flex-shrink-0 space-y-8 pb-10">
      
      {/* Header of Sidebar */}
      <div className="flex items-center justify-between">
        <div>
            <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100 uppercase tracking-wider">
            Refine Results
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                Showing {resultsCount} experiments
            </p>
        </div>
        <button 
            onClick={resetFilters}
            className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
        >
            <RotateCcw size={12} /> Reset
        </button>
      </div>

      {/* Structure Input */}
      <SmilesEditor />

      <div className="h-px bg-slate-200 dark:bg-slate-700 w-full" />

      {/* Stability Section */}
      <div className="space-y-3">
        <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">Stability Requirements</h4>
        
        <label className="flex items-center justify-between p-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 cursor-pointer hover:border-blue-300 dark:hover:border-blue-700 transition-colors group">
            <div className="flex items-center gap-3">
                <div className="p-2 bg-blue-50 dark:bg-blue-900/30 rounded-md text-blue-500 dark:text-blue-400 group-hover:bg-blue-100 dark:group-hover:bg-blue-900/50 transition-colors">
                    <Droplets size={18} />
                </div>
                <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Water Stable</span>
            </div>
            <input 
                type="checkbox" 
                checked={filters.waterStable}
                onChange={(e) => handleChange('waterStable', e.target.checked)}
                className="w-4 h-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500"
            />
        </label>

        <label className="flex items-center justify-between p-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 cursor-pointer hover:border-teal-300 dark:hover:border-teal-700 transition-colors group">
            <div className="flex items-center gap-3">
                <div className="p-2 bg-teal-50 dark:bg-teal-900/30 rounded-md text-teal-500 dark:text-teal-400 group-hover:bg-teal-100 dark:group-hover:bg-teal-900/50 transition-colors">
                    <Wind size={18} />
                </div>
                <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Air Stable</span>
            </div>
            <input 
                type="checkbox" 
                checked={filters.airStable}
                onChange={(e) => handleChange('airStable', e.target.checked)}
                className="w-4 h-4 text-teal-600 rounded border-gray-300 focus:ring-teal-500"
            />
        </label>
      </div>

      {/* Thermal Stability - Conditional Mode */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-slate-700 dark:text-slate-200">
                <Flame size={16} className="text-orange-500" />
                <span className="text-sm font-medium">Thermal Stability (TGA)</span>
            </div>
            <span className="text-xs font-mono text-slate-500 dark:text-slate-400">
                &gt; {filters.minTgaTemp}°C
            </span>
        </div>
        
        <input 
            type="range"
            min="0"
            max="600"
            step="50"
            value={filters.minTgaTemp}
            onChange={(e) => handleChange('minTgaTemp', parseInt(e.target.value))}
            className="w-full h-2 bg-slate-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-orange-500"
        />
        <div className="flex justify-between text-xs text-slate-400">
            <span>0°C</span>
            <span>600°C+</span>
        </div>
      </div>

      <div className="h-px bg-slate-200 dark:bg-slate-700 w-full" />

      {/* Structural Properties */}
      <div className="space-y-6">
        <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Physical Properties</h4>
        
        <div className="space-y-2">
            <div className="flex justify-between text-sm">
                <span className="text-slate-700 dark:text-slate-300">BET Surface Area</span>
                <span className="font-mono text-slate-500 text-xs">&gt; {filters.minSurfaceArea} m²/g</span>
            </div>
            <input 
                type="range"
                min="0"
                max="5000"
                step="100"
                value={filters.minSurfaceArea}
                onChange={(e) => handleChange('minSurfaceArea', parseInt(e.target.value))}
                className="w-full h-2 bg-slate-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-indigo-500"
            />
        </div>

        <div className="space-y-2">
            <div className="flex justify-between text-sm">
                <span className="text-slate-700 dark:text-slate-300">Pore Diameter</span>
                <span className="font-mono text-slate-500 text-xs">&gt; {filters.minPoreDiameter} Å</span>
            </div>
            <input 
                type="range"
                min="0"
                max="50"
                step="1"
                value={filters.minPoreDiameter}
                onChange={(e) => handleChange('minPoreDiameter', parseInt(e.target.value))}
                className="w-full h-2 bg-slate-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-indigo-500"
            />
        </div>
      </div>

      <div className="h-px bg-slate-200 dark:bg-slate-700 w-full" />

      {/* Synthesis Params */}
      <div className="space-y-6">
        <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Synthesis Conditions</h4>
        
        <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
                 <div className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
                    <Thermometer size={12} /> Max Temp
                 </div>
                 <select 
                    value={filters.maxTemperature}
                    onChange={(e) => handleChange('maxTemperature', parseInt(e.target.value))}
                    className="w-full p-2 text-sm bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-md focus:ring-1 focus:ring-blue-500 focus:outline-none dark:text-slate-200"
                 >
                    <option value={300}>Any</option>
                    <option value={100}>&lt; 100°C</option>
                    <option value={150}>&lt; 150°C</option>
                    <option value={200}>&lt; 200°C</option>
                 </select>
            </div>
            <div className="space-y-2">
                 <div className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
                    <Clock size={12} /> Max Time
                 </div>
                 <select 
                    value={filters.maxTime}
                    onChange={(e) => handleChange('maxTime', parseInt(e.target.value))}
                    className="w-full p-2 text-sm bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-md focus:ring-1 focus:ring-blue-500 focus:outline-none dark:text-slate-200"
                 >
                    <option value={200}>Any</option>
                    <option value={24}>&lt; 24 h</option>
                    <option value={48}>&lt; 48 h</option>
                    <option value={72}>&lt; 72 h</option>
                 </select>
            </div>
        </div>
      </div>

      {/* Classification Filters */}
      <div className="space-y-4">
        <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Chemistry</h4>
        
        <div className="relative">
            <select
                value={filters.metal}
                onChange={(e) => handleChange('metal', e.target.value)}
                className="w-full p-2.5 pl-3 pr-8 text-sm bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg appearance-none focus:ring-2 focus:ring-blue-500 focus:outline-none dark:text-slate-200"
            >
                <option value="">All Metals</option>
                {METALS.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
            <ChevronDown className="absolute right-3 top-3 text-slate-400 pointer-events-none" size={16} />
        </div>

        <div className="relative">
            <select
                value={filters.topology}
                onChange={(e) => handleChange('topology', e.target.value)}
                className="w-full p-2.5 pl-3 pr-8 text-sm bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg appearance-none focus:ring-2 focus:ring-blue-500 focus:outline-none dark:text-slate-200"
            >
                <option value="">All Topologies</option>
                {TOPOLOGIES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            <ChevronDown className="absolute right-3 top-3 text-slate-400 pointer-events-none" size={16} />
        </div>
      </div>

    </div>
  );
};
