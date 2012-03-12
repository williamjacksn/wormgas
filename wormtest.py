#!/usr/bin/python
"""
Tests for wormgas.
https://github.com/subtlecoolness/wormgas
"""

import os
import unittest
import wormgas

class TestCommands(unittest.TestCase):
	config_db = "test.sqlite"

	# In case setUp breaks, this will prevent the first test we run from
	# using an old test config DB.
	try:
		os.remove(config_db)
	except OSError:
		pass #Test DB doesn't exist, mission accomplished.

	def setUp(self):
		self.wormgas = wormgas.wormgas(config_db=self.config_db, log_file=None)

	def tearDown(self):
		self.wormgas.stop()
		os.remove(self.config_db)

	def testNewBotConfig(self):
		pass

if __name__ == "__main__":
	unittest.main()
