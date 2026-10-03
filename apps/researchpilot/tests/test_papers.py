import json
from threading import Event

import pytest

from researchpilot.db import dump
from researchpilot.papers import normalize_prose, paper_fragments, sentence_parts
from researchpilot.query_terms import expand_query
from researchpilot.retrieval import rank
from test_api import make_pdf, wait_task
from test_imports import submit, wait_import


def test_sentence_chunks_preserve_words_and_do_not_repeat_text():
    text = ' '.join(f'Sentence {i} describes this scientific method completely.' for i in range(60))
    parts = list(sentence_parts(text, 180))
    assert ' '.join(p for p, _ in parts) == text
    assert all(p.startswith('Sentence') and p.endswith('.') and not continued for p, continued in parts)
    assert all(len(p) <= 180 for p, _ in parts)


def test_long_sentences_are_bounded_and_explicitly_marked():
    parts = list(sentence_parts('x' * 4000, 1300))
    assert all(continued and len(p) <= 1300 for p, continued in parts)
    assert ''.join(p for p, _ in parts) == 'x' * 4000


def test_ligatures_and_broken_words_without_flattening_math():
    assert normalize_prose('uniﬁed super-\nvised pre-\ntrained pre-\ndicted super-\nresolution') == 'unified supervised pre-trained predicted super-resolution'
    assert normalize_prose('x² + αₜ') == 'x² + αₜ'


def test_sections_visual_blocks_and_footnotes():
    raw = 'Abstract\nWe study restoration and recov-\n∗Equal contribution,†Corresponding author.\nery using a diffusion model.\n3. Preliminary\nA mathematical definition follows below:\nx = √α\n(8)\n1'
    blocks = list(paper_fragments([(1, raw)]))
    assert blocks[0][1] == 'We study restoration and recovery using a diffusion model.'
    assert blocks[0][2]['section'] == 'Abstract'
    assert any(s['type'] == 'visual' and '(8)' in t for _, t, s in blocks)
    assert all(t != '1' for _, t, _ in blocks)
    assert blocks[-1][2]['section'] == ''


def test_affiliations_and_bibliography_are_not_section_headings():
    blocks = list(paper_fragments([(1, '1 Fudan University, 2Shanghai AI Laboratory\n8171. PMLR, 2021. 3, 19\nA. Additional Experiments\nWe describe all additional experimental results here.')]))
    assert all(s['section'] in {'', 'A. Additional Experiments'} for _, _, s in blocks)
    assert blocks[-1][2]['section'] == 'A. Additional Experiments'


@pytest.mark.parametrize('return_line', ['return Restored image', 'returnx0'])
def test_algorithm_does_not_run_into_following_prose(return_line):
    blocks = list(paper_fragments([(2, 'Algorithm 1: Guided diffusion\nInput: A noisy input image\nx = α\n'+return_line+'\nThe following paragraph discusses the experimental results.')]))
    assert blocks[0][2]['type'] == 'visual'
    assert blocks[-1][2]['type'] == 'prose'
    assert blocks[-1][1].startswith('The following paragraph')


def test_longest_term_and_no_forced_translation():
    result = expand_query('无监督的低光照图像增强')
    assert {r['term'] for r in result} == {'无监督', '低光照图像增强'}
    assert expand_query('火星地质岩层年代') == []


def chunk(text, page=1, math=False):
    return {'id':str(page), 'name':'paper', 'locator':f'第 {page} 页', 'text':text,
            'structure':{'math':math}, 'page':page}


def test_chinese_retrieval_requires_all_concept_words():
    chunks = [chunk('A model is proposed.'), chunk('The degradation model is optimized.', 2)]
    result = rank('退化模型如何估计', chunks)
    assert [r['page'] for r in result] == [2]
    assert result[0]['query_expansion'][0]['term'] == '退化模型'


def test_equation_number_not_page_or_reference_number():
    chunks = [chunk('8 by 8 patches; see reference [8].', 8), chunk('p(y) = √α (8)', 4, True)]
    assert [r['page'] for r in rank('公式（8）', chunks)] == [4]
    assert rank('公式999', chunks) == []


def test_chinese_question_reaches_offline_agent(client, workspace):
    client.post(f'/api/workspaces/{workspace}/upload', files={'file':('paper.pdf',make_pdf('The degradation model is optimized for low-light enhancement.'))})
    created = client.post(f'/api/workspaces/{workspace}/tasks',json={'prompt':'低光照增强使用什么退化模型'}).json()
    task = wait_task(client, created['id'])
    assert task['status'] == 'completed'
    assert task['citations'] and task['citations'][0]['page'] == 1
    assert 'degradation model' in task['answer'] and '中文术语对应检索词' in task['answer']
    assert '不会自动翻译' in task['answer']


def test_upgrade_keeps_source_original_notes_and_history(client, app, workspace):
    first = wait_import(client, submit(client,workspace,make_pdf('The degradation model is optimized.')))
    source_id = first['result']['id']
    before = client.get(f'/api/sources/{source_id}').json()
    note = client.post(f'/api/workspaces/{workspace}/notes',json={'chunk_id':before['chunks'][0]['id']}).json()
    task_id = client.post(f'/api/workspaces/{workspace}/tasks',json={'prompt':'退化模型'}).json()['id']
    task = wait_task(client,task_id)
    metadata = before['metadata'];metadata.pop('paper_index_version')
    app.state.db.execute('UPDATE sources SET metadata=? WHERE id=?',(dump(metadata),source_id))
    job = wait_import(client,client.post(f'/api/sources/{source_id}/reindex').json()['id'])
    assert job['status'] == 'completed' and job['result']['reindexed']
    after = client.get(f'/api/sources/{source_id}').json()
    assert len(app.state.library.list(workspace)) == 1
    assert after['metadata']['original_id'] == before['metadata']['original_id']
    assert after['chunks'][0]['id'] != before['chunks'][0]['id']
    assert client.get(f'/api/tasks/{task_id}').json()['citations'] == task['citations']
    assert client.get(f"/api/workspaces/{workspace}/notes/{note['id']}").json()['evidence'] == note['evidence']
    # Same binary re-upload now deduplicates against the upgraded source.
    again = wait_import(client,submit(client,workspace,make_pdf('The degradation model is optimized.')))
    assert again['result']['duplicate'] and again['result']['id'] == source_id


@pytest.mark.parametrize('action', ['cancel', 'delete'])
def test_interrupted_reindex_is_atomic(client, app, workspace, monkeypatch, action):
    first = wait_import(client,submit(client,workspace,make_pdf('The original text must remain available.')))
    source_id = first['result']['id']
    before = client.get(f'/api/sources/{source_id}').json()
    arrived, release = Event(), Event()
    progress = app.state.imports.progress
    def pause(identifier, phase, *args):
        progress(identifier, phase, *args)
        if phase == 'indexing':
            arrived.set();assert release.wait(5)
    monkeypatch.setattr(app.state.imports, 'progress', pause)
    response = client.post(f'/api/sources/{source_id}/reindex')
    assert response.status_code == 202
    job_id = response.json()['id']
    try:
        assert arrived.wait(5)
        if action == 'cancel':
            assert client.post(f'/api/sources/{source_id}/reindex').json()['id'] == job_id
            client.post(f'/api/imports/{job_id}/cancel')
        else:
            client.delete(f'/api/sources/{source_id}')
    finally:
        release.set()
    app.state.imports.close()
    if action == 'cancel':
        assert client.get(f'/api/sources/{source_id}').json() == before
        assert app.state.imports.get(job_id)['status'] == 'cancelled'
    else:
        assert client.get(f'/api/sources/{source_id}').status_code == 404
        assert app.state.imports.get(job_id)['status'] == 'failed'
    assert not app.state.imports.path(job_id).exists()


def test_reindex_validation(client, workspace):
    assert client.post('/api/sources/missing/reindex').status_code == 404
    source = client.post(f'/api/workspaces/{workspace}/upload',files={'file':('paper.pdf',make_pdf('No original preserved.'))}).json()
    assert client.post(f"/api/sources/{source['id']}/reindex").status_code == 404
    source = client.post(f'/api/workspaces/{workspace}/upload',files={'file':('log.log',b'epoch=1 loss=0.3')}).json()
    assert client.post(f"/api/sources/{source['id']}/reindex").status_code == 422
