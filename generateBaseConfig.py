#!/usr/bin/env python2
import sqlite3
from os import getenv
from collections import defaultdict

colors	=	{
				# To add a new supported shell, just add a new dict entry with its name (the name of the binary) and some values for the colors.
				"bash":	{
							"red"		: "\033[1;31m",
							"cyan"		: "\033[0;36m",
							"green"		: "\033[0;32m",
							"normal"	: "\033[0m"
						},
				# default fallback. No colors to avoid compatibility problems with unknown shells. So unless the shell is explicitely supported, no colors.
				None:	{
							"red"		: "",
							"cyan"		: "",
							"green"		: "",
							"normal"	: ""
						},
			}

def addIfMissing(config_id, config_value):
	# sine global variables, to store the database cursor and the shell colors.
	global cursor, colors
	# make sure the cursor variable is correctly set.
	try:
		if not isinstance(cursor, sqlite3.Cursor):
			raise NameError
	except NameError:
		print("No connection to the database")
		return False
	# get the shell value from the system
	shell = getenv("SHELL").split("/").pop()
	# if the shell color aren't defined, fallback to fallback. :D
	if not shell in colors :
		shell = None
	# poll for the asked config entry
	cursor.execute('''SELECT * FROM botconfig WHERE config_id = "''' + config_id + '''";''')
	# fetch any results in 'item'
	item = cursor.fetchone()
	# if the entry does not exist
	if item == None :
		# add it
		cursor.execute('''INSERT INTO botconfig VALUES ("''' + config_id + '''", "''' + config_value + '''");''')
		# and print a message saying so
		print('''Configuring ''' + colors[shell]["cyan"] + config_id + colors[shell]["normal"] + ''' to ''' + colors[shell]["green"] + '''"''' + config_value + '''"''' + color[shell]["normal"])
	# else
	else:
		# warn the user that the entry is already configured
		print(colors[shell]["red"] + '''[WARNING]''' + colors[shell]["normal"] + ''' ''' + colors[shell]["cyan"] + config_id + colors[shell]["normal"] + ''' already configured to ''' + colors[shell]["green"] + '''"''' + item[1] + '''"''' + colors[shell]["normal"] + '''.''')
	# and return successfuly
	return True

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
