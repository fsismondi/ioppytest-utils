import doctest
import unittest
import messages


# python3 -m unittest tests/test_doctests.py -vvv

suite = unittest.TestSuite()
suite.addTest(doctest.DocTestSuite(messages))
runner = unittest.TextTestRunner(verbosity=2)
runner.run(suite)
