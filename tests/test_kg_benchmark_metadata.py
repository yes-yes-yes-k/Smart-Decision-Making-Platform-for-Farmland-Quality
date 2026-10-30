from scripts.prepare_kg_benchmark_metadata import page_sections


def test_metadata_identity_windows_keep_identifier_and_literal_positions():
    text=''.join(f'普通行{i}\n' for i in range(90))+'https://doi.org/10.1234/example\n'+''.join(f'后文{i}\n' for i in range(100))
    rows=page_sections(1,text)
    assert any('10.1234/example' in row['text'] for row in rows)
    assert all(text[r['start']:r['end']]==r['text'] for r in rows)
    assert len({r['id'] for r in rows})==len(rows)


def test_empty_pdf_text_is_not_invented_from_filename():
    assert page_sections(1,'')==[]
    rows=page_sections(1,'土壤'+('x'*1500)+'\n')
    assert ''.join(r['text'] for r in rows)=='土壤'+('x'*1500)+'\n'
