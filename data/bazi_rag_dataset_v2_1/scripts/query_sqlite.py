import sqlite3, sys
from pathlib import Path
q=' '.join(sys.argv[1:]).strip() or '甲日主'
db=Path(__file__).resolve().parents[1]/'import/sqlite/bazi_rag.sqlite'
con=sqlite3.connect(db)
sql="SELECT r.chunk_id,r.collection_name,r.trust_tier,r.title,snippet(records_fts,4,'[',']','…',18) FROM records_fts JOIN records r USING(chunk_id) WHERE records_fts MATCH ? ORDER BY bm25(records_fts) LIMIT 8"
try:
 rows=con.execute(sql,(q,)).fetchall()
except sqlite3.OperationalError:
 # Quote punctuation-heavy queries as a phrase.
 rows=con.execute(sql,('"'+q.replace('"','')+'"',)).fetchall()
for row in rows: print(row)
con.close()
