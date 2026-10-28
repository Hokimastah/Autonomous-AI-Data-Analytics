"""Optional local Streamlit UI: pip install -r requirements-ui.txt; streamlit run app.py."""
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

import streamlit as st

from autonalytics.cleaning import create_approval
from autonalytics.runner import run_pipeline
from autonalytics.settings import ROOT, load_config
from autonalytics.storage import recent_runs
from autonalytics.utils import load_json

st.set_page_config(page_title='Local Autonomous Analytics', layout='wide', page_icon='📊')
st.title('Local Autonomous Analytics')
st.caption('Offline-first data analysis · local Ollama option · deterministic tools · source files never overwritten')

with st.sidebar:
    st.header('Agent settings')
    mode = st.selectbox('Planner mode',['rules','auto','ollama'], index=0,
                        help='auto tries Ollama, then falls back; ollama fails closed; rules needs no model')
    goal = st.text_area('Business goal',value='Analyze trends, performance by category, and data quality',height=105)
    max_steps = st.slider('Max analysis steps',2,30,12)
    st.caption('For LLM mode, install Ollama and pull the configured local model.')

left,right=st.columns([1,1])
with left:
    upload=st.file_uploader('Choose a CSV or Excel file',type=['csv','xlsx','parquet'])
    st.caption('Files are copied into project data/uploads/. Keep the app bound to localhost.')
with right:
    st.info('The agent proposes cleaning but cannot change data without explicit approval. All analytical operations are allowlisted and audited.')

if st.button('Run autonomous analysis',type='primary',disabled=upload is None):
    try:
        clean_name=re.sub(r'[^A-Za-z0-9_.-]','_',Path(upload.name).name)
        if not clean_name or clean_name.startswith('.'):
            raise ValueError('Invalid file name')
        raw=upload.getvalue()
        if len(raw) > 100 * 1024 * 1024:
            raise ValueError('File is larger than the configured 100 MB limit')
        digest=hashlib.sha256(raw).hexdigest()[:12]
        dest=ROOT/'data'/'uploads'/f'{digest}_{clean_name}'
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(raw)
        rel=str(dest.relative_to(ROOT)).replace('\\','/')
        cfg=load_config(overrides={'input_file':rel,'mode':mode,'goal':goal,'max_steps':max_steps})
        with st.spinner('Running local analytics...'):
            result=run_pipeline(cfg,verbose=False)
        st.session_state['selected_run']=result['run_id']
        st.success(f'Run completed: {result["run_id"]} ({result["state"]["status"]})')
    except Exception as exc:
        st.error(f'{type(exc).__name__}: {exc}')

st.divider()
st.subheader('Saved runs')
runs=recent_runs(30)
if not runs:
    st.write('No runs yet. Start an analysis above or run: `python main.py run`.')
else:
    choices={f"{r['run_id']} | {r['status']} | {r['source_file']}":r['run_id'] for r in runs}
    labels=list(choices)
    selected=st.session_state.get('selected_run',runs[0]['run_id'])
    idx=next((i for i,v in enumerate(choices.values()) if v==selected),0)
    label=st.selectbox('Select a run',labels,index=idx)
    rid=choices[label]
    folder=ROOT/'outputs'/rid
    auditfile=folder/'audit.json'
    statefile=auditfile if auditfile.is_file() else folder/'state.json'
    if statefile.is_file():
        state=load_json(statefile)
        prof=state['profile']
        col1,col2,col3,col4=st.columns(4)
        col1.metric('Rows',prof['rows']);col2.metric('Columns',prof['columns'])
        col3.metric('Steps',len(state['history']));col4.metric('Alerts',len(state.get('alerts',[])))
        tabs=st.tabs(['Findings','Decisions','Quality & cleaning','Downloads'])
        with tabs[0]:
            for e in state.get('evidence',[]):
                st.write(f"**{e['evidence_id']}**: {e['observation']}")
            for e in state.get('narrative',[]):
                st.info(f"AI draft ({e['evidence_id']}): {e['observation']} — {e['next_action']}")
        with tabs[1]:
            for h in state['history']:
                st.write(f"Step {h['step']}: `{h['action']['operation']}` — {h['status']} — {h.get('summary',h.get('error',''))}")
            st.caption('Full parameters and result records are saved in audit.json.')
        with tabs[2]:
            for a in state.get('alerts',[]): st.warning(a['detail'])
            st.dataframe(prof['column_info'],use_container_width=True)
            planfile=folder/'cleaning_proposals.json'
            if planfile.is_file():
                plans=load_json(planfile)['proposals']
                if plans:
                    st.write('**Proposed changes (never auto-applied)**')
                    st.dataframe(plans,use_container_width=True)
                    ids=st.multiselect('Approve only these proposal IDs',
                                       options=[p['id'] for p in plans],
                                       format_func=lambda x: next((p['operation']+' — '+str(p['column']) for p in plans if p['id']==x),x))
                    if st.button('Approve and rerun cleaned copy',disabled=not ids):
                        try:
                            approval=create_approval(planfile,ids=ids)
                            cfg=load_config(overrides={'input_file':state['source_file'],
                                                      'mode':mode,'goal':goal,'max_steps':max_steps})
                            with st.spinner('Applying approved operations and analyzing copied data...'):
                                fresh=run_pipeline(cfg,approval_file=approval,verbose=False)
                            st.session_state['selected_run']=fresh['run_id']
                            st.success('New run on the cleaned copy: '+fresh['run_id'])
                            st.rerun()
                        except Exception as exc:
                            st.error(f'{type(exc).__name__}: {exc}')
                else:
                    st.success('No cleaning proposals for this dataset.')
        with tabs[3]:
            path=folder/'report.html'
            if path.is_file():
                st.download_button('Download HTML report',data=path.read_bytes(),file_name='report.html',mime='text/html')
            if auditfile.is_file():
                st.download_button('Download audit JSON',data=auditfile.read_bytes(),file_name='audit.json',mime='application/json')
            archive=io.BytesIO()
            with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
                for f in folder.rglob('*'):
                    if f.is_file():z.write(f,str(f.relative_to(folder)))
            st.download_button('Download full report bundle (offline charts)',data=archive.getvalue(),
                               file_name=f'analysis_{rid}.zip',mime='application/zip')
            st.caption('For charts, extract the report bundle and open report.html. Standalone HTML references its local chart assets.')
