"""Regression cases from the complete raw-vessel audit and charge ambiguity."""
import csv
from pathlib import Path
import tempfile
import unittest

from mofinder.curation.process_vessels import vessel_type, vessel_volume_mL
from mofinder.curation.process_details import prepare_process_details


class VesselTests(unittest.TestCase):
    def test_ptfe_accessories_do_not_change_body(self):
        examples = {
            '40 mL glass vial with PTFE septum':'Vial',
            '20 mL glass scintillation vial, Teflon-lined screw-top cap':'Vial',
            'glass vial (15 mL, Teflon-supported cover)':'Vial',
            'Pyrex vial with PTFE-lined phenolic cap':'Vial',
            'sealed DURAN culture glass tube with PTFE-faced sealing wad':'Tube / capillary',
            '100 mL bottle with Teflon-taped screw cap':'Bottle / jar',
            '5 L glass reactor with reflux condenser and Teflon-lined mechanical stirrer':'Reactor / reaction chamber',
            '20 mL scintillation vial (sealed with urethane cap and PTFE liner)':'Vial',
            'Teflon-lined sealed solvothermal vessel':'PTFE vessel / liner',
        }
        for raw, expected in examples.items():
            with self.subTest(raw=raw):
                self.assertEqual(vessel_type(raw)['value'],expected)

    def test_nested_and_apparatus_only_context(self):
        for raw in ['10 mL vial in 100 mL high-pressure autoclave',
                    '20 mL test tube with inner vial', 'Teflon-lined autoclave; glass vial',
                    '30 mL Teflon vessel sealed in glass vial',
                    'Teflon beaker for gel prep; glass test tube for gel diffusion',
                    'Space-confined glass slide reactor immersed in 100 mL Schott bottle']:
            with self.subTest(raw=raw):
                self.assertEqual(vessel_type(raw)['value'],'Nested / multiple vessels')
                self.assertEqual(vessel_volume_mL(raw)['value'],'Ambiguous')
        self.assertEqual(vessel_type('capped conical flask in preheated oven (closed glass vessel)')['value'],'Flask')
        self.assertEqual(vessel_volume_mL('Teflon vial (2 mL) in HT reactor block')['value'],2)
        self.assertEqual(vessel_volume_mL('80 mL Teflon tube in microwave reactor')['value'],80)

    def test_charge_is_not_capacity(self):
        for raw in ['DURAN glass tube (12 mm); 2 mL suspension charged',
                    'vial containing 5 mL reaction mixture','glass vial filled with 5 mL methanol',
                    'glass vial (5 mL working volume)']:
            self.assertEqual(vessel_volume_mL(raw)['value'],'Not reported',raw)
        self.assertEqual(vessel_volume_mL('PTFE-lined steel autoclave (37 mL; reaction volume 20 mL)')['value'],37)
        self.assertEqual(vessel_volume_mL('25 mL vial containing 5 mL ethanol')['value'],25)

    def test_symbol_and_unit_variants(self):
        for raw,expected in [('23-M L Teflon-lined autoclave',23),('２０ mL vial',20),
                             ('PTFE insert (300 μL)',.3),('PTFE insert (300 µL)',.3),
                             ('1 L reactor',1000),('50 cm³ vessel',50),('1,000 mL flask',1000),
                             ('Teflon-lined autoclave (2 × 250 mL)',250)]:
            self.assertEqual(vessel_volume_mL(raw)['value'],expected,raw)

    def test_ambiguity_is_not_silently_imputed(self):
        for raw in ['vial (20–28 mL)','PTFE insert (300 ?L)','6-dram glass vial',
                    'six-dram glass vial','6 dr glass vial','10 L glass vial',
                    '0 mL vial','-10 mL vial']:
            self.assertEqual(vessel_volume_mL(raw)['value'],'Ambiguous',raw)
        self.assertEqual(vessel_volume_mL('Parr 4749 vessel')['value'],'Not reported')
        self.assertEqual(vessel_volume_mL('glass tube 25 × 40 mm')['value'],'Not reported')

    def test_shapes_and_equipment(self):
        for raw,expected in [('autoclavable glass bottle','Bottle / jar'),('Schlenk flask','Flask'),
                             ('glass reactor with drying tube','Reactor / reaction chamber'),
                             ('20 mL ampulla','Ampoule'),('Erlenmeyer (2 L) with condenser','Flask'),
                             ('PEEK screw-cap insert inside 7 mm MAS rotor (zirconia)','Not reported')]:
            self.assertEqual(vessel_type(raw)['value'],expected,raw)
        for raw in ['vapor diffusion setup','liquid–liquid diffusion','spray dryer (AF-88)','block heater']:
            self.assertEqual(vessel_type(raw)['value'],'Not reported',raw)

    def test_pressure_requires_text_evidence(self):
        self.assertEqual(vessel_type('high-pressure stainless steel batch reactor (~10 mL)')['value'],
                         'Autoclave / pressure vessel')
        self.assertEqual(vessel_type('stainless steel sealed vessel')['value'],'Metal vessel')

    def test_consolidated_types_preserve_detailed_class_and_capacity(self):
        for raw, expected in [('glass vessel','Glass vessel'), ('polypropylene container','Polymer vessel'),
                              ('metal vessel','Metal vessel'), ('reaction vessel','Not reported'),
                              ('crucible (25 mL)','Not reported'), ('dialysis bag','Not reported')]:
            with self.subTest(raw=raw):
                parsed = vessel_type(raw)
                self.assertEqual(parsed['value'], expected)
                self.assertTrue(parsed['consolidation_rule'])
                self.assertNotEqual(parsed['detailed_value'], parsed['value'])
        self.assertEqual(vessel_type('crucible (25 mL)')['detailed_value'], 'Crucible')
        self.assertEqual(vessel_volume_mL('crucible (25 mL)')['value'], 25)
        self.assertEqual(vessel_type('reaction cell')['value'], 'Reaction cell')
        self.assertEqual(vessel_type('ampoule')['value'], 'Ampoule')

    def test_pipeline_preserves_source_cells_and_missing_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            fields=['doi','vessel_type','stirring','other']
            rows=[{'doi':'10.x/a','vessel_type':'20 mL vial','stirring':'static','other':'001.00'},
                  {'doi':'10.x/b','vessel_type':'','stirring':'','other':'x,y\nnext line'}]
            for label in ['positive','negative']:
                with (root/f'{label}.csv').open('w',encoding='utf-8-sig',newline='') as f:
                    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
            metadata=prepare_process_details(root/'positive.csv',root/'negative.csv',root/'output')
            with (root/'output/Process_detail_positive.csv').open(encoding='utf-8-sig',newline='') as f:
                observed=list(csv.DictReader(f))
            self.assertEqual([r['other'] for r in observed],[r['other'] for r in rows])
            self.assertEqual(observed[1]['vessel_volume_mL'],'Not reported')
            self.assertEqual(len(observed[0]),len(fields)+3)
            self.assertTrue(metadata['rows_preserved'])


if __name__=='__main__':
    unittest.main()
