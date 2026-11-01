import json
import os
import sqlite3
import time
from pathlib import Path
from uuid import uuid4

def uid():
    return uuid4().hex

class Store:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv('GUARD_DB', '.data/guard.db'))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.executescript('''
              CREATE TABLE IF NOT EXISTS documents(kind TEXT, id TEXT, data TEXT, PRIMARY KEY(kind,id));
              CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, at REAL, kind TEXT, data TEXT);
            ''')

    def connect(self):
        c = sqlite3.connect(self.path, timeout=15)
        c.execute('PRAGMA journal_mode=WAL')
        return c

    def put(self, kind, id, data):
        with self.connect() as c:
            c.execute('INSERT OR REPLACE INTO documents VALUES(?,?,?)', (kind,id,json.dumps(data,ensure_ascii=False)))
        return data

    def get(self, kind, id):
        with self.connect() as c:
            r = c.execute('SELECT data FROM documents WHERE kind=? AND id=?',(kind,id)).fetchone()
        return json.loads(r[0]) if r else None

    def all(self, kind):
        with self.connect() as c:
            return [json.loads(r[0]) for r in c.execute('SELECT data FROM documents WHERE kind=? ORDER BY rowid DESC',(kind,))]

    def delete(self, kind, id):
        with self.connect() as c:
            c.execute('DELETE FROM documents WHERE kind=? AND id=?',(kind,id))

    def event(self, task_id, kind, data):
        with self.connect() as c:
            c.execute('INSERT INTO events(task_id,at,kind,data) VALUES(?,?,?,?)',(task_id,time.time(),kind,json.dumps(data,ensure_ascii=False)))

    def events(self, task_id=None, after=0):
        with self.connect() as c:
            q = 'SELECT seq,task_id,at,kind,data FROM events WHERE seq>?'
            params = [after]
            if task_id:
                q += ' AND task_id=?'
                params.append(task_id)
            rows = c.execute(q+' ORDER BY seq LIMIT 1000',params).fetchall()
        return [dict(seq=r[0],task_id=r[1],at=r[2],kind=r[3],data=json.loads(r[4])) for r in rows]
