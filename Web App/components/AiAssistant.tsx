import React, { useState } from 'react';
import { X, MessageSquare, Sparkles, Send, Brain, ArrowRight } from 'lucide-react';

interface AiAssistantProps {
  isOpen: boolean;
  onClose: () => void;
}

export const AiAssistant: React.FC<AiAssistantProps> = ({ isOpen, onClose }) => {
  const [prompt, setPrompt] = useState('');
  const [response, setResponse] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  if (!isOpen) return null;

  const handleRecommend = () => {
    if (!prompt.trim()) return;
    
    setIsLoading(true);
    
    // Mock AI Delay
    setTimeout(() => {
      setIsLoading(false);
      // Simple heuristic mock response
      const p = prompt.toLowerCase();
      let text = "";
      
      if (p.includes('co2') || p.includes('carbon')) {
        text = "Based on your requirement for carbon capture, I highly recommend **Mg-MOF-74** or **Ni-MOF-74**. These frameworks contain a high density of open metal sites that interact strongly with CO2 molecules, giving strong uptake at low pressures.";
      } else if (p.includes('water') || p.includes('humid')) {
        text = "For applications in humid environments, stability is critical. I recommend **UiO-66**, **MIL-101(Cr)**, or **Al-Fum (MIL-53-Al)**. These carboxylate frameworks with high-valence metals (Zr4+, Cr3+, Al3+) maintain structural integrity in the presence of moisture.";
      } else if (p.includes('large') || p.includes('protein') || p.includes('enzyme')) {
        text = "For hosting large guests such as enzymes or proteins, pore size drives performance. **NU-1000**, **PCN-222**, and **MIL-101(Cr)** offer mesoporous cavities above 2 nm that can fit bulky biomolecules.";
      } else if (p.includes('bio') || p.includes('biocompat') || p.includes('biomed')) {
        text = "For biocompatible or biological applications, frameworks like **MIL-88A**, **ZIF-8**, and **Fe-MIL series** are strong choices. They are known for mild synthesis conditions, acceptable cytocompatibility profiles, and the ability to load or release biomolecules under physiologically relevant conditions.";
      } else {
        text = "Based on your general description, a good starting point would be **HKUST-1** or **ZIF-8**. Both are accessible, easy to prepare, and work well as baseline materials for tuning new protocols.";
      }
      setResponse(text);
    }, 1500);
  };

  return (
    <div className="fixed inset-0 z-[110] flex items-end sm:items-center justify-center p-0 sm:p-4 bg-slate-900/50 backdrop-blur-sm">
      <div className="bg-white dark:bg-slate-900 w-full max-w-md sm:rounded-2xl shadow-2xl h-[80vh] sm:h-auto flex flex-col animate-in slide-in-from-bottom-10 duration-300 border border-slate-200 dark:border-slate-800">
        
        {/* Header */}
        <div className="p-4 border-b border-slate-100 dark:border-slate-800 flex justify-between items-center bg-gradient-to-r from-indigo-600 to-blue-600 text-white sm:rounded-t-2xl">
           <div className="flex items-center gap-2">
              <Brain size={20} />
              <h3 className="font-bold">AI MOF Recommender</h3>
           </div>
           <button onClick={onClose} className="text-white/80 hover:text-white hover:bg-white/20 p-1 rounded-full transition-colors">
              <X size={20} />
           </button>
        </div>

        {/* Body */}
        <div className="flex-1 p-6 overflow-y-auto">
           {!response ? (
             <div className="space-y-6">
               <div className="text-center space-y-2 py-4">
                  <div className="w-12 h-12 bg-indigo-50 dark:bg-indigo-900/30 rounded-full flex items-center justify-center mx-auto text-indigo-600 dark:text-indigo-400">
                    <Sparkles size={24} />
                  </div>
                  <h4 className="text-lg font-semibold text-slate-800 dark:text-slate-100">Describe your application</h4>
                  <p className="text-sm text-slate-500 dark:text-slate-400">
                    Tell me what you want to use the MOF for (e.g., "CO2 capture from flue gas", "Catalysis in water", "Drug delivery").
                  </p>
               </div>

               <div className="relative">
                 <textarea 
                   value={prompt}
                   onChange={(e) => setPrompt(e.target.value)}
                   placeholder="e.g. I need a water-stable MOF with large pores for enzyme immobilization..."
                   className="w-full h-32 p-4 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl resize-none focus:ring-2 focus:ring-indigo-500 focus:outline-none text-sm text-slate-800 dark:text-slate-200"
                 />
                 <button 
                   onClick={handleRecommend}
                   disabled={!prompt || isLoading}
                   className="absolute bottom-3 right-3 p-2 bg-indigo-600 text-white rounded-lg disabled:opacity-50 hover:bg-indigo-700 transition-colors"
                 >
                   {isLoading ? <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"/> : <Send size={18} />}
                 </button>
               </div>
             </div>
           ) : (
             <div className="space-y-4 animate-in fade-in duration-300">
                <div className="flex gap-3 items-start">
                   <div className="w-8 h-8 bg-slate-200 dark:bg-slate-700 rounded-full flex-shrink-0 flex items-center justify-center text-slate-500">
                      <MessageSquare size={14} />
                   </div>
                   <div className="bg-slate-100 dark:bg-slate-800 p-3 rounded-lg rounded-tl-none text-sm text-slate-700 dark:text-slate-300">
                      {prompt}
                   </div>
                </div>

                <div className="flex gap-3 items-start">
                   <div className="w-8 h-8 bg-indigo-100 dark:bg-indigo-900/50 rounded-full flex-shrink-0 flex items-center justify-center text-indigo-600 dark:text-indigo-400">
                      <Brain size={14} />
                   </div>
                   <div className="bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-100 dark:border-indigo-800/50 p-4 rounded-lg rounded-tl-none text-sm text-slate-800 dark:text-slate-200 leading-relaxed">
                      <p dangerouslySetInnerHTML={{ __html: response.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') }} />
                   </div>
                </div>

                <button 
                  onClick={() => { setResponse(null); setPrompt(''); }}
                  className="w-full py-2.5 mt-4 border border-dashed border-slate-300 dark:border-slate-700 rounded-lg text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors text-sm flex items-center justify-center gap-2"
                >
                   Start New Query <ArrowRight size={14} />
                </button>
             </div>
           )}
        </div>
      </div>
    </div>
  );
};