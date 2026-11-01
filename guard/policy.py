"""Ordered, typed production rules with three-valued condition evaluation."""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
from .models import Action, Assessment

READ = {'scroll','wait','screenshot','dropdown_options','find_text','search_page','find_elements','extract'}
NAV = {'navigate','go_back','switch','close','search'}
SUPPORTED = READ | NAV | {'click','input','select_dropdown','send_keys','done'}
CATALOG = Path(__file__).parent/'policies'/'base.json'

def catalog():
    data=json.loads(CATALOG.read_text(encoding='utf-8'))
    assert isinstance(data['version'],int) and data['version']>0
    ids=set()
    def validate(c):
        if 'all' in c or 'any' in c:
            key='all' if 'all' in c else 'any'
            if not c[key] or not isinstance(c[key],list):raise ValueError('Invalid rule condition')
            for child in c[key]:validate(child)
        elif set(c)!={'field','op','value'} or c['op'] not in {'eq','in','not_in'}:
            raise ValueError('Unsupported rule predicate')
        elif c['op'] in {'in','not_in'} and not isinstance(c['value'],list):
            raise ValueError('Membership requires a list')
    for r in data['rules']:
        if r['id'] in ids or r['stage'] not in {'pre','post'} or r['verdict'] not in {'ALLOW','ASK_USER','BLOCK'}:
            raise ValueError('Invalid rule catalog')
        ids.add(r['id']);validate(r['when'])
    return data

def catalog_hash():
    return hashlib.sha256(json.dumps(catalog(),sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def evaluate(condition,facts):
    for key in ('all','any'):
        if key in condition:
            values=[evaluate(c,facts) for c in condition[key]]
            if key=='all':return False if False in values else None if None in values else True
            return True if True in values else None if None in values else False
    value=facts.get(condition['field'])
    if value is None:return None
    op=condition['op'];expected=condition['value']
    if op=='eq':return value==expected
    if op=='in':return value in expected
    if op=='not_in':return value not in expected
    raise ValueError('Unsupported operator')

def origin(url):
    u=urlparse(url)
    return f'{u.scheme}://{u.netloc}' if u.netloc else ''

def facts_for(action,assessment=None,strict=False):
    urls=[action.observation.url]
    if action.tool=='navigate':urls.append(action.arguments.get('url',''))
    control=False
    for url in urls:
        try:
            u=urlparse(url)
            control|=u.hostname in {'127.0.0.1','localhost'} and u.port==8765 and not u.path.startswith('/lab') and action.tool!='done'
        except ValueError:control=True
    return {'tool':action.tool,'origin':origin(action.observation.url),'supported':action.tool in SUPPORTED,
            'control_plane':control,'secret':action.payload_class=='secret',
            'context_available':action.tool in {'done','wait'} or bool(action.observation.fingerprint) and 'missing_index' not in action.observation.target,
            'fast_observation':action.tool in READ or action.tool=='done','strict':strict,
            'alignment':assessment.alignment if assessment else 'unknown','effect':assessment.effect if assessment else 'unknown',
            'authorization':assessment.authorization if assessment else 'unclear',
            'uncertain':not assessment or assessment.uncertain or assessment.effect=='unknown' or assessment.alignment=='unknown',
            'verified_injection_effect':bool(assessment and assessment.injection_suspected and assessment.evidence and
               assessment.evidence in action.observation.page_excerpt and assessment.effect not in {'read','navigate'})}

def matches(action,assessment,rules,strict,stage):
    facts=facts_for(action,assessment,strict)
    found=[r for r in catalog()['rules'] if (r['stage']==stage or (stage=='post' and r['stage']=='pre' and r['verdict']=='BLOCK')) and evaluate(r['when'],facts) is True]
    for r in rules:
        if r.get('enabled',True) and facts.get(r['field'])==r['value']:
            found.append({'id':r['id'],'priority':30 if r['verdict']=='BLOCK' else 43,'verdict':r['verdict'],
                          'reason':'Действие запрещено пользовательским правилом.' if r['verdict']=='BLOCK' else 'Пользовательское правило требует подтверждения.'})
    return sorted(found,key=lambda r:(r['priority'],r['id']))

def result(found):
    if not found:return None
    first=found[0]
    return first['verdict'],first['reason'],[r['id'] for r in found]

def initial(action:Action,rules:list[dict]):
    return result(matches(action,None,rules,False,'pre'))

def resolve(action:Action,assessment:Assessment|None,rules:list[dict],strict=False):
    return result(matches(action,assessment,rules,strict,'post')) or ('BLOCK','Нет доказанного разрешения.', ['P10'])
