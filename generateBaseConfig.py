#!/usr/bin/env python2
import getopt, sys, sqlite3
from os import getenv
from collections import defaultdict

configValues =	[
					["msg:ignore",          ""],
					["irc:server",          "irc.synirc.org"],
					["irc:channel",         "#rainwave"],
					["irc:nick",            "wormgas"],
					["irc:name",            "wormgas"],
					["lasttime:forumcheck", ""],
					["lasttime:msg",        ""],
					["lasttime:musiccheck", ""],
					["msg:last",            ""],
					["timeout:chat",        ""],
					["timeout:forumcheck",  ""],
					["timeout:musiccheck",  ""],
				]

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

def usage(name):
	print("usage : " + name + " [option]\nWhere option is one of the following:\n\t-h, --help : display this message\n\t-a, --automatic (default) : automatic configuration, doesn't ask for anything\n\t-i, --interactive : interactive configuration, will as for not yet configured values\n\t-r, --reconfigure : can be used to re-enter values. Can be used in conjunction with automatic or interactive options.")
	sys.exit()

def getConfig(config_id, config_value):
	# global variable to store the database cursor.
	global cursor
	# make sure the cursor variable is correctly set.
	try:
		if not isinstance(cursor, sqlite3.Cursor):
			raise NameError
	except NameError:
		print("No connection to the database")
		return False
	# poll for the asked config entry
	cursor.execute('''SELECT * FROM botconfig WHERE config_id = "''' + config_id + '''";''')
	# fetch any results in 'item'
	return cursor.fetchone()

def setConfig(config_id, config_value):
	# global variable to store the database cursor.
	global cursor
	# make sure the cursor variable is correctly set.
	try:
		if not isinstance(cursor, sqlite3.Cursor):
			raise NameError
	except NameError:
		print("No connection to the database")
		return False
	if getConfig(config_id, config_value) != None:
		# modify
		cursor.execute('''UPDATE botconfig SET config_value="''' + config_value + '''" WHERE config_id="''' + config_id + '''";''')
	else:
		# add
		cursor.execute('''INSERT INTO botconfig VALUES ("''' + config_id + '''", "''' + config_value + '''");''')

def main():
	global cursor, configValues, colors
	# get the shell value from the system
	shell = getenv("SHELL").split("/").pop()
	# if the shell color aren't defined, fallback to fallback. :D
	if not shell in colors :
		shell = None
	automatic = False
	interactive = False
	reconfigure = False
	conn = sqlite3.connect('config.sqlite')
	cursor = conn.cursor()
	
	cursor.execute("CREATE TABLE IF NOT EXISTS botconfig (config_id, config_value)")
	
	if(len(sys.argv) > 1):
		try:
			opts, args = getopt.getopt(sys.argv[1:], "hair", ["help", "automatic", "interactive", "reconfigure"])
		except getopt.GetoptError, err:
			# print help information and exit:
			print str(err) # will print something like "option -a not recognized"
			usage(sys.argv[0])
			sys.exit(2)
		for o, a in opts:
			if o in ("-h", "--help"):
				usage(sys.argv[0])
				sys.exit()
			elif o in ("-a", "--automatic"):
				automatic = True
			elif o in ("-i", "--interactive"):
				interactive = True
			elif o in ("-r", "--reconfigure"):
				reconfigure = True
			else:
				assert False, "unhandled option"
	
	if automatic and interactive :
		print("Error : you have to choose between automatic and interactive.")
		sys.exit()

	if not automatic and not interactive :
		automatic = True

	if automatic :
		for conf in configValues:
			currentConf = getConfig(conf[0], conf[1])
			if currentConf != None :
				sys.stdout.write(colors[shell]["red"] + '''[WARNING]''' + colors[shell]["normal"] + ''' ''' + colors[shell]["cyan"] + conf[0] + colors[shell]["normal"] + ''' already configured to ''' + colors[shell]["green"] + '''"''' + currentConf[1] + '''"''' + colors[shell]["normal"] + '''.''')
				if reconfigure :
					print(''' Reconfiguring to ''' + colors[shell]["green"] + '''"''' + conf[1] + '''"''' + colors[shell]["normal"])
					setConfig(conf[0], conf[1])
				else:
					print(" Ignoring.")
			else:
				print('''Configuring ''' + colors[shell]["cyan"] + conf[0] + colors[shell]["normal"] + ''' to ''' + colors[shell]["green"] + '''"''' + conf[1] + '''"''' + colors[shell]["normal"])
				setConfig(conf[0], conf[1])

	if interactive :
		for conf in configValues:
			currentConf = getConfig(conf[0], conf[1])
			if currentConf != None :
				if reconfigure :
					s = raw_input("Setting " + conf[0] + " [" + currentConf[1] + "] : ")
					sys.stdout.write(colors[shell]["red"] + '''[WARNING]''' + colors[shell]["normal"] + ''' ''' + colors[shell]["cyan"] + conf[0] + colors[shell]["normal"] + ''' already configured to ''' + colors[shell]["green"] + '''"''' + currentConf[1] + '''"''' + colors[shell]["normal"] + '''.''')
					if s != "" :
						print(''' Reconfiguring to ''' + colors[shell]["green"] + '''"''' + s + '''"''' + colors[shell]["normal"])
						setConfig(conf[0], s)
					else :
						print(" Ignoring.")
				else:
					print(colors[shell]["red"] + '''[WARNING]''' + colors[shell]["normal"] + ''' ''' + colors[shell]["cyan"] + conf[0] + colors[shell]["normal"] + ''' already configured to ''' + colors[shell]["green"] + '''"''' + currentConf[1] + '''"''' + colors[shell]["normal"] + '''. Ignoring.''')
			else:
				s = ''
				while s == '' :
					s = raw_input("Setting " + conf[0] + " : ")
					if s == '' :
						print("Please enter some value.")
				print('''Configuring ''' + colors[shell]["cyan"] + conf[0] + colors[shell]["normal"] + ''' to ''' + colors[shell]["green"] + '''"''' + s + '''"''' + colors[shell]["normal"])
				setConfig(conf[0], s)
	
	conn.commit()
	conn.close()

if __name__ == "__main__":
	main()
