import sqlite3
DB = r'C:\Users\ryans\.local\share\opencode\opencode.db'
conn = sqlite3.connect(DB)
print('--- TC-041 sessions:')
for r in conn.execute("SELECT id, directory, title FROM session WHERE title LIKE 'acceptance TC-041%'").fetchall():
    print(r)
print('--- live (not archived) sessions in HomeAILab dir:')
for r in conn.execute("SELECT id, title FROM session WHERE directory LIKE '%HomeAILab' AND (time_archived IS NULL OR time_archived=0)").fetchall():
    print(r)
conn.close()
