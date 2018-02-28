import logging
import sys

from wormgas import wormgas

logging.basicConfig(level='INFO', format='%(asctime)s | %(name)s | %(levelname)s | %(message)s', stream=sys.stdout)

wormgas.main()
