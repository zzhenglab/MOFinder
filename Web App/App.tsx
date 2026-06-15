import React, { useState, useEffect, useMemo } from 'react';
import { Header } from './components/Header';
import { FilterSidebar } from './components/FilterSidebar';
import { MofCard } from './components/MofCard';
import { DetailModal } from './components/DetailModal';
import { AiAssistant } from './components/AiAssistant';
import { MOCK_MOF_DATA } from './constants';
import { FilterState, MofEntry } from './types';
import { Search, Beaker, LineChart, Sparkles, FlaskConical } from 'lucide-react';

const App: React.FC = () => {
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [selectedMof, setSelectedMof] = useState<MofEntry | null>(null);
  const [isAiAssistantOpen, setIsAiAssistantOpen] = useState(false);
  
  const [filters, setFilters] = useState<FilterState>({
    searchQuery: '',
    minSurfaceArea: 0,
    minPoreDiameter: 0,
    maxTemperature: 300, // Default generous max
    maxTime: 100, // Default generous max
    minTgaTemp: 0,
    waterStable: false,
    airStable: false,
    topology: '',
    metal: '',
  });

  // Theme handling
  useEffect(() => {
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      setIsDarkMode(true);
    }
  }, []);

  useEffect(() => {
    if (isDarkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDarkMode]);

  const toggleTheme = () => setIsDarkMode(!isDarkMode);

  // Filtering Logic
  const filteredData = useMemo(() => {
    return MOCK_MOF_DATA.filter((item) => {
      // Text Search
      if (filters.searchQuery) {
        const query = filters.searchQuery.toLowerCase();
        const matchesName = item.mof_name.toLowerCase().includes(query);
        const matchesLinker = item.linker_1.toLowerCase().includes(query) || item.linker_1_abbr.toLowerCase().includes(query);
        const matchesMetal = item.metal_1.toLowerCase().includes(query) || item.metal_1_abbr.toLowerCase().includes(query);
        if (!matchesName && !matchesLinker && !matchesMetal) return false;
      }

      // Numeric Filters
      if (item.bet_surface_area_m2g < filters.minSurfaceArea) return false;
      if (item.pore_diameter_A < filters.minPoreDiameter) return false;
      if (item.temperature_c > filters.maxTemperature) return false;
      if (item.time_h > filters.maxTime) return false;
      if (item.tga_decomposition_temp_c < filters.minTgaTemp) return false;

      // Boolean Toggles (Only filter if TRUE, if filter is false, we show everything)
      if (filters.waterStable && !item.water_stable) return false;
      if (filters.airStable && !item.air_stable) return false;

      // Dropdowns
      if (filters.topology && item.topology_code !== filters.topology) return false;
      if (filters.metal && item.metal_1_abbr !== filters.metal) return false;

      return true;
    });
  }, [filters]);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 font-sans transition-colors duration-200">
      <Header 
        isDarkMode={isDarkMode} 
        toggleTheme={toggleTheme} 
        onAiAssistantClick={() => setIsAiAssistantOpen(true)}
      />

      <main className="container mx-auto px-4 py-8">
        {/* Hero Section */}
        <div className="mb-10 text-center max-w-3xl mx-auto space-y-6">
            <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight text-slate-900 dark:text-white">
                Discover <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-indigo-600 dark:from-blue-400 dark:to-indigo-400">Synthesis</span> Conditions
            </h1>
            <p className="text-lg text-slate-600 dark:text-slate-400 leading-relaxed">
                Explore experimental benchmarks for Metal-Organic Frameworks. 
                Filter by topological net, stability, and pore metrics to find the perfect candidate for your synthesis.
            </p>
            
            {/* Global Search Bar */}
            <div className="relative max-w-xl mx-auto">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                    <Search className="text-slate-400" size={20} />
                </div>
                <input 
                    type="text"
                    placeholder="Search by MOF name, linker, or metal (e.g., MOF-808, Zirconium)..." 
                    className="w-full pl-11 pr-4 py-4 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-2xl shadow-lg shadow-slate-200/50 dark:shadow-none focus:ring-2 focus:ring-blue-500 focus:outline-none transition-all text-base"
                    value={filters.searchQuery}
                    onChange={(e) => setFilters(prev => ({...prev, searchQuery: e.target.value}))}
                />
            </div>
        </div>

        {/* Stats Summary */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-12 max-w-4xl mx-auto">
            <div className="bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm flex items-center gap-4">
                <div className="p-3 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg text-emerald-600 dark:text-emerald-400">
                    <Beaker size={24} />
                </div>
                <div>
                    <div className="text-2xl font-bold">12,507</div>
                    <div className="text-sm text-slate-500 dark:text-slate-400">Unique Experiments</div>
                </div>
            </div>
            <div className="bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm flex items-center gap-4">
                <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-blue-600 dark:text-blue-400">
                    <LineChart size={24} />
                </div>
                <div>
                    <div className="text-2xl font-bold">7,200+</div>
                    <div className="text-sm text-slate-500 dark:text-slate-400">Max Surface Area (m²/g)</div>
                </div>
            </div>
            <div className="bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm flex items-center gap-4">
                <div className="p-3 bg-purple-50 dark:bg-purple-900/20 rounded-lg text-purple-600 dark:text-purple-400">
                    <Sparkles size={24} />
                </div>
                <div>
                    <div className="text-2xl font-bold">2,340</div>
                    <div className="text-sm text-slate-500 dark:text-slate-400">Crystal Structures</div>
                </div>
            </div>
        </div>

        {/* Main Layout: Sidebar + Grid */}
        <div className="flex flex-col lg:flex-row gap-8">
          <FilterSidebar 
            filters={filters} 
            setFilters={setFilters} 
            resultsCount={filteredData.length}
          />

          <div className="flex-1">
             
             {/* Results Bar */}
             <div className="mb-6 flex items-center justify-between">
                <h2 className="text-lg font-bold text-slate-800 dark:text-slate-200">Experimental Results (Demo: 16)</h2>
                <div className="flex gap-2">
                   {/* Placeholder for sorting or view toggle */}
                   <span className="text-sm text-slate-500 dark:text-slate-400">
                     Sorted by Relevance
                   </span>
                </div>
             </div>

            {filteredData.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                    {filteredData.map((mof, index) => (
                    <MofCard 
                      key={`${mof.mof_name}-${index}`} 
                      mof={mof} 
                      onClick={setSelectedMof} 
                    />
                    ))}
                </div>
            ) : (
                <div className="flex flex-col items-center justify-center py-20 bg-white dark:bg-slate-900 rounded-2xl border border-dashed border-slate-300 dark:border-slate-700">
                    <div className="p-4 bg-slate-100 dark:bg-slate-800 rounded-full text-slate-400 mb-4">
                        <Beaker size={48} />
                    </div>
                    <h3 className="text-lg font-bold text-slate-700 dark:text-slate-300 mb-2">No MOFs Found</h3>
                    <p className="text-slate-500 dark:text-slate-400 text-center max-w-md">
                        Try adjusting your filters (e.g., lowering surface area requirements) or checking different stability toggles.
                    </p>
                    <button 
                        onClick={() => setFilters(prev => ({...prev, minSurfaceArea: 0, minPoreDiameter: 0, waterStable: false, airStable: false}))}
                        className="mt-6 px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors"
                    >
                        Clear Filters
                    </button>
                </div>
            )}
          </div>
        </div>
      </main>
      
      <footer className="bg-white dark:bg-slate-900 border-t border-slate-200 dark:border-slate-800 py-12 mt-20">
        <div className="container mx-auto px-4 text-center">
            <div className="flex items-center justify-center gap-2 mb-4 text-slate-400">
                <FlaskConical size={24} />
                <span className="font-bold text-lg">MOFinder</span>
            </div>
            <p className="text-slate-500 dark:text-slate-400 text-sm">
                &copy; {new Date().getFullYear()} MOFinder Database. All rights reserved.
            </p>
        </div>
      </footer>

      {/* Detail Modal */}
      {selectedMof && (
        <DetailModal mof={selectedMof} onClose={() => setSelectedMof(null)} />
      )}

      {/* AI Assistant Modal */}
      <AiAssistant isOpen={isAiAssistantOpen} onClose={() => setIsAiAssistantOpen(false)} />
    </div>
  );
};

export default App;