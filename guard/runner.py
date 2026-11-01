import asyncio
import os
import time
from pathlib import Path
from browser_use import Agent, Browser, ChatOpenAI, ChatAnthropic
from .analysis import configured
from .integration import GuardedTools

def make_llm():
    params = dict(model=os.environ['AGENT_MODEL'],api_key=os.environ['MODEL_API_KEY'],base_url=os.environ.get('MODEL_BASE_URL'))
    if os.getenv('MODEL_PROVIDER') == 'anthropic':
        return ChatAnthropic(**params)
    return ChatOpenAI(**params)

async def run_task(store, task):
    id = task['id']
    task.update(status='running',started_at=time.time())
    store.put('task',id,task)
    agent_row = store.get('agent',task['agent_id'])
    agent_row.update(status='running',task_id=id)
    store.put('agent',agent_row['id'],agent_row)
    tools = GuardedTools(id)
    executable = os.getenv('BROWSER_EXECUTABLE')
    if not executable:
        candidate = Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
        executable = str(candidate) if candidate.exists() else None
    browser = Browser(headless=os.getenv('BROWSER_HEADLESS','true').lower()=='true',executable_path=executable,
                      user_data_dir=str(Path('.data/profiles')/id),enable_default_extensions=False)
    try:
        agent = Agent(task=task['goal'],llm=make_llm(),tools=tools,browser=browser,use_vision=True,
                      max_actions_per_step=1,step_timeout=300,llm_timeout=75,max_failures=3,use_judge=False,
                      generate_gif=False,calculate_cost=False,save_conversation_path=None)
        # Verify the running instance is actually wired to our executor, not just registered.
        if agent.tools is not tools:
            raise RuntimeError('Protected tools were not installed')
        agent_row.update(verified=True)
        store.put('agent',agent_row['id'],agent_row)
        store.event(id,'integration_ready',{'version':agent_row['version'],'tools':list(tools.registry.registry.actions),'guard':'Tools.act before original executor'})

        async def step_end(a):
            store.event(id,'step',{'step':a.state.n_steps})

        history = await agent.run(max_steps=task['max_steps'],on_step_end=step_end)
        current = store.get('task',id)
        if current['status'] != 'cancelled':
            current.update(status='completed' if history.is_successful() else 'failed',result=history.final_result(),finished_at=time.time(),
                           errors=[str(e)[:1000] for e in history.errors() if e])
            store.put('task',id,current)
            store.event(id,'task_finished',{'status':current['status'],'result':current['result']})
    except asyncio.CancelledError:
        current = store.get('task',id)
        current.update(status='cancelled',finished_at=time.time())
        store.put('task',id,current)
        raise
    except Exception as exc:
        current = store.get('task',id)
        # Do not persist exception text: providers sometimes include request details.
        current.update(status='failed',error=type(exc).__name__,finished_at=time.time())
        store.put('task',id,current)
        store.event(id,'task_failed',{'error':type(exc).__name__})
    finally:
        await tools.close_client()
        await browser.kill()
        agent_row.update(status='idle',task_id=None)
        store.put('agent',agent_row['id'],agent_row)

async def queue_worker(store,jobs):
    while True:
        if configured() and not jobs:
            queued = [t for t in store.all('task') if t['status']=='queued']
            if queued:
                task = min(queued,key=lambda t:t['created_at'])
                job = asyncio.create_task(run_task(store,task))
                jobs[task['id']] = job
                job.add_done_callback(lambda _,id=task['id']:jobs.pop(id,None))
        await asyncio.sleep(.5)
