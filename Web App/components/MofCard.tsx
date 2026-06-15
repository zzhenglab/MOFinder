import React from 'react';
import { MofEntry } from '../types';
import { Box, ExternalLink, Droplets, Flame, Wind } from 'lucide-react';

interface MofCardProps {
  mof: MofEntry;
  onClick: (mof: MofEntry) => void;
}

export const MofCard: React.FC<MofCardProps> = ({ mof, onClick }) => {
  return (
    <div 
      onClick={() => onClick(mof)}
      className="group bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm hover:shadow-md dark:hover:border-slate-600 hover:translate-y-[-2px] transition-all duration-200 flex flex-col h-full overflow-hidden cursor-pointer"
    >
      
      {/* Card Header */}
      <div className="p-5 pb-3">
        <div className="flex items-start justify-between mb-2">
            <div className="flex items-center gap-2">
                <div className="p-1.5 bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 rounded-lg">
                    <Box size={18} />
                </div>
                <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                    {mof.mof_name}
                </h3>
            </div>
            <div className="flex gap-1">
                 {/* Stability Badges */}
                 {mof.water_stable && (
                     <div className="p-1 rounded bg-blue-50 dark:bg-blue-900/20 text-blue-500 dark:text-blue-400" title="Water Stable">
                         <Droplets size={14} />
                     </div>
                 )}
                 {mof.air_stable && (
                     <div className="p-1 rounded bg-teal-50 dark:bg-teal-900/20 text-teal-500 dark:text-teal-400" title="Air Stable">
                         <Wind size={14} />
                     </div>
                 )}
                 {mof.tga_decomposition_temp_c > 350 && (
                     <div className="p-1 rounded bg-orange-50 dark:bg-orange-900/20 text-orange-500 dark:text-orange-400" title={`High Thermal Stability (>350°C)`}>
                         <Flame size={14} />
                     </div>
                 )}
            </div>
        </div>
        
        <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-2 h-8 leading-relaxed">
            {mof.mof_description}
        </p>
      </div>

      {/* Key Metrics Grid */}
      <div className="px-5 py-2">
        <div className="grid grid-cols-2 gap-2">
            <div className="bg-slate-50 dark:bg-slate-800/50 rounded-lg p-2 border border-slate-100 dark:border-slate-700/50">
                <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Surface Area</div>
                <div className="text-lg font-bold text-slate-800 dark:text-slate-200 font-mono">
                    {mof.bet_surface_area_m2g} <span className="text-xs font-normal text-slate-500">m²/g</span>
                </div>
            </div>
            <div className="bg-slate-50 dark:bg-slate-800/50 rounded-lg p-2 border border-slate-100 dark:border-slate-700/50">
                <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Yield</div>
                <div className={`text-lg font-bold font-mono ${mof.yield_percent > 80 ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-800 dark:text-slate-200'}`}>
                    {mof.yield_percent}<span className="text-xs font-normal text-slate-500">%</span>
                </div>
            </div>
        </div>
      </div>

      {/* Details List */}
      <div className="px-5 py-2 space-y-1.5 flex-grow">
         <div className="flex justify-between text-xs py-1 border-b border-slate-100 dark:border-slate-700/50">
             <span className="text-slate-500 dark:text-slate-400">Synthesis</span>
             <span className="font-medium text-slate-700 dark:text-slate-300">
                 {mof.temperature_c}°C <span className="text-slate-400 mx-1">•</span> {mof.time_h}h
             </span>
         </div>
         <div className="flex justify-between text-xs py-1 border-b border-slate-100 dark:border-slate-700/50">
             <span className="text-slate-500 dark:text-slate-400">Topology</span>
             <span className="font-mono bg-slate-100 dark:bg-slate-700 px-1.5 rounded text-slate-700 dark:text-slate-300">
                 {mof.topology_code}
             </span>
         </div>
         <div className="flex justify-between text-xs py-1 border-b border-slate-100 dark:border-slate-700/50">
             <span className="text-slate-500 dark:text-slate-400">Components</span>
             <div className="flex gap-1 text-slate-700 dark:text-slate-300 font-medium max-w-[60%] truncate justify-end">
                 <span>{mof.metal_1_abbr}</span>
                 <span className="text-slate-400">/</span>
                 <span className="truncate" title={mof.linker_1_abbr}>{mof.linker_1_abbr}</span>
             </div>
         </div>
      </div>

      {/* Footer */}
      <div className="p-4 bg-slate-50 dark:bg-slate-900/30 border-t border-slate-100 dark:border-slate-700 flex items-center justify-between">
         <div className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${
             mof.crystal_form === 'Single Crystal' 
             ? 'bg-purple-50 text-purple-600 border-purple-100 dark:bg-purple-900/20 dark:text-purple-300 dark:border-purple-900/50' 
             : 'bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700'
         }`}>
             {mof.crystal_form}
         </div>
         
         {/* We use a span here instead of a link, because clicking the whole card opens modal. 
             The DOI link is inside the modal now. */}
         <span 
            className="text-xs font-medium text-blue-600 dark:text-blue-400 flex items-center gap-1"
         >
             View Details <ExternalLink size={10} />
         </span>
      </div>
    </div>
  );
};