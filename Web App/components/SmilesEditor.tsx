import React, { useState } from 'react';
import { Pencil, Hexagon, Eraser, Undo, Redo } from 'lucide-react';

export const SmilesEditor: React.FC = () => {
  const [mode, setMode] = useState<'text' | 'draw'>('text');
  const [smiles, setSmiles] = useState('');

  return (
    <div className="w-full space-y-3">
      <div className="flex items-center justify-between mb-1">
        <label className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
          Linker Structure
        </label>
        <div className="flex bg-slate-100 dark:bg-slate-800 rounded-lg p-0.5">
          <button
            onClick={() => setMode('text')}
            className={`px-3 py-1 text-xs font-medium rounded-md transition-all ${
              mode === 'text'
                ? 'bg-white dark:bg-slate-700 text-blue-600 dark:text-blue-400 shadow-sm'
                : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300'
            }`}
          >
            SMILES
          </button>
          <button
            onClick={() => setMode('draw')}
            className={`px-3 py-1 text-xs font-medium rounded-md transition-all flex items-center gap-1 ${
              mode === 'draw'
                ? 'bg-white dark:bg-slate-700 text-blue-600 dark:text-blue-400 shadow-sm'
                : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300'
            }`}
          >
            <Pencil size={12} /> Draw
          </button>
        </div>
      </div>

      {mode === 'text' ? (
        <div className="relative">
          <input
            type="text"
            value={smiles}
            onChange={(e) => setSmiles(e.target.value)}
            placeholder="c1ccccc1 (Benzene)"
            className="w-full pl-3 pr-10 py-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 dark:text-slate-100 placeholder-slate-400"
          />
          <div className="absolute right-3 top-2.5 text-slate-400">
            <Hexagon size={16} />
          </div>
        </div>
      ) : (
        <div className="w-full h-48 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg relative overflow-hidden group cursor-crosshair">
          <div className="absolute top-2 left-2 flex flex-col gap-2 bg-white/90 dark:bg-slate-800/90 p-1 rounded shadow-sm border border-slate-200 dark:border-slate-600 z-10">
             <button className="p-1.5 hover:bg-slate-100 dark:hover:bg-slate-700 rounded text-slate-600 dark:text-slate-300"><Hexagon size={14}/></button>
             <button className="p-1.5 hover:bg-slate-100 dark:hover:bg-slate-700 rounded text-slate-600 dark:text-slate-300"><Eraser size={14}/></button>
          </div>
          
          <div className="w-full h-full flex items-center justify-center">
             <div className="text-center space-y-2 opacity-40 group-hover:opacity-20 transition-opacity">
                <Hexagon size={48} className="mx-auto text-slate-300 dark:text-slate-600" />
                <p className="text-xs text-slate-400 dark:text-slate-500">Interactive Canvas Placeholder</p>
             </div>
             
             {/* Mock drawn lines */}
             <svg className="absolute inset-0 w-full h-full pointer-events-none" style={{opacity: 0.6}}>
                <path d="M 100 100 L 140 80 L 180 100 L 180 140 L 140 160 L 100 140 Z" stroke="currentColor" strokeWidth="2" fill="none" className="text-slate-800 dark:text-slate-200" />
                <line x1="140" y1="80" x2="140" y2="50" stroke="currentColor" strokeWidth="2" className="text-slate-800 dark:text-slate-200" />
                <text x="135" y="45" className="fill-red-500 text-xs font-bold">OH</text>
             </svg>
          </div>
          
          <div className="absolute bottom-2 right-2 flex gap-1">
            <button className="p-1 bg-slate-100 dark:bg-slate-800 rounded hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-500"><Undo size={14}/></button>
            <button className="p-1 bg-slate-100 dark:bg-slate-800 rounded hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-500"><Redo size={14}/></button>
          </div>
        </div>
      )}
    </div>
  );
};
