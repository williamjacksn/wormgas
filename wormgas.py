#!/usr/bin/python

# wormgas -- IRC bot for Rainwave (http://rainwave.cc)
# https://github.com/subtlecoolness/wormgas

import os
import time
import sqlite3
from ircbot import SingleServerIRCBot

class wormgas(SingleServerIRCBot):

	def __init__(self):
		self.abspath = os.path.abspath(__file__)
		(self.path, self.file) = os.path.split(self.abspath)
		self.cdbh = sqlite3.connect("%s/config.sqlite" % (self.path,))
		self.ccur = self.cdbh.cursor()
		server = self.get_config("irc:server")
		nick = self.get_config("irc:nick")
		name = self.get_config("irc:name")
		SingleServerIRCBot.__init__(self, [(server, 6667)], nick, name)

	def __del__(self):
		self.cdbh.close()

	def on_welcome(self, c, e):
		c.privmsg("nickserv", "identify %s" % self.get_config("irc:nickservpass"))
		c.join(self.get_config("irc:channel"))

	def print_to_log(self, msg):
		"""Print to the log file, with UTC timestamp"""

		now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
		logfile = open("%s.log" % (self.abspath,), "a")
		logfile.write("%s -- %s\n" % (now, msg))
		logfile.close()

	def get_config(self, id):
		"""Read a value from the configuration database
			 Returns the value, or -1 if the configuration id does not exist"""

		config_value = "-1"
		sql = "select config_value from botconfig where config_id = ?"
		self.ccur.execute(sql, (id,))
		for r in self.ccur:
			config_value = r[0]
		self.print_to_log("[INFO] get_config(): %s = %s" % (id, config_value))
		return(config_value)

def main():
	bot = wormgas()
	bot.start()

if __name__ == "__main__":
	main()