"""Append audited process features to positive/negative CSVs without filtering.

Run: python -m mofinder.curation.process_details --config configs/process_details.json
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

from .process_vessels import VERSION, vessel_type, vessel_volume_mL
from .process_stirring import normalize_stirring

FEATURES = ('vessel_type','vessel_volume_mL','stirring')
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
        if 'vessel_volume_mL' in fields or any(x in fields for x in RAW_RENAMES.values()):
            raise ValueError('Expected original processed CSVs, not already enriched inputs')
        output_fields = [RAW_RENAMES.get(x,x) for x in fields]+list(FEATURES)
        source_counts[label] = len(rows)
        exported = []
        for i,row in enumerate(rows):
            v = vessel_type(row['vessel_type'])
            volume = vessel_volume_mL(row['vessel_type'])
            stir = normalize_stirring(row['stirring'])
            derived = {'vessel_type':v,'vessel_volume_mL':volume,'stirring':stir}
            clean = {RAW_RENAMES.get(k,k):value for k,value in row.items()}
            clean.update({k:csv_text(info['value']) for k,info in derived.items()})
            exported.append(clean)
            audit = {'dataset':label,'source_row_id':offset+i,'csv_data_row_1based':i+1,'doi':row['doi'],
                     'vessel_type_raw':row['vessel_type'],'stirring_raw':row['stirring']}
            for feature,info in derived.items():
                audit[feature]=csv_text(info['value'])
                audit[feature+'_rule']=info['rule']
                audit[feature+'_review_reason']=info['review_reason']
                raw_value = row['stirring' if feature=='stirring' else 'vessel_type']
                key=(feature,raw_value)
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
    manifest={'schema_version':1,'normalization_version':VERSION,'files':outputs,
              'features':list(FEATURES),'vessel_volume_unit':'mL',
              'missing_value':'Not reported','ambiguous_volume_value':'Ambiguous',
              'normalization_code_sha256':{f.name:digest(f) for f in
                    [Path(__file__),Path(__file__).with_name('process_vessels.py'),Path(__file__).with_name('process_stirring.py')]},
              'raw_mappings':len(mapping_rows),'review_required_mappings':len(flagged),
              'rare_mappings_frequency_le5':len(rare),
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
