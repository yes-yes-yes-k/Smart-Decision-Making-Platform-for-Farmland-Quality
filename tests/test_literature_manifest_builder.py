import json

from framework.upload.manifest_builder import build_manifest


def test_manifest_builder_combines_ris_and_explicit_domain_mapping(tmp_path):
    category = tmp_path / '耕地质量评价'
    category.mkdir()
    (category / 'paper.pdf').write_bytes(b'%PDF-1.7')
    (category / 'records.ris').write_text(
        'TY  - JOUR\nTI  - A mapped paper\nAU  - Zhang San\n'
        'DO  - 10.1000/example\nL1  - paper.pdf\nER  - \n',
        encoding='utf-8',
    )
    rows = build_manifest(
        tmp_path, {'耕地质量评价': ['cultivated_land_quality']},
    )
    assert len(rows) == 1
    assert rows[0]['title'] == 'A mapped paper'
    assert rows[0]['doi'] == '10.1000/example'
    assert rows[0]['authors'] == ['Zhang San']
    assert rows[0]['domain_labels'] == ['cultivated_land_quality']


def test_manifest_builder_does_not_infer_missing_domain_mapping(tmp_path):
    category = tmp_path / '未知专题'
    category.mkdir()
    (category / 'standard.pdf').write_bytes(b'%PDF-1.7')
    rows = build_manifest(tmp_path, {})
    assert rows[0]['domain_labels'] == []
    assert rows[0]['source_category'] == '未知专题'


def test_manifest_builder_adapts_standard_master_and_category_catalogs(tmp_path):
    standards = tmp_path / '标准' / '标准'
    category = standards / '05_土壤重金属污染'
    category.mkdir(parents=True)
    filename = 'DB12-T 1143-2022_旱田土壤镉污染修复技术规程.pdf'
    (category / filename).write_bytes(b'%PDF-1.7')
    (standards / '01_全部标准检索目录.txt').write_text(
        '全部标准检索目录\n分类\t标准号\t标准名称\t文件名\n'
        f'05_土壤重金属污染\tDB12/T 1143-2022\t旱田土壤镉污染修复技术规程\t{filename}\n',
        encoding='utf-8',
    )
    (category / '00_标准清单与下载来源.txt').write_text(
        '05_土壤重金属污染\n\n'
        '01. DB12/T 1143-2022  旱田土壤镉污染修复技术规程\n'
        f'文件：{filename}\n'
        '类型：地方标准\n地区/行业：天津市\n来源目录状态：现行\n'
        '实施日期：2022-10-14\nPDF页数：4\n'
        '来源页：https://example.test/detail\n全文地址：https://example.test/pdf\n'
        f'SHA256：{"a" * 64}\n',
        encoding='utf-8',
    )

    rows = build_manifest(tmp_path, {'标准': ['cultivated_land_quality']})

    assert len(rows) == 1
    assert rows[0]['document_kind'] == 'standard'
    assert rows[0]['title'] == '旱田土壤镉污染修复技术规程'
    assert rows[0]['standard_number'] == 'DB12/T 1143-2022'
    assert rows[0]['issuing_authority'] == '天津市'
    assert rows[0]['publication_date'] == '2022-10-14'
    assert rows[0]['authority_status'] == 'unverified'
    assert rows[0]['source_metadata'] == {
        'standard_category': '05_土壤重金属污染',
        'standard_type': '地方标准',
        'source_catalog_status': '现行',
        'source_url': 'https://example.test/detail',
        'download_url': 'https://example.test/pdf',
        'expected_sha256': 'a' * 64,
        'expected_page_count': 4,
    }
