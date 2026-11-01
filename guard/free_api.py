"""Zero-budget endpoint gate. No paid fallbacks or arbitrary base URLs."""
import os
import httpx

ENDPOINTS={
    'groq':('https://api.groq.com/openai/v1','GROQ_API_KEY',{'openai/gpt-oss-120b','openai/gpt-oss-20b'}),
    'zai':('https://api.z.ai/api/paas/v4','ZAI_API_KEY',{'glm-4.7-flash','glm-4.6v-flash','glm-4.5-flash'}),
    'openrouter':('https://openrouter.ai/api/v1','OPENROUTER_API_KEY',{'nvidia/nemotron-3.5-super-vl:free'}),
}

def credentials(provider,model):
    if provider not in ENDPOINTS:
        raise ValueError('Provider is not in the free-only allowlist')
    base,var,models=ENDPOINTS[provider]
    if model not in models:
        raise ValueError('Model is not in the verified free-only allowlist')
    if provider=='groq' and os.getenv('GROQ_FREE_PLAN_CONFIRMED','false').lower()!='true':
        raise ValueError('Groq Free plan is not confirmed; generation is disabled')
    key=os.getenv(var,'').strip()
    if not key:
        raise ValueError('Missing '+var)
    return base,key

async def complete(provider,model,messages,max_tokens=800):
    base,key=credentials(provider,model)
    payload={'model':model,'messages':messages,'temperature':0}
    if provider=='groq':
        payload.update(max_completion_tokens=max_tokens,reasoning_effort='low')
    else:
        payload['max_tokens']=max_tokens
    if provider=='zai':
        payload['thinking']={'type':'disabled'}
    async with httpx.AsyncClient(timeout=45) as c:
        if provider=='openrouter':
            # Pin the free variant and fail closed if current catalog pricing changes.
            r=await c.get(base+'/models');r.raise_for_status()
            entry=next((m for m in r.json()['data'] if m['id']==model),None)
            if not entry or any(float(entry.get('pricing',{}).get(k,1))!=0 for k in ('prompt','completion')):
                raise ValueError('OpenRouter model is absent or no longer zero-priced')
            payload['provider']={'allow_fallbacks':False,'max_price':{'prompt':0,'completion':0,'request':0,'image':0}}
            payload['reasoning']={'effort':'low'}
        r=await c.post(base+'/chat/completions',headers={'Authorization':'Bearer '+key},json=payload)
        r.raise_for_status()
        return r.json()
