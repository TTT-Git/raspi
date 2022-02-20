import logging
import sys


logging.basicConfig(level=logging.INFO, 
    format='%(asctime)s %(threadName)s:%(levelname)s:%(name)s: %(message)s')

logger = logging.getLogger(__name__)
test_dict = {
    'a': 'afdsa',
    'b': 'fdawfe'
}

logger.info({
    'action': 'test',
    'status': 'test status',
    'message': 'testtesttest',
    'data': f"ttt={test_dict['a']}"
})