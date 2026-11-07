from fastapi.testclient import TestClient
from backend.app.main import app
client=TestClient(app)
def login(role):
    r=client.post('/api/auth/login',json={'email':role+'@demo.bank','password':'Demo@2026!'})
    assert r.status_code==200,r.text
    return {'Authorization':'Bearer '+r.json()['token']}
def test_authentication_required():
    assert client.get('/api/disputes').status_code in (401,403)
def test_customer_isolation():
    h=login('customer')
    assert all(c['customer_id']=='CUS-001' for c in client.get('/api/disputes',headers=h).json())
    assert client.get('/api/disputes/BDR-2026-00002',headers=h).status_code==403
    assert client.get('/api/users',headers=h).status_code==403
def test_workflow_and_two_person_gate():
    h=login('analyst')
    r=client.post('/api/disputes',headers=h,json={'transaction_id':'TXN-00001','amount':887.5,'category':'Unauthorized transaction','description':'I did not authorize this transaction. Please investigate.'})
    assert r.status_code==201,r.text
    c=r.json(); assert len(c['agents'])==10 and c['status']=='PENDING_HUMAN_REVIEW' and c['two_person']
    assert c['policies']
    url='/api/reviews/'+c['id']+'/approve'; body={'reason':'Independent review of the available evidence completed.'}
    assert client.post(url,headers=login('customer'),json=body).status_code==403
    assert client.post(url,headers=h,json=body).json()['status']=='PENDING_HUMAN_REVIEW'
    assert client.post(url,headers=h,json=body).status_code==409
    assert client.post(url,headers=login('admin'),json=body).json()['status']=='RESOLVED'
def test_bad_evidence_and_export():
    h=login('officer')
    assert client.post('/api/disputes/BDR-2026-00001/evidence',headers=h,files={'file':('fake.pdf',b'not pdf','application/pdf')}).status_code==400
    assert client.get('/api/reports/export',headers=h).status_code==200
def test_rejection_audited():
    h=login('admin');c=client.post('/api/disputes',headers=h,json={'transaction_id':'TXN-00002','amount':1025,'category':'Duplicate transaction','description':'Two charges appear for the same purchase. Please investigate.'}).json()
    r=client.post('/api/reviews/'+c['id']+'/reject',headers=h,json={'reason':'Transaction verified and duplicate charge not supported.'})
    assert r.json()['status']=='REJECTED'
    assert any(a['action']=='Human reject' and a['case_id']==c['id'] for a in client.get('/api/audit-logs',headers=h).json())
