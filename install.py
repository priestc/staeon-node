import os
import sys

is_py2 = False
if sys.version_info <= (3,0):
    is_py2 = True
    input = raw_input

#os.system("pip install -r requirements.txt")
#os.system("cp local_settings_default.py upcoin_node/upcoin_node/local_settings.py")
#os.system("python upcoin_node/manage.py migrate")

domain = input("Enter your node's public domain: ")
pk = input("Enter your node's payout private key: ")
os.system("echo '%s\n%s' > node.conf" % (domain, pk))
