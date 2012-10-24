#!/usr/bin/env python2
import sqlite3
from os import getenv

colors = {"bash": {"red" : "\033[1;31m", "cyan" : "\033[0;36m", "green" : "\033[0;32m", "normal" : "\033[0m"}}

def addIfMissing(config_id, config_value):
	global cursor, colors
	shell = getenv("SHELL").split("/").pop()
	# if c isn't defined to a sqlite connection cursor, this function will fail. It's easy to add some try / catch structure to avoid this, so feel free to do it.
	cursor.execute('''SELECT * FROM botconfig WHERE config_id = "''' + config_id + '''";''')
	item = cursor.fetchone()
	if item == None :	
		print('''Configuring ''' + colors[shell]["cyan"] + config_id + colors[shell]["normal"] + ''' to ''' + colors[shell]["green"] + '''"''' + config_value + '''"''' + color[shell]["normal"])
		cursor.execute('''INSERT INTO botconfig VALUES ("''' + config_id + '''", "''' + config_value + '''");''')
	else:
		print(colors[shell]["red"] + '''[WARNING]''' + colors[shell]["normal"] + ''' ''' + colors[shell]["cyan"] + config_id + colors[shell]["normal"] + ''' already configured to ''' + colors[shell]["green"] + '''"''' + item[1] + '''"''' + colors[shell]["normal"] + '''.''')
		

def main():
	global cursor
	conn = sqlite3.connect('config.sqlite')
	cursor = conn.cursor()
	
	addIfMissing("msg:ignore",          "")
	addIfMissing("irc:server",          "irc.synirc.org")
	addIfMissing("irc:nick",            "wormgas")
	addIfMissing("irc:name",            "wormgas")
	addIfMissing("irc:channel",         "#rainwave")
	addIfMissing("lasttime:forumcheck", "")
	addIfMissing("lasttime:msg",        "")
	addIfMissing("lasttime:musiccheck", "")
	addIfMissing("msg:last",            "")
	addIfMissing("timeout:chat",        "")
	addIfMissing("timeout:forumcheck",  "")
	addIfMissing("timeout:musiccheck",  "")
	
	conn.commit()
	conn.close()

if __name__ == "__main__":
	main()
