from os import path
from cobe.brain import Brain

b = Brain("%s/shakespeare.sqlite" % path.split(path.abspath(__file__))[0])

b.start_batch_learning()

with open("shakespeare.txt") as f:
    for l in f:
        b.learn(l)

b.stop_batch_learning()
