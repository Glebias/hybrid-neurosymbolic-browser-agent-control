"""Stateless, tool-restricted Codex CLI inference for calibration, not API evaluation.

The local client uses the existing ChatGPT login. It is not an offline model.
Every call has a fresh empty working directory and is rejected if a tool is used.
"""
import asyncio
import base64
import json
import os
import shutil
import tempfile
from pathlib import Path

SAFE_ENV = {'PATH','PATHEXT','SYSTEMROOT','WINDIR','COMSPEC','APPDATA','LOCALAPPDATA',
            'USERPROFILE','TEMP','TMP','USERNAME','LANG','CODEX_HOME'}
DISABLED = ['shell_tool','shell_snapshot','code_mode','apps','browser_use',
            'browser_use_external','computer_use','multi_agent','skill_search','skill_mcp_dependency_install',
            'tool_suggest','workspace_dependencies','goals','sleep_tool','view_image']

def executable():
    custom=os.getenv('CODEX_EXECUTABLE')
    if custom and Path(custom).is_file():
        return custom
    found=shutil.which('codex.exe') or shutil.which('codex')
    if found:return found
    bins=Path(os.environ.get('LOCALAPPDATA',''))/'OpenAI'/'Codex'/'bin'
    candidates=list(bins.glob('*/codex.exe'))
    if not candidates:raise RuntimeError('Codex CLI not found')
    return str(max(candidates,key=lambda p:p.stat().st_mtime))

def strict_schema(schema):
    schema=json.loads(json.dumps(schema))
    def walk(x):
        if isinstance(x,dict):
            if x.get('type')=='object' and 'properties' in x:
                x['additionalProperties']=False
                x['required']=list(x['properties'])
            for v in x.values():walk(v)
        elif isinstance(x,list):
            for v in x:walk(v)
    walk(schema)
    return schema

def command(folder, schema_path, output_path, images):
    args=[executable(),'exec','--ignore-user-config','--ignore-rules','--ephemeral','--skip-git-repo-check',
          '--sandbox','read-only','--strict-config','--model',os.getenv('CODEX_MODEL','gpt-6.1-sol'),
          '--json','--color','never','--output-schema',str(schema_path),'-o',str(output_path),'-C',str(folder)]
    config={'approval_policy':'never','web_search':'disabled',
            'apps._default.enabled':False,'project_doc_max_bytes':0,'forced_login_method':'chatgpt',
            'history.persistence':'none','features.skip_host_skill_discovery':True,
            'suppress_unstable_features_warning':True,
            'model_reasoning_effort':'low'}
    for k,v in config.items():args+=['-c',k+'='+json.dumps(v)]
    for feature in DISABLED:args+=['--disable',feature]
    for image in images:args+=['--image',str(image)]
    return args+['-']

async def invoke(messages, schema, model=None):
    root=Path('.data/codex-calls').resolve();root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='call-',dir=root) as tmp:
        folder=Path(tmp)
        schema_path=folder/'response.schema.json';output_path=folder/'response.json'
        schema_path.write_text(json.dumps(strict_schema(schema)),encoding='utf-8')
        serial=[];images=[]
        for message in messages:
            message=message.model_dump(exclude_none=True) if hasattr(message,'model_dump') else message
            content=message.get('content','')
            if isinstance(content,list):
                parts=[]
                for part in content:
                    if part.get('type')=='image_url':
                        url=part['image_url']['url']
                        if not url.startswith('data:image/'):
                            raise ValueError('Only inline images are accepted')
                        header,encoded=url.split(',',1)
                        image=folder/f'image-{len(images)}.png'
                        image.write_bytes(base64.b64decode(encoded,validate=True))
                        images.append(image)
                        parts.append({'type':'attached_image','image_number':len(images)})
                    elif part.get('type')=='text':parts.append({'type':'text','text':part['text']})
                content=parts
            serial.append({'role':message['role'],'content':content})
        prompt=('Act only as a stateless model for the following role-labelled inference request. '
                'Apply the supplied messages according to their roles, including the supplied system message. '
                'Use no native tools, filesystem, browser, skills, connectors or outside context. '
                'Return only the requested JSON. You have no authority to execute the described browser actions.\n'
                +json.dumps({'messages':serial},ensure_ascii=False))
        env={k:v for k,v in os.environ.items() if k.upper() in SAFE_ENV}
        proc=await asyncio.create_subprocess_exec(*command(folder,schema_path,output_path,images),
                stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,
                env=env,limit=8*1024*1024)
        try:
            stdout,stderr=await asyncio.wait_for(proc.communicate(prompt.encode('utf-8')),timeout=180)
        except BaseException:
            if proc.returncode is None:
                proc.kill();await proc.wait()
            raise
        if proc.returncode or not output_path.exists():
            # Do not echo provider errors or the prompt into runtime events.
            raise RuntimeError('Restricted Codex call failed (exit '+str(proc.returncode)+')')
        usage={};items=[]
        for line in stdout.decode('utf-8',errors='replace').splitlines():
            try:event=json.loads(line)
            except ValueError:continue
            if event.get('type')=='turn.completed':usage=event.get('usage',{})
            if event.get('type','').startswith('item.'):
                kind=event.get('item',{}).get('type')
                if kind=='error':
                    raise RuntimeError('Codex protocol error: '+str(event.get('item',{}).get('message',''))[:500])
                items.append(kind)
                if kind not in {'agent_message','reasoning'}:
                    raise RuntimeError('Restricted Codex attempted a native tool: '+str(kind))
        raw=output_path.read_text(encoding='utf-8')
        return {'output':json.loads(raw),'usage':usage,'audit':{'item_types':sorted(set(items)),
                'sandbox':'read-only','native_tools_used':False,'user_config_loaded':False,
                'api_credentials_inherited':False,'model':os.getenv('CODEX_MODEL','gpt-6.1-sol')}}

class CodexChatModel:
    model=os.getenv('CODEX_MODEL','gpt-6.1-sol')
    provider='codex-calibration'
    _verified_api_keys=True
    name=model
    model_name=model

    async def ainvoke(self,messages,output_format=None,**kwargs):
        from browser_use.llm.views import ChatInvokeCompletion,ChatInvokeUsage
        schema=output_format.model_json_schema() if output_format else {'type':'object','properties':{'text':{'type':'string'}},'required':['text'],'additionalProperties':False}
        response=await invoke(messages,schema)
        u=response['usage'];output=response['output']
        completion=output_format.model_validate(output) if output_format else output['text']
        return ChatInvokeCompletion(completion=completion,usage=ChatInvokeUsage(prompt_tokens=u.get('input_tokens',0),
             prompt_cached_tokens=u.get('cached_input_tokens',0),prompt_cache_creation_tokens=None,prompt_image_tokens=None,
             completion_tokens=u.get('output_tokens',0),total_tokens=u.get('input_tokens',0)+u.get('output_tokens',0)))
