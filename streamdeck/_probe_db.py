import sqlite3, glob, os
DB = r'C:\Users\ryans\.local\share\opencode\opencode.db'
conn = sqlite3.connect(DB)
print('session rows for TC-010:')
for r in conn.execute("SELECT id, title, directory, time_archived FROM session WHERE title LIKE 'acceptance TC-010%' ORDER BY time_updated DESC").fetchall():
    print(' ', r)
print('part count for the TC-010 session:')
print(' ', conn.execute("SELECT COUNT(*) FROM part WHERE session_id='ses_f9087c8deffeOo6PK9DHb6UkDL'").fetchone()[0])
conn.close()

# Where might the serve instance write? Look for other opencode DB files.
print('--- opencode db files under .local/share/opencode:')
for f in glob.glob(r'C:\Users\ryans\.local\share\opencode\*.db*'):
    print(' ', f, os.path.getsize(f))
