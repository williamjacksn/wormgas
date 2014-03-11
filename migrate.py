import json
import sqlite3

db = sqlite3.connect(u'config.sqlite')
cur = db.cursor()

# botconfig
config = dict()
cur.execute(u'select config_id, config_value from botconfig')
for r in cur:
    config[r[0]] = r[1]

with open(u'config.json', u'w') as f:
    json.dump(config, f)

# rps_log
rps = list()
cur.execute(u'select timestamp, user_nick, challenge, response from rps_log')
for r in cur:
    rps.append(r)

with open(u'rps.json', u'w') as f:
    json.dump(rps, f)

# user_keys
keys = dict()
cur.execute(u'select user_nick, user_id, user_key from user_keys')
for r in cur:
    keys[r[0]] = (r[1], r[2])

with open(u'keys.json', u'w') as f:
    json.dump(keys, f)
