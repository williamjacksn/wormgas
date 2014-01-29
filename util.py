import htmlentitydefs
import json
import os
import random
import re
import requests


class CollectionOfNamedLists:
	"""A collection of lists, each list has a name, optional persistence"""

	def __init__(self, path=None):

		self.data = {}

		if path is None:
			self.persist = False
		else:
			self.persist = True
			self.path = path
			if os.path.exists(path):
				with open(self.path, 'r') as f:
					self.data = json.load(f)

	def __del__(self):
		self._flush()

	def _flush(self):
		"""Write data to file"""
		if self.persist:
			with open(self.path, 'w') as f:
				json.dump(self.data, f)

	def names(self):
		"""Return a list of names"""
		return self.data.keys()

	def items(self, name):
		"""Return a list by name"""
		if name in self.data:
			return self.data[name]
		else:
			return []

	def set(self, name, items):
		"""Replace a list"""
		self.data[name] = items
		self._flush()

	def add(self, name, item):
		"""Add an item to a ist"""
		if name not in self.data:
			self.data[name] = []
		self.data[name].append(item)
		self._flush()

	def remove(self, name, item):
		"""Remove an item from a list"""
		if name in self.data:
			if item in self.data[name]:
				self.data[name].remove(item)
			if len(self.data[name]) == 0:
				del self.data[name]
			self._flush()

	def clear(self, name):
		"""Remove all items from a list"""
		if name in self.data:
			del self.data[name]
			self._flush()

	def shuffle(self, name):
		"""Randomize the items in a list"""
		if name in self.data:
			random.shuffle(self.data[name])
			self._flush()

	def up(self, name, item):
		"""Move an item one step closer to the beginning of the list"""
		if name in self.data:
			if item in self.data[name]:
				orig_index = self.data[name].index(item)
				if orig_index == 0:
					# Already at beginning of list
					return
				new_index = orig_index - 1
				self.data[name].remove(item)
				self.data[name].insert(new_index, item)
				self._flush()

	def down(self, name, item):
		"""Move an item one step away from the beginning of the list"""
		if name in self.data:
			if item in self.data[name]:
				orig_index = self.data[name].index(item)
				if orig_index + 1 == len(self.data[name]):
					# Already at end of list
					return
				new_index = orig_index + 1
				self.data[name].remove(item)
				self.data[name].insert(new_index, item)
				self._flush()

	def pop(self, name, index):
		"""Remove an item from the list and return it"""
		if name in self.data:
			item = self.data[name].pop(index)
			if len(self.data[name]) == 0:
				del self.data[name]
			self._flush()
			return item


class TitleFetcherError(Exception):
	pass


class TitleFetcher(object):
	'''Get the contents of the <title> tag in HTML pages'''

	def get_title(self, url):
		try:
			data = requests.get(url, stream=True)
		except:
			m = u'There was a problem fetching data from: {}'
			raise TitleFetcherError(m.format(url))
		if u'content-type' in data.headers:
			ct = data.headers[u'content-type']
			if u'audio/' in ct or u'image/' in ct or u'/zip' in ct:
				raise TitleFetcherError(u'Invalid content-type: {}'.format(ct))
		if u'<title>' in data.text:
			title = data.text.partition(u'<title>')[2].partition(u'</title>')[0]
			return self.unescape(u' '.join(title.split()))
		else:
			raise TitleFetcherError(u'There is no <title> tag at: {}'.format(url))

	# from Fredrik Lundh, http://effbot.org/zone/re-sub.htm#unescape-html
	def unescape(self, text):
		def fixup(m):
			text = m.group(0)
			if text[:2] == "&#":
				# character reference
				try:
					if text[:3] == "&#x":
						return unichr(int(text[3:-1], 16))
					else:
						return unichr(int(text[2:-1]))
				except ValueError:
					pass
			else:
				# named entity
				try:
					text = unichr(htmlentitydefs.name2codepoint[text[1:-1]])
				except KeyError:
					pass
			return text  # leave as is
		return re.sub("&#?\w+;", fixup, text)
