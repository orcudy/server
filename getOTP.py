import pyotp
import time

class OTP:
    def __init__(self):
        self.totp = pyotp.TOTP('WTZC26BY55Z24XC5')
        
    def gen_code(self):
#        print "in gen_code"
        
        value = self.totp.now()
#        print "    Value now =", value
        
        return value

    def gen_prov(self, email_addr):
#        print "in gen_pass wtih %s" % email_addr
        
        provisioned = self.totp.provisioning_uri(email_addr)
#        print "    Provisioned =", provisioned
        
#        test = pyotp.TOTP("WTZC26BY55Z24XC5")
#        print "    Value now =", test.now()
        
        return provisioned
