# -*- coding: utf-8 -*-
"""
twisted-server.py
~~~~~~~~~~~~~~~~~

A fully-functional HTTP/2 server written for Twisted.
"""
import functools
import mimetypes
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

from hyper import HTTPConnection

RequestData = collections.namedtuple('RequestData', ['headers', 'data'])

class H2Protocol(Protocol):
    def __init__(self, root):
        self.conn = H2Connection(client_side=False)
        self.known_proto = None
        self.root = root
        self.stream_data = {}
        self.s_body = {}
        self.invalid_method = False
        self.error = False
        self.method_type = 'None'
        self.post_type = 'None'
        self.success = False
        self.failure = False
        self.uname = 'None'
        self.cipher_key = 'f456a56b567f4094ccd45745f063a465'

        # this hard-coded URL simulates the Client address
        self.url = 'https://httpbin.org'
        
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
        request_data = RequestData(headers, io.BytesIO())
        self.stream_data[stream_id] = request_data 
        
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

                ##### call db_validate for username #####
                if self.db_validate(param_list[1]) is None:
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

        ###################################################
        # This is very liberally set just to ease testing #
        # In production it should be tested with != and   #
        # probably the seconds should be tested too!      #
        ###################################################
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
        
        #===============================================================
        # THIS OCCURS WHEN CLIENT FIRST REGISTERS NEW USER WITH SERVER #
        #===============================================================
        if 'register' in self.post_type:
            print "...REGISTER new user!"

            self.get_stream_data(data, stream_id) 
            
            try:
                jdata = json.loads(data)
                
                print "    username: " + jdata["username"]
                print "    email: " + jdata["email"]
                
                # if user is already registered, the POST should fail
                if self.db_validate(jdata["username"]) is not None:
                    print "    ALREADY REGISTERED!"
                    self.error = True
                    return                
                
                else:
                    # generate random token
                    token = self.gen_token()

                    # add token to JSON string
                    jdata.update({'token':str(token)})

                    print "    Adding token '%s' to jdata." % token
                    print "    Result:", json.dumps(jdata)

                    # write user data in database
                    self.db_set(jdata, stream_id) 
                                       
                    print "    Removing 'email' from JSON..."
                    jdata.pop('email')
                    print "    JSON to be POST-ed:", json.dumps(jdata)
                
                    # Send POST with TOKEN to Client
                    # - the Client displays the token to the User
                    # so the user can use it to register with the App.
                    # - the App will then use that token to communicate
                    # with the Server (instead of a username)
                    self.send_POST(json.dumps(jdata))
                
            except KeyError:
                print "=-=-= Invalid POST with register!"            
                pass

        #==================================================================#
        # THIS OCCURS WHEN USER REGISTERS ON THE APP AND THE APP VERIFIES  #
        # USER WITH THE SERVER                                             #
        #==================================================================#
        elif 'verify' in self.post_type:
            print "...VERIFY new user with App!"

            self.get_stream_data(data, stream_id) 

            try:
                jdata = json.loads(data)                
                
                print "    id_token: " + jdata["id_token"]
                print "    dev_token: " + jdata["dev_token"]
                
                # if user token is not in DB, the POST should fail
                if self.db_validate_token(jdata["id_token"]) is not None:
                    print "    USER TOKEN FOUND!"
                    self.db_update_token(jdata, stream_id)
                    
                else:
                    print "    CAN'T UPDATE NON-EXISTENT USER!"
                    self.error = True
                    return                

            except KeyError:
                print "=-=-= Invalid POST with verify!"           
                pass
                
        #=======================================
        # THIS IS WHERE WE SHOULD CALL THE APN #
        #=======================================   
        elif 'login' in self.post_type:
            print "...LOG IN user into Client!"

            self.get_stream_data(data, stream_id) 

            try:
                jdata = json.loads(data)                
                print "    token: " + jdata["token"]
                
                # if user token is not in DB, the POST should fail
                if self.db_validate_token(jdata["token"]) is not None:
                    print "    USER TOKEN FOUND!"

                    #################################################
                    # Send POST with TOKEN to APN
                    # - APN notifies User
                    # - User authenticates (or doesn't)
                    # - App notifies Server of success/failure
                    #################################################
                    
                    # This is a POST-request to httpbin.org
                    # Need actual call to APN
                    self.send_POST(json.dumps(jdata))
                    
                else:
                    print "    CAN'T LOGIN NON-EXISTENT USER!"
                    self.error = True
                    return                

            except KeyError:
                print "=-=-= Invalid POST with login!"           
                pass

        #===================================================
        # We receive POST from App with 'success'/'failure'#
        # and we return login 'success' or 'failure' POST  #
        # to the Client                                    #
        #===================================================   
        elif 'success' in self.post_type:
            print "...SUCCESSFUL login for user!"   
            self.success = True
            
            self.get_stream_data(data, stream_id)

            try:
                jdata = json.loads(data)                
                print "    token: " + jdata["token"]
                
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

            except KeyError:
                print "=-=-= Invalid POST with success!"           
                pass            

            
        elif 'failure' in self.post_type:
            print "...FAILED login for user!"                 
            self.failure = True
            
            self.get_stream_data(data, stream_id)

            try:
                jdata = json.loads(data)                
                print "    token: " + jdata["token"]
                
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

            except KeyError:
                print "=-=-= Invalid POST with failure!"           
                pass            
 
        print "POST complete."

    # ================================================ #
    #   When the App sends a POST request to Server    #
    #   with the success/failure param, we send a      #
    #   POST request to notify Client of user's        #
    #   successful or failed login attempt             #
    # ================================================ #
    def send_POST(self, response):        
        c = HTTPConnection('http2bin.org')
        c.request('POST', '/post', body=response)
        resp = c.get_response()
        
        # If you wish to see what was POST-ed, uncomment line below
        print resp.read()        
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
                request_data = self.stream_data[stream_id]
                self.s_body = to_send
                #print "    >> loaded:", json.loads(self.s_body)
            
                try:
                    stream_data = self.stream_data[stream_id]
                except KeyError:
                    print "GET KeyError..."
                    self.conn.reset_stream(stream_id, error_code=PROTOCOL_ERROR)
                else:

                    ########################################################
                    ########################################################
                    # THIS WAS INITIAL IMPLEMENTATION -- NOT VALID ANYMORE
                    # send POST to APN
                    # if APP POSTS 'success' we respond to the 
                    # GET with 'success'
                    # else we respond with 'failure'
                    ########################################################
                    ########################################################

                    # Send POST with TOKEN to the APN
                    self.send_POST(to_send)
                  
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
                print "Yikes in streamComplete."
                return

            # Pack in the JSON to return in body
            body = json.loads(request_data.data.getvalue().decode('utf-8'))
            
            # pack data to send with response to GET
            if self.method_type == 'GET':        
                data = json.dumps(body).encode("utf8") 

            # POST returns no data
            elif self.method_type == 'POST':
                data = ''
           
        # Send headers and data
        response_headers = self.return_200(data)
        self.conn.send_headers(stream_id, response_headers)
        self.conn.send_data(stream_id, data, end_stream=True)
        self.transport.write(self.conn.data_to_send())
        
        print "Done in streamComplete."

    # ================================================ #
    #   Helper function to open the database           #
    # ================================================ #
    def db_open(self):
        db = MySQLdb.connect("localhost", "130user", "130security", "cs130")
        cursor = db.cursor()
        return (db, cursor)
        
    # ================================================ #
    #   Helper function to close database (LOL)        #
    # ================================================ #
    def db_close(self, db):
        db.close()       

    # ================================================ #
    #   Check whether the user is in the database      #
    # ================================================ #
    def db_validate(self, data):
        db, cursor = self.db_open()

        # Query database for username
        cursor.execute(
            "SELECT username, COUNT(*) FROM Users WHERE username='%s' " % data
        )        

        has_it = cursor.fetchone()
        self.db_close(db)

        # if user is not found, the GET should fail
        if has_it[0] is None:
            print "    NOT IN DB!"
        else:
            print "--> FETCHED:", has_it[0]

        return has_it[0]

    # ================================================ #
    #   Check whether user token is in the database    #
    # ================================================ #
    def db_validate_token(self, token):
        db, cursor = self.db_open()

        # Query database for username
        cursor.execute(
            "SELECT id_token, COUNT(*) FROM Users WHERE id_token='%s' " % token
        )        

        has_it = cursor.fetchone()
        self.db_close(db)

        # if user is not found, the GET should fail
        if has_it[0] is None:
            print "    NOT IN DB!"
        else:
            print "--> FETCHED:", has_it[0]

        return has_it[0]
        
    # ================================================ #
    #   Register the user in the database              #
    # ================================================ #    
    def db_set(self, dat, stream_id):
        db, cursor = self.db_open()
        
        print "in db_set, values %s %s %s" % (dat["username"], dat["email"], dat["token"])
        
        # Insert values into database 
        sql = "INSERT INTO Users (username, email, id_token, dev_token) VALUES ('%s', '%s', '%s', '%s')" % \
             (dat["username"], dat["email"], dat["token"], '')
        
        try:
            cursor.execute(sql)
            db.commit()
            print "Values inserted into database."
        except:
            db.rollback()
            print "Error inserting, rolling back..."
            print "409 Conflict, Invalid POST -- entry already in database?"
            
        self.db_close(db)

    # ================================================ #
    #   Update the user token in the database          #
    # ================================================ #
    def db_update(self, dat, stream_id):
        db, cursor = self.db_open()

        print "in db_update, values %s %s %s" % (dat["username"], dat["email"], dat["token"])
        
        # Update values in database 
        sql = 'UPDATE Users SET id_token="%s" WHERE username="%s" ' % (dat["token"], dat["username"])
        
        print "UPDATING token"
        
        try:
            cursor.execute(sql)
            db.commit()
            print "    New token value '%s' inserted into database." % dat["token"]
        except:
            db.rollback()
            print "Error inserting, rolling back..."
            print "409 Conflict, Invalid POST -- entry already in database?"
            
        self.db_close(db)

    # ================================================ #
    #   Update the device dev_token in the database    #
    # ================================================ #
    def db_update_token(self, dat, stream_id):
        db, cursor = self.db_open()

        print "in db_update_token, values %s %s" % (dat["id_token"], dat["dev_token"])
        
        # Update values in database 
        sql = 'UPDATE Users SET dev_token="%s" WHERE id_token="%s" ' % (dat["dev_token"], dat["id_token"])
        
        print "UPDATING dev_token"
        
        try:
            cursor.execute(sql)
            db.commit()
            print "    New token value '%s' inserted into database." % dat["dev_token"]
        except:
            db.rollback()
            print "Error inserting, rolling back..."
            print "409 Conflict -- entry already in database?"
            
        self.db_close(db)

    # ================================================ #
    #   Get user info from database for GET response   #
    # ================================================ #
    def db_get(self, data):
        
        print "in db_get with username '%s'" % data
            
        try:
            db, cursor = self.db_open()
            
            # Query database for token
            cursor.execute("SELECT id_token FROM Users WHERE username= %s ", (data,))
            res = cursor.fetchall()
            self.db_close(db)
        except:
            print "Error fetching data..."
        
        print "    Status obtained from database, token = ", res[0][0]

        # Specify what to return for GET requests
        # in this case, return username and token for the user
        jstr = {}
        jstr['username'] = data
        jstr['token'] = res[0][0]
        jstr_data = json.dumps(jstr)
        return jstr_data


    # ================================================ #
    #   Get user token from database for APN POST      #
    # ================================================ #
    def db_get_user_token(self, data):
        
        print "in db_get_user_token with username '%s'" % data
            
        try:
            db, cursor = self.db_open()
            
            # Query database for token
            cursor.execute("SELECT id_token FROM Users WHERE username= %s ", (data,))
            res = cursor.fetchall()
            self.db_close(db)
        except:
            print "    Error fetching data..."
        
        print "    Values obtained from database, token = ", res[0][0]

        # Specify what to return for GET requests
        # in this case, return username and token for the user
        jstr = {}
        jstr['token'] = res[0][0]
        jstr_data = json.dumps(jstr)
        return jstr_data

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

    # ================================================ #
    #   Generate random token to identify user by      #
    # ================================================ #
    def gen_token(self):
        # Use all digits and letters to choose from
        seed = string.letters + string.digits
        
        return ''.join(random.choice(seed) for i in xrange(16))

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
    acceptableProtocols=[b'h2'],
)

endpoint = endpoints.SSL4ServerEndpoint(reactor, 8080, options, backlog=128)
print "Server is running..."
endpoint.listen(H2Factory(root))
reactor.run()