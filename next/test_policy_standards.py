import unittest
from next import policy_standards as p

class NoSeededCases(unittest.TestCase):
    def test_no_registered_policy_or_agency(self):
        self.assertEqual(p.SOURCE_PROFILES,{})
        found,actions,health=p.scan_policy_standards(lambda *_:None,{}, {})
        self.assertEqual(found,[])
        self.assertEqual(actions,[])
        self.assertEqual(health["registered"],0)
    def test_no_invented_downstream_roles(self):
        self.assertEqual(p.link_verified_welfare_dependencies([],[]),
            {"linked_rules":0,"linked_actions":0})

if __name__=="__main__":unittest.main()
