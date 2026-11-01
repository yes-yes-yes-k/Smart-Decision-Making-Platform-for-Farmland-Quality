"""AI visual identity observations from the reviewed rendered first pages."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,lines,dump,readlines
from framework.knowledge_graph.benchmark_rebuild import sha256_file

# Each primary number was read visually from the contact sheets/original covers.
# Replaced editions printed below it are deliberately not registered as primary.
OBSERVED='''212|10.1093/ismejo/wrag217
352|10.1093/ismejo/wrag131
496|DB32/T 4404-2022
498|DB32/T 4426-2022
520|HJ/T 166-2004
522|NY/T 1121.1-2006
524|NY/T 3956-2021
528|SY/T 7465-2020
551|DB61/T 2060-2025
552|DB62/T 4720.1-2023
553|DB62/T 4720.2-2023
557|HJ 1068-2019
561|NY/T 1121.20-2008
564|NY/T 1121.23-2010
568|NY/T 2367-2013
569|NY/T 3180-2018
570|NY/T 3528-2019
571|NY/T 3678-2020
574|QX/T 343-2016
576|QX/T 567-2020
598|DB62/T 4588-2022
599|DB65/T 4631.9-2023
612|NY/T 1121.15-2006
613|NY/T 1121.24-2012
615|NY/T 1121.7-2014
621|NY/T 1867-2010
622|NY/T 3242-2018
627|NY/T 890-2004
663|NY/T 1121.17-2006
664|NY/T 1121.18-2006
667|NY/T 1378-2007
671|NY/T 3443-2019
672|NY/T 3936-2021
698|GB 15618-2018
715|HJ 1080-2019
720|NY/T 1613-2008
721|NY/T 3788-2020
737|HJ 1052-2019
740|HJ 1055-2019
776|NY/T 2067-2011
777|NY/T 3151-2017
778|NY/T 3787-2020
779|NY/T 3835-2021
824|DB53/T 1382-2025
825|DB61/T 1904-2024
832|DB65/T 4785-2024
836|NY/T 1119-2019
839|NY/T 2626-2014
840|NY/T 2872-2015
842|NY/T 3701-2020
893|DB65/T 4830-2025
894|NY/T 1105-2006
896|NY/T 1868-2021
898|NY/T 2624-2014
901|NY/T 3554-2020
903|NY/T 496-2010
930|DB53/T 1320-2024
940|LS/T 6134-2018'''


def main():
    packets={p['document_id']:p for p in readlines(OUT/'metadata-review-preparation/source-packets.jsonl')}
    rows=[]
    for line in OBSERVED.splitlines():
        ident,number=line.split('|');i=int(ident)
        image=OUT/f'execution/cover-ocr-v1/{i}-page1.png'
        if not image.is_file():raise ValueError('visual_source_missing')
        rows.append(dict(document_id=i,file_sha256=packets[i]['file_sha256'],page=1,
            identifier=number,identifier_kind='doi' if number.startswith('10.') else 'standard_number',
            source_kind='academic_paper' if number.startswith('10.') else 'standard',
            identity_status='AI_visual_primary_identifier_reviewed',
            image_path=image.relative_to(ROOT).as_posix(),image_sha256=sha256_file(image),
            reviewer='Codex_AI_visual_source_audit',expert_certified=False,metadata_only=True,
            transcription_scope='primary_identifier_only_whitespace_and_dash_normalized',
            input_title_and_body_not_modified=True,extractor_tuning_exposure=False,
            extraction_reference_answers_not_read=True))
    target=OUT/'execution/cover-visual-review-v1'
    lines(target/'decisions.jsonl',rows)
    dump(target/'report.json',dict(status='source_identity_reviewed_not_KG_labels',reviewed_documents=len(rows),
        papers=2,standards=56,expert_certified=False,cloud_requests=0))
    print(len(rows))


if __name__=='__main__':main()
