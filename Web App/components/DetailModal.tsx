import React, { useState } from 'react';
import { X, Beaker, Thermometer, Clock, Maximize, Zap, Share2, Download, FileText, CheckCircle, Cpu, Hexagon, ChevronDown, ChevronUp, Droplets, Flame } from 'lucide-react';
import { MofEntry } from '../types';

interface DetailModalProps {
  mof: MofEntry;
  onClose: () => void;
}

export const DetailModal: React.FC<DetailModalProps> = ({ mof, onClose }) => {
  const [isSynthesisExpanded, setIsSynthesisExpanded] = useState(true);

  // Stop propagation when clicking content to prevent closing
  const handleContentClick = (e: React.MouseEvent) => {
    e.stopPropagation();
  };

  return (
    <div 
      className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm transition-all duration-300"
      onClick={onClose}
    >
      <div 
        className="bg-white dark:bg-slate-900 w-full max-w-4xl max-h-[90vh] rounded-2xl shadow-2xl overflow-hidden flex flex-col border border-slate-200 dark:border-slate-800 animate-in fade-in zoom-in-95 duration-200"
        onClick={handleContentClick}
      >
        {/* Header */}
        <div className="flex items-start justify-between p-6 border-b border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-900 sticky top-0 z-10">
          <div className="pr-8">
            <div className="flex items-center gap-3 mb-2">
               <div className="px-2.5 py-1 rounded-md bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 text-xs font-bold uppercase tracking-wide">
                 {mof.topology_code} Net
               </div>
               <div className={`px-2.5 py-1 rounded-md text-xs font-bold uppercase tracking-wide flex items-center gap-1 ${mof.status === 'ok' ? 'bg-emerald-100 dark:bg-emerald-900/50 text-emerald-700 dark:text-emerald-300' : 'bg-amber-100 text-amber-700'}`}>
                  <CheckCircle size={12} /> Verified Experiment
               </div>
            </div>
            <h2 className="text-3xl font-extrabold text-slate-900 dark:text-white mb-2">
              {mof.mof_name}
            </h2>
            <p className="text-slate-600 dark:text-slate-400 leading-relaxed text-sm max-w-2xl">
              {mof.mof_description}
            </p>
          </div>
          <button 
            onClick={onClose}
            className="p-2 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
          >
            <X size={24} />
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="overflow-y-auto p-6 space-y-8 custom-scrollbar">
          
          {/* Synthesis Card */}
          <section>
             <h3 className="flex items-center gap-2 text-lg font-bold text-slate-800 dark:text-slate-200 mb-4">
               <Beaker className="text-indigo-500" size={20} /> Synthesis Protocol
             </h3>
             <div className="bg-slate-50 dark:bg-slate-800/50 rounded-xl p-6 border border-slate-200 dark:border-slate-700">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                   <div className="space-y-1">
                      <div className="text-xs text-slate-500 uppercase font-semibold">Primary Metal Source</div>
                      <div className="font-medium text-slate-900 dark:text-slate-200">{mof.metal_1}</div>
                      <div className="text-xs text-slate-400">Abbr: {mof.metal_1_abbr}</div>
                   </div>
                   <div className="space-y-1">
                      <div className="text-xs text-slate-500 uppercase font-semibold">Organic Linker</div>
                      <div className="font-medium text-slate-900 dark:text-slate-200">{mof.linker_1}</div>
                      <div className="text-xs text-slate-400">Abbr: {mof.linker_1_abbr}</div>
                   </div>
                   <div className="space-y-1">
                      <div className="text-xs text-slate-500 uppercase font-semibold">Solvent System</div>
                      <div className="font-medium text-slate-900 dark:text-slate-200">{mof.solvent_main}</div>
                   </div>
                   <div className="space-y-1">
                      <div className="text-xs text-slate-500 uppercase font-semibold">Yield</div>
                      <div className="text-xl font-bold text-emerald-600 dark:text-emerald-400">{mof.yield_percent}%</div>
                      <div className="text-xs text-slate-400">Based on metal</div>
                   </div>
                </div>
                
                <div className="mt-6 pt-6 border-t border-slate-200 dark:border-slate-700 grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="flex items-center gap-3 p-3 bg-white dark:bg-slate-800 rounded-lg shadow-sm">
                        <div className="p-2 bg-orange-50 dark:bg-orange-900/20 text-orange-500 rounded"><Thermometer size={20} /></div>
                        <div>
                           <div className="text-xs text-slate-400 font-semibold">Reaction Temp</div>
                           <div className="font-bold text-slate-900 dark:text-slate-100">{mof.temperature_c} °C</div>
                        </div>
                    </div>
                    <div className="flex items-center gap-3 p-3 bg-white dark:bg-slate-800 rounded-lg shadow-sm">
                        <div className="p-2 bg-blue-50 dark:bg-blue-900/20 text-blue-500 rounded"><Clock size={20} /></div>
                        <div>
                           <div className="text-xs text-slate-400 font-semibold">Reaction Time</div>
                           <div className="font-bold text-slate-900 dark:text-slate-100">{mof.time_h} Hours</div>
                        </div>
                    </div>
                    <div className="flex items-center gap-3 p-3 bg-white dark:bg-slate-800 rounded-lg shadow-sm">
                        <div className="p-2 bg-purple-50 dark:bg-purple-900/20 text-purple-500 rounded"><Hexagon size={20} /></div>
                        <div>
                           <div className="text-xs text-slate-400 font-semibold">Morphology</div>
                           <div className="font-bold text-slate-900 dark:text-slate-100 truncate" title={mof.crystal_morphology}>{mof.crystal_morphology}</div>
                        </div>
                    </div>
                </div>
             </div>

             {/* Expanded Step-by-Step */}
             <div className="mt-4">
                <button 
                  onClick={() => setIsSynthesisExpanded(!isSynthesisExpanded)}
                  className="w-full flex items-center justify-between p-3 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors"
                >
                  <span>Step-by-Step Preparation & Activation</span>
                  {isSynthesisExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                </button>
                
                {isSynthesisExpanded && (
                  <div className="mt-2 p-5 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg animate-in slide-in-from-top-2 duration-200">
                     <div className="space-y-4">
                       <div>
                         <h4 className="text-xs font-bold text-indigo-600 dark:text-indigo-400 uppercase mb-2">Preparation</h4>
                         <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
                           {mof.synthesis_procedure}
                         </p>
                       </div>
                       <div className="h-px bg-slate-100 dark:bg-slate-700" />
                       <div>
                         <h4 className="text-xs font-bold text-indigo-600 dark:text-indigo-400 uppercase mb-2">Activation</h4>
                         <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
                           {mof.activation_procedure}
                         </p>
                       </div>
                     </div>
                  </div>
                )}
             </div>
          </section>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
             {/* Properties */}
             <section>
                <h3 className="flex items-center gap-2 text-lg font-bold text-slate-800 dark:text-slate-200 mb-4">
                   <Maximize className="text-teal-500" size={20} /> Physical Properties
                </h3>
                <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
                    <div className="divide-y divide-slate-100 dark:divide-slate-700">
                        <div className="p-4 flex justify-between items-center">
                            <span className="text-slate-600 dark:text-slate-400 text-sm font-medium">BET Surface Area</span>
                            <span className="text-slate-900 dark:text-slate-100 font-bold font-mono">{mof.bet_surface_area_m2g} m²/g</span>
                        </div>
                        <div className="p-4 flex justify-between items-center">
                            <span className="text-slate-600 dark:text-slate-400 text-sm font-medium">Pore Diameter</span>
                            <span className="text-slate-900 dark:text-slate-100 font-bold font-mono">{mof.pore_diameter_A} Å</span>
                        </div>
                        <div className="p-4 flex justify-between items-center">
                            <span className="text-slate-600 dark:text-slate-400 text-sm font-medium">TGA Decomposition</span>
                            <span className="text-slate-900 dark:text-slate-100 font-bold font-mono">{mof.tga_decomposition_temp_c} °C</span>
                        </div>
                        <div className="p-4 flex justify-between items-center">
                            <span className="text-slate-600 dark:text-slate-400 text-sm font-medium">Stability</span>
                            <div className="flex gap-2">
                                {mof.water_stable ? 
                                  <span className="px-2 py-1 rounded bg-blue-100 text-blue-700 text-xs font-bold">Water Stable</span> : 
                                  <span className="px-2 py-1 rounded bg-slate-100 text-slate-500 text-xs">Water Unstable</span>
                                }
                                {mof.air_stable ? 
                                  <span className="px-2 py-1 rounded bg-teal-100 text-teal-700 text-xs font-bold">Air Stable</span> : 
                                  <span className="px-2 py-1 rounded bg-slate-100 text-slate-500 text-xs">Air Unstable</span>
                                }
                            </div>
                        </div>
                    </div>
                </div>
             </section>

             {/* AI Predictions */}
             <section className="flex flex-col h-full">
                <h3 className="flex items-center gap-2 text-lg font-bold text-slate-800 dark:text-slate-200 mb-4">
                   <Cpu className="text-indigo-600 dark:text-indigo-400" size={20} /> 
                   AI Predictions <span className="text-[10px] bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded uppercase tracking-wider">Beta</span>
                </h3>
                <div className="flex-1 bg-gradient-to-br from-indigo-50 to-blue-50 dark:from-slate-800 dark:to-indigo-900/20 rounded-xl p-6 border border-indigo-100 dark:border-indigo-900/30 relative overflow-hidden">
                    <div className="absolute top-0 right-0 p-4 opacity-5">
                        <Zap size={120} />
                    </div>
                    
                    <div className="relative z-10 space-y-6">
                        {/* Synthesizability */}
                        <div>
                           <div className="flex justify-between items-end mb-1">
                              <div className="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase">Synthesizability Score</div>
                              <div className="text-sm font-bold text-indigo-600 dark:text-indigo-400">{mof.ai_metrics.synthesizability}%</div>
                           </div>
                           <div className="w-full bg-slate-200 dark:bg-slate-700 h-2 rounded-full overflow-hidden">
                               <div className="bg-indigo-500 h-full rounded-full" style={{width: `${mof.ai_metrics.synthesizability}%`}}></div>
                           </div>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            {/* Water Stability */}
                            <div className="bg-white/60 dark:bg-slate-900/40 p-3 rounded-lg backdrop-blur-sm border border-white/50 dark:border-slate-700/50">
                                <div className="flex items-center gap-2 mb-2">
                                   <Droplets size={14} className="text-blue-500" />
                                   <span className="text-xs font-semibold text-slate-600 dark:text-slate-300">Water Stability</span>
                                </div>
                                <div className="text-xl font-bold text-slate-800 dark:text-slate-200">
                                  {mof.ai_metrics.water_stability_score}% <span className="text-[10px] font-normal text-slate-500">Prob.</span>
                                </div>
                            </div>

                            {/* Thermal Stability */}
                            <div className="bg-white/60 dark:bg-slate-900/40 p-3 rounded-lg backdrop-blur-sm border border-white/50 dark:border-slate-700/50">
                                <div className="flex items-center gap-2 mb-2">
                                   <Flame size={14} className="text-orange-500" />
                                   <span className="text-xs font-semibold text-slate-600 dark:text-slate-300">Thermal Stability</span>
                                </div>
                                <div className="text-xl font-bold text-slate-800 dark:text-slate-200">
                                  {mof.ai_metrics.thermal_stability_score}% <span className="text-[10px] font-normal text-slate-500">Prob.</span>
                                </div>
                            </div>
                        </div>

                        <div className="bg-indigo-100/50 dark:bg-indigo-900/30 p-3 rounded-lg border border-indigo-200 dark:border-indigo-800/50 mt-2">
                            <p className="text-xs text-indigo-800 dark:text-indigo-200 italic">
                                "AI Model v2.1 predicts this framework fits the standard {mof.topology_code} topology template with high fidelity. Suggested for catalytic applications."
                            </p>
                        </div>
                    </div>
                </div>
             </section>
          </div>

        </div>

        {/* Footer Actions */}
        <div className="p-4 border-t border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 flex justify-between items-center sticky bottom-0">
             <a 
                href={`https://doi.org/${mof.doi}`}
                target="_blank"
                rel="noopener noreferrer" 
                className="flex items-center gap-2 text-sm font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
             >
                 View Original Paper <FileText size={16} />
             </a>
             
             <div className="flex gap-3">
                 <button className="flex items-center gap-2 px-4 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors text-sm font-medium">
                    <Share2 size={16} /> Share
                 </button>
                 <button className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors text-sm font-medium shadow-sm shadow-blue-200 dark:shadow-none">
                    <Download size={16} /> Export Data
                 </button>
             </div>
        </div>
      </div>
    </div>
  );
};