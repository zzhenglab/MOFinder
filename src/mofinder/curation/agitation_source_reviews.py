"""DOI-and-raw-value-scoped agitation clarifications checked against local sources.

The original extracted cells are retained. These replacements clarify only the
reported agitation method or stage for the exact DOI/raw-value pair; they are
not general rules for words such as ``vigorous`` or bare rotation rates.
The same lookup applies to both datasets. A matching negative row still carries
an inherited source-protocol annotation, not an independently verified attempt.
Source paths are relative to the research workspace, which contains the PDFs.
"""

SOURCE_REVIEWS = (
    {
        "doi": "10.1039/c4ta02568g",
        "raw_value": "vigorous 5 min before heating",
        "corrected_text": "vigorously stirred 5 min before heating",
        "source_path": "14489 paper/downloaded/10.1039_c4ta02568g.pdf",
        "location": "p. 2, Preparation of CnGua-HKUST-1",
        "evidence": "The synthesis mixture is explicitly stirred vigorously for five minutes before sealed-autoclave heating. Agitation during heating is not specified.",
    },
    {
        "doi": "10.1039/d1qi01562a",
        "raw_value": "vigorous for 1 h, then constant for 3 h",
        "corrected_text": "stirred during preparation for 1 h; stirred during synthesis for 3 h",
        "source_path": "14489 paper/downloaded/10.1039_d1qi01562a.pdf",
        "location": "p. 2, Synthesis of CoNi-piz and Synthesis of CoNi-pyz",
        "evidence": "Both protocols stir the precursor solution for one hour and continue stirring the combined reactants for three hours before collecting the product.",
    },
    {
        "doi": "10.1039/d4gc01350f",
        "raw_value": "500 rpm",
        "corrected_text": "stirred during synthesis at 500 rpm for 30 min",
        "source_path": "14489 paper/downloaded/10.1039_d4gc01350f.pdf",
        "location": "p. 2, section 2.2, stirred-tank comparison",
        "evidence": "The stirred-tank comparator continuously stirs the mixture in a beaker at 500 rpm for 30 minutes. The matching extracted row identifies a stirred tank reactor (beaker), distinguishing it from the separate rotating-packed-bed speed series.",
    },
    {
        "doi": "10.1002/aoc.4062",
        "raw_value": "vigorous",
        "corrected_text": "vigorously stirred during synthesis for 24 h",
        "source_path": "14489 paper/SI downloaded/10.1002_aoc.4062_SI.docx",
        "location": "section 1.2, Room temperature synthesis (RT)",
        "evidence": "The room-temperature ZIF-8 protocol mixes the two methanolic precursor solutions under vigorous stirring for 24 hours, followed by product centrifugation. The extracted row has the corresponding 24-hour duration and 0.75 metal/linker ratio.",
    },
    {
        "doi": "10.1016/j.cattod.2015.08.030",
        "raw_value": "vigorous",
        "corrected_text": "vigorously stirred during synthesis for 5 min",
        "source_path": "14489 paper/downloaded/10.1016_j.cattod.2015.08.030.pdf",
        "location": "p. 2, section 2.2, initial ZIF-8 synthesis",
        "evidence": "The initial ZIF-8 synthesis combines aqueous zinc nitrate and methylimidazole under vigorous stirring for five minutes at room temperature, then washes and collects the nanoparticles. The extracted row reports the matching 0.083-hour duration; later catalytic reactions in the same paper were not used.",
    },
    {
        "doi": "10.1016/j.inoche.2011.06.030",
        "raw_value": "vigorous",
        "corrected_text": "vigorously stirred during synthesis",
        "source_path": "14489 paper/downloaded/10.1016_j.inoche.2011.06.030.pdf",
        "location": "p. 1, precipitation syntheses of Zn-1, Zn-2 and Zn-3",
        "evidence": "All three reported precipitation conditions inject cobalt nitrate into a vigorously stirred linker solution at 60 or 90 degrees Celsius; the 90-degree standard condition explicitly continues stirring after suspension formation. The three positive records match these conditions. Negative matches inherit this source-protocol annotation.",
    },
    {
        "doi": "10.1016/j.matchemphys.2025.130363",
        "raw_value": "vigorous",
        "corrected_text": "vigorously stirred during synthesis for 1 h",
        "source_path": "14489 paper/downloaded/10.1016_j.matchemphys.2025.130363.pdf",
        "location": "p. 2, ZIF-8 synthesis",
        "evidence": "The zinc solution is added to methylimidazole under vigorous stirring at room temperature for one hour, followed by particle collection. This agrees with the one-hour extracted ZIF-8 record; later silver-loading procedures were not used.",
    },
    {
        "doi": "10.1002/adma.201901570",
        "raw_value": "agitated",
        "corrected_text": "stirred during preparation for 5 min",
        "source_path": "14489 paper/SI downloaded/10.1002_adma.201901570_SI.pdf",
        "location": "p. 4, section 5, Synthesis of pEGFP-C1@ZIF-8 nanostructures",
        "evidence": "The matching protocol stirs the initial methylimidazole mixture for five minutes, adds 2.4 mg zinc nitrate while agitating, and ages for 15 minutes. The extracted 23.75 mg linker, 2.4 mg metal precursor and 15-minute duration match this protocol. The agitation method during aging is not stated, so neither static aging nor continuous stirring is inferred.",
    },
    {
        "doi": "10.1039/c4ce00158c",
        "raw_value": "ultrasonically stirred 15 min before heating",
        "corrected_text": "sonicated 15 min before heating",
        "source_path": "14489 paper/downloaded/10.1039_c4ce00158c.pdf",
        "location": "pp. 2-3, synthesis protocols for compounds 1-9",
        "evidence": "All nine synthesis protocols describe ultrasonic agitation for 15 minutes before heating for three days. This denotes sonication; separate mechanical stirring is not documented. Agitation during heating is not specified.",
    },
    {
        "doi": "10.1039/d4gc01350f",
        "raw_value": "RPB 1500 rpm, then static",
        "corrected_text": "rotated at 1500 rpm, then static",
        "source_path": "14489 paper/downloaded/10.1039_d4gc01350f.pdf",
        "location": "p. 2, section 2.2; corresponding SI p. 2, Co variants and MOF-74-Ni",
        "evidence": "Reactant streams mix in a rotating packed bed at 1500 rpm for two minutes; the collected suspension then stands without stirring. The SI carries the same procedure over to the Co variants and Ni product. The four matching records retain the reported rotation-to-static sequence.",
    },
    {
        "doi": "10.1039/d4gc01350f",
        "raw_value": "RPB 1500 rpm",
        "corrected_text": "rotated during synthesis at 1500 rpm",
        "source_path": "14489 paper/SI downloaded/10.1039_d4gc01350f_SI.pdf",
        "location": "p. 2, MOF-74-Zn synthesis",
        "evidence": "The zinc precursors mix and crystallize in the rotating packed bed at 1500 rpm, and product is collected immediately at the outlet. The matching Zn record has a 0.033-hour duration and does not describe a subsequent static hold.",
    },
    {
        "doi": "10.1021/ic402198a",
        "raw_value": "rotated (1.1 kHz MAS)",
        "corrected_text": "rotated during synthesis at 1.1 kHz",
        "source_path": "14489 paper/downloaded/10.1021_ic402198a.pdf",
        "location": "pp. 2-3, In Situ NMR Experiments and synthesis tracking",
        "evidence": "The precursor solution reacts inside a PEEK insert in a MAS rotor at 1.1 kHz while in-situ NMR follows formation at 130 degrees Celsius. The extracted record identifies the same PEEK insert and MAS rotor. This is rotation during an in-situ synthesis experiment, not post-synthesis characterization of a recovered powder.",
    },
)
