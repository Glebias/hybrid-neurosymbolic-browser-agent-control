"""Pure, ordered symbolic policy. Model facts cannot grant execution alone."""
from urllib.parse import urlparse
from .models import Action, Assessment

READ = {'scroll','wait','screenshot','dropdown_options','find_text','search_page','find_elements','extract'}
NAV = {'navigate','go_back','switch','close','search'}
SUPPORTED = READ | NAV | {'click','input','select_dropdown','send_keys','done'}

def origin(url):
    u = urlparse(url)
    return f'{u.scheme}://{u.netloc}' if u.netloc else ''

def match_rules(action, assessment, rules):
    values = {'tool':action.tool,'origin':origin(action.observation.url),'effect':assessment.effect if assessment else 'unknown'}
    return [r for r in rules if r.get('enabled',True) and values.get(r['field']) == r['value']]

def initial(action: Action, rules: list[dict]):
    if action.tool not in SUPPORTED:
        return ('BLOCK','Неподдерживаемый или непрозрачный инструмент.', ['P0'])
    if action.payload_class == 'secret':
        return ('BLOCK','Предложена передача данных, отмеченных как секретные.', ['P1'])
    if action.tool not in {'done','wait'} and (not action.observation.fingerprint or 'missing_index' in action.observation.target):
        return ('BLOCK','Не удалось получить актуальный контекст действия.', ['CONTEXT_MISSING'])
    matches = match_rules(action,None,rules)
    blocks = [r for r in matches if r['verdict']=='BLOCK']
    if blocks:
        return ('BLOCK','Действие запрещено пользовательским правилом.',[r['id'] for r in blocks])
    asks = [r for r in matches if r['verdict']=='ASK_USER']
    if asks:
        return ('ASK_USER','Пользовательское правило требует подтверждения.',[r['id'] for r in asks])
    if action.tool in READ or action.tool == 'done':
        return ('ALLOW','Проверенный инструмент наблюдения или завершения задачи.', ['P7_FAST'])
    return None

def resolve(action: Action, assessment: Assessment | None, rules: list[dict], strict=False):
    if assessment is None:
        return ('ASK_USER','Недостаточно смысловых сведений о последствиях действия.', ['P4'])
    if assessment.injection_suspected and assessment.evidence and assessment.evidence in action.observation.page_excerpt and assessment.effect not in {'read','navigate'}:
        return ('BLOCK','Наблюдается инструкция страницы, перенаправляющая действие агента.', ['P2'])
    if assessment.alignment in {'conflicts','unrelated'}:
        return ('BLOCK','Действие противоречит задаче пользователя или не относится к ней.', ['P2_GOAL'])
    matches = match_rules(action,assessment,rules)
    blocks = [r for r in matches if r['verdict']=='BLOCK']
    if blocks:
        return ('BLOCK','Последствия действия запрещены пользовательским правилом.',[r['id'] for r in blocks])
    asks = [r for r in matches if r['verdict']=='ASK_USER']
    if asks:
        return ('ASK_USER','Правило требует согласия пользователя.',[r['id'] for r in asks])
    if assessment.uncertain or assessment.effect == 'unknown' or assessment.alignment == 'unknown':
        return ('ASK_USER','Смысл действия или его соответствие задаче не установлены.', ['P4'])
    if assessment.effect in {'purchase','delete','auth','send'}:
        return ('ASK_USER','Действие имеет значимые последствия: требуется точное согласие.', ['P5_P6'])
    if strict and assessment.effect in {'write','input'}:
        return ('ASK_USER','Строгий профиль требует подтверждения изменения данных.', ['P9_STRICT'])
    return ('ALLOW','Действие соответствует задаче и допустимому классу последствий.', ['P7_P9'])
