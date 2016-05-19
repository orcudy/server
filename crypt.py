from Crypto.Cipher import AES
from Crypto import Random

BS = 16
padded = lambda s: s + (BS - len(s) % BS) * chr(BS - len(s) % BS) 
unpadded = lambda s : s[0:-ord(s[-1])]

# ==================================================== #
# Basic AES encryption/decription for provided string  #
# ==================================================== #
class AESCipher:
    def __init__(self, key):
        self.key = key.decode("hex")

    def encrypt(self, msg):
        try:
            msg = padded(msg)
            IV = Random.new().read(AES.block_size);
            cipher = AES.new(self.key, AES.MODE_CBC, IV)
        except TypeError:
            print "Bad input."
            return False
        return (IV + cipher.encrypt(msg)).encode("hex")

    def decrypt(self, enc):
        print "In decrypt"
        try:
            e = enc.decode("hex")
            IV = e[:16]
            e = e[16:]
            cipher = AES.new(self.key, AES.MODE_CBC, IV)
        except TypeError:
            print "Bad string."
            return False
        return unpadded(cipher.decrypt(e))

