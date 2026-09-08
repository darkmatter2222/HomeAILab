import sys
sys.path.insert(0, r'C:\Users\ryans\source\repos\HomeAILab\streamdeck')
import acceptance as a
h = a.Harness(keep_session='ses_f913cd0f2ffeZglY2RzKnCMBj0')
stale = ["ses_f90ce0caeffehC6Fcb83M9X70j",
          "ses_f90cc94e8ffeN4sdXoh2dlYvpX",
          "ses_f90cb1ecbffefqNgYcsbnHhj0J"]
for sid in stale:
    try:
        code = h.serve.close_session(sid)
        print(sid[-14:], '->', code)
    except Exception as e:
        print(sid[-14:], '-> ERROR:', e)
# verify homeai dir is now OFF
states = a.db_live_states(h.keep_session)
d = h._norm_path(h._dir_for_alias('homeai'))
s = states.get(d)
print('homeai live session after cleanup:', (s['state'], s['sessionId'][-14:]) if s else 'NONE')
