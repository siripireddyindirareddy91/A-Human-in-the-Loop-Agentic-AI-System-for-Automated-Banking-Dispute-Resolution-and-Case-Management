"""Versioned synthetic history. User-created cases are never overwritten."""
from datetime import datetime, timedelta, timezone

NAMES = ['Ananya Sharma','Rohan Patel','Meera Iyer','Vikram Singh','Sara Khan','Aarav Reddy','Diya Nair','Arjun Gupta','Ishita Rao','Kabir Mehta','Neha Joshi','Aditya Das','Kavya Menon','Rahul Verma','Sneha Kapoor','Nikhil Shah','Pooja Desai','Varun Bhat','Riya Malhotra','Siddharth Jain','Aditi Kulkarni','Karan Sethi','Tanvi Ghosh','Dev Anand','Maya Thomas','Pranav Bose','Anika Sinha','Ritesh Kumar','Shreya Pillai','Akash Chawla','Nandini Roy','Yash Agarwal','Simran Kaur','Harsh Vardhan','Anjali Saxena','Manav Khanna','Sanya Bansal','Rohit Suri','Ira Chandra','Dhruv Mathur','Tara Dutta','Vivek Prasad','Avni Chopra','Sahil Arora','Mitali Sen','Aman Tripathi','Suhani Goel','Gaurav Pandey','Leela Krishnan','Om Prakash']
COMPLAINTS = [
    'A UPI debit appeared while my phone was with me. I do not recognize the recipient and did not authorize this payment. Please verify the device and authorization records.',
    'My card was debited twice for one purchase. The merchant confirmed a single order. Please compare the settlement references for a possible duplicate charge.',
    'The ATM displayed a timeout and did not dispense cash, but the withdrawal was debited. Please obtain the ATM journal and cash reconciliation records.',
    'The merchant confirmed my return was accepted, but the refund is not visible in my account. Please trace the refund reference and settlement date.',
    'The amount on my bank statement differs from the receipt. Please verify the original authorization and final settlement amount.',
    'I noticed an unusually large transfer to an unfamiliar recipient. Please investigate the beneficiary and authorization history.',
    'The merchant charged me for an order cancelled before dispatch. Please request the cancellation and settlement records.',
    'My UPI payment showed failed, yet the amount was debited. The recipient has not received the money. Please verify both transaction legs.',
    'The beneficiary has not received my NEFT transfer although the debit appears successful. Please trace the transfer reference.',
    'An unexpected service charge appeared on my statement. Please review the fee description and the sample account terms.',
]

def enrich_demo(api):
    with api.Session.begin() as s:
        marker='dataset-operations-v2'
        if s.scalar(api.select(api.Record).where(api.Record.key==marker)): return
        staff=api.get(s,'user-admin'); anchor=datetime.now(timezone.utc)
        for i,name in enumerate(NAMES,1):
            customer=api.get(s,f'CUS-{i:03}'); customer['name']=name; api.put(s,'customer',customer)
        for tx in api.rows(s,'transaction'):
            n=int(tx['id'].split('-')[1]); tx['date']=(anchor-timedelta(days=n%29,hours=n%17)).isoformat()
            tx['location']=['Hyderabad','Bengaluru','Mumbai','Chennai','Delhi'][n%5]
            tx['status']='PENDING' if n%13==0 else 'FAILED' if n%19==0 else 'SETTLED'
            api.put(s,'transaction',tx)
        for i in range(1,31):
            c=api.get(s,f'BDR-2026-{i:05}')
            if c['agents'] or c['reviews'] or c['notes'] or c['evidence']: continue
            index=(i-1)%10; c['customer']=NAMES[i-1]; c['description']=COMPLAINTS[index]
            c['created_at']=(anchor-timedelta(days=1+(i*7)%28,hours=i%12)).isoformat()
            c['sla_due_at']=(datetime.fromisoformat(c['created_at'])+timedelta(days=7)).isoformat()
            c['assigned']='Arjun Rao' if index in [0,5] else 'Priya Mehta'; c['demo_seed']=True
            c=api.investigate(s,c,staff)
            c['notes']=[{'author':'Priya Mehta','text':'Synthetic case history: transaction matched. Awaiting customer documents and an authorized review decision.','created_at':c['created_at']}]
            if i%5==0:
                c['status']='RESOLVED'
                c['reviews']=[{'reviewer_id':'user-analyst','reviewer':'Arjun Rao','action':'approve','reason':'Synthetic historical review: sample settlement records checked. No financial action executed.','created_at':(anchor-timedelta(days=i%4)).isoformat(),'demo_seed':True}]
                if c['two_person']: c['reviews'].append({'reviewer_id':'user-admin','reviewer':'Indira Reddy','action':'approve','reason':'Synthetic independent senior approval for this sample case.','created_at':(anchor-timedelta(days=i%4)).isoformat(),'demo_seed':True})
                api.event(s,staff,'Sample historical resolution',c['id'],'Seeded synthetic history; no financial action.')
            elif i%7==0:
                c['status']='AWAITING_INFORMATION'; api.notify(s,c,'Additional evidence requested: receipt or merchant confirmation')
            elif i%6==0:
                c['status']='ESCALATED'; c['assigned']='Arjun Rao'; api.notify(s,c,'High-priority case assigned to senior risk review')
            api.put(s,'case',c)
        api.put(s,'dataset',{'id':marker,'created_at':api.now(),'description':'Synthetic operational history v2'})
