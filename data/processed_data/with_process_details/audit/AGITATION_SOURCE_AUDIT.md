# Agitation source audit

The former combined class contained **121 positive records from 57 distinct DOIs**, plus **115 negative records**. The plotted value 57 was a unique-DOI count, not a record count. It combined seven detailed categories because each had fewer than 50 positive records. Those categories are listed below as a historical description of the superseded grouping; they are not recommended final labels.

| Former detailed category | Positive records | Positive DOIs | Negative records |
| --- | ---: | ---: | ---: |
| Agitation before static synthesis, method unspecified | 34 | 15 | 54 |
| Shaking or rotation, stage unspecified | 29 | 12 | 2 |
| Sonication, stage unspecified | 24 | 12 | 39 |
| Sonication during preparation | 13 | 9 | 1 |
| Agitation, method and stage unspecified | 12 | 8 | 8 |
| Agitation during preparation, method unspecified | 5 | 2 | 1 |
| Stirring during synthesis | 4 | 3 | 10 |

A DOI can contribute to multiple categories, so the category DOI counts sum to more than 57. The raw descriptions included stirring, sonication, shaking, rotation, mixing and homogenization, with distinct reported stages. Low frequency alone does not make these procedures equivalent. The current nine-class representation combines non-sonication methods by the reported stage; it does not assert that stirring, rotation, shaking, and homogenization are physically equivalent. Specific method evidence remains in the detailed audit.

## Source-based clarifications

The table below records direct checks of local article or supporting-information documents. Each correction is restricted to the exact DOI and normalized raw value. Original extracted cells remain unchanged. The reviewed text is a classifier input and does not add new training fields. Classification applies identically to both datasets. Negative records can inherit source-protocol annotations; source review does not independently verify a failed experiment.

The registry is maintained in `src/mofinder/curation/agitation_source_reviews.py`. PDF paths are relative to the research workspace, outside the GitHub repository. Page references mean PDF page numbers, beginning with 1. The DOCX reference uses its section heading because its pagination depends on the renderer.

| DOI | Original extracted value | Reviewed classifier text | Positive / negative records | Local source and location |
| --- | --- | --- | ---: | --- |
| 10.1039/c4ta02568g | vigorous 5 min before heating | vigorously stirred 5 min before heating | 4 / 0 | `14489 paper/downloaded/10.1039_c4ta02568g.pdf`; p. 2, Preparation of CnGua-HKUST-1 |
| 10.1039/d1qi01562a | vigorous for 1 h, then constant for 3 h | stirred during preparation for 1 h; stirred during synthesis for 3 h | 2 / 0 | `14489 paper/downloaded/10.1039_d1qi01562a.pdf`; p. 2, Synthesis of CoNi-piz and Synthesis of CoNi-pyz |
| 10.1039/d4gc01350f | 500 rpm | stirred during synthesis at 500 rpm for 30 min | 1 / 0 | `14489 paper/downloaded/10.1039_d4gc01350f.pdf`; p. 2, section 2.2, stirred-tank comparison |
| 10.1002/aoc.4062 | vigorous | vigorously stirred during synthesis for 24 h | 1 / 0 | `14489 paper/SI downloaded/10.1002_aoc.4062_SI.docx`; section 1.2, Room temperature synthesis (RT) |
| 10.1016/j.cattod.2015.08.030 | vigorous | vigorously stirred during synthesis for 5 min | 1 / 0 | `14489 paper/downloaded/10.1016_j.cattod.2015.08.030.pdf`; p. 2, section 2.2, initial ZIF-8 synthesis |
| 10.1016/j.inoche.2011.06.030 | vigorous | vigorously stirred during synthesis | 3 / 8 | `14489 paper/downloaded/10.1016_j.inoche.2011.06.030.pdf`; p. 1, precipitation syntheses of Zn-1, Zn-2 and Zn-3 |
| 10.1016/j.matchemphys.2025.130363 | vigorous | vigorously stirred during synthesis for 1 h | 1 / 0 | `14489 paper/downloaded/10.1016_j.matchemphys.2025.130363.pdf`; p. 2, ZIF-8 synthesis |
| 10.1002/adma.201901570 | agitated | stirred during preparation for 5 min | 1 / 0 | `14489 paper/SI downloaded/10.1002_adma.201901570_SI.pdf`; p. 4, section 5, Synthesis of pEGFP-C1@ZIF-8 nanostructures |
| 10.1039/c4ce00158c | ultrasonically stirred 15 min before heating | sonicated 15 min before heating | 9 / 0 | `14489 paper/downloaded/10.1039_c4ce00158c.pdf`; pp. 2-3, synthesis protocols for compounds 1-9 |
| 10.1039/d4gc01350f | RPB 1500 rpm, then static | rotated at 1500 rpm, then static | 4 / 0 | `14489 paper/downloaded/10.1039_d4gc01350f.pdf`; p. 2, section 2.2; corresponding SI p. 2, Co variants and MOF-74-Ni |
| 10.1039/d4gc01350f | RPB 1500 rpm | rotated during synthesis at 1500 rpm | 1 / 0 | `14489 paper/SI downloaded/10.1039_d4gc01350f_SI.pdf`; p. 2, MOF-74-Zn synthesis |
| 10.1021/ic402198a | rotated (1.1 kHz MAS) | rotated during synthesis at 1.1 kHz | 1 / 0 | `14489 paper/downloaded/10.1021_ic402198a.pdf`; pp. 2-3, In Situ NMR Experiments and synthesis tracking |

## Evidence and interpretation

- **10.1039/c4ta02568g: `vigorous 5 min before heating`:** The synthesis mixture is explicitly stirred vigorously for five minutes before sealed-autoclave heating. Agitation during heating is not specified.
- **10.1039/d1qi01562a: `vigorous for 1 h, then constant for 3 h`:** Both protocols stir the precursor solution for one hour and continue stirring the combined reactants for three hours before collecting the product.
- **10.1039/d4gc01350f: `500 rpm`:** The stirred-tank comparator continuously stirs the mixture in a beaker at 500 rpm for 30 minutes. The matching extracted row identifies a stirred tank reactor (beaker), distinguishing it from the separate rotating-packed-bed speed series.
- **10.1002/aoc.4062: `vigorous`:** The room-temperature ZIF-8 protocol mixes the two methanolic precursor solutions under vigorous stirring for 24 hours, followed by product centrifugation. The extracted row has the corresponding 24-hour duration and 0.75 metal/linker ratio.
- **10.1016/j.cattod.2015.08.030: `vigorous`:** The initial ZIF-8 synthesis combines aqueous zinc nitrate and methylimidazole under vigorous stirring for five minutes at room temperature, then washes and collects the nanoparticles. The extracted row reports the matching 0.083-hour duration; later catalytic reactions in the same paper were not used.
- **10.1016/j.inoche.2011.06.030: `vigorous`:** All three reported precipitation conditions inject cobalt nitrate into a vigorously stirred linker solution at 60 or 90 degrees Celsius; the 90-degree standard condition explicitly continues stirring after suspension formation. The three positive records match these conditions. Negative matches inherit this source-protocol annotation.
- **10.1016/j.matchemphys.2025.130363: `vigorous`:** The zinc solution is added to methylimidazole under vigorous stirring at room temperature for one hour, followed by particle collection. This agrees with the one-hour extracted ZIF-8 record; later silver-loading procedures were not used.
- **10.1002/adma.201901570: `agitated`:** The matching protocol stirs the initial methylimidazole mixture for five minutes, adds 2.4 mg zinc nitrate while agitating, and ages for 15 minutes. The extracted 23.75 mg linker, 2.4 mg metal precursor and 15-minute duration match this protocol. The agitation method during aging is not stated, so neither static aging nor continuous stirring is inferred.
- **10.1039/c4ce00158c: `ultrasonically stirred 15 min before heating`:** All nine synthesis protocols describe ultrasonic agitation for 15 minutes before heating for three days. This denotes sonication; separate mechanical stirring is not documented. Agitation during heating is not specified.
- **10.1039/d4gc01350f: `RPB 1500 rpm, then static`:** Reactant streams mix in a rotating packed bed at 1500 rpm for two minutes; the collected suspension then stands without stirring. The SI carries the same procedure over to the Co variants and Ni product. The four matching records retain the reported rotation-to-static sequence.
- **10.1039/d4gc01350f: `RPB 1500 rpm`:** The zinc precursors mix and crystallize in the rotating packed bed at 1500 rpm, and product is collected immediately at the outlet. The matching Zn record has a 0.033-hour duration and does not describe a subsequent static hold.
- **10.1021/ic402198a: `rotated (1.1 kHz MAS)`:** The precursor solution reacts inside a PEEK insert in a MAS rotor at 1.1 kHz while in-situ NMR follows formation at 130 degrees Celsius. The extracted record identifies the same PEEK insert and MAS rotor. This is rotation during an in-situ synthesis experiment, not post-synthesis characterization of a recovered powder.

These checks resolve all six positive records and eight negative records whose raw value is only `vigorous`. Such a word is not treated as a universal synonym for stirring: the lookup requires a reviewed DOI. The isolated `500 rpm` record is identified as the stirred-tank comparison by its vessel and 30-minute duration; the same paper also contains rotating-packed-bed speed experiments, so the bare rate alone would be insufficient.

The nine `ultrasonically stirred` records come from outside the former combined class. The source consistently describes ultrasonic agitation before heating, so they are treated as sonication during preparation. It does not report a separate mechanical-stirring step or establish static conditions during heating.

The 1.1 kHz MAS case is retained as rotation during synthesis. The precursor mixture reacts inside the rotating NMR insert while crystallization is followed in situ; it is not merely analysis of a previously isolated solid. The rotating-packed-bed records also represent synthesis operations. Their subsequent static hold is retained only where explicitly reported.

This is a targeted audit of ambiguous method and stage descriptions. It is not a claim that every extraction in the full corpus has been rechecked against its original source.

## Where the former combined records now appear

The original 121 positive records span 57 unique DOIs; the 115 negative rows use the same rules. The [record-level breakdown](former_combined_agitation_records.csv) retains the source row, DOI, original text, detailed method, final class, and applied rule. The table below covers only the former combined class. DOI counts use distinct DOI sets within each merged class; a DOI can contribute to several classes.

| Current class | Positive records | Positive DOIs | Negative records |
|---|---:|---:|---:|
| Agitated before static synthesis | 34 | 15 | 54 |
| Agitated during preparation | 6 | 3 | 1 |
| Agitated during synthesis | 15 | 10 | 18 |
| Agitated; stage not reported | 29 | 11 | 2 |
| Sonicated during preparation | 13 | 9 | 1 |
| Sonicated; stage not reported | 24 | 12 | 39 |
