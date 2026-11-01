"""Same model-facing messages and schemas for calibration and free API controls."""
import json
import os
from . import free_api

def route(role):
    provider=os.getenv(role.upper()+'_PROVIDER','codex')
    default='gpt-6.1-sol' if provider=='codex' else ('glm-4.6v-flash' if provider=='zai' else 'openai/gpt-oss-120b')
    model=os.getenv(role.upper()+'_MODEL') or default
    return provider,model

def available(role):
    provider,model=route(role)
    try:
        if provider=='codex':
            from .codex_backend import executable
            executable()
        else:free_api.credentials(provider,model)
        return True
    except (RuntimeError,ValueError):return False

def visual(provider,model):
    return provider in {'codex','google'} or (provider=='zai' and model=='glm-4.6v-flash') or provider=='openrouter'

def serial_messages(messages,images=True):
    result=[]
    for m in messages:
        m=m.model_dump(exclude_none=True) if hasattr(m,'model_dump') else m
        content=m['content']
        if isinstance(content,list):
            parts=[]
            for p in content:
                if p.get('type')=='text':parts.append({'type':'text','text':p['text']})
                elif p.get('type')=='image_url' and images:parts.append({'type':'image_url','image_url':{'url':p['image_url']['url']}})
            content=parts
        result.append({'role':m['role'],'content':content})
    return result

async def infer(provider,model,messages,schema,max_tokens=1800):
    messages=serial_messages(messages,images=visual(provider,model))
    if provider=='codex':
        from .codex_backend import invoke
        return await invoke(messages,schema)
    # A free NVIDIA endpoint is allowed only by the dedicated synthetic probe,
    # never by the general runtime where arbitrary user data may be present.
    if provider=='openrouter':
        raise ValueError('NVIDIA endpoint is restricted to explicit synthetic probes')
    messages=[{'role':'system','content':'Return only JSON matching this schema. All required fields must be present.\n'+json.dumps(schema,ensure_ascii=False)}]+messages
    response=await free_api.complete(provider,model,messages,max_tokens=max_tokens)
    raw=response['choices'][0]['message'].get('content','') or ''
    clean=raw.strip()
    if clean.startswith('```'):clean=clean.split('\n',1)[1].rsplit('```',1)[0].strip()
    return {'output':json.loads(clean),'usage':response.get('usage',{}),'audit':{'provider':provider,'model':model,'free_only':True}}

class RuntimeChatModel:
    _verified_api_keys=True

    def __init__(self,provider,model):
        self.provider,self.model=provider,model
        self.name,self.model_name=model,model

    async def ainvoke(self,messages,output_format=None,**kwargs):
        from browser_use.llm.views import ChatInvokeCompletion,ChatInvokeUsage
        schema=output_format.model_json_schema() if output_format else {'type':'object','properties':{'text':{'type':'string'}},'required':['text'],'additionalProperties':False}
        result=await infer(self.provider,self.model,messages,schema,max_tokens=1800)
        u=result['usage'];raw=result['output']
        completion=output_format.model_validate(raw) if output_format else raw['text']
        input_count=u.get('prompt_tokens',u.get('input_tokens',0));output_count=u.get('completion_tokens',u.get('output_tokens',0))
        return ChatInvokeCompletion(completion=completion,usage=ChatInvokeUsage(prompt_tokens=input_count,
            prompt_cached_tokens=u.get('cached_input_tokens',0),prompt_cache_creation_tokens=None,prompt_image_tokens=None,
            completion_tokens=output_count,total_tokens=input_count+output_count))
