import pyotp
import time

class OTP:
    def __init__(self):
        self.secret = 'WTZC26BY55Z24XC5'
        
    def gen_totp(self):
        # print "in gen_totp"
        totp = pyotp.TOTP(self.secret)
        value = totp.now()
        # print "    Value now =", value
        
        return value
    
    def verify_totp(self, incoming_code):
        # print "in verify_totp with %s", incoming_code
        
        totp = pyotp.TOTP(self.secret)
        generated_now = totp.now()
        
        # print "    generated code: %s, user code: %s" % (generated_now, incoming_code)
        
        is_it_valid = totp.verify(incoming_code)
        # print "    valid:", is_it_valid
        
        return is_it_valid

    def gen_hotp(self, count):
        # print "in gen_hotp with count %s" % count
        hotp = pyotp.HOTP(self.secret)
        value = hotp.at(count)
        # print "    Value now =", value
        
        return value   
        
    def verify_hotp(self, incoming_code, cntr):
        # print "in verify_hotp wtih %s and %s" % (incoming_code, cntr)
        
        hotp = pyotp.HOTP(self.secret)
        generated_now = hotp.at(cntr)
        
        # print "    generated code: %s, user code: %s" % (generated_now, incoming_code) 
        
        is_it_valid = hotp.verify(incoming_code, cntr)
        # print "    valid:", is_it_valid
        
        return is_it_valid
