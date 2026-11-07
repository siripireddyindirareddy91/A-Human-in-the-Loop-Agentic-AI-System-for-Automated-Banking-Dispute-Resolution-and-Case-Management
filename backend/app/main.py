import os, io, csv, json, secrets, time, uuid, re, math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TypedDict
import bcrypt, jwt
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, Text, Float, select
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from langgraph.graph import StateGraph, END

DEMO = os.getenv('DEMO_MODE', 'true').lower() == 'true'
SECRET = os.getenv('JWT_SECRET_KEY')
if not SECRET:
    if not DEMO: raise RuntimeError('JWT_SECRET_KEY is required outside demo mode')
    SECRET = secrets.token_hex(32)
DB = os.getenv('DATABASE_URL', 'sqlite:////tmp/banking.db' if os.getenv('VERCEL') else 'sqlite:///./banking.db')
engine = create_engine(DB, connect_args={'check_same_thread': False} if DB.startswith('sqlite') else {}, pool_pre_ping=True)
Session = sessionmaker(engine)
class Base(DeclarativeBase): pass
class Record(Base):
    __tablename__ = 'records'
    id = Column(Integer, primary_key=True)
    kind = Column(String(40), index=True, nullable=False)
    key = Column(String(100), unique=True, nullable=False)
    owner = Column(String(100), index=True)
    data = Column(Text, nullable=False)
Base.metadata.create_all(engine)
def now(): return datetime.now(timezone.utc).isoformat()
def rows(s, kind): return [json.loads(r.data) for r in s.scalars(select(Record).where(Record.kind == kind))]
def get(s, key):
    r = s.scalar(select(Record).where(Record.key == key))
    if not r: raise HTTPException(404, 'Record not found')
    return json.loads(r.data)
def put(s, kind, d):
    r = s.scalar(select(Record).where(Record.key == d['id']))
    if r: r.data = json.dumps(d)
    else: s.add(Record(kind=kind, key=d['id'], owner=d.get('customer_id'), data=json.dumps(d)))
    s.flush()
def event(s, user, action, case=None, detail=''):
    put(s,'audit',{'id':str(uuid.uuid4()),'actor':user['name'],'action':action,'case_id':case,'detail':detail,'created_at':now()})
def notify(s, c, text):
    put(s,'notification',{'id':str(uuid.uuid4()),'customer_id':c['customer_id'],'case_id':c['id'],'title':text,'is_read':False,'created_at':now()})
CATEGORIES = ['Unauthorized transaction','Duplicate transaction','ATM cash not received','Refund not received','Incorrect amount','Suspicious high-value transaction','Merchant dispute','UPI transfer failed','NEFT transfer dispute','Account complaint']
AGENTS = ['Complaint Understanding','Transaction Verification','Customer History','Fraud Detection','Banking Policy RAG','Dispute Investigation','Resolution Recommendation','Quality Validation','Human Escalation','Case Management']
ROLES = ['customer','officer','analyst','admin']
with Session.begin() as s:
    if not rows(s,'user'):
        hashed = bcrypt.hashpw(b'Demo@2026!', bcrypt.gensalt()).decode()
        for i,role in enumerate(ROLES): put(s,'user',{'id':f'user-{role}','name':{'customer':'Ananya Sharma','officer':'Priya Mehta','analyst':'Arjun Rao','admin':'Indira Reddy'}[role],'email':f'{role}@demo.bank','role':role,'customer_id':'CUS-001' if role=='customer' else None,'password_hash':hashed})
        for i in range(1,51): put(s,'customer',{'id':f'CUS-{i:03}','name': ['Ananya Sharma','Rohan Patel','Meera Iyer','Vikram Singh','Sara Khan'][ (i-1)%5]+(f' {i}' if i>5 else ''),'account':f'•••• {4100+i}'})
        for i in range(1,201): put(s,'transaction',{'id':f'TXN-{i:05}','customer_id':f'CUS-{(i-1)%50+1:03}','amount':round(750+i*137.5,2),'merchant':['Amazon India','Metro ATM','Swiggy','UPI · merchant','Flipkart'][i%5],'channel':['UPI','ATM','Debit Card','NEFT','Credit Card'][i%5],'status':'SETTLED','date':f'2026-11-{(i%7)+1:02}','account':f'•••• {4100+(i-1)%50+1}'})
        for i,cat in enumerate(CATEGORIES): put(s,'policy',{'id':f'POL-{i+1:02}','name':cat+' — sample procedure','category':cat,'section':'§ 2 · Evidence and review','text':f'SAMPLE POLICY, NOT OFFICIAL REGULATION. For {cat.lower()}, verify the transaction reference, customer evidence and settlement status. Request missing evidence. A human officer must approve any resolution. High risk and amounts above INR 20,000 require two distinct reviewers. No financial operation may be executed by an AI agent.','created_at':now()})
        for i in range(1,31):
            tx=get(s,f'TXN-{i:05}'); customer=get(s,tx['customer_id'])
            put(s,'case',{'id':f'BDR-2026-{i:05}','customer_id':tx['customer_id'],'customer':customer['name'],'transaction_id':tx['id'],'amount':tx['amount'],'category':CATEGORIES[(i-1)%10],'description':f'I need help investigating this {CATEGORIES[(i-1)%10].lower()}. Please verify the transaction and provide a resolution.','status':['SUBMITTED','PENDING_HUMAN_REVIEW','UNDER_INVESTIGATION','RESOLVED','ESCALATED'][i%5],'risk_score':(i*17)%100,'risk_level':'HIGH' if (i*17)%100>=65 else 'LOW','priority':'HIGH' if i%3==0 else 'MEDIUM','assigned':'Priya Mehta','created_at':now(),'updated_at':now(),'reviews':[],'notes':[],'evidence':[],'agents':[]})

app=FastAPI(title='DisputeOS API',version='1.0.0',description='Synthetic banking sandbox. No real money operations.')
app.add_middleware(CORSMiddleware,allow_origins=os.getenv('CORS_ORIGINS','http://localhost:5173').split(','),allow_methods=['*'],allow_headers=['*'])
bearer=HTTPBearer()
def session():
    with Session.begin() as s: yield s
def auth(token:HTTPAuthorizationCredentials=Depends(bearer),s=Depends(session)):
    try: payload=jwt.decode(token.credentials, SECRET, algorithms=['HS256']); return get(s,payload['sub'])
    except (jwt.PyJWTError,KeyError): raise HTTPException(401,'Invalid or expired session')
def staff(u):
    if u['role']=='customer': raise HTTPException(403,'Staff access required')
def admin(u):
    if u['role']!='admin': raise HTTPException(403,'Administrator access required')
def case_access(s,key,u):
    c=get(s,key)
    if not key.startswith('BDR-'): raise HTTPException(404,'Case not found')
    if u['role']=='customer' and c['customer_id']!=u['customer_id']: raise HTTPException(403,'Case access denied')
    return c
def visible(s,u): return [c for c in rows(s,'case') if u['role']!='customer' or c['customer_id']==u['customer_id']]
class Login(BaseModel):
    email:str
    password:str=Field(min_length=8,max_length=72)
class Register(Login): name:str=Field(min_length=2,max_length=100)
class NewCase(BaseModel):
    transaction_id:str=Field(min_length=1,max_length=100)
    category:str
    description:str=Field(min_length=20,max_length=10000)
    amount:float=Field(gt=0,le=10000000)
class Decision(BaseModel): reason:str=Field(min_length=10,max_length=2000)
class Search(BaseModel): query:str=Field(min_length=2,max_length=500)
@app.get('/api/health')
def health(): return {'status':'ok','demo_mode':DEMO,'persistent_storage':not bool(os.getenv('VERCEL')) or not DB.startswith('sqlite')}
@app.post('/api/auth/login')
def login(v:Login,s=Depends(session)):
    u=next((u for u in rows(s,'user') if u['email']==v.email),None)
    if not u or not bcrypt.checkpw(v.password.encode(),u['password_hash'].encode()): raise HTTPException(401,'Incorrect email or password')
    return {'token':jwt.encode({'sub':u['id'],'exp':datetime.now(timezone.utc)+timedelta(hours=8)},SECRET,algorithm='HS256'),'user':{k:v for k,v in u.items() if k!='password_hash'}}
@app.post('/api/auth/register',status_code=201)
def register(v:Register,s=Depends(session)):
    if any(u['email']==v.email for u in rows(s,'user')): raise HTTPException(409,'Email already registered')
    cid='CUS-'+uuid.uuid4().hex[:8]
    put(s,'customer',{'id':cid,'name':v.name,'account':'•••• demo'})
    u={'id':'user-'+uuid.uuid4().hex,'name':v.name,'email':v.email,'role':'customer','customer_id':cid,'password_hash':bcrypt.hashpw(v.password.encode(),bcrypt.gensalt()).decode()}
    put(s,'user',u); return {'id':u['id']}
@app.get('/api/auth/me')
def me(u=Depends(auth)): return {k:v for k,v in u.items() if k!='password_hash'}
@app.get('/api/disputes')
def cases(u=Depends(auth),s=Depends(session)): return visible(s,u)
@app.get('/api/disputes/{key}')
def detail(key:str,u=Depends(auth),s=Depends(session)): return case_access(s,key,u)
class State(TypedDict): case:dict; outputs:list; policies:list; transactions:list; history:list
def retrieve(s,query):
    docs=rows(s,'policy')
    if not docs: return []
    tokens=lambda text: Counter(re.findall(r'[a-z0-9]+',text.lower()))
    corpus=[tokens(d['category']+' '+d['text']) for d in docs]
    idf={word:math.log((len(docs)+1)/(1+sum(word in doc for doc in corpus)))+1 for doc in corpus for word in doc}
    def vector(counts): return {w:n*idf.get(w,1) for w,n in counts.items()}
    q=vector(tokens(query)); qnorm=math.sqrt(sum(v*v for v in q.values())) or 1
    scores=[]
    for doc in corpus:
        v=vector(doc); norm=math.sqrt(sum(n*n for n in v.values())) or 1
        scores.append(sum(n*v.get(w,0) for w,n in q.items())/(qnorm*norm))
    return [{**docs[i],'score':round(scores[i],3)} for i in sorted(range(len(docs)),key=lambda i:scores[i],reverse=True)[:3] if scores[i]>0]
def node(name):
    def run(st):
        c=st['case']; tx=next((t for t in st['transactions'] if t['id']==c['transaction_id']),None); risk=min(99,15+int(c['amount']/1000)+(55 if 'Unauthorized' in c['category'] or 'Suspicious' in c['category'] else 0))
        output={
          'Complaint Understanding':{'summary':c['description'],'category':c['category'],'transaction_id':c['transaction_id'],'amount':c['amount'],'confidence':0.92},
          'Transaction Verification':{'found':bool(tx),'amount_matches': bool(tx and abs(tx['amount']-c['amount'])<0.01),'transaction':tx,'missing_information':[] if tx else ['Valid transaction reference']},
          'Customer History':{'previous_cases':len(st['history']),'note':'Prior complaints are context, never proof of fraud.'},
          'Fraud Detection':{'risk_score':risk,'risk_level':'HIGH' if risk>=65 else 'MEDIUM' if risk>=35 else 'LOW','indicators':(['High transaction value'] if c['amount']>=20000 else [])+(['Potential unauthorized activity'] if 'Unauthorized' in c['category'] else []),'model_version':'explainable-rules-v1','limitation':'Decision support only. No calibrated fraud probability.'},
          'Banking Policy RAG':{'sources':st['policies'],'method':'Local TF-IDF cosine similarity'},
          'Dispute Investigation':{'findings':['Transaction located' if tx else 'Transaction not located','Evidence must be reviewed by an officer'],'missing_evidence':[] if c['evidence'] else ['Customer supporting documents'],'hypothesis':'Settlement discrepancy requires verification'},
          'Resolution Recommendation':{'action':'Request Additional Information' if not tx or not c['evidence'] else 'Recommend Manual Investigation','confidence':0.85 if tx else 0.4,'human_approval_required':True},
          'Quality Validation':{'valid':bool(st['policies'] and tx),'citations_valid':all(p['id'] for p in st['policies']),'unsupported_financial_actions':False},
          'Human Escalation':{'required':True,'reason':'Human authorization required; AI never approves resolutions','two_person':risk>=65 or c['amount']>=20000},
          'Case Management':{'status':'PENDING_HUMAN_REVIEW','priority':'HIGH' if risk>=65 else 'MEDIUM'}
        }[name]
        return {'outputs':st['outputs']+[{'agent':name,'status':'COMPLETED','output':output,'created_at':now(),'duration_ms':1}]}
    return run
graph=StateGraph(State)
for name in AGENTS: graph.add_node(name,node(name))
graph.set_entry_point(AGENTS[0])
for a,b in zip(AGENTS,AGENTS[1:]): graph.add_edge(a,b)
graph.add_edge(AGENTS[-1],END)
workflow=graph.compile()
def investigate(s,c,u):
    result=workflow.invoke({'case':c,'outputs':[],'policies':retrieve(s,c['category']),'transactions':rows(s,'transaction'),'history':[x for x in rows(s,'case') if x['customer_id']==c['customer_id'] and x['id']!=c['id']]})
    c['agents']=result['outputs']; fraud=c['agents'][3]['output']; c.update(risk_score=fraud['risk_score'],risk_level=fraud['risk_level'],status='PENDING_HUMAN_REVIEW',updated_at=now()); c['recommendation']=c['agents'][6]['output']; c['policies']=result['policies']; c['two_person']=c['agents'][8]['output']['two_person']
    put(s,'checkpoint',{'id':'checkpoint-'+c['id'],'case_id':c['id'],'state':result,'created_at':now()}); put(s,'case',c); event(s,u,'Investigation completed',c['id']); notify(s,c,'Investigation ready for human review'); return c
@app.post('/api/disputes',status_code=201)
def create(v:NewCase,u=Depends(auth),s=Depends(session)):
    tx=get(s,v.transaction_id)
    if not v.transaction_id.startswith('TXN-'): raise HTTPException(400,'Invalid transaction')
    if u['role']=='customer' and tx['customer_id']!=u['customer_id']: raise HTTPException(403,'Transaction access denied')
    if v.category not in CATEGORIES: raise HTTPException(422,'Invalid category')
    customer=get(s,tx['customer_id']); c={'id':'BDR-2026-'+uuid.uuid4().hex[:10].upper(),'customer_id':tx['customer_id'],'customer':customer['name'],**v.model_dump(),'status':'SUBMITTED','priority':'MEDIUM','risk_level':'LOW','risk_score':0,'assigned':'Priya Mehta','created_at':now(),'updated_at':now(),'reviews':[],'notes':[],'evidence':[],'agents':[]}
    put(s,'case',c); event(s,u,'Dispute submitted',c['id']); return investigate(s,c,u)
@app.post('/api/investigations/{key}/start')
def start(key:str,u=Depends(auth),s=Depends(session)):
    c=case_access(s,key,u)
    if c['status'] in ['RESOLVED','REJECTED','CLOSED']: raise HTTPException(409,'Finalized cases cannot be reinvestigated')
    if c['reviews']: raise HTTPException(409,'Reviewed cases cannot be reinvestigated')
    return investigate(s,c,u)
@app.get('/api/investigations/{key}')
def investigation(key:str,u=Depends(auth),s=Depends(session)): return case_access(s,key,u)['agents']
@app.post('/api/reviews/{key}/{action}')
def review(key:str,action:str,v:Decision,u=Depends(auth),s=Depends(session)):
    staff(u); c=case_access(s,key,u)
    if action not in ['approve','reject','request-information','escalate']: raise HTTPException(400,'Invalid review action')
    if c['status'] not in ['PENDING_HUMAN_REVIEW','ESCALATED','AWAITING_INFORMATION']: raise HTTPException(409,'Case is not awaiting review')
    if not c['agents']: raise HTTPException(409,'Run investigation before review')
    if (c.get('two_person') or c['risk_score']>=65) and u['role'] not in ['analyst','admin']: raise HTTPException(403,'High risk decisions require senior analyst or administrator')
    if any(r['reviewer_id']==u['id'] and r['action']=='approve' for r in c['reviews']): raise HTTPException(409,'A second distinct reviewer is required')
    c['reviews'].append({'reviewer_id':u['id'],'reviewer':u['name'],'action':action,'reason':v.reason,'created_at':now()})
    approvals=len({r['reviewer_id'] for r in c['reviews'] if r['action']=='approve'})
    c['status']=('RESOLVED' if approvals >= (2 if c.get('two_person') else 1) else 'PENDING_HUMAN_REVIEW') if action=='approve' else {'reject':'REJECTED','request-information':'AWAITING_INFORMATION','escalate':'ESCALATED'}[action]
    c['updated_at']=now(); put(s,'case',c); event(s,u,'Human '+action,key,v.reason); notify(s,c,'Review decision: '+c['status']); return c
@app.post('/api/disputes/{key}/notes')
def notes(key:str,v:Decision,u=Depends(auth),s=Depends(session)):
    c=case_access(s,key,u); c['notes'].append({'author':u['name'],'text':v.reason,'created_at':now()}); put(s,'case',c); event(s,u,'Note added',key); return c
@app.post('/api/disputes/{key}/evidence')
async def evidence(key:str,file:UploadFile=File(...),u=Depends(auth),s=Depends(session)):
    c=case_access(s,key,u); raw=await file.read(5*1024*1024+1); ext=Path(file.filename or '').suffix.lower()
    if len(raw)>5*1024*1024: raise HTTPException(413,'Maximum file size is 5 MB')
    signatures={'.pdf':b'%PDF','.png':b'\x89PNG\r\n\x1a\n','.jpg':b'\xff\xd8\xff','.jpeg':b'\xff\xd8\xff','.docx':b'PK'}
    if ext not in signatures or not raw.startswith(signatures[ext]): raise HTTPException(400,'Invalid file type or signature')
    import base64
    fid=str(uuid.uuid4()); put(s,'file',{'id':fid,'case_id':key,'content':base64.b64encode(raw).decode(),'filename':Path(file.filename).name})
    c['evidence'].append({'id':fid,'filename':Path(file.filename).name,'size':len(raw),'created_at':now()}); put(s,'case',c); event(s,u,'Evidence uploaded',key); return c
@app.get('/api/evidence/{fid}')
def download(fid:str,u=Depends(auth),s=Depends(session)):
    import base64
    f=get(s,fid); case_access(s,f['case_id'],u); return Response(base64.b64decode(f['content']),media_type='application/octet-stream',headers={'Content-Disposition':'attachment; filename="evidence'+Path(f['filename']).suffix+'"'})
@app.get('/api/transactions')
def transactions(u=Depends(auth),s=Depends(session)): return [t for t in rows(s,'transaction') if u['role']!='customer' or t['customer_id']==u['customer_id']]
@app.get('/api/dashboard/summary')
def summary(u=Depends(auth),s=Depends(session)):
    cs=visible(s,u); return {'total':len(cs),'open':sum(c['status'] not in ['RESOLVED','REJECTED','CLOSED'] for c in cs),'review':sum(c['status']=='PENDING_HUMAN_REVIEW' for c in cs),'resolved':sum(c['status']=='RESOLVED' for c in cs),'high_risk':sum(c['risk_score']>=65 for c in cs),'exposure':sum(c['amount'] for c in cs),'categories':[{'name':cat,'value':sum(c['category']==cat for c in cs)} for cat in CATEGORIES]}
@app.get('/api/knowledge/documents')
def policies(u=Depends(auth),s=Depends(session)): return rows(s,'policy')
@app.post('/api/knowledge/search')
def search(v:Search,u=Depends(auth),s=Depends(session)): return retrieve(s,v.query)
@app.post('/api/knowledge/upload')
async def upload_policy(file:UploadFile=File(...),u=Depends(auth),s=Depends(session)):
    admin(u); raw=await file.read(5*1024*1024+1)
    if len(raw)>5*1024*1024: raise HTTPException(413,'Maximum file size is 5 MB')
    try:
        ext=Path(file.filename or '').suffix.lower()
        if ext=='.pdf':
            from pypdf import PdfReader
            text='\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(raw)).pages)
        elif ext=='.docx':
            from docx import Document
            text='\n'.join(p.text for p in Document(io.BytesIO(raw)).paragraphs)
        elif ext=='.txt': text=raw.decode('utf-8')
        else: raise ValueError('Unsupported format')
    except Exception: raise HTTPException(400,'Cannot process document; use PDF, DOCX or TXT')
    if not text.strip(): raise HTTPException(400,'No extractable text found')
    doc={'id':'POL-'+uuid.uuid4().hex,'name':Path(file.filename).name,'category':'Uploaded sample','section':'Full document','text':text[:100000],'created_at':now()}; put(s,'policy',doc); event(s,u,'Policy ingested',detail=doc['name']); return doc
@app.get('/api/agents')
def agents(u=Depends(auth),s=Depends(session)):
    staff(u); executions=[a for c in visible(s,u) for a in c['agents']]; return [{'name':n,'executions':sum(a['agent']==n for a in executions),'status':'IDLE','outputs':[a for a in executions if a['agent']==n][-5:]} for n in AGENTS]
@app.get('/api/audit-logs')
def audit(u=Depends(auth),s=Depends(session)): staff(u); return rows(s,'audit')[::-1]
@app.get('/api/users')
def users(u=Depends(auth),s=Depends(session)): admin(u); return [{k:v for k,v in x.items() if k!='password_hash'} for x in rows(s,'user')]
@app.get('/api/notifications')
def notifications(u=Depends(auth),s=Depends(session)): return [n for n in rows(s,'notification') if u['role']!='customer' or n['customer_id']==u['customer_id']]
@app.patch('/api/notifications/{key}/read')
def read(key:str,u=Depends(auth),s=Depends(session)):
    n=get(s,key)
    if u['role']=='customer' and n.get('customer_id')!=u['customer_id']: raise HTTPException(403,'Access denied')
    n['is_read']=True; put(s,'notification',n); return n
@app.get('/api/reports/export')
def export(format:str='csv',u=Depends(auth),s=Depends(session)):
    cs=visible(s,u)
    if format=='pdf':
        from reportlab.pdfgen.canvas import Canvas
        out=io.BytesIO(); pdf=Canvas(out); pdf.setTitle('DisputeOS case report'); y=800
        pdf.drawString(40,y,'DisputeOS | Synthetic banking case report'); y-=35
        for c in cs:
            if y<50: pdf.showPage(); y=800
            pdf.drawString(40,y,f"{c['id']} | INR {c['amount']:,.2f} | {c['status']}"); y-=22
        pdf.save(); return Response(out.getvalue(),media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="disputes.pdf"'})
    out=io.StringIO(); writer=csv.writer(out); writer.writerow(['Case','Category','Amount','Status','Risk'])
    for c in cs: writer.writerow([c['id'],c['category'],c['amount'],c['status'],c['risk_score']])
    return Response(out.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="disputes.csv"'})

if DEMO:
    import sys
    from backend.app.demo_data import enrich_demo
    enrich_demo(sys.modules[__name__])
