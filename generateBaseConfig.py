#!/usr/bin/env python2
import sqlite3

def addIfMissing(config_id, config_value):
	global c
	# if c isn't defined to a sqlite connection cursor, this function will fail. It's easy to add some try / catch structure to avoid this, so feel free to do it.
	c.execute('''SELECT * FROM botconfig WHERE config_id = "''' + config_id + '''";''')
	if c.fetchone() == None :	
		print('''Configuring ''' + config_id + ''' to "''' + config_value + '''"''')
		c.execute('''INSERT INTO botconfig VALUES ("''' + config_id + '''", "''' + config_value + '''");''')
	else:
		print(config_id + ''' already configured.''')
		

def main():
	global c
	conn = sqlite3.connect('config.sqlite')
	c = conn.cursor()
	
	addIfMissing("msg:ignore", "")
	addIfMissing("irc:server", "irc.synirc.org")
	addIfMissing("irc:nick",   "wormgas")
	addIfMissing("irc:name",   "wormgas")
	
	conn.commit()
	conn.close()

if __name__ == "__main__":
	main()
