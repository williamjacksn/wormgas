import json
import os

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
