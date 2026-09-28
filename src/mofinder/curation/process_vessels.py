"""Conservative, auditable normalization of vessel descriptions and capacities.

Categories describe the text, not experimentally verified apparatus. Capacities
are in mL; charge volumes and geometric dimensions are never used as capacity.
"""
import math
import re
import unicodedata

NOT_REPORTED = 'Not reported'
AMBIGUOUS = 'Ambiguous'
MISSING = {'', 'none', 'null', 'nan', 'na', 'n/a', 'not reported', 'not_reported',
           'unknown', 'unspecified', 'not specified', '-', '--'}
VERSION = '2.0.0'
VESSEL_LABEL_MAP = {
    'Glass vessel (shape not reported)': 'Glass vessel',
    'Polymer vessel (shape not reported)': 'Polymer vessel',
    'Metal vessel (shape not reported)': 'Metal vessel',
}
# Fixed classes audited in the full positive reference cohort, not recomputed
# separately for negative records, holdout data, or each future input file.
VESSEL_RARE_POSITIVE_COUNTS = {'Crucible': 1, 'Dialysis bag': 3, 'Rotor insert': 1}


def normalize_text(value):
    if value is None or isinstance(value, float) and math.isnan(value):
        return ''
    s = unicodedata.normalize('NFKC', str(value)).casefold()
    for char in ['‐', '‑', '‒', '–', '—', '−']:
        s = s.replace(char, '-')
    s = s.replace('μ', 'u').replace('µ', 'u').replace('\u200b', '')
    s = re.sub(r'(?<=\d),(?=\d{3}(?:\D|$))', '', s)
    s = re.sub(r'(\d),(\d{1,2})(?=\s*(?:ml|ul|l)\b)', r'\1.\2', s)
    s = re.sub(r'(?<=\d)\s*[x×]\s*(?=\d)', ' x ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return '' if s in MISSING else s


def result(value, rule, normalized_text, review_reason=''):
    return dict(value=value, rule=rule, normalized_text=normalized_text,
                review_reason=review_reason)


def nested_vessels(s):
    # A PTFE liner in a steel shell is a normal lined vessel, not two recipes.
    # Microwave hardware/heater blocks are not a second reaction container.
    s = re.sub(r'\b(?:in|within)\s+(?:a\s+)?(?:ht |microwave )?reactor block\b.*', '', s)
    s = re.sub(r'\b(?:in|within)\s+(?:a\s+)?microwave reactor\b.*', '', s)
    s = re.sub(r'\bin\s+(?:a\s+)?(?:preheated\s+)?oven\b.*', '', s)
    portable = r'(?:vials?|tubes?|bottles?|ampoules?|ampules?|flasks?|beakers?|vessels?|bags?)'
    outer = r'(?:vials?|tubes?|bottles?|autoclaves?|reactors?|containers?|vessels?)'
    if re.search(portable+r'\b.*\b(?:inside|within|in|into)\b.*\b'+outer, s):
        return True
    if re.search(r'\b(?:reactor|autoclave|vessel)\b.*\b(?:vial|tube)\b.*\b(?:inside|inserted)\b', s):
        return True
    if re.search(r'\b(?:with|containing)\b.*\bvial\b.*\binside\b', s):
        return True
    if re.search(r'\b(?:transferred|transfer|crystallization in)\b', s) and len(re.findall(portable,s)) > 1:
        return True
    if ';' in s and re.search(portable+r'|\bautoclave\b',s.split(';',1)[0]) and re.search(portable,s.split(';',1)[1]):
        return True
    if re.search(r'\binner (?:vial|tube|vessel)\b',s):
        return True
    if re.search(r'\breactor\b.*\bimmersed in\b.*\bbottle\b',s):
        return True
    return False


def _vessel_type_detail(value):
    s = normalize_text(value)
    if not s:
        return result(NOT_REPORTED, 'missing', s)
    if nested_vessels(s):
        return result('Nested / multiple vessels', 'multiple_vessels', s,
                      'Nested or sequential apparatus; no single vessel selected')
    if re.search(r'\bmicrowave\b', s) and re.search(r'vial|tube|vessel|reactor|bottle|autoclave|synthesizer',s):
        return result('Microwave vessel', 'microwave_apparatus', s)
    # Remove ancillary PTFE components before identifying a lined vessel body.
    body = re.sub(r'\bcap and (?:teflon|ptfe) liner\b', 'cap', s)
    body = re.sub(r'\bcapped with (?:a )?(?:teflon|ptfe) (?:vial|cup)\b', '', body)
    body = re.sub(r'\b(?:teflon|ptfe)[- ]+(?:capped|sealed)\b', '', body)
    body = re.sub(r'\b(?:teflon|ptfe)(?:[- ]+(?:lined|coated|rubber|mechanical|screw(?:-top)?|'
                  r'faced|sealing|taped|wrapped|phenolic|supported)){0,4}'
                  r'[- ]+(?:caps?|capped|seals?|tape|stirrers?|stir(?:ring)? bars?|'
                  r'adaptors?|adapters?|spacers?|lids?|screwcap|septum|septa|gaskets?|wads?|covers?|necks?)\b', '', body)
    ptfe = bool(re.search(r'\b(?:teflon|ptfe|polytetrafluoroethylene)\b', body))
    pressure = bool(re.search(r'\bautoclaves?\b|\bbombs?\b|\bdigestion\b',body) or
                    re.search(r'\bpressure\b',body) and re.search(r'\b(?:vessel|reactor|container)\b',body))
    if ptfe and pressure:
        return result('PTFE-lined autoclave / pressure vessel', 'ptfe_pressure_vessel', s)
    if pressure:
        return result('Autoclave / pressure vessel', 'pressure_vessel', s)
    if ptfe:
        return result('PTFE vessel / liner', 'ptfe_body', s)
    if re.search(r'\b(?:ampoules?|ampules?|ampullae?|ampulla)\b',s):
        return result('Ampoule', 'ampoule', s)
    if re.search(r'\bflasks?\b|erlenmeyer|round[- ]bottom|three[- ]neck(?:ed)? balloon',s):
        return result('Flask', 'flask', s)
    if re.search(r'\b(?:beakers?)\b',s):
        return result('Beaker', 'beaker', s)
    if re.search(r'\b(?:bottles?|jars?)\b',s):
        return result('Bottle / jar', 'bottle_jar', s)
    if re.search(r'\b(?:vials?)\b|scintillation',s):
        return result('Vial', 'vial', s)
    if re.search(r'\breactors?\b|\bkettles?\b|\breaction chambers?\b',s):
        return result('Reactor / reaction chamber', 'reactor', s)
    if re.search(r'\btubes?\b|\bschlenk\b|\bcapillar(?:y|ies)\b',s):
        return result('Tube / capillary', 'tube', s)
    if re.search(r'\b(?:petri|culture|staining|evaporating) dishes?\b|\bdish\b|\bwell[- ]?plate\b|\bmultiwell\b',s):
        return result('Dish / well plate', 'dish_plate', s)
    if 'crucible' in s:
        return result('Crucible', 'crucible', s)
    if re.search(r'dialysis (?:bag|membrane)|dialysis tubing',s):
        return result('Dialysis bag', 'dialysis_bag', s)
    if re.search(r'\brotor\b',s) and re.search(r'\binsert\b',s):
        return result('Rotor insert', 'rotor_insert', s)
    if re.search(r'\bcell\b',s):
        return result('Reaction cell', 'reaction_cell', s)
    if re.search(r'glass|pyrex|borosilicate|quartz',s) and re.search(r'vessel|container|cell|liner|chamber',s):
        return result('Glass vessel (shape not reported)', 'generic_glass', s)
    if re.search(r'polypropylene|polyethylene|\bhdpe\b|plastic',s) and re.search(r'vessel|container|cell',s):
        return result('Polymer vessel (shape not reported)', 'generic_polymer', s)
    if re.search(r'\b(?:steel|metal)\b',s) and re.search(r'vessel|container',s):
        return result('Metal vessel (shape not reported)', 'generic_metal', s)
    if re.search(r'\b(?:vessels?|containers?|cells?|chambers?|inserts?|liners?)\b',s):
        return result('Vessel (type not reported)', 'generic_vessel', s,
                      'Vessel is named but shape/material cannot be resolved')
    if re.search(r'heater|oven|furnace|oil bath|water bath|ultraso|lyophiliz|reflux|layer|soak|ambient|room temperature|diffusion|spray dryer',s):
        return result(NOT_REPORTED, 'equipment_or_operation_only', s,
                      'Description specifies equipment/operation, not an identifiable reaction vessel')
    return result('Unresolved vessel description', 'unresolved', s,
                  'No defensible vessel category from the recorded text')


def vessel_type(value):
    """Return the model category and retain the finer parsed class for audit."""
    info = _vessel_type_detail(value)
    detailed = info['value']
    info['detailed_value'] = detailed
    info['consolidation_rule'] = ''
    if detailed in VESSEL_LABEL_MAP:
        info['value'] = VESSEL_LABEL_MAP[detailed]
        info['consolidation_rule'] = 'simplify_material_vessel_label'
    elif detailed == 'Vessel (type not reported)':
        info['value'] = NOT_REPORTED
        info['consolidation_rule'] = 'unspecified_vessel_type_to_not_reported'
    elif detailed in VESSEL_RARE_POSITIVE_COUNTS:
        info['value'] = NOT_REPORTED
        info['consolidation_rule'] = 'positive_reference_count_below_10_to_not_reported'
        info['review_reason'] = (
            'Reported vessel pooled into Not reported by the requested rare-class policy; '
            f'positive reference count={VESSEL_RARE_POSITIVE_COUNTS[detailed]}. '
            'The raw description and detailed class remain available in the audit.'
        )
    return info


UNITS = r'(?:m\s*l|u\s*l|l|c\s*m\s*3|c\s*c)'
CAPACITY = re.compile(r'(?<![\w.])(?P<number>[-+]?\d+(?:\.\d+)?)\s*-?\s*(?P<unit>'+UNITS+r')\b')


def vessel_volume_mL(value):
    s = normalize_text(value)
    if not s:
        return result(NOT_REPORTED, 'missing_vessel', s)
    kind = vessel_type(value)
    if kind['rule'] == 'equipment_or_operation_only':
        return result(NOT_REPORTED, 'no_identified_vessel', s, kind['review_reason'])
    if nested_vessels(s):
        return result(AMBIGUOUS, 'nested_vessel_capacity', s,
                      'Capacity cannot be assigned to one reaction vessel in nested/sequential apparatus')
    if re.search(r'\d\s*(?:-|to|or|/)\s*\d+(?:\.\d+)?\s*-?\s*'+UNITS+r'\b',s):
        return result(AMBIGUOUS, 'range_or_alternative_capacity', s,
                      'Range, alternative, or fraction is not reduced to an arbitrary scalar')
    if re.search(r'\d\s*(?:\?|�)\s*l\b',s):
        return result(AMBIGUOUS, 'damaged_volume_unit', s,
                      'Corrupted unit could change the volume scale; no unit guessed')
    hits = list(CAPACITY.finditer(s))
    candidates = []
    charge_count = 0
    for hit in hits:
        before = s[max(0,hit.start()-40):hit.start()]
        after = s[hit.end():hit.end()+35]
        if (re.search(r'(?:reaction|solution|liquid|solvent|working|charge)\s+volume[^;,()]*$',before)
            or re.search(r'\b(?:containing|filled with|charged with)\s*$',before)
            or re.match(r'\s*(?:of )?(?:suspension|solution|reaction mixture|water|h2o|etoh|dmf|methanol|ethanol|acetone|acetonitrile)\b',after)
            or re.match(r'\s*(?:working|reaction|solution|liquid|solvent) volume\b',after)):
            charge_count += 1
            continue
        number = float(hit.group('number'))
        unit = re.sub(r'\s+','',hit.group('unit'))
        scale = {'ml':1.0,'ul':.001,'l':1000.0,'cm3':1.0,'cc':1.0}[unit]
        candidates.append(number*scale)
    if not candidates:
        if hits and charge_count:
            return result(NOT_REPORTED, 'charge_volume_only', s,
                          'Only a reaction/solution charge is stated, not vessel capacity')
        if re.search(r'\b(?:drams?|dr|ounces?|oz)\b',s):
            return result(AMBIGUOUS, 'unspecified_imperial_volume', s,
                          'Imperial/US customary size without explicit mL equivalent; convention not assumed')
        if re.search(r'\d.*\b(?:ml|ul|cm3|cc)\b',s):
            return result(AMBIGUOUS, 'unparsed_capacity', s,
                          'Volume-like text requires review')
        return result(NOT_REPORTED, 'capacity_not_reported', s)
    distinct = sorted(set(round(x,10) for x in candidates))
    if any(x <= 0 for x in distinct):
        return result(AMBIGUOUS, 'nonpositive_capacity', s, 'Capacity must be positive')
    if len(distinct) != 1:
        return result(AMBIGUOUS, 'multiple_capacity_values', s,
                      'Several distinct volume values without an unambiguous single capacity')
    number = distinct[0]
    reason = ''
    if kind['value'] == 'Vial' and number >= 1000:
        return result(AMBIGUOUS, 'suspect_vial_volume_scale', s,
                      'Vial description with capacity >=1000 mL requires source verification; no unit correction guessed')
    if number < 1 or number > 500:
        reason = 'Uncommon stated capacity retained; source verification recommended'
    return result(number, 'explicit_capacity_ml', s, reason)
