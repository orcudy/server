from email.header    import Header
from email.mime.text import MIMEText
from smtplib         import SMTP_SSL
from getpass         import getpass
import keyring
  
class send_Email:
    def __init__(self):
        # I absolutely hate that the email pass is here, however
        # there doesn't seem to be a way to grab it in a more secure
        # way. Options are:
        # - include it here
        # - prompt user for password
        # - pull it from keyring (which will prompt for keyring password)
        # Booo. :(
        self.login, self.password = 'twoefay@gmail.com', '130security'
        
        # get pass from keyring
        # this assumes the password has been store in keyring with:
        # keyring.set_password('gmail.com', 'twoefay', '<password>')
        #keyring.get_password('gmail.com','twoefay') 
        
        # prompt user for password when program runs
        #, getpass('Gmail password:')
        
    def send(self, email_addr, message):

        print "got email address '%s' and message '%s'" % (email_addr, message)
        recipients = [email_addr]

        # Encode the message to send
        msg = MIMEText(message, 'plain', 'utf-8')
        msg['Subject'] = Header('TwoEfAy one-time-pass', 'utf-8')
        msg['From'] = self.login
        msg['To'] = ", ".join(recipients)

        # Send the message
        s = SMTP_SSL('smtp.gmail.com', 465, timeout=10)
        
        # to display useful debug info
#        s.set_debuglevel(1)
        try:
            s.login(self.login, self.password)
            s.sendmail(msg['From'], recipients, msg.as_string())
            print "    -->Email sent."
        except:
            print "    -->Failed to send email."
            pass
        finally:
            s.quit()
