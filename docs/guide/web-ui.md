# Step 6: Add a web UI

← [Back to the guide](../BUILD_YOUR_OWN_AGENT.md)

Wrap `run_agent` in FastAPI and serve one HTML page with a text box.

```python
# ui.py
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from agent import run_agent

app = FastAPI()

@app.post("/ask")
def ask(body: dict):
    return {"answer": run_agent(body["question"])}

@app.get("/", response_class=HTMLResponse)
def index():
    return """<input id=q size=60><button onclick="go()">Ask</button><pre id=a></pre>
    <script>async function go(){
      const r = await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({question:q.value})});
      a.textContent=(await r.json()).answer}</script>"""
```

Run it:

```bash
uvicorn ui:app --reload
```

Open http://127.0.0.1:8000.

Once it works, move the HTML into `templates/` and the JavaScript into `static/` so the Python file stays about routes only. agent0 does this in `core/ui.py`, `templates/` and `static/`.

Back to the guide: [v1 is done](../BUILD_YOUR_OWN_AGENT.md#v1-is-done).
