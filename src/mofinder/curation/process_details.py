"""Append audited process features to positive/negative CSVs without filtering.

Run: python -m mofinder.curation.process_details --config configs/process_details.json
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

from .process_vessels import VERSION, VESSEL_LABEL_MAP, VESSEL_RARE_POSITIVE_COUNTS, vessel_type, vessel_volume_mL
from .process_stirring import STIRRING_LABEL_MAP, STIRRING_PARSER_VERSION, STIRRING_CLASSES, normalize_stirring, write_stirring_audit

FEATURES = ('vessel_type','vessel_volume_mL','agitation')
RAW_RENAMES = {'vessel_type':'vessel_type_raw','stirring':'stirring_raw'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def csv_text(value):
    if isinstance(value,(int,float)):
        return format(value,'.10g')
    return str(value)


def write_csv(path, fields, rows):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temp = path.with_name(path.name+'.tmp')
    with temp.open('w',encoding='utf-8-sig',newline='') as f:
        writer = csv.DictWriter(f,fieldnames=fields,lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames,list(reader)
    if not fields or len(set(fields)) != len(fields) or not rows:
        raise ValueError(f'Expected nonempty CSV with unique headers: {path}')
    if any(None in row or None in row.values() for row in rows):
        raise ValueError(f'Malformed CSV row: {path}')
    return fields,rows


def prepare_process_details(positive_csv, negative_csv, output_dir):
    out = Path(output_dir).resolve()
    audit_dir = out/'audit'
    audit_dir.mkdir(parents=True,exist_ok=True)
    outputs, audit_rows, source_counts = [], [], {}
    mappings = {}
    offset = 0
    for label, path in [('positive',Path(positive_csv).resolve()),('negative',Path(negative_csv).resolve())]:
        destination = out/f'Process_detail_{label}.csv'
        if destination.resolve() in {Path(positive_csv).resolve(),Path(negative_csv).resolve()}:
            raise ValueError('Output must not replace either original input')
        initial_hash = digest(path)
        fields, rows = read_csv(path)
        for required in ['doi','vessel_type','stirring']:
            if required not in fields:
                raise ValueError(f'Missing required column {required}: {path}')
        if 'agitation' in fields or 'vessel_volume_mL' in fields or any(x in fields for x in RAW_RENAMES.values()):
            raise ValueError('Expected original processed CSVs, not already enriched inputs')
        output_fields = [RAW_RENAMES.get(x,x) for x in fields]+list(FEATURES)
        source_counts[label] = len(rows)
        exported = []
        for i,row in enumerate(rows):
            v = vessel_type(row['vessel_type'])
            volume = vessel_volume_mL(row['vessel_type'])
            stir = normalize_stirring(row['stirring'], row['doi'])
            derived = {'vessel_type':v,'vessel_volume_mL':volume,'agitation':stir}
            derived = {feature: {
                'value': info['value'], 'detailed_value': info.get('detailed_value', info['value']),
                'rule': info['rule'], 'consolidation_rule': info.get('consolidation_rule', ''),
                'normalized_text': info['normalized_text'], 'review_reason': info['review_reason'],
            } for feature, info in derived.items()}
            clean = {RAW_RENAMES.get(k,k):value for k,value in row.items()}
            clean.update({k:csv_text(info['value']) for k,info in derived.items()})
            exported.append(clean)
            audit = {'dataset':label,'source_row_id':offset+i,'csv_data_row_1based':i+1,'doi':row['doi'],
                     'vessel_type_raw':row['vessel_type'],'stirring_raw':row['stirring']}
            for feature,info in derived.items():
                audit[feature]=csv_text(info['value'])
                audit[feature+'_detailed_value']=csv_text(info['detailed_value'])
                audit[feature+'_rule']=info['rule']
                audit[feature+'_consolidation_rule']=info['consolidation_rule']
                audit[feature+'_review_reason']=info['review_reason']
                raw_value = row['stirring' if feature=='agitation' else 'vessel_type']
                key=(feature,raw_value,info['value'],info['rule'])
                if key not in mappings:
                    mappings[key]={'feature':feature,'raw_value':raw_value,**info,
                                   'positive_records':0,'negative_records':0}
                mappings[key][label+'_records']+=1
            audit['process_provenance']=('extracted positive annotation' if label=='positive' else
                                        'reconstructed negative; process may be inherited from positive parent')
            audit_rows.append(audit)
        write_csv(destination,output_fields,exported)
        check_fields, check_rows = read_csv(destination)
        assert check_fields==output_fields and len(check_rows)==len(rows)
        assert all(all(before[k]==after[RAW_RENAMES.get(k,k)] for k in fields)
                   for before,after in zip(rows,check_rows)), 'Source cells or row order changed'
        if digest(path) != initial_hash:
            raise ValueError(f'Source changed during normalization: {path}')
        repo = Path(__file__).resolve().parents[3]
        source_path = path.relative_to(repo).as_posix() if path.is_relative_to(repo) else str(path)
        outputs.append({'dataset':label,'file':destination.name,'rows':len(rows),
                        'input_columns':len(fields),'output_columns':len(output_fields),
                        'input':source_path,'input_sha256':digest(path),'sha256':digest(destination),
                        'retained_cells_and_order_equal':True,'raw_column_renames':RAW_RENAMES})
        offset+=len(rows)
    write_csv(audit_dir/'record_process_audit.csv',list(audit_rows[0]),audit_rows)
    mapping_rows = sorted(mappings.values(),key=lambda r:(r['feature'],-r['positive_records']-r['negative_records'],r['raw_value']))
    write_csv(audit_dir/'all_raw_value_mappings.csv',list(mapping_rows[0]),mapping_rows)
    flagged = [r for r in mapping_rows if r['review_reason']]
    write_csv(audit_dir/'review_required_mappings.csv',list(mapping_rows[0]),flagged)
    rare = [r for r in mapping_rows if r['positive_records']+r['negative_records']<=5]
    write_csv(audit_dir/'rare_value_mappings.csv',list(mapping_rows[0]),rare)
    consolidation = {}
    for item in mapping_rows:
        if not item['consolidation_rule']:
            continue
        key = (item['feature'], str(item['detailed_value']), str(item['value']), item['consolidation_rule'])
        entry = consolidation.setdefault(key, dict(zip(
            ['feature','detailed_value','final_value','consolidation_rule'], key),
            positive_records=0, negative_records=0))
        for label in ('positive_records','negative_records'):
            entry[label] += item[label]
    consolidation_fields = ['feature','detailed_value','final_value','consolidation_rule','positive_records','negative_records']
    write_csv(audit_dir/'category_consolidation.csv',consolidation_fields,list(consolidation.values()))
    count_rows=[]
    for label in source_counts:
        selected=[r for r in audit_rows if r['dataset']==label]
        for feature in FEATURES:
            counts=Counter(r[feature] for r in selected)
            for value,count in counts.most_common():
                dois={r['doi'].strip().casefold() for r in selected if r[feature]==value}
                count_rows.append({'dataset':label,'feature':feature,'value':value,'records':count,
                                   'record_percent':count/source_counts[label]*100,'unique_dois':len(dois)})
    write_csv(audit_dir/'feature_counts.csv',list(count_rows[0]),count_rows)
    stirring_audit = write_stirring_audit(Path(positive_csv), Path(negative_csv), audit_dir)
    manifest={'schema_version':1,'normalization_version':VERSION,'files':outputs,
              'features':list(FEATURES),'vessel_volume_unit':'mL',
              'missing_value':'Not reported','ambiguous_volume_value':'Ambiguous',
              'category_consolidation': {
                  'frequency_basis': 'positive synthesis records in the audited reference cohort',
                  'same_fixed_mapping_for_positive_negative_train_holdout': True,
                  'vessel_label_map': VESSEL_LABEL_MAP,
                  'vessel_rare_positive_counts': VESSEL_RARE_POSITIVE_COUNTS,
                  'vessel_rare_threshold_exclusive': 10,
                  'agitation_frequency_pooling': False,
                  'agitation_classes': list(STIRRING_CLASSES),
                  'agitation_grouping': 'Non-sonication methods share stage-based classes; sonication remains separate. Detailed methods stay in audit fields.',
                  'agitation_label_map': STIRRING_LABEL_MAP,
                  'agitation_parser_version': STIRRING_PARSER_VERSION,
                  'agitation_label_max_words': 5,
                  'detailed_classes_retained_in_audit': True,
                  'audit_file': 'audit/category_consolidation.csv',
                  'not_reported_caveat': 'Includes unspecified vessel types, pooled rare vessel types, and descriptions that do not uniquely specify synthesis agitation.',
              },
              'normalization_code_sha256':{f.name:digest(f) for f in
                    [Path(__file__),Path(__file__).with_name('process_vessels.py'),Path(__file__).with_name('process_stirring.py'),Path(__file__).with_name('agitation_source_reviews.py')]},
              'raw_mappings':len(mapping_rows),'review_required_mappings':len(flagged),
              'rare_mappings_frequency_le5':len(rare),
              'agitation_audit': stirring_audit,
              'rows_preserved':True,'source_values_preserved':True,
              'negative_provenance':'Negative process annotations can be inherited; normalization does not validate failed attempts.'}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path)
    parser.add_argument('--positive',type=Path)
    parser.add_argument('--negative',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    settings={}
    if args.config:
        settings=json.loads(args.config.read_text(encoding='utf-8'))
        root=(args.config.resolve().parent/settings.get('project_root','..')).resolve()
        settings={key:root/value for key,value in settings.items() if key!='project_root'}
    positive=args.positive or settings.get('positive_csv')
    negative=args.negative or settings.get('negative_csv')
    output=args.output or settings.get('output_dir')
    if not all([positive,negative,output]):
        parser.error('Provide --config or all of --positive, --negative, --output')
    print(json.dumps(prepare_process_details(positive,negative,output),indent=2))


if __name__=='__main__':
    main()
