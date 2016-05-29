# -*- coding: utf-8 -*-
"""
twisted-server.py
~~~~~~~~~~~~~~~~~

A fully-functional HTTP/2 server written for Twisted.
"""
import os
import os.path
import sys

from OpenSSL import crypto
from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.internet.protocol import Protocol, Factory
from twisted.internet import endpoints
from twisted.internet import reactor, ssl, defer
from h2.connection import H2Connection
from h2.events import (
    RequestReceived, DataReceived, StreamEnded, WindowUpdated
)
from h2.errors import PROTOCOL_ERROR
from hyper import HTTPConnection
from twisted.web import server, resource
import json
import MySQLdb
import collections
import io
import requests

import crypt
from datetime import datetime
from dateutil.parser import parse
import random
import string

import time
import sendEmail
import getOTP
import sendSMS

RequestData = collections.namedtuple('RequestData', ['headers', 'data'])

cnt = 0  # counter for HOTP code

class H2Protocol(Protocol):
    def __init__(self, root):
        self.conn = H2Connection(client_side=False)
        self.known_proto = None
        self.root = root
        self.stream_data = {}
        self.invalid_method = False
        self.error = False
        self.method_type = 'None'
        self.post_type = 'None'
        self.success = False
        self.failure = False
        self.uname = 'None'
        self.cipher_key = 'f456a56b567f4094ccd45745f063a465'
        self.return_JSON = ''

        # this hard-coded URL simulates the Client address
        self.url = 'httpbin.org'
        
        # hard-coded values to send in success/failure POST
        self.post_data_success = '{"user":"bro","login":"success"}'
        self.post_data_failure = '{"user":"bro","login":"failure"}'

        self._flow_control_deferreds = {}

    def connectionMade(self):
        self.conn.initiate_connection()
        self.transport.write(self.conn.data_to_send())

    def dataReceived(self, data):
        if not self.known_proto:
            self.known_proto = True

        events = self.conn.receive_data(data)
        if self.conn.data_to_send:
            self.transport.write(self.conn.data_to_send())

        for event in events:
            if isinstance(event, RequestReceived):
                self.requestReceived(event.headers, event.stream_id)
            elif isinstance(event, DataReceived):
                self.dataFrameReceived(event.stream_id, event.data)
            elif isinstance(event, StreamEnded):
                self.streamComplete(event.stream_id)                
        self.transport.write(self.conn.data_to_send())
    
    def requestReceived(self, headers, stream_id):
        # Read in request headers
        headers = collections.OrderedDict(headers)
        self.method_type = headers[':method']

        # Return 405 status if user sends anything other than GET or POST
        if self.method_type not in ('GET', 'POST'):
            self.return_XXX('405', stream_id)
            print "Unsupported method '%s'" % self.method_type
            self.invalid_method = True
            return

        path = headers[':path'].lstrip('/')
        print "Given path: ", path
        
        if not self.validate_params(path):
            print "Params are wrong."
            self.error = True
            return
        
        # Read data sent with request
        try:
            request_data = RequestData(headers, io.BytesIO())
            self.stream_data[stream_id] = request_data 
        except:
            "Issue getting request data in requestReceived!"
            self.error = True
            pass
        
        # GET can be handled immediately
        if self.method_type == 'GET':
            print '-- RECEIVED GET' 
            self.handle_GET(self.uname, stream_id)
        
        # POST will be handled in dataFrameReceived       
        elif self.method_type == 'POST':
            print '-- RECEIVED POST'    
                
        print "Done handling request."
        return

    # ================================================ #
    #   Validate request parameters before processing  #
    # ================================================ #
    def validate_params(self, path):
        MAX_GET_PARAMS = 2
        MAX_POST_PARAMS = 1
                    
        # Return 404 status if empty request path
        if not path:
            print "Nothing to fetch in path '%s'" % path
            self.error = True
            return
        
        param_list = path.split('/')
        num_params = len(path.split('/'))
        print "Param#:", num_params
        
        # DEBUGGING
        i = -(num_params)
        while (i < 0):
            param = path.split('/')[i]
            print "Param['%d']: %s" % ((i + num_params), param)
            i += 1
            
        # Validate GET request    
        if self.method_type == 'GET':
            if num_params < MAX_GET_PARAMS:
                print "Insufficient # params for GET: ", num_params
                return False
            elif num_params > MAX_GET_PARAMS:
                print "Too many params for GET: ", num_params
                return False
            else:
                if param_list[0] != 'user':
                    print "First param not 'user' but '%s'" % param_list[0]
                    return False

                ##### call db_validate_username for username #####
                if self.db_validate_username(param_list[1]) is None:
                    print "Erroneous username provided '%s'" % param_list[1]
                    return False
                
                ##### validate secret #####
#                secret_validated = self.trigger_secret_validation(param_list[2])
#                if not secret_validated:
#                    return False                   
                
                # store the validated username
                self.uname = param_list[1]
                print "Params verified, setting username to '%s'" % self.uname
                return True
                              
        # Validate POST request:            
        if self.method_type == 'POST':
            if num_params < MAX_POST_PARAMS:
                print "Insufficient # of POST params: ", num_params
                return False
            elif num_params > MAX_POST_PARAMS:
                print "Too many POST params: ", num_params
                return False

            ##### validate secret #####
#            secret_validated = self.trigger_secret_validation(param_list[1])
#            if not secret_validated:
#                return False
            ### REMEMBER: if you uncomment this validate secret code above,
            ### you also need to change the number of params allowed at the top
            ### -- increase by 1!
            
            ##### check post type #####
            if param_list[0] == 'register':
                print "REGISTER new user!"
                self.post_type = 'register'             
            elif param_list[0] == 'verify':
                print "VERIFY new user!"
                self.post_type = 'verify'            
            elif param_list[0] == 'login':
                print "LOG IN user!"
                self.post_type = 'login'
            elif param_list[0] == 'backup':
                print "BACKUP LOG IN for user!"
                self.post_type = 'backup'                
            elif param_list[0] == 'success':
                print "SUCCESSFUL login!"
                self.post_type = 'success'
            elif param_list[0] == 'failure':
                print "FAILED login!"
                self.post_type = 'failure'
            else:
                print "BOGUS POST param '%s'" % param_list[0]
                return False
            
            print "POST validated as '%s'." % self.post_type
            return True

    # ================================================ #
    #   Sends the sender secret to be validated        #
    # ================================================ #
    def trigger_secret_validation(self, param):        
        state = self.validate_sender(param)        
        print "state =", state
        
        if not state:
            print "Bad sender secret msg!"
            return False
        return True               

    # ================================================ #
    #   Decrypt encrypted string to validate request   #
    # ================================================ #
    def validate_sender(self, secret):
        c = crypt.AESCipher(self.cipher_key)
        
        # Decrypt the secret message
        plain = c.decrypt(secret)
        #print "Decrypted Message =", plain

        # Validate secret message before parsing
        if not self.validate_decrypted_msg(plain):
            print "Creepy sender"
            return False
        try:
            year = parse(plain).year
            month = parse(plain).month
            day = parse(plain).day
            hour = parse(plain).hour
            minute = parse(plain).minute
        except ValueError:
            raise ValueError("Error parsing secret msg time.")
            return False

        # Get current time to compare with secret
        curr_time = datetime.now()
        #print "Current time =", str(curr_time)

        try:
            new_year = parse(str(curr_time)).year
            new_month = parse(str(curr_time)).month
            new_day = parse(str(curr_time)).day
            new_hour = parse(str(curr_time)).hour
            new_min = parse(str(curr_time)).minute
        except ValueError:
            raise ValueError("Error parsing current time.")
            return False

        if new_year != year:
            print "Year mismatch!"
            return False
        elif new_month != month:
            print "Month mismatch!"
            return False
        elif new_day != day:
            print "Day mismatch!"
            return False
        elif new_hour != hour:
            print "Hour mismatch!"
            return False

        # This is very liberally set just to ease testing
        # In production it should be tested with != and
        # probably the seconds should be tested too!
        
#        elif new_min < minute:
#            print "Minute mismatch!"
#            return False
        return True
    
    # ================================================ #
    #   Validate decrypted secret                      #
    # ================================================ #        
    def validate_decrypted_msg(self, decrypted_str):
        try:
            date = parse(str(decrypted_str))     
        except ValueError:
            print "Ha, gotcha! Not a date of the format YYYY/MM/DD HH:MM:SS"
            return False
        print "Valid date"  
        return True
    
    # ================================================ #
    #   Try reading data from stream or reset it       #
    # ================================================ #    
    def get_stream_data(self, data, stream_id):
    
        try:
            stream_data = self.stream_data[stream_id]
        except KeyError:
            self.conn.reset_stream(stream_id, error_code=PROTOCOL_ERROR)
        else:
            stream_data.data.write(data)
    
    # ================================================ #
    #   Handle POST requests                           #
    # ================================================ #    
    def handle_POST(self, data, stream_id):
        print "in handle_POST"
            
        try:
            self.get_stream_data(data, stream_id)
        except:
            print "Issue getting stream data in handle_POST!"
            self.error = True
            pass

        try:
            jdata = json.loads(data)
        except KeyError:
            print "=-=-= Invalid POST with %s!" % self.post_type            
            pass
        
        # WHEN CLIENT FIRST REGISTERS NEW USER WITH SERVER
        if 'register' in self.post_type:
            self.handle_register_request(jdata, stream_id)

        # USER REGISTERS ON APP, APP VERIFIES USER WITH SERVER
        elif 'verify' in self.post_type:
            self.handle_verify_request(jdata, stream_id)
                
        # LOGIN ATTEMPT, WE SHOULD CALL THE APN  
        elif 'login' in self.post_type:
            self.handle_login_request(jdata, stream_id)
            
        # BACKUP LOGIN ATTEMPT, WE NOTIFY CLIENT & VERIFY OTP  
        elif 'backup' in self.post_type:
            self.handle_backup_request(jdata, stream_id)

        # received 'success' POST from App, send 'success' POST to Client 
        elif 'success' in self.post_type:
            self.handle_success_request(jdata, stream_id)
            
        # received 'failure' POST from App, send 'failure' POST to Client          
        elif 'failure' in self.post_type:
            self.handle_failure_request(jdata, stream_id)
 
        print "POST complete."

    # ================================================ #
    #   handle POST for a /register request            #
    # ================================================ #
    def handle_register_request(self, jdata, stream_id):
        print "...REGISTER new user!"
        
        try:            
            print "    username: " + jdata["username"]
            print "    email: " + jdata["email"]
            print "    phone: " + jdata["phone"]
        except KeyError:
            print "    KeyError -- invalid JSON provided: %s" % jdata
            self.error = True
            return
        
        # if user is already registered, the POST should fail
        if self.db_validate_username(jdata["username"]) is not None:
            print "    ALREADY REGISTERED!"
            self.error = True
            return
        else:       
            # generate random token
            token = self.gen_token()

            print "    Adding token '%s' to jdata." % token
            # add token to JSON string
            jdata.update({'token':str(token)})
            print "    Result:", json.dumps(jdata)

            # save new user's username, email, and phone in database
            self.db_set(jdata) 
                               
            print "    Removing 'email' from JSON..."
            jdata.pop('email')
            print "    Removing 'phone' from JSON..."
            jdata.pop('phone')

            # send token in the response to the POST request itself
            print "    Removing 'username' from JSON..."
            jdata.pop('username')            
            self.return_JSON = json.dumps(jdata)            

            print "    JSON to be POST-ed:", self.return_JSON

    # ================================================ #
    #   handle POST for a /verify request              #
    # ================================================ #
    def handle_verify_request(self, jdata, stream_id):
        print "...VERIFY new user with App!"
        
        try:            
            print "    id_token: " + jdata["id_token"]
            print "    dev_token: " + jdata["dev_token"]
        except KeyError:
            print "    KeyError -- invalid JSON provided: %s" % jdata
            self.error = True
            return
        
        # if user token is not in DB, the POST should fail
        if self.db_validate_token(jdata["id_token"]) is not None:
            print "    USER TOKEN FOUND!"
            self.db_update_token(jdata)   
            
            ### responsd to App
            print "    Adding 'verified' to jdata."
            # add 'verified' to JSON to return in POST
            jdata.update({'login':'verified'})

            print "    Removing 'id_token' from JSON..."
            jdata.pop('id_token')
            print "    Removing 'dev_token' from JSON..."
            jdata.pop('dev_token')            
            
            # setting the JSON to return as response to login POST from Client
            self.return_JSON = json.dumps(jdata)
            print "    JSON to be returned:", self.return_JSON
             
        else:
            print "    CAN'T VERIFY NON-EXISTENT USER!"
            self.error = True
            return
        
    # ================================================ #
    #   handle POST for a /login request               #
    # ================================================ #
    def handle_login_request(self, jdata, stream_id):
        print "...LOG IN user into Client!"
        
        try:            
            print "    token: " + jdata["token"]
        except KeyError:
            print "    KeyError -- invalid JSON provided: %s" % jdata
            self.error = True
            return        

        # if user token is not in DB, the POST should fail
        if self.db_validate_token(jdata["token"]) is not None:
            print "    USER TOKEN FOUND!"
           
            # Get dev_token from database using id_token
            validated = json.loads(self.db_get_user_dev_token(jdata["token"]))
            
            ### Backup method ###
            # If dev_token is '' (i.e. no dev_token to call APN)
            # send OTP via email/sms and POST OTP to Client 
            if not validated['dev_token']:
                print "    will send OTP via backup instead"
                dat = json.dumps(jdata)

                ### contact User -- send OTP via email or SMS
                
                # send OTP code via email                        
                # self.send_email(dat)
                                       
                # send SMS
                self.send_sms(dat)

                ### responsd to Client
                print "    Adding 'unverified' to jdata."
                # add 'unverified' to JSON to return in POST
                jdata.update({'login':'unverified'})

                print "    Removing 'token' from JSON..."
                jdata.pop('token')
                
                # setting the JSON to return as response to login POST from Client
                self.return_JSON = json.dumps(jdata)
                print "    JSON to be returned:", self.return_JSON
                    
            else:
                # Send POST with TOKEN to APN
                # - APN notifies User
                # - User authenticates (or doesn't)
                # - App notifies Server of success/failure
                
                # This is a POST-request to httpbin.org
                ######################################
                ### Need actual call to APN
                ######################################
                self.send_POST(json.dumps(jdata))
                
        else:
            print "    CAN'T LOGIN NON-EXISTENT USER!"
            self.error = True
            return

    # ================================================ #
    #   handle POST for a /backup request             #
    # ================================================ #
    def handle_backup_request(self, jdata, stream_id):
        print "...BACKUP login for user!"   

        try:            
            print "    token: " + jdata["token"]
            print "    otp: " + jdata["otp"]
        except KeyError:
            print "    KeyError -- invalid JSON provided: %s" % jdata
            self.error = True
            return   
                
        # if user token is not in DB, the POST should fail
        if self.db_validate_token(jdata["token"]) is not None:
            print "    USER TOKEN FOUND!"

            print "    Removing 'token' from JSON..."
            jdata.pop('token')

            # check that user typed in the correct OTP:            
            ### verify TOPT
            #verified = self.verify_TOTP_code(jdata["otp"])          
            
            ### verify HOTP
            verified = self.verify_HOTP_code(jdata["otp"])
            login_status = ''
            
            if verified:
                print "    Verification succeeded!"
                login_status = 'success'

                # add {'login':'success'} to the return JSON
                jdata.update({'login':'success'})
                         
            else:
                print "    Verficiation failed!"
                login_status = 'failure'

                # add {'login':'failure'} to the return JSON
                jdata.update({'login':'failure'})
                
            print "    Adding login '%s' to jdata." % login_status
            print "    Result:", json.dumps(jdata)

            # setting to return response to login POST from Client
            self.return_JSON = json.dumps(jdata)
            
        else:
            print "    CAN'T SUCCEED FOR NON-EXISTENT USER!"
            self.error = True
            return

    # ================================================ #
    #   handle POST for a /success request             #
    # ================================================ #
    def handle_success_request(self, jdata, stream_id):
        print "...SUCCESSFUL login for user!"   
        self.success = True

        try:            
            print "    token: " + jdata["token"]
        except KeyError:
            print "    KeyError -- invalid JSON provided: %s" % jdata
            self.error = True
            return  
        
        # if user token is not in DB, the POST should fail
        if self.db_validate_token(jdata["token"]) is not None:
            print "    USER TOKEN FOUND!"

            # add {'login':'success'} to the return JSON
            jdata.update({'login':self.post_type})

            print "    Adding login '%s' to jdata." % self.post_type
            print "    Result:", json.dumps(jdata)
            
            #################################################
            # Received 'success' from the App for a user,
            # so send POST with login status to the Client
            #################################################

            # This is a POST-request to httpbin.org
            # Need actual URL for Client         
            self.send_POST(json.dumps(jdata))  
        else:
            print "    CAN'T SUCCEED FOR NON-EXISTENT USER!"
            self.error = True
            return

    # ================================================ #
    #   handle POST for a /failure request             #
    # ================================================ #
    def handle_failure_request(self, jdata, stream_id):
        print "...FAILED login for user!"                 
        self.failure = True

        try:            
            print "    token: " + jdata["token"]
        except KeyError:
            print "    KeyError -- invalid JSON provided: %s" % jdata
            self.error = True
            return
        
        # if user token is not in DB, the POST should fail
        if self.db_validate_token(jdata["token"]) is not None:
            print "    USER TOKEN FOUND!"

            # add {'login':'success'} to the return JSON
            jdata.update({'login':self.post_type})

            print "    Adding login '%s' to jdata." % self.post_type
            print "    Result:", json.dumps(jdata)
            
            #################################################
            # Received 'failure' from the App for a user,
            # so send POST with login status to the Client
            #################################################
            
            # This is a POST-request to httpbin.org
            # Need actual URL for Client
            self.send_POST(json.dumps(jdata))
        else:
            print "    CAN'T FAIL FOR NON-EXISTENT USER!"
            self.error = True
            return

    # ================================================ #
    #   When the App sends a POST request to Server    #
    #   with the success/failure param, we send a      #
    #   POST request to notify Client of user's        #
    #   successful or failed login attempt             #
    # ================================================ #
    def send_POST(self, response):
        c = HTTPConnection(self.url)
        c.request('POST', '/post', body=response)
        resp = c.get_response()
        
        # If you wish to see what was POST-ed, uncomment line below
#        print resp.read()        
        #return (resp.status)
        
        if resp.status == 200:
            print "    JSON POST-ed successfully"
        else:
            print "    JSON POST failed with status %d!" % resp.status
            self.error = True
            return

    # ================================================ #
    #   Handle GET requests                            #
    # ================================================ #    
    def handle_GET(self, uname, stream_id):
        print "in handle_GET with %s" % uname
        
        if uname:
            to_send = self.db_get_user_token(uname)
            
            print "    >> about to send %s" % to_send         
        
            try:
                stream_data = self.stream_data[stream_id]
            except KeyError:
                print "KeyError with stream_data in handle_GET."
                self.conn.reset_stream(stream_id, error_code=PROTOCOL_ERROR)
            else:
                # Send the response to the GET request
                stream_data.data.write(to_send)
        else:
            print "=== Invalid username provided!"
            self.error = True
            return
        
        print "GET complete."

    # ================================================ #
    #   This is where POST data is received and we     #
    #   begin handling the POST request
    # ================================================ #        
    def dataFrameReceived(self, stream_id, data):
        """
        Pull data from stream or reset if data not expected.
        """
        print "in dataFrameReceived."
        
        if self.error:
            print "   skipping due to error flag..."
            return
        else:
            self.handle_POST(data, stream_id)
        print "Done with dataFrameReceived."

    # ================================================ #
    #   When the request has been processed, this is   #
    #   where we send out the appropriate response     #
    #   and notify requestor we're done responding     #
    # ================================================ #        
    def streamComplete(self, stream_id):
        """
        Complete response and send out.
        """
        print "in streamComplete"
        
        # If any issues were encountered, skip to return 404 instead
        if self.invalid_method:
            print "    skipping due to invalid method."
            return
        if self.error:
            print "   skipping due to error flag."
            self.errorFound(stream_id)
            return
        
        # We don't need to return data for success/failure requests
        elif self.success or self.failure:
            print "   success/failure flag, return 200"
            data = ''
        else:
            try:
                request_data = self.stream_data[stream_id]
            except KeyError:
                print "Yikes, KeyError in streamComplete."
                return
            
            # pack data to send with response to GET response
            if self.method_type == 'GET':
                # Pack in the JSON to return in body
                try:
                    body = json.loads(request_data.data.getvalue().decode('utf-8'))
                except:
                    print "Issues decoding request JSON in streamComplete!"
                    body = ''
                    pass
                data = json.dumps(body).encode("utf8") 

            # POST response returns special JSON data
            elif self.method_type == 'POST':
                data = self.return_JSON
           
        # Send headers and data
        response_headers = self.return_200(data)
        self.conn.send_headers(stream_id, response_headers)
        self.conn.send_data(stream_id, data, end_stream=True)
        self.transport.write(self.conn.data_to_send())
        
        print "Done in streamComplete."

    # ================================================ #
    #   Get user's email from user token               #
    # ================================================ #
    def get_email(self, user):        
        print "in get_email with user '%s'" % user
        
        jstr = json.loads(user)
        jemail = json.loads(self.db_get_user_email(jstr['token']))
        email_addr = jemail['email']
        return email_addr

    # ================================================ #
    #   Send email to unverified users                 #
    # ================================================ #
    def send_email(self, user):           
        print "in send_email with user '%s'" % user

        s = sendEmail.send_Email()
        email = self.get_email(user)
        
        ### generate TOTP to send -- secure but not reliable, expires in < 30 sec
        # otp = self.generate_TOTP_code()

        ### generate HOTP to send
        otp = self.generate_HOTP_code()
        
        print "    About to email '%s' with OTP '%s'" % (email, otp)
        s.send(email, otp)

    # ================================================ #
    #   Get user's phone number from user token        #
    # ================================================ #
    def get_phone(self, user):        
        print "in get_phone with user '%s'" % user
        
        jstr = json.loads(user)
        phone_num = json.loads(self.db_get_user_phone(jstr['token']))
        phone = phone_num['phone']
        return phone

    # ================================================ #
    #   Send text to unverified users                  #
    # ================================================ #
    def send_sms(self, user):
        print "in send_sms with user '%s'" % user

        s = sendSMS.send_SMS()
        phone = self.get_phone(user)
        
        ### generate TOTP to send -- secure but not reliable, expires in < 30 sec
        # otp = self.generate_TOTP_code()

        ### generate HOTP to send
        otp = self.generate_HOTP_code()
        
        print "    About to send sms '%s' with OTP '%s'" % (phone, otp)
        s.send(phone, otp)

    # ================================================ #
    #   Generate one-time-pass                         #
    # ================================================ #
    def generate_TOTP_code(self):
        print "in generate_TOTP_code"
        
        otp = getOTP.OTP()               
        value = otp.gen_totp()
        
        print "    GOT value '%s'" % value 
        return value

    # ================================================ #
    #   Generate counter-based one-time-pass           #
    # ================================================ #
    def generate_HOTP_code(self):
        print "in generate_HOTP_code"        

        hotp = getOTP.OTP()
        global cnt         
        value = hotp.gen_hotp(cnt)

        # increment counter so next HOTP code differs
        # if counter exceeds max int value in system, reset
        if cnt < sys.maxsize:
            cnt += 1
        else:
            cnt = 0
        
        print "    GOT value '%s'" % value 
        return value

    # ================================================ #
    #   Verify time-based one-time-pass                #
    # ================================================ #
    def verify_TOTP_code(self, code):
        print "in verify_TOTP_code"        

        totp = getOTP.OTP()
        value = totp.verify_totp(code)
        
        print "    GOT value '%s'" % value 
        return value

    # ================================================ #
    #   Verify counter-based one-time-pass             #
    # ================================================ #
    def verify_HOTP_code(self, code):
        print "in verify_HOTP_code"        

        hotp = getOTP.OTP()
        global cnt
        
        count = 0
        if cnt > 0:
            count = cnt - 1
        
        print "    curr code: %s, count: %d" % (code, count)
        value = hotp.verify_hotp(code, count)
        
        print "    GOT value '%s'" % value 
        return value

    # ================================================ #
    #   Generate random token to identify user by      #
    # ================================================ #
    def gen_token(self):
        # Use all digits and letters to choose from
        seed = string.letters + string.digits
        return ''.join(random.choice(seed) for i in xrange(16))

    # ================================================ #
    #   Trigger return of 404 in case of error         #
    # ================================================ #
    def errorFound(self, stream_id):
        self.error = False
        self.return_XXX('404', stream_id)

    # ================================================ #
    #   Create the 200 response header                 #
    # ================================================ #
    def return_200(self, to_send):
        """
        Pack and return 200 status.
        """
        response_headers = [
            (':status', '200'),
            ('content-type', 'application/json'),
            ('content-length', len(to_send)),
            ('server', 'TwoEfAy'),
        ]
        return response_headers

    # ================================================ #
    #   Create the 404 and 405 response header         #
    # ================================================ #
    def return_XXX(self, status, stream_id):    
        """
        Not found or error, return 404 status.
        Unsupported method, return 405 status.
        """
        response_headers = [
            (':status', status),
            ('content-length', '0'),
            ('server', 'TwoEfAy'),
        ]
        self.conn.send_headers(stream_id, response_headers, end_stream=True)

    ###########################################
    ###### DATABASE FUNCTIONS BEGIN HERE ######
    ###########################################

    # ================================================ #
    #   Helper function to open the database           #
    # ================================================ #
    def db_open(self):
        db = MySQLdb.connect("localhost", "130user", "130Security!", "cs130")
        cursor = db.cursor()
        return (db, cursor)
        
    # ================================================ #
    #   Helper function to close database (LOL)        #
    # ================================================ #
    def db_close(self, db):
        db.close()       

    # ================================================ #
    #   One DB function to validate all                #
    #   (i.e. execute lookup/verify queries)           #
    # ================================================ #    
    def db_run_validate_query(self, query):
        db, cursor = self.db_open()   
        cursor.execute(query)
        has_it = cursor.fetchone()
        self.db_close(db)
        
        if has_it[0] is None:
            print "    NOT IN DB!"
        else:
            print "--> DB FETCHED:", has_it[0]
            
        return has_it[0]
    
    # ================================================ #
    #   Check whether the user is in the database      #
    # ================================================ #
    def db_validate_username(self, data):    
        print "==> in db_validate_username with %s" % data
        
        query = "SELECT username, COUNT(*) FROM Users WHERE username='%s' " % data           
        res = self.db_run_validate_query(query)
        
        return res
    
    # ================================================ #
    #   Check whether user token is in the database    #
    # ================================================ #
    def db_validate_token(self, token):
        print "==> in db_validate_token with %s" % token    
    
        query = "SELECT id_token, COUNT(*) FROM Users WHERE id_token='%s' " % token
        res = self.db_run_validate_query(query)
        
        return res

    # ================================================ #
    #   Run additive queries to database               #
    # ================================================ #
    def db_run_modify_query(self, query):
        db, cursor = self.db_open()
        
        try:
            cursor.execute(query)
            db.commit()
            print "Values inserted into database."
        except:
            db.rollback()
            print "Error inserting, rolling back..."
            print "409 Conflict, Invalid POST -- entry already in database?"
            
        self.db_close(db)  
        
    # ================================================ #
    #   Register the user in the database              #
    # ================================================ #    
    def db_set(self, dat):       
        print "in db_set, values %s %s %s %s" % (dat["username"], dat["email"], dat["phone"], dat["token"])
        
        query = "INSERT INTO Users (username, email, phone, id_token, dev_token) VALUES ('%s', '%s', '%s', '%s', '%s')" % \
             (dat["username"], dat["email"], dat["phone"], dat["token"], '')

        print "    INSERTING user data into DB..." 
        self.db_run_modify_query(query)
               
    # ================================================ #
    #   Update the device dev_token in the database    #
    # ================================================ #
    def db_update_token(self, dat):
        print "in db_update_token, values %s %s" % (dat["id_token"], dat["dev_token"])
        
        query = 'UPDATE Users SET dev_token="%s" WHERE id_token="%s" ' % (dat["dev_token"], dat["id_token"])
        
        print "    UPDATING dev_token in DB..."
        self.db_run_modify_query(query)

    # ================================================ #
    #   Run select query in database                   #
    # ================================================ #
    def db_run_get_query(self, query, to_return):
        try:
            db, cursor = self.db_open()
            cursor.execute(query)
            res = cursor.fetchall()
            self.db_close(db)
        except:
            print "    Error fetching data..."
        else:       
            print "    Values obtained from database, token = ", res[0][0]
            jstr = {}
            jstr[to_return] = res[0][0]
            jstr_data = json.dumps(jstr)
            return jstr_data
        return ''

    # ================================================ #
    #   Get user token from database for APN POST      #
    # ================================================ #
    def db_get_user_token(self, data):
        print "in db_get_user_token with username '%s'" % data

        obtain_json = 'token'
        query = "SELECT id_token FROM Users WHERE username='%s' " % data
        res = self.db_run_get_query(query, obtain_json)
        return res

    # ================================================ #
    #   Get user email from database for emaling       #
    # ================================================ #
    def db_get_user_email(self, data):
        print "in db_get_user_email with token '%s'" % data

        obtain_json = 'email'
        query = "SELECT email FROM Users WHERE id_token='%s' " % data
        res = self.db_run_get_query(query, obtain_json) 
        return res

    # ================================================ #
    #   Get user dev_token from database               #
    # ================================================ #
    def db_get_user_dev_token(self, data):
        print "in db_get_user_dev_token with token '%s'" % data

        obtain_json = 'dev_token'
        query = "SELECT dev_token FROM Users WHERE id_token='%s' " % data
        res = self.db_run_get_query(query, obtain_json) 
        return res

    # ================================================ #
    #   Get user phone from database for texting       #
    # ================================================ #
    def db_get_user_phone(self, data):
        print "in db_get_user_phone with token '%s'" % data

        obtain_json = 'phone'
        query = "SELECT phone FROM Users WHERE id_token='%s' " % data
        res = self.db_run_get_query(query, obtain_json) 
        return res

# ================================================ #
#   Setup the H2 factory for the HTTP/2.0 protocol #
# ================================================ #
class H2Factory(Factory):
    def __init__(self, root):
        self.root = root

    def buildProtocol(self, addr):
        return H2Protocol(self.root)

root = sys.argv[1]

# Load the certificate and the certificate key
with open('../certs/server.crt', 'r') as f:
    cert_data = f.read()
with open('../certs/server.key', 'r') as f:
    key_data = f.read()

cert = crypto.load_certificate(crypto.FILETYPE_PEM, cert_data)
key = crypto.load_privatekey(crypto.FILETYPE_PEM, key_data)
options = ssl.CertificateOptions(
    privateKey=key,
    certificate=cert,
    acceptableProtocols=[b'h2', b'http/1.1'],
)

endpoint = endpoints.SSL4ServerEndpoint(reactor, 8080, options, backlog=128)
print "Server is running..."
endpoint.listen(H2Factory(root))
reactor.run()