import json
from pathlib import Path
import pandas as pd
import pytest
from autonalytics.cleaning import apply_approved, create_approval, propose_cleaning
from autonalytics.ingest import ingest
from autonalytics.operations import execute, validate_action
from autonalytics.planner import candidates
from autonalytics.runner import run_pipeline
from autonalytics.semantics import infer_semantics, derive_metrics
from autonalytics.settings import ROOT, load_config, file_in_data
from autonalytics.utils import load_json, sha256_file


@pytest.fixture
def sample():
    return pd.DataFrame({'order_id':['a','b','c','d','e','e'],
                         'order_date':['2025-01-04','2025-01-08','2025-02-09','2025-03-12','2025-04-19','2025-04-19'],
                         'product':[' P ','P','Q','Q','P','P'],
                         'quantity':[1,2,3,4,5,5], 'revenue':[100.,200.,None,300.,500.,500.]})


def test_semantics_and_derived(sample):
    roles=infer_semantics(sample)
    assert roles['order_date']=='date'
    assert roles['order_id']=='identifier'
    assert roles['revenue']=='measure'
    df=derive_metrics(sample,{'double_qty':{'multiply':['quantity','quantity']}})
    assert df['double_qty'].iloc[1] == 4
    with pytest.raises(ValueError): derive_metrics(sample,{'foo':{'python':'__import__("os")'}})


def test_operations_and_permissions(sample):
    roles=infer_semantics(sample)
    action={'operation':'group_sum','column':'product','metric':'revenue'}
    records=execute(sample,roles,action)
    assert len(records)==3
    with pytest.raises(ValueError): execute(sample,roles,{'operation':'python_exec','code':'print(1)'})
    with pytest.raises(ValueError): execute(sample,roles,{'operation':'group_sum','column':'order_id','metric':'revenue'})
    with pytest.raises(ValueError): execute(sample,roles,{'operation':'group_sum','column':'product','metric':'order_id'})


def test_candidate_planning_changes_with_history(sample):
    roles=infer_semantics(sample)
    opts=candidates(sample,roles,'revenue trend and product',[])
    assert opts
    monthly=next(x for x in opts if x['action']['operation']=='monthly_sum')
    action=monthly['action']
    history=[{'step':1,'status':'ok','action':action,'records':[],'summary':'monthly values'}]
    next_opts=candidates(sample,roles,'revenue trend and product',history)
    assert any(o['action']['operation']=='monthly_change' for o in next_opts)
    assert not any(o['action']==action for o in next_opts)


def test_approval_and_no_source_changes(sample,tmp_path):
    src=tmp_path/'source.csv'
    sample.to_csv(src,index=False)
    old_bytes=src.read_bytes()
    roles=infer_semantics(sample)
    proposals=propose_cleaning(sample,roles)
    assert any(p['operation']=='drop_exact_duplicates' for p in proposals)
    plan={'source_sha256':sha256_file(src),'source_file':'data/example.csv','proposals':proposals}
    planfile=tmp_path/'cleaning_proposals.json';planfile.write_text(json.dumps(plan))
    approvalfile=create_approval(planfile,all_items=True)
    result,changes=apply_approved(sample,load_json(approvalfile),sha256_file(src),'data/example.csv')
    assert len(result) == 5
    assert src.read_bytes()==old_bytes
    with pytest.raises(ValueError):apply_approved(sample,load_json(approvalfile),'modified-hash','data/example.csv')


def test_config_local_only_and_input_path():
    with pytest.raises(ValueError):
        load_config(overrides={'ollama_url':'https://evil.example/api/chat'})
    with pytest.raises(ValueError):
        file_in_data(ROOT/'config.json')
    cfg=load_config(overrides={'mode':'rules','max_steps':3})
    assert cfg['max_steps']==3


def test_full_run_and_resume():
    cfg=load_config(overrides={'mode':'rules','max_steps':3,'max_charts':2})
    original=ROOT/'data'/'sales_demo.csv'
    oldhash=sha256_file(original)
    outcome=run_pipeline(cfg,verbose=False)
    folder=Path(outcome['output_dir'])
    assert outcome['state']['status']=='complete'
    assert len(outcome['state']['history'])==3
    for file in ('report.html','audit.json','profile.json','evidence.json','alerts.json','state.json','cleaning_proposals.json'):
        assert (folder/file).is_file()
    assert sha256_file(original)==oldhash
    again=run_pipeline(cfg,resume=outcome['run_id'],verbose=False)
    assert again['resumed']
    assert again['state']['history']==outcome['state']['history']


def test_resume_corrupted_input_rejected():
    cfg=load_config(overrides={'mode':'rules','max_steps':2})
    outcome=run_pipeline(cfg,verbose=False)
    changed=load_config(overrides={'mode':'rules','max_steps':3})
    with pytest.raises(ValueError,match='Cannot resume'):
        run_pipeline(changed,resume=outcome['run_id'],verbose=False)


def test_ollama_fallback(monkeypatch):
    from autonalytics import llm
    def offline(*args,**kwargs):
        raise ConnectionError('offline')
    monkeypatch.setattr(llm.requests,'post',offline)
    cfg=load_config(overrides={'mode':'auto','max_steps':2,'max_charts':0})
    result=run_pipeline(cfg,verbose=False)
    assert result['state']['status']=='complete'
    assert len(result['state']['errors'])>=1
    assert result['state']['history'][0]['planner']=='deterministic'


def test_strict_ollama_fails_closed(monkeypatch):
    from autonalytics import llm
    def offline(*args,**kwargs):raise ConnectionError('offline')
    monkeypatch.setattr(llm.requests,'post',offline)
    cfg=load_config(overrides={'mode':'ollama','max_steps':2,'max_charts':0})
    result=run_pipeline(cfg,verbose=False)
    assert result['state']['status']=='failed'
    assert result['state']['stop_reason']=='ollama_planner_error'


def test_reject_unapproved_cleaning_tamper(sample,tmp_path):
    roles=infer_semantics(sample)
    proposals=propose_cleaning(sample,roles)
    pfile=tmp_path/'cleaning_proposals.json'
    pfile.write_text(json.dumps({'source_sha256':'abcdef','source_file':'data/source.csv','proposals':proposals}))
    approved=create_approval(pfile,all_items=True)
    obj=load_json(approved);obj['proposals'][0]['operation']='delete_everything'
    with pytest.raises(ValueError,match='modified'):
        apply_approved(sample,obj,'abcdef','data/source.csv')


def test_structured_ollama_candidate_and_narrative(monkeypatch):
    from autonalytics import llm
    class Response:
        def __init__(self,body):self.body=body
        def raise_for_status(self):pass
        def json(self):return {'message':{'content':json.dumps(self.body)}}
    def mock_post(url,json=None,timeout=None):
        if 'allowed_candidates' in json['messages'][1]['content']:
            candidates=json_module.loads(json['messages'][1]['content'])['allowed_candidates']
            return Response({'candidate_id':candidates[0]['id'],'reason':'Highest ranked'})
        return Response({'insights':[{'evidence_id':'step-1','observation':'Descriptive finding',
                                      'next_action':'Review with domain expert'}]})
    json_module=__import__('json')
    monkeypatch.setattr(llm.requests,'post',mock_post)
    cfg=load_config(overrides={'mode':'ollama','max_steps':2,'max_charts':0})
    outcome=run_pipeline(cfg,verbose=False)
    assert outcome['state']['status']=='complete'
    assert all(h['planner']=='ollama' for h in outcome['state']['history'])
    assert outcome['state']['narrative'][0]['evidence_id']=='step-1'


def test_xlsx_ingestion(tmp_path):
    path=tmp_path/'sample.xlsx'
    frame=pd.DataFrame({'product':['A','B'], 'revenue':[100, 200]})
    frame.to_excel(path,index=False)
    cfg=load_config(overrides={'max_rows':20})
    result=ingest(path,cfg)
    assert result['revenue'].sum()==300


def test_resume_unfinished_steps_only():
    from autonalytics.utils import dump_json
    cfg=load_config(overrides={'mode':'rules','max_steps':4,'max_charts':0})
    original=run_pipeline(cfg,verbose=False)
    folder=Path(original['output_dir'])
    checkpoint=load_json(folder/'state.json')
    first_step=checkpoint['history'][0]
    checkpoint['history']=checkpoint['history'][:1]
    checkpoint['status']='running'
    checkpoint['stop_reason']=None
    checkpoint['completed_utc']=None
    checkpoint['narrative']=[]
    dump_json(folder/'state.json',checkpoint)
    resumed=run_pipeline(cfg,resume=original['run_id'],verbose=False)
    assert len(resumed['state']['history'])==4
    assert resumed['state']['history'][0]==first_step
    assert resumed['state']['history'][1]['step']==2
    assert resumed['state']['status']=='complete'


def test_own_dataset_other_schema(tmp_path):
    path=ROOT/'data'/'test_own_schema.csv'
    try:
        pd.DataFrame({'date':['2025-01-01','2025-02-01','2025-03-01'],
                      'category':['A','B','A'],'amount':[2.0,4.0,6.0]}).to_csv(path,index=False)
        cfg=load_config(overrides={'mode':'rules','input_file':'data/test_own_schema.csv','max_steps':4})
        result=run_pipeline(cfg,verbose=False)
        assert result['state']['status']=='complete'
        assert result['state']['profile']['rows']==3
    finally:
        path.unlink(missing_ok=True)
