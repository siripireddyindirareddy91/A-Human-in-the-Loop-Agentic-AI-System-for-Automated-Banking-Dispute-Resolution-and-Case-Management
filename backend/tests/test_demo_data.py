from backend.app.main import Session, rows
from backend.app.demo_data import enrich_demo
import backend.app.main as api

def test_demo_dataset_has_operational_records():
    with Session() as s:
        assert len(rows(s,'customer')) >= 50
        assert len(rows(s,'transaction')) >= 200
        assert all(t.get('location') for t in rows(s,'transaction'))
        seeded=[c for c in rows(s,'case') if c.get('demo_seed')]
        assert seeded
        assert all(len(c['agents'])==10 for c in seeded)
        assert any(c['status']=='RESOLVED' and c['reviews'] for c in seeded)
        assert rows(s,'notification') and rows(s,'audit')

def test_demo_enrichment_is_idempotent():
    with Session() as s:
        before={kind:len(rows(s,kind)) for kind in ['case','notification','audit']}
    enrich_demo(api)
    with Session() as s:
        assert before=={kind:len(rows(s,kind)) for kind in before}
