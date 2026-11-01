import React, {useEffect, useRef} from 'react';
import {Check, X, Clock, ChevronRight, Shield} from 'lucide-react';

export type Obj = Record<string, any>;
export const stateNames: Obj = {queued:'В очереди',running:'Выполняется',waiting:'Ждёт подтверждения',completed:'Завершена',failed:'Ошибка',cancelled:'Отменена',interrupted:'Прервана',idle:'Свободен'};
export const verdictNames: Obj = {ALLOW:'Разрешено',BLOCK:'Заблокировано',ASK_USER:'Нужно подтверждение'};
export const toolNames: Obj = {navigate:'Открыть страницу',click:'Нажать элемент',input:'Ввести текст',scroll:'Прокрутить страницу',done:'Завершить задачу',search:'Поиск',select_dropdown:'Выбрать значение',extract:'Прочитать содержимое',wait:'Подождать',go_back:'Вернуться',switch:'Сменить вкладку',close:'Закрыть вкладку',send_keys:'Нажать клавиши'};
export const effectNames: Obj = {read:'Чтение и поиск',navigate:'Переход',input:'Ввод данных',write:'Изменение данных',send:'Отправка',purchase:'Покупка',delete:'Удаление',auth:'Авторизация',unknown:'Не установлен'};
export const modeNames: Obj = {hybrid:'Модель + правила',symbolic:'Только правила',neural:'Только модель',off:'Без контроля'};
export const fmt = (t:number) => new Date(t*1000).toLocaleTimeString('ru',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
export const dateFmt = (t:number) => new Date(t*1000).toLocaleString('ru',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});
export function plural(n:number,forms:[string,string,string]) {const x=Math.abs(n)%100,y=x%10;return x>=11&&x<=14?forms[2]:y===1?forms[0]:y>=2&&y<=4?forms[1]:forms[2];}
export const isActive = (t?:Obj) => !!t && ['queued','running','waiting'].includes(t.status);
export function isPending(d:Obj,t?:Obj) {return d.verdict==='ASK_USER' && d.approval===null && !d.cancelled_at && d.expires_at>Date.now()/1000 && isActive(t);}
export function shortGoal(goal:string) {
 const text=goal.replace(/https?:\/\/\S+/g,'').replace(/^\s*(Открой|Перейди|Start at)\s*[.,;]?\s*/i,'').replace(/^и\s+/i,'').replace(/\s+/g,' ').trim();
 return text?text[0].toLocaleUpperCase('ru')+text.slice(1):goal;
}
export function host(url:string) {try {return new URL(url).host;} catch {return url || 'Адрес не указан';}}
export function execution(d:Obj,events:Obj[],task?:Obj) {
 const result=events.find(e=>e.kind==='execution_result' && e.data.decision_id===d.decision_id);
 if(result) return result.data.success?'Выполнено':'Ошибка исполнения';
 if(d.cancelled_at) return 'Предложение отменено';
 if(d.verdict==='BLOCK') return 'Не исполнялось';
 if(d.verdict==='ASK_USER') {
  if(d.approval===false) return 'Отклонено пользователем';
  if(d.approval===true) return 'Исполнение не подтверждено';
  if(!isActive(task)) return 'Запрос закрыт';
  if(d.expires_at<=Date.now()/1000) return 'Срок ответа истёк';
  const seconds=Math.max(0,Math.ceil(d.expires_at-Date.now()/1000));
  return `Ожидает ответа · ${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`;
 }
 return 'Исполнение не подтверждено';
}
export function Badge({value}:{value:string}) {return <span className={'badge '+value.toLowerCase()}>{value==='ALLOW'?<Check size={13}/>:value==='BLOCK'?<X size={13}/>:value==='ASK_USER'?<Clock size={13}/>:null}{verdictNames[value]||stateNames[value]||value}</span>;}

// A deliberately small safe subset: plain paragraphs and **emphasis**, never HTML.
export function ResultText({text}:{text:string}) {return <div className="result-text">{text.split(/\n\s*\n/).map((paragraph,i)=><p key={i}>{paragraph.split(/(\*\*[^*]+\*\*)/g).map((s,j)=>s.startsWith('**')&&s.endsWith('**')?<strong key={j}>{s.slice(2,-2)}</strong>:s)}</p>)}</div>;}

type FeedProps={decisions:Obj[];events:Obj[];task:Obj;busy:boolean;connected:boolean;onDetail:(d:Obj)=>void;onApprove:(id:string,allow:boolean)=>void};
export function ActionFeed({decisions,events,task,busy,connected,onDetail,onApprove}:FeedProps) {
 return <ol className="timeline">{decisions.map((d,i)=>{
  const target=d.action.observation.target?.text || (d.action.tool==='navigate'?d.action.arguments.url:'');
  const pending=isPending(d,task);
  return <li className={'timeline-item '+d.verdict.toLowerCase()} key={d.decision_id}>
   <span className="step-number" aria-label={'Шаг '+(i+1)}>{String(i+1).padStart(2,'0')}</span>
   <div className="timeline-body"><div className="timeline-title"><h3>{toolNames[d.action.tool]||d.action.tool}</h3><Badge value={d.verdict}/><time dateTime={new Date(d.created_at*1000).toISOString()}>{fmt(d.created_at)}</time></div>
    {target&&<div className="action-target" title={target}>{target.slice(0,180)}</div>}
    <p className="decision-reason">{d.reason}</p>
    <div className="action-meta"><span className="execution-state">{execution(d,events,task)}</span><span>{task.mode==='off'?'Контроль отключён':d.model_skipped?'Правила':task.mode==='neural'?'Модель':'Модель + правила'}</span><span>{Math.round(d.latency_ms)} мс</span><button className="text-button" onClick={()=>onDetail(d)}>Контекст <ChevronRight size={15}/></button></div>
    {pending&&<div className="inline-approval"><div><strong>Разрешить это действие?</strong><span>Согласие действует только для этого вызова.</span></div><div className="button-group"><button className="secondary" disabled={busy||!connected} onClick={()=>onApprove(d.decision_id,false)}>Отказать</button><button className="primary" disabled={busy||!connected} onClick={()=>onApprove(d.decision_id,true)}>Разрешить</button></div></div>}
   </div>
  </li>;
 })}</ol>;
}

export function Inspector({decision:d,task,events,onClose}:{decision:Obj;task?:Obj;events:Obj[];onClose:()=>void}) {
 const dialog=useRef<HTMLDialogElement>(null);const heading=useRef<HTMLHeadingElement>(null);
 useEffect(()=>{
  const opener=document.activeElement as HTMLElement|null;
  dialog.current?.showModal();heading.current?.focus();
  return ()=>{dialog.current?.close();if(opener?.isConnected)opener.focus();};
 },[]);
 const observation=d.action.observation;const a=d.assessment;
 const result=events.find(e=>e.kind==='execution_result'&&e.data.decision_id===d.decision_id);
 return <dialog ref={dialog} className="inspector" aria-labelledby="inspector-heading" onCancel={e=>{e.preventDefault();onClose();}} onClick={e=>{if(e.target===e.currentTarget)onClose();}}>
  <div className="inspector-content"><div className="inspector-heading"><div><p className="overline">Проверка действия</p><h2 id="inspector-heading" ref={heading} tabIndex={-1}>{toolNames[d.action.tool]||d.action.tool}</h2></div><button className="icon-button" aria-label="Закрыть контекст" onClick={onClose}><X size={20}/></button></div>
  <div className="decision-summary"><Badge value={d.verdict}/><span>{execution(d,events,task)}</span><p>{d.reason}</p></div>
  <section><h3>Что проверялось</h3><dl className="facts"><dt>Сайт</dt><dd>{observation.url||'Не указан'}</dd>{observation.target?.text&&<><dt>Элемент</dt><dd>{observation.target.text}</dd></>}{observation.target?.form?.destination&&<><dt>Адрес отправки</dt><dd>{observation.target.form.destination}</dd></>}<dt>Задача</dt><dd>{task?.goal||'Исходная задача недоступна'}</dd></dl></section>
  <section><h3>Основание решения</h3>{a?<><p>{a.explanation}</p><dl className="facts"><dt>Последствие</dt><dd>{effectNames[a.effect]||a.effect}</dd><dt>Связь с целью</dt><dd>{({aligned:'Соответствует',conflicts:'Противоречит',unrelated:'Не относится',unknown:'Не установлена'} as Obj)[a.alignment]}</dd><dt>Полномочия</dt><dd>{({explicit:'Прямое поручение',implicit:'Следует из задачи',unclear:'Неоднозначны',forbidden:'Прямой запрет'} as Obj)[a.authorization]}</dd>{a.authorization_evidence&&<><dt>Из поручения</dt><dd>«{a.authorization_evidence}»</dd></>}<dt>Неопределённость</dt><dd>{a.uncertain?'Да':'Нет'}</dd></dl>{a.evidence&&<blockquote>{a.evidence}</blockquote>}</>:<p>{task?.mode==='off'?'Контроль был отключён. Модель не вызывалась.':d.model_skipped?'Решение принято по правилам. Модель не вызывалась.':'Оценку модели получить не удалось; действие остановлено.'}</p>}
   <div className="rule-tags">{d.rule_ids.map((id:string)=><code key={id}>{id}</code>)}</div>
   <p className="helper">Версия правил {d.policy_version} · {Math.round(d.latency_ms)} мс на стороне сервиса{!d.model_skipped&&` · ${d.model_name}`}</p>
  </section>
  {result&&<section><h3>Результат инструмента</h3><p className="pre-line">{result.data.summary||'Результат записан без текстового описания.'}</p></section>}
  {d.has_screenshot&&<details><summary>Снимок страницы перед действием</summary><img className="context-screenshot" src={'/api/decisions/'+d.decision_id+'/screenshot'} alt="Страница перед предложенным действием"/></details>}
  <details><summary>Наблюдение страницы <span>Недоверенные данные</span></summary><pre>{observation.page_excerpt||'Текст наблюдения не сохранялся.'}</pre></details>
  <details><summary>Технические данные</summary><pre>{JSON.stringify({tool:d.action.tool,arguments:d.action.arguments,target:observation.target,assessment:a,proposal_id:d.proposal_id},null,2)}</pre></details>
  <div className="inspector-footer"><Shield size={15}/> Разрешение и фактическое исполнение учитываются отдельно.</div>
  </div>
 </dialog>;
}
