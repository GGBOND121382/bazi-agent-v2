from pathlib import Path
import json, sqlite3
root=Path(__file__).resolve().parents[1]
expected={
 'approved_core.jsonl':234,
 'qa_explanations.jsonl':7203,
 'benchmark_case_qa.jsonl':200,
 'combined_rag.jsonl':7637,
}
ids=set(); counts={}
for name,nexp in expected.items():
 p=root/'data/production'/name; n=0
 with p.open(encoding='utf-8') as f:
  for line in f:
   r=json.loads(line); n+=1
   if name=='combined_rag.jsonl':
    assert r['production_enabled'] is True
    assert r['chunk_id'] not in ids; ids.add(r['chunk_id'])
    if r['permissions'].get('can_support_claim'):
     assert r['trust_tier'] in ('A','B')
    if r.get('collection')=='benchmark_case_qa':
     assert r['permissions'].get('can_support_case_analogy') is True
     assert r['permissions'].get('can_support_claim') is False
 assert n==nexp,(name,n,nexp); counts[name]=n
assert not (root/'data/optional').exists()
con=sqlite3.connect(root/'import/sqlite/bazi_rag.sqlite')
db_count=con.execute('select count(*) from records').fetchone()[0]
case_count=con.execute("select count(*) from records where collection_name='benchmark_case_qa'").fetchone()[0]
con.close()
assert db_count==7637 and case_count==200
print({'status':'ok','counts':counts,'sqlite_rows':db_count,'benchmark_cases':case_count,'korean_optional_removed':True})
