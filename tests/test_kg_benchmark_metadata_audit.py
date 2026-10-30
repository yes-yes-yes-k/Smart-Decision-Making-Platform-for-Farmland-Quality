from scripts.report_kg_benchmark_metadata import identifier_candidates,audit_proposal


def section(text, ident='p1'):
    return dict(id=ident,kind='pdf_page_text',page=1,start=20,end=20+len(text),text=text)


def test_identifier_cannot_be_invented_by_joining_disjoint_windows():
    assert identifier_candidates('doi',[section('10.1234/'),section('abc','p2')])==[]
    rows=identifier_candidates('doi',[section('DOI: 10.1234/ABC.'),section('10.1234/ABC','p2')])
    assert len(rows)==1 and rows[0]['value']=='10.1234/abc'
    assert len(rows[0]['evidence'])==2


def test_identifier_revisions_remain_distinct_and_ambiguous():
    rows=identifier_candidates('standard_number',[section('GB 2762—2025 代替 GB 2762—2022')])
    assert len(rows)==2


def test_contiguous_prefix_and_decimal_part_are_source_bound():
    a=section('NY/T\n');b=dict(section('1121.14—2023','p2'),start=a['end'],end=a['end']+len('1121.14—2023'))
    result=identifier_candidates('standard_number',[b,a])
    assert len(result)==1 and result[0]['value']=='NY/T1121.14-2023'
    assert result[0]['evidence'][0]['section_ids']==['p1','p2']
    assert identifier_candidates('standard_number',[section('DB2301/T 213—2024')])[0]['value']=='DB2301/T213-2024'


def test_identifier_width_and_layout_preserve_literal_evidence():
    assert identifier_candidates('standard_number',[section('DB 13/T 5953—2024')])[0]['value']=='DB13/T5953-2024'
    original='１０．２０１０３／ｊ．ｓｔｘｂ．２０２３１２２５２８１７'
    result=identifier_candidates('doi',[section(original)])
    assert result[0]['value']=='10.20103/j.stxb.202312252817'
    assert result[0]['evidence'][0]['quote']==original
    assert identifier_candidates('doi',[section('10.1038/abc|www.example.com')])[0]['value']=='10.1038/abc'


def test_provenance_failure_blocks_trust_without_hiding_sample():
    s=section('原文');wrong=dict(s,text='改写')
    p=dict(document_id=1,file_sha256='hash',sections=[s])
    r=dict(state='protocol_valid',protocol=dict(metadata=dict(file_sha256='hash',identity_status='verified',
        source_kind='standard',title_ids=['p1']),source_evidence=dict(title_ids=[wrong])))
    a=audit_proposal(p,r,dict(document_kind='academic_paper'))
    assert 'source_kind_conflict' in a['audit_flags']
    assert 'source_section_mismatch:title_ids' in a['audit_flags']
    assert not a['source_text_provenance_verified'] and not a['final_eligible']
