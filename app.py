# -*- coding: utf-8 -*-
"""
Flask Triage App — Telephone 4-Level Triage
- صفحه‌ی اول: فهرست علایم
- صفحه‌ی دوم: چت‌بات — سؤالات ABCS + اختصاصی هر علامت
- خروجی: سطح‌بندی قرمز / زرد / سبز / سفید + دلایل
- ✅ هیستوری گفتگو برای هر علامت حفظ می‌شود
- ✅ دکمه Reset برای پاک کردن هیستوری
- ✅ عبارت «متشکرم. سؤال بعد» حذف شد (فقط متن سؤال بعدی ثبت می‌شود)
⚠️ آموزشی؛ قبل از استفادهٔ بالینی بازبینی شود.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Dict, List, Any
from flask import Flask, request, session, redirect, url_for, render_template, abort

app = Flask(__name__)
app.secret_key = os.environ.get("TRIAGE_SECRET_KEY", "dev-secret-change-me")

# ==============================
# داده‌ها و مدل‌ها
# ==============================
SYMPTOMS = [
    "انسداد راه هوایی (خفگی/جسم خارجی)",
    "مشکلات تنفسی",
    "درد قفسه سینه",
    "سکته مغزی",
    "تشنج",
    "سردرد",
    "دیابت (مشکلات مرتبط)",
    "درد شکم و پهلو",
    "درد کمر/کشاله ران/اسکروتوم",
    "فتق مختنق",
    "زایمان/بارداری",
    "ضعف/بی‌حالی",
    "تغییرات فشارخون",
    "استفراغ/اسهال/تهوع",
    "تب و لرز",
    "مشکلات چشمی",
    "غرق‌شدگی",
    "برق‌گرفتگی",
    "مسمومیت‌ها",
    "آنافیلاکسی (آلرژی شدید)",
    "گزیدگی‌ها",
    "سوختگی",
]

@dataclass
class Question:
    id: str
    text: str
    qtype: str = "select"  # select|yesno|number|text
    options: List[str] = field(default_factory=list)

@dataclass
class RuleSet:
    red_any: List[Dict[str, Any]] = field(default_factory=list)
    yellow_any: List[Dict[str, Any]] = field(default_factory=list)
    green_any: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class SymptomFlow:
    symptom: str
    questions: List[Question]
    rules: RuleSet

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
    why = [c.get("why", c["id"]) for c in flow.rules.red_any if _cmp(answers.get(c["id"]), c["op"], c.get("value"))]
    if why: return {"level": "قرمز", "why": why}
    why = [c.get("why", c["id"]) for c in flow.rules.yellow_any if _cmp(answers.get(c["id"]), c["op"], c.get("value"))]
    if why: return {"level": "زرد", "why": why}
    why = [c.get("why", c["id"]) for c in flow.rules.green_any if _cmp(answers.get(c["id"]), c["op"], c.get("value"))]
    if why: return {"level": "سبز", "why": why}
    return {"level": "سفید", "why": ["هیچ معیار جدی برقرار نشد."]}

# ==============================
# سؤالات ABCS عمومی
# ==============================
ABCS_QS = [
    Question("a_speak","آیا بیمار قادر به صحبت/بلع است؟","select",["بله","خیر"]),
    Question("b_breath","تنگی نفس/تنفس صدادار/تقلا؟","select",["خیر","خفیف","شدید"]),
    Question("c_bleed","خون‌ریزی کنترل‌نشده/رنگ‌پریدگی شدید؟","select",["خیر","بله"]),
    Question("c_faint","سنکوب/بی‌هوشی/عدم پاسخ؟","select",["خیر","بله"]),
]

ABCS_RULES = RuleSet(
    red_any=[
        {"id":"a_speak","op":"eq","value":"خیر","why":"تهدید راه‌هوایی"},
        {"id":"b_breath","op":"eq","value":"شدید","why":"دیسترس تنفسی شدید"},
        {"id":"c_bleed","op":"eq","value":"بله","why":"شوک/خون‌ریزی کنترل‌نشده"},
        {"id":"c_faint","op":"eq","value":"بله","why":"کاهش سطح هوشیاری"},
    ],
    yellow_any=[{"id":"b_breath","op":"eq","value":"خفیف","why":"تنگی‌نفس قابل توجه"}]
)

def build_flow(symptom: str, extra_qs: List[Question], extra_rules: RuleSet) -> SymptomFlow:
    return SymptomFlow(symptom, ABCS_QS + extra_qs,
        RuleSet(
            red_any=ABCS_RULES.red_any + extra_rules.red_any,
            yellow_any=ABCS_RULES.yellow_any + extra_rules.yellow_any,
            green_any=extra_rules.green_any
        )
    )

FLOWS: Dict[str, SymptomFlow] = {}

def add(sym, qs, rules): FLOWS[sym] = build_flow(sym, qs, rules)

# ---- چند فلو نمونه کامل (می‌توانید توسعه دهید) ----
add("انسداد راه هوایی (خفگی/جسم خارجی)", [
    Question("aw_sudden","شروع ناگهانی پس از خوردن/جسم خارجی؟","select",["خیر","بله"]),
    Question("aw_voice","استریدور/تغییر صدا؟","select",["خیر","بله"]),
    Question("aw_cyan","کبودی لب/صورت؟","select",["خیر","بله"]),
], RuleSet(red_any=[
    {"id":"aw_sudden","op":"eq","value":"بله","why":"شک جسم خارجی راه‌هوایی"},
    {"id":"aw_voice","op":"eq","value":"بله","why":"انسداد فوقانی"},
    {"id":"aw_cyan","op":"eq","value":"بله","why":"سیانوز"},
]))

add("مشکلات تنفسی", [
    Question("br_rate","تعداد تنفس در دقیقه؟","number"),
    Question("br_color","آبی شدن لب/صورت؟","select",["خیر","بله"]),
], RuleSet(
    red_any=[{"id":"br_color","op":"eq","value":"بله","why":"سیانوز"}],
    yellow_any=[{"id":"br_rate","op":">=","value":22,"why":"تاکی‌پنه"}]
))

add("درد قفسه سینه", [
    Question("cp_type","نوع درد سینه؟","select",["فشارنده/سنگین","تیز/پلوریتیک","نامشخص"]),
    Question("cp_radiate","انتشار به بازو/فک/گردن؟","select",["خیر","بله"]),
], RuleSet(
    red_any=[
        {"id":"cp_type","op":"eq","value":"فشارنده/سنگین","why":"درد تیپیک قلبی"},
        {"id":"cp_radiate","op":"eq","value":"بله","why":"انتشار درد"},
    ],
    yellow_any=[{"id":"cp_type","op":"eq","value":"نامشخص","why":"نیاز به ارزیابی"}]
))

add("سکته مغزی", [
    Question("st_face","افتادگی صورت یک‌طرفه؟","select",["خیر","بله"]),
    Question("st_arm","ضعف/بی‌حسی اندام یک‌طرفه؟","select",["خیر","بله"]),
    Question("st_speech","اختلال گفتار/درک؟","select",["خیر","بله"]),
], RuleSet(red_any=[
    {"id":"st_face","op":"eq","value":"بله","why":"علامت حاد سکته"},
    {"id":"st_arm","op":"eq","value":"بله","why":"علامت حاد سکته"},
    {"id":"st_speech","op":"eq","value":"بله","why":"علامت حاد سکته"},
]))

add("تشنج", [
    Question("sz_now","هم‌اکنون تشنج ادامه دارد؟","select",["خیر","بله"]),
    Question("sz_awake","هوشیاری بعد از تشنج؟","select",["طبیعی","کاهش یافته"]),
], RuleSet(
    red_any=[{"id":"sz_now","op":"eq","value":"بله","why":"استاتوس تشنجی"}],
    yellow_any=[{"id":"sz_awake","op":"eq","value":"کاهش یافته","why":"پست‌اکت"}]
))

add("آنافیلاکسی (آلرژی شدید)", [
    Question("ana_breath","تنگی نفس/سفتی گلو؟","select",["خیر","بله"]),
    Question("ana_swelling","ورم صورت/لب/گلو؟","select",["خیر","بله"]),
    Question("ana_rash","کهیر منتشر؟","select",["خیر","بله"]),
], RuleSet(
    red_any=[
        {"id":"ana_breath","op":"eq","value":"بله","why":"درگیری تنفسی"},
        {"id":"ana_swelling","op":"eq","value":"بله","why":"ادم راه‌هوایی"},
    ],
    yellow_any=[{"id":"ana_rash","op":"eq","value":"بله","why":"علامت پوستی"}]
))

# برای سایر علایم — حداقل ABCS + یک سؤال متنی
for s in SYMPTOMS:
    FLOWS.setdefault(s, build_flow(s, [Question("note","توضیح دهید","text")], RuleSet()))

# ==============================
# Routes
# ==============================
@app.get("/")
def index():
    q = request.args.get("q","")
    filtered = [s for s in SYMPTOMS if q in s]
    return render_template("index.html", symptoms=filtered, q=q)

@app.get("/chat/<path:symptom>")
def chat_start(symptom):
    if symptom not in FLOWS: abort(404)
    triages = session.get("triages", {})
    data = triages.get(symptom)
    flow = FLOWS[symptom]
    if not data:
        data = {"answers": {}, "idx":0, "messages":[{"role":"bot","text":"شروع گفتگو"}]}
        triages[symptom] = data; session["triages"]=triages
        # نمایش اولین سؤال در هیستوری
        data["messages"].append({"role":"bot","text": flow.questions[0].text})
    idx = data["idx"]
    q = flow.questions[idx] if idx < len(flow.questions) else None
    done = idx >= len(flow.questions)
    return render_template("chat.html", symptom=symptom, q=q, step=idx,
                           total=len(flow.questions), messages=data["messages"],
                           done=done, result=data.get("result"))

@app.post("/chat/<path:symptom>")
def chat_step(symptom):
    if symptom not in FLOWS: abort(404)
    triages = session.get("triages", {}); data = triages.get(symptom); flow = FLOWS[symptom]
    if not data:
        return redirect(url_for("chat_start", symptom=symptom))
    ans = request.form.get("ans"); q_prev = flow.questions[data["idx"]]
    data["answers"][q_prev.id]=ans
    data["messages"].append({"role":"user","text":ans})
    data["idx"]+=1
    if data["idx"]>=len(flow.questions):
        data["result"]=evaluate_level(data["answers"],flow)
        done=True; q=None
    else:
        q=flow.questions[data["idx"]]; done=False
        # فقط متن سؤال بعدی را ثبت می‌کنیم (بدون «متشکرم…»)
        data["messages"].append({"role":"bot","text":q.text})
    triages[symptom]=data; session["triages"]=triages
    return render_template("chat.html", symptom=symptom, q=q, step=data["idx"],
                           total=len(flow.questions), messages=data["messages"],
                           done=done, result=data.get("result"))

@app.post("/chat/<path:symptom>/reset")
def chat_reset(symptom):
    triages=session.get("triages",{}); triages.pop(symptom,None); session["triages"]=triages
    return redirect(url_for("chat_start",symptom=symptom))

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8000)))
