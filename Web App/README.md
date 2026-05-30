# MOFinder

A searchable platform for exploring literature-derived MOF synthesis data.

MOFinder is an interactive web application for searching, filtering, and analyzing metal-organic framework (MOF) synthesis information extracted from the scientific literature. The platform enables researchers to rapidly explore synthesis conditions, reaction parameters, and material properties across thousands of reported MOFs.

MOFinder was developed as part of the MOF Reactome project to support data-driven materials discovery, literature mining, and AI-assisted synthesis planning.

## Features

- Search MOFs by name, metal, linker, or DOI
- Explore literature-derived synthesis conditions
- Visualize reaction parameters and material properties
- Browse metal, linker, solvent, and modulator usage
- Interactive filtering and data exploration
- AI-ready structured synthesis dataset
- Web-based interface with no installation required

## Research Applications

MOFinder supports:

- MOF synthesis planning
- Literature exploration
- Materials informatics
- Reticular chemistry research
- Data-driven materials discovery
- AI-assisted materials design

## Technology Stack

- React
- TypeScript
- Vite
- Tailwind CSS
- Gemini API

## Run Locally

### Prerequisites

- Node.js

### Installation

Install dependencies:

```bash
npm install
```

Create `.env.local`:

```env
GEMINI_API_KEY=YOUR_API_KEY
```

Run locally:

```bash
npm run dev
```

Build for production:

```bash
npm run build
```

## Online Version

https://mofinder.chemistry.wustl.edu/

## Related Projects

- MOF Reactome
- MOF Quest
- LLM-based MOF literature mining
- Negative-data reasoning for materials discovery



## Acknowledgements

This application was initially prototyped using Google AI Studio and Gemini models.



© 2026 Zheng Research Group
