# -*- coding: utf-8 -*-
from __future__ import annotations
import os, json
from dataclasses import dataclass, field
from typing import Dict, List, Any
from flask import Flask, request, session, redirect, url_for, render_template, abort, send_from_directory

app = Flask(__name__)
app.secret_key = os.environ.get("TRIAGE_SECRET_KEY", "dev-secret-change-me")

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "protocols.json")
with open(DATA_PATH, "r", encoding="utf-8") as f:
    PROTOCOLS = json.load(f)

SYMPTOMS = [flow["symptom"] for flow in PROTOCOLS["flows"]]

@dataclass
class Question:
    id: str
    text: str
    qtype: str = "select"
    options: List[str] = field(default_factory=list)

@dataclass
class RuleSet:
    red_any: List[Dict[str, Any]] = field(default_factory=list)
    orange_any: List[Dict[str, Any]] = field(default_factory=list)
    yellow_any: List[Dict[str, Any]] = field(default_factory=list)
    green_any: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class SymptomFlow:
    symptom: str
    questions: List[Question]
    rules: RuleSet

def load_flows() -> Dict[str, SymptomFlow]:
    flows = {}
    for fl in PROTOCOLS["flows"]:
        qs = [Question(**q) for q in fl["questions"]]
        rules = RuleSet(**fl["rules"])
        flows[fl["symptom"]] = SymptomFlow(fl["symptom"], qs, rules)
    return flows

FLOWS = load_flows()

def _cmp(ans, op, val):
    if op == "eq": return ans == val
    if op == "neq": return ans != val
    if op == "in": return ans in (val or [])
    if op == "nin": return ans not in (val or [])
    try:
        a = float(ans); v = float(val)
        return {">": a > v, "<": a < v, ">=": a >= v, "<=": a <= v}.get(op, False)
    except Exception:
        return False

def evaluate_level(answers, flow: SymptomFlow):
    for c in flow.rules.red_any:
        if _cmp(answers.get(c["id"]), c["op"], c.get("value")):
            return {"level":"قرمز","why":[c.get("why", c["id"])]}
    for c in flow.rules.yellow_any:
        if _cmp(answers.get(c["id"]), c["op"], c.get("value")):
            return {"level":"زرد","why":[c.get("why", c["id"])]}
    for c in flow.rules.green_any:
        if _cmp(answers.get(c["id"]), c["op"], c.get("value")):
            return {"level":"سبز","why":[c.get("why", c["id"])]}
    return {"level":"سفید","why":["هیچ معیار کتاب برقرار نشد."]}

@app.get("/")
def index():
    q = request.args.get("q","")
    filtered = [s for s in SYMPTOMS if q in s]
    return render_template("index.html", symptoms=filtered, q=q, meta=PROTOCOLS.get("metadata",{}))

@app.get("/chat/<path:symptom>")
def chat_start(symptom):
    if symptom not in FLOWS: abort(404)
    triages = session.get("triages", {})
    data = triages.get(symptom)
    flow = FLOWS[symptom]
    if not data:
        data = {"answers":{}, "idx":0, "messages":[{"role":"bot","text":"گفت‌وگو آغاز شد."}]}
        triages[symptom]=data; session["triages"]=triages
        data["messages"].append({"role":"bot","text": flow.questions[0].text})
    idx = data["idx"]
    q = flow.questions[idx] if idx < len(flow.questions) else None
    done = idx >= len(flow.questions)
    return render_template("chat.html", symptom=symptom, q=q, step=idx, total=len(flow.questions),
                           messages=data["messages"], done=done, result=data.get("result"))

@app.post("/chat/<path:symptom>")
def chat_step(symptom):
    if symptom not in FLOWS: abort(404)
    triages = session.get("triages", {}); data = triages.get(symptom); flow = FLOWS[symptom]
    if not data: return redirect(url_for("chat_start", symptom=symptom))
    ans = request.form.get("ans"); q_prev = flow.questions[data["idx"]]
    data["answers"][q_prev.id]=ans
    data["messages"].append({"role":"user","text":ans})
    data["idx"]+=1
    if data["idx"]>=len(flow.questions):
        data["result"]=evaluate_level(data["answers"],flow)
        done=True; q=None
    else:
        q=flow.questions[data["idx"]]; done=False
        data["messages"].append({"role":"bot","text":q.text})
    triages[symptom]=data; session["triages"]=triages
    return render_template("chat.html", symptom=symptom, q=q, step=data["idx"], total=len(flow.questions),
                           messages=data["messages"], done=done, result=data.get("result"))

@app.post("/chat/<path:symptom>/reset")
def chat_reset(symptom):
    triages=session.get("triages",{}); triages.pop(symptom,None); session["triages"]=triages
    return redirect(url_for("chat_start",symptom=symptom))

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8000)))


@app.get("/assets/<path:filename>")
def assets(filename):
    # Serve files placed alongside app.py (e.g., IRANSans.woff2 / IRANSans.ttf)
    return send_from_directory(os.path.dirname(__file__), filename)
