from twilio.rest import TwilioRestClient


class send_SMS:
    def __init__(self):
        self.account_sid = "ACccea3903b33eb633f77de84a6f6b6097"
        self.auth_token = "82b349ced193d1be154e24ca9069ac94"
        self.my_num = "+16198178104"

    def send(self, phone, otp):
        print "in send SMS with '%s' and '%s'" % (phone, otp)

        message = ''
        try:
            client = TwilioRestClient(self.account_sid, self.auth_token)
            message = client.messages.create(to=phone, from_=self.my_num, body=otp)
        except:
            print "ERROR sending SMS!"
            pass
                                        
        print "Message id '%s' ...sent." % message
