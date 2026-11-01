"""Zero-budget endpoint gate. No paid fallbacks or arbitrary base URLs."""
import os
import asyncio
import httpx

class FreeQuotaExceeded(RuntimeError):
    """Sanitized free-tier limit; never switch endpoint or buy capacity."""

async def post_with_limits(client,url,**kwargs):
    for attempt in range(3):
        response=await client.post(url,**kwargs)
        if response.status_code!=429:
            response.raise_for_status()
            return response
        delay=5*(attempt+1)
        try:
            delay=float(response.headers.get('retry-after',delay))
            details=response.json().get('error',{}).get('details',[])
            for detail in details:
                if 'RetryInfo' in detail.get('@type',''):
                    delay=float(detail['retryDelay'].removesuffix('s'))
                for violation in detail.get('violations',[]):
                    quota_id=violation.get('quotaId','').lower()
                    if 'perday' in quota_id or violation.get('quotaValue')=='0':
                        raise FreeQuotaExceeded('Free quota exhausted; no paid fallback')
        except (ValueError,KeyError,TypeError):pass
        if attempt==2 or delay>30:
            raise FreeQuotaExceeded('Free API rate limit; no paid fallback')
        await asyncio.sleep(max(.1,delay)+.25)

ENDPOINTS={
    'google':('https://generativelanguage.googleapis.com/v1beta','GOOGLE_API_KEY',{'gemini-2.5-flash'}),
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
    if provider=='google' and os.getenv('GOOGLE_FREE_PLAN_CONFIRMED','false').lower()!='true':
        raise ValueError('Google Free Tier is not confirmed; generation is disabled')
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
        if provider=='google':
            system=[];contents=[]
            for m in messages:
                if m['role']=='system':
                    system.append({'text':m['content']});continue
                content=m['content']
                if isinstance(content,str):parts=[{'text':content}]
                else:
                    parts=[]
                    for p in content:
                        if p.get('type')=='text':parts.append({'text':p['text']})
                        elif p.get('type')=='image_url':
                            head,data=p['image_url']['url'].split(',',1)
                            parts.append({'inlineData':{'mimeType':head[5:].split(';')[0],'data':data}})
                contents.append({'role':'model' if m['role']=='assistant' else 'user','parts':parts})
            body={'contents':contents,'generationConfig':{'temperature':0,'maxOutputTokens':max_tokens,'responseMimeType':'application/json','thinkingConfig':{'thinkingBudget':0}}}
            if system:body['systemInstruction']={'parts':system}
            r=await post_with_limits(c,base+'/models/'+model+':generateContent',headers={'x-goog-api-key':key},json=body)
            response=r.json();raw=''.join(p.get('text','') for p in response['candidates'][0]['content']['parts'])
            u=response.get('usageMetadata',{})
            return {'choices':[{'message':{'content':raw}}],'usage':{'prompt_tokens':u.get('promptTokenCount',0),'completion_tokens':u.get('candidatesTokenCount',0),'total_tokens':u.get('totalTokenCount',0)}}
        if provider=='openrouter':
            # Pin the free variant and fail closed if current catalog pricing changes.
            r=await c.get(base+'/models');r.raise_for_status()
            entry=next((m for m in r.json()['data'] if m['id']==model),None)
            if not entry or any(float(entry.get('pricing',{}).get(k,1))!=0 for k in ('prompt','completion')):
                raise ValueError('OpenRouter model is absent or no longer zero-priced')
            payload['provider']={'allow_fallbacks':False,'max_price':{'prompt':0,'completion':0,'request':0,'image':0}}
            payload['reasoning']={'effort':'low'}
        r=await post_with_limits(c,base+'/chat/completions',headers={'Authorization':'Bearer '+key},json=payload)
        return r.json()
